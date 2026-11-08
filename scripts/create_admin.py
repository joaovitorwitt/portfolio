"""
Creates the admin account, or sets a new password for it and unlocks it. Needs
migration 006. The password is typed here, never passed as an argument, so it
stays out of the shell history.

    python scripts/create_admin.py
"""

import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from website.auth import MIN_PASSWORD_LENGTH, hash_password  # noqa: E402
from website.db import AdminUsers, get_pool  # noqa: E402


def check_password(password: str, repeated: str) -> str | None:
    """Why the password can't be used, or None if it can."""
    if password != repeated:
        return 'the passwords do not match'

    if len(password) < MIN_PASSWORD_LENGTH:
        return f'use at least {MIN_PASSWORD_LENGTH} characters'

    return None


def main() -> int:
    username = input('Username: ').strip()
    if not username:
        print('aborting: the username is empty')
        return 1

    password = getpass.getpass('Password: ')
    problem = check_password(password, getpass.getpass('Repeat it: '))
    if problem:
        print(f'aborting: {problem}')
        return 1

    AdminUsers().save(username, hash_password(password))
    print(f'saved the account "{username}"')
    return 0


if __name__ == '__main__':
    try:
        raise SystemExit(main())
    finally:
        get_pool().close()
