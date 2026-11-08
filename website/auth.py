"""
The admin login: password hashes, the lockout, the session and CSRF tokens.

The session is Flask's signed cookie, so no server memory is involved: any
function instance can check it. CSRF tokens live in that same session.
"""

import hmac
import secrets
from functools import lru_cache, wraps

from flask import abort, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import settings

MIN_PASSWORD_LENGTH = 12

WRONG_CREDENTIALS = 'Wrong username or password.'
LOCKED = f'Too many wrong attempts. Try again in {settings.ADMIN_LOCK_MINUTES} minutes.'

CSRF_FIELD = 'csrf_token'


def hash_password(password: str) -> str:
    """scrypt, Werkzeug's default: slow on purpose, salted per password."""
    return generate_password_hash(password)


@lru_cache(maxsize=1)
def _dummy_hash() -> str:
    return generate_password_hash(secrets.token_hex(16))


def authenticate(users, username: str, password: str) -> tuple[dict | None, str | None]:
    """
    Returns (user, None) when the password is right, or (None, message). An
    unknown username still runs a hash check, so it answers as slowly as a
    wrong password and doesn't reveal which usernames exist. A locked account
    is refused without looking at the password.
    """
    user = users.get(username)
    if user is None:
        check_password_hash(_dummy_hash(), password)
        return None, WRONG_CREDENTIALS

    if user['locked']:
        return None, LOCKED

    if not check_password_hash(user['password_hash'], password):
        users.record_failure(
            user['id'], settings.ADMIN_MAX_ATTEMPTS, settings.ADMIN_LOCK_MINUTES
        )
        return None, WRONG_CREDENTIALS

    users.record_success(user['id'])
    return user, None


def sign_in(user: dict) -> None:
    """A fresh session, so nothing set before the login carries over."""
    session.clear()
    session.permanent = True
    session['admin_id'] = user['id']
    session['admin_name'] = user['username']


def sign_out() -> None:
    session.clear()


def signed_in() -> bool:
    return 'admin_id' in session


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not signed_in():
            return redirect(url_for('admin.login'))

        return view(*args, **kwargs)

    return wrapper


def csrf_token() -> str:
    """The session's token, made on first use. Every admin form includes it."""
    if CSRF_FIELD not in session:
        session[CSRF_FIELD] = secrets.token_urlsafe(32)

    return session[CSRF_FIELD]


def check_csrf() -> None:
    """Refuses a POST whose token is missing or isn't the session's."""
    expected = session.get(CSRF_FIELD)
    sent = request.form.get(CSRF_FIELD, '')
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, 'The form expired or did not come from this site. Reload it.')
