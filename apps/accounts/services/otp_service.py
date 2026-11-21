
"""
OTP service for TourismPlanner.

Responsibilities:
- Generate secure six-digit OTPs.
- Store only hashed OTPs in MongoDB.
- Enforce expiry, attempt limits and resend cooldown.
- Verify OTPs and activate pending accounts.

Development:
The calling view can print the generated OTP to the terminal.
Never log OTPs in production.
"""

from __future__ import annotations

import math
import secrets

from datetime import datetime, timedelta, timezone
from typing import Any

from bson import ObjectId
from django.contrib.auth.hashers import check_password, make_password
from pymongo import ASCENDING

from core.db import get_db


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

OTP_COLLECTION = "otp_challenges"
USERS_COLLECTION = "users"

OTP_LENGTH = 6
OTP_EXPIRY_MINUTES = 5
OTP_MAX_ATTEMPTS = 5
OTP_RESEND_COOLDOWN_SECONDS = 60


# ---------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------

class OTPError(ValueError):
    """Base exception for OTP-related errors."""


class OTPExpiredError(OTPError):
    """Raised when an OTP has expired."""


class OTPInvalidError(OTPError):
    """Raised when an OTP is incorrect."""


class OTPAttemptsExceededError(OTPError):
    """Raised when the maximum number of attempts is exceeded."""


class OTPResendCooldownError(OTPError):
    """Raised when an OTP is requested before the cooldown ends."""

    def __init__(self, remaining_seconds: int):
        self.remaining_seconds = remaining_seconds
        super().__init__(
            f"Please wait {remaining_seconds} seconds "
            "before requesting another OTP."
        )


class OTPAccountError(OTPError):
    """Raised when the account cannot receive or use an OTP."""


# ---------------------------------------------------------
# Database helpers
# ---------------------------------------------------------

def _otp_collection():
    return get_db()[OTP_COLLECTION]


def _users_collection():
    return get_db()[USERS_COLLECTION]


# ---------------------------------------------------------
# Date and time helpers
# ---------------------------------------------------------

def _utc_now() -> datetime:
    """
    Return timezone-aware UTC time.

    MongoDB BSON dates have millisecond precision,
    so microseconds are truncated to milliseconds.
    """
    now = datetime.now(timezone.utc)

    return now.replace(
        microsecond=(now.microsecond // 1000) * 1000
    )


def _ensure_utc(value: datetime) -> datetime:
    """
    Convert a MongoDB datetime into timezone-aware UTC.

    PyMongo normally returns naive UTC datetimes.
    This helper makes them safe to compare with aware UTC values.
    """
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)

    return value.astimezone(timezone.utc)


# ---------------------------------------------------------
# Index creation
# ---------------------------------------------------------


def _get_pending_user(user_id: str | ObjectId) -> dict[str, Any]:
    """Retrieve an account eligible for email verification."""

    try:
        object_id = (
            user_id
            if isinstance(user_id, ObjectId)
            else ObjectId(user_id)
        )
    except Exception as exc:
        raise OTPAccountError("Invalid account.") from exc

    user = _users_collection().find_one({"_id": object_id})

    if not user:
        raise OTPAccountError("Account not found.")

    if user.get("account_status") not in ("pending", "active"):
        raise OTPAccountError("This account cannot be verified.")

    if user.get("email_verified"):
        raise OTPAccountError("Email address is already verified.")

    if not user.get("email"):
        raise OTPAccountError("No email address is registered.")

    return user



# ---------------------------------------------------------
# OTP generation
# ---------------------------------------------------------

def generate_otp() -> str:
    """
    Generate a cryptographically secure six-digit OTP.
    Leading zeroes are allowed.
    """
    return f"{secrets.randbelow(10 ** OTP_LENGTH):06d}"



def create_otp_challenge(
    user_id: str | ObjectId,
    *,
    enforce_cooldown: bool = True,
) -> dict[str, Any]:

    user = _get_pending_user(user_id)
    collection = _otp_collection()

    now = _utc_now()
    purpose = "email_verification"

    existing = collection.find_one({
        "user_id": user["_id"],
        "purpose": purpose,
        "consumed": False,
    })

    if existing and enforce_cooldown:
        created_at = existing.get("created_at")

        if created_at:
            created_at = _ensure_utc(created_at)
            elapsed = (now - created_at).total_seconds()
            remaining = OTP_RESEND_COOLDOWN_SECONDS - elapsed

            if remaining > 0:
                raise OTPResendCooldownError(math.ceil(remaining))

    otp = generate_otp()
    otp_hash = make_password(otp)
    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    challenge = {
        "user_id": user["_id"],
        "purpose": purpose,
        "otp_hash": otp_hash,
        "created_at": now,
        "expires_at": expires_at,
        "attempts": 0,
        "max_attempts": OTP_MAX_ATTEMPTS,
        "consumed": False,
    }

    collection.update_one(
        {
            "user_id": user["_id"],
            "purpose": purpose,
        },
        {"$set": challenge},
        upsert=True,
    )

    return {
        "otp": otp,
        "expires_at": expires_at,
        "email": user["email"],
    }


