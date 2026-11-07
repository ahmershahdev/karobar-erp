import uuid

from django.contrib.auth.tokens import default_token_generator
from django.core import signing
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

from .models import User

VERIFY_EMAIL_SALT = "accounts.verify-email"
EMAIL_TOKEN_MAX_AGE = 60 * 60 * 24 * 3


def make_email_token(user: User) -> str:
    # Signing the address too means a link stops working once the user changes their email.
    return signing.dumps({"u": str(user.public_id), "e": user.email}, salt=VERIFY_EMAIL_SALT)


def read_email_token(token: str) -> User | None:
    try:
        data = signing.loads(token, salt=VERIFY_EMAIL_SALT, max_age=EMAIL_TOKEN_MAX_AGE)
    except signing.BadSignature:
        return None
    try:
        public_id = uuid.UUID(str(data.get("u")))
    except ValueError:
        return None
    return User.objects.filter(public_id=public_id, email=data.get("e"), is_active=True).first()


def make_reset_token(user: User) -> tuple[str, str]:
    # Django's generator hashes the password and last login into the token, so a link dies as
    # soon as it is used or the password changes another way.
    return urlsafe_base64_encode(force_bytes(user.public_id)), default_token_generator.make_token(
        user
    )


def read_reset_token(uid: str, token: str) -> User | None:
    try:
        public_id = uuid.UUID(force_str(urlsafe_base64_decode(uid)))
    except (ValueError, TypeError, UnicodeDecodeError):
        return None
    user = User.objects.filter(public_id=public_id, is_active=True).first()
    if user is None or not default_token_generator.check_token(user, token):
        return None
    return user


CHANGE_EMAIL_SALT = "accounts.change-email"
CHANGE_EMAIL_MAX_AGE = 60 * 60 * 24


def _account_state(user: User) -> str:
    # Any change of password, email or confirmation time changes this, so it ends every link sent
    # before. Without it, an attacker's link would outlive the owner changing the password, and a
    # link would work again after the email went from A to B and back to A.
    state = f"{user.password}|{user.email}|{user.email_verified_at}"
    return salted_hmac(CHANGE_EMAIL_SALT, state, algorithm="sha256").hexdigest()


def make_email_change_token(user: User, new: str) -> str:
    return signing.dumps(
        {"u": str(user.public_id), "s": _account_state(user), "n": new}, salt=CHANGE_EMAIL_SALT
    )


def read_email_change_token(token: str) -> tuple[User, str] | None:
    """Reads the user from the database each time, so call it again under the row lock."""
    try:
        data = signing.loads(token, salt=CHANGE_EMAIL_SALT, max_age=CHANGE_EMAIL_MAX_AGE)
    except signing.BadSignature:
        return None
    try:
        public_id = uuid.UUID(str(data.get("u")))
    except ValueError:
        return None
    user = User.objects.filter(public_id=public_id, is_active=True).first()
    new = data.get("n")
    if user is None or not isinstance(new, str):
        return None
    if not constant_time_compare(_account_state(user), str(data.get("s"))):
        return None
    return user, new
