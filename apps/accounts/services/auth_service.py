
from apps.accounts.services.user_service import get_user_by_email
from django.contrib.auth.hashers import check_password


class InvalidCredentialsError(Exception):
    """Invalid email or password."""


class AccountNotActiveError(Exception):
    """Account has not been activated."""


class AccountDisabledError(Exception):
    """Account has been disabled."""


class EmailNotVerifiedError(Exception):
    """Email address has not been verified."""


def authenticate_user(email, password):
    """
    Authenticate a TourismPlanner user using MongoDB credentials.

    Returns the user document without its password hash.
    """

    user = get_user_by_email(
        email,
        include_password_hash=True,
    )

    if not user:
        raise InvalidCredentialsError("Invalid email or password.")

    password_hash = user.get("password_hash")

    if not password_hash or not check_password(password, password_hash):
        raise InvalidCredentialsError("Invalid email or password.")

    account_status = user.get("account_status")

    if account_status == "disabled":
        raise AccountDisabledError("Your account has been disabled.")

    if account_status != "active":
        raise AccountNotActiveError(
            "Your account is not active. Complete email verification first."
        )

    if not user.get("email_verified"):
        raise EmailNotVerifiedError(
            "Please verify your email address first."
        )

    user.pop("password_hash", None)

    return user