def verify_otp(
    user_id: str | ObjectId,
    submitted_otp: str,
) -> dict[str, Any]:
    """
    Verify email OTP and activate the user's account.

    On successful verification:
    - OTP challenge is consumed.
    - Account becomes active.
    - email_verified becomes True.
    """

    # 1. Validate ObjectId.
    try:
        object_id = (
            user_id
            if isinstance(user_id, ObjectId)
            else ObjectId(user_id)
        )
    except Exception as exc:
        raise OTPAccountError("Invalid account.") from exc

    # 2. Validate OTP format.
    if (
        not isinstance(submitted_otp, str)
        or len(submitted_otp) != OTP_LENGTH
        or not submitted_otp.isdigit()
    ):
        raise OTPInvalidError("Enter a valid six-digit OTP.")

    users = _users_collection()
    challenges = _otp_collection()

    # 3. Find user.
    user = users.find_one({"_id": object_id})

    if not user:
        raise OTPAccountError("Account not found.")
    
    if user.get("account_status") not in ("pending", "active"):
        raise OTPAccountError(
            "This account cannot be verified."
        )

    if (
        user.get("account_status") == "active"
        and user.get("email_verified")
    ):
        raise OTPAccountError("This email address is already verified.")

    

    # 4. Find active email OTP challenge.
    challenge = challenges.find_one(
        {
            "user_id": object_id,
            "purpose": "email_verification",
            "consumed": False,
        }
    )

    if not challenge:
        raise OTPInvalidError(
            "No active OTP found. Please request a new OTP."
        )

    now = _utc_now()

    # 5. Check OTP expiry.
    expires_at = _ensure_utc(challenge["expires_at"])

    if expires_at <= now:
        challenges.update_one(
            {
                "_id": challenge["_id"],
                "consumed": False,
            },
            {
                "$set": {"consumed": True}
            },
        )

        raise OTPExpiredError(
            "Your OTP has expired. Please request a new one."
        )

    # 6. Check maximum attempts.
    if challenge["attempts"] >= challenge["max_attempts"]:
        raise OTPAttemptsExceededError(
            "Maximum OTP attempts exceeded. Please request a new OTP."
        )

    # 7. Verify submitted OTP against stored hash.
    if not check_password(submitted_otp, challenge["otp_hash"]):

        result = challenges.update_one(
            {
                "_id": challenge["_id"],
                "consumed": False,
                "attempts": challenge["attempts"],
            },
            {
                "$inc": {"attempts": 1}
            },
        )

        if result.modified_count != 1:
            raise OTPError(
                "OTP challenge changed. Please try again."
            )

        attempts_used = challenge["attempts"] + 1
        remaining = challenge["max_attempts"] - attempts_used

        if remaining <= 0:
            raise OTPAttemptsExceededError(
                "Maximum OTP attempts exceeded. Please request a new OTP."
            )

        raise OTPInvalidError(
            f"Incorrect OTP. You have {remaining} attempt(s) remaining."
        )

    # 8. Consume the correct OTP.
    consumed = challenges.update_one(
        {
            "_id": challenge["_id"],
            "consumed": False,
            "attempts": {
                "$lt": challenge["max_attempts"]
            },
        },
        {
            "$set": {
                "consumed": True,
                "consumed_at": now,
            }
        },
    )

    if consumed.modified_count != 1:
        raise OTPError(
            "OTP challenge has already been used. Please try again."
        )

    # 9. Activate the account.
    activation = users.update_one(
    {
        "_id": object_id,
        "account_status": user["account_status"],
        "email_verified": {"$ne": True},
    },
    {
        "$set": {
            "email_verified": True,
            "account_status": "active",
            "updated_at": now,
        }
    },
)

    if activation.modified_count != 1:
        raise OTPAccountError(
            "The account could not be activated."
        )

    # 10. Return verification result.
    return {
        "user_id": str(object_id),
        "email_verified": True,
        "account_status": "active",
    }



def _get_active_user(user_id: str | ObjectId) -> dict[str, Any]:
    """Retrieve an active user eligible for email OTP login."""

    try:
        object_id = (
            user_id
            if isinstance(user_id, ObjectId)
            else ObjectId(user_id)
        )
    except Exception as exc:
        raise OTPAccountError("Invalid account.") from exc

    user = _users_collection().find_one({"_id": object_id})

    if not user:
        raise OTPAccountError("Account not found.")

    if user.get("account_status") != "active":
        raise OTPAccountError("This account is not active.")

    if not user.get("email_verified"):
        raise OTPAccountError("Email address is not verified.")

    if not user.get("email"):
        raise OTPAccountError("No email address is registered.")

    return user


