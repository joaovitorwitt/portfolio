from scripts.create_admin import check_password
from website.auth import MIN_PASSWORD_LENGTH


def test_passwords_must_match():
    assert check_password('a' * 20, 'b' * 20) == 'the passwords do not match'


def test_passwords_must_be_long_enough():
    short = 'a' * (MIN_PASSWORD_LENGTH - 1)

    assert 'at least' in check_password(short, short)


def test_a_good_password_passes():
    good = 'correct horse battery staple'

    assert check_password(good, good) is None