def create_login_otp_challenge(
    user_id: str | ObjectId,
    *,
    enforce_cooldown: bool = True,
) -> dict[str, Any]:
    """
    Generate a login OTP for an already-active user.

    Stores only the hashed OTP in MongoDB.
    Does not modify the user's account status.
    """

    user = _get_active_user(user_id)
    collection = _otp_collection()

    now = _utc_now()
    purpose = "login"

    existing = collection.find_one({
        "user_id": user["_id"],
        "purpose": purpose,
        "consumed": False,
    })

    if existing and enforce_cooldown:
        created_at = existing.get("created_at")

        if created_at:
            created_at = _ensure_utc(created_at)
            elapsed = (now - created_at).total_seconds()
            remaining = OTP_RESEND_COOLDOWN_SECONDS - elapsed

            if remaining > 0:
                raise OTPResendCooldownError(math.ceil(remaining))

    otp = generate_otp()
    otp_hash = make_password(otp)

    expires_at = now + timedelta(minutes=OTP_EXPIRY_MINUTES)

    challenge = {
        "user_id": user["_id"],
        "purpose": purpose,
        "otp_hash": otp_hash,
        "created_at": now,
        "expires_at": expires_at,
        "attempts": 0,
        "max_attempts": OTP_MAX_ATTEMPTS,
        "consumed": False,
    }

    collection.update_one(
        {
            "user_id": user["_id"],
            "purpose": purpose,
        },
        {"$set": challenge},
        upsert=True,
    )

    return {
        "otp": otp,
        "expires_at": expires_at,
        "email": user["email"],
    }


def verify_login_otp(
    user_id: str | ObjectId,
    submitted_otp: str,
) -> dict[str, Any]:
    """
    Verify a login OTP for an already-active user.

    Consumes the OTP but does not activate or modify the account.
    """

    try:
        object_id = (
            user_id
            if isinstance(user_id, ObjectId)
            else ObjectId(user_id)
        )
    except Exception as exc:
        raise OTPAccountError("Invalid account.") from exc

    if (
        not isinstance(submitted_otp, str)
        or len(submitted_otp) != OTP_LENGTH
        or not submitted_otp.isdigit()
    ):
        raise OTPInvalidError("Enter a valid six-digit OTP.")

    user = _get_active_user(object_id)
    challenges = _otp_collection()

    challenge = challenges.find_one({
        "user_id": object_id,
        "purpose": "login",
        "consumed": False,
    })

    if not challenge:
        raise OTPInvalidError(
            "No active login OTP found. Please request a new one."
        )

    now = _utc_now()
    expires_at = _ensure_utc(challenge["expires_at"])

    if expires_at <= now:
        challenges.update_one(
            {
                "_id": challenge["_id"],
                "consumed": False,
            },
            {"$set": {"consumed": True}},
        )

        raise OTPExpiredError(
            "Your login OTP has expired. Please request a new one."
        )

    if challenge["attempts"] >= challenge["max_attempts"]:
        raise OTPAttemptsExceededError(
            "Maximum OTP attempts exceeded. Please request a new OTP."
        )

    if not check_password(submitted_otp, challenge["otp_hash"]):
        result = challenges.update_one(
            {
                "_id": challenge["_id"],
                "consumed": False,
                "attempts": challenge["attempts"],
            },
            {"$inc": {"attempts": 1}},
        )

        if result.modified_count != 1:
            raise OTPError(
                "OTP challenge changed. Please try again."
            )

        attempts_used = challenge["attempts"] + 1
        remaining = challenge["max_attempts"] - attempts_used

        if remaining <= 0:
            raise OTPAttemptsExceededError(
                "Maximum OTP attempts exceeded. Please request a new OTP."
            )

        raise OTPInvalidError(
            f"Incorrect OTP. You have {remaining} attempt(s) remaining."
        )

    consumed = challenges.update_one(
        {
            "_id": challenge["_id"],
            "consumed": False,
            "attempts": {"$lt": challenge["max_attempts"]},
        },
        {
            "$set": {
                "consumed": True,
                "consumed_at": now,
            }
        },
    )

    if consumed.modified_count != 1:
        raise OTPError(
            "OTP challenge has already been used. Please try again."
        )

    return {
        "user_id": str(object_id),
        "verified": True,
        "purpose": "login",
        "account_status": user["account_status"],
    }





def invalidate_otp_challenge(user_id, purpose):
    """
    Invalidate an unused OTP challenge when email delivery fails.
    """

    try:
        object_id = (
            user_id
            if isinstance(user_id, ObjectId)
            else ObjectId(user_id)
        )
    except Exception as exc:
        raise OTPAccountError("Invalid account.") from exc

    _otp_collection().update_one(
        {
            "user_id": object_id,
            "purpose": purpose,
            "consumed": False,
        },
        {
            "$set": {
                "consumed": True,
                "consumed_at": _utc_now(),
            }
        },
    )