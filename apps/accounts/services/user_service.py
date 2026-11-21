"""
MongoDB user repository for TourismPlanner.

Passwords are hashed with Django's make_password. The shared PyMongo
client in core.db is reused; this module never constructs MongoClient.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from bson.errors import InvalidId
from django.conf import settings
from django.contrib.auth.hashers import make_password
import phonenumbers
from phonenumbers import NumberParseException, PhoneNumberFormat
from pymongo import ASCENDING, ReturnDocument
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from core.db import get_db

USERS_COLLECTION = "users"

ACCOUNT_STATUS_PENDING = "pending"
ACCOUNT_STATUS_ACTIVE = "active"
ACCOUNT_STATUS_DISABLED = "disabled"
ACCOUNT_STATUSES = frozenset(
    {
        ACCOUNT_STATUS_PENDING,
        ACCOUNT_STATUS_ACTIVE,
        ACCOUNT_STATUS_DISABLED,
    }
)

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_MIN_PASSWORD_LENGTH = 8
_MAX_NAME_LENGTH = 120
_MAX_EMAIL_LENGTH = 254

_PUBLIC_EXCLUDE = frozenset({"password_hash"})
_ALLOWED_UPDATE_FIELDS = frozenset({
    "name",
    "mobile_number",
    "mobile_verified",
    "email_verified",
    "account_status",
    "last_login_at",
    "password",
})


class UserValidationError(ValueError):
    """Raised when user input is missing, malformed, or unsafe."""


class DuplicateUserError(ValueError):
    """Raised when email or mobile already belongs to another user."""

    def __init__(self, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.field = field


class InvalidUserIdError(ValueError):
    """Raised when a user id is not a valid MongoDB ObjectId."""


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _users() -> Collection:
    return get_db()[USERS_COLLECTION]


def _is_unsafe_key(key: str) -> bool:
    return key.startswith("$") or "." in key


def _require_plain_string(value: Any, field: str) -> str:
    """Reject non-strings so MongoDB operators (dicts) cannot be injected."""
    if not isinstance(value, str):
        raise UserValidationError(f"{field} must be a string.")
    return value


def normalize_email(email: str) -> str:
    cleaned = _require_plain_string(email, "email").strip().lower()
    if not cleaned or len(cleaned) > _MAX_EMAIL_LENGTH or not _EMAIL_RE.match(cleaned):
        raise UserValidationError("Enter a valid email address.")
    return cleaned


def normalize_mobile(mobile_number: str | None) -> str | None:
    """
    Return an E.164 number (for example +919876543210).

    If the input includes a leading '+', the country code in the input is used.
    If it does not, Django's DEFAULT_PHONE_REGION is used (IN for this project).
    Country codes are never guessed beyond that library behaviour.
    """
    if mobile_number is None:
        return None
    raw = _require_plain_string(mobile_number, "mobile_number").strip()
    if raw == "":
        return None

    default_region = getattr(settings, "DEFAULT_PHONE_REGION", "IN")
    try:
        parsed = phonenumbers.parse(raw, default_region)
    except NumberParseException as exc:
        raise UserValidationError("Enter a valid mobile number.") from exc

    if not phonenumbers.is_valid_number(parsed):
        raise UserValidationError("Enter a valid mobile number.")

    return phonenumbers.format_number(parsed, PhoneNumberFormat.E164)


def _parse_object_id(user_id: Any) -> ObjectId:
    if isinstance(user_id, ObjectId):
        return user_id
    if not isinstance(user_id, str) or not user_id.strip():
        raise InvalidUserIdError("user_id must be a MongoDB ObjectId string.")
    try:
        return ObjectId(user_id.strip())
    except (InvalidId, TypeError) as exc:
        raise InvalidUserIdError("user_id is not a valid ObjectId.") from exc


def to_public_user(document: dict[str, Any] | None) -> dict[str, Any] | None:
    """Return a copy of the user document without password_hash."""
    if document is None:
        return None
    return {key: value for key, value in document.items() if key not in _PUBLIC_EXCLUDE}


def ensure_user_indexes(collection: Collection | None = None) -> None:
    """
    Create uniqueness indexes for users.

    email_normalized is always unique.
    mobile_number is unique only when the field is a non-empty string,
    so several accounts may exist without a mobile number.
    """
    coll = collection if collection is not None else _users()
    coll.create_index(
        [("email_normalized", ASCENDING)],
        unique=True,
        name="uniq_email_normalized",
    )
    coll.create_index(
        [("mobile_number", ASCENDING)],
        unique=True,
        name="uniq_mobile_number",
        partialFilterExpression={"mobile_number": {"$type": "string"}},
    )


def create_user(
    *,
    name: str,
    email: str,
    password: str,
    mobile_number: str | None = None,
    collection: Collection | None = None,
) -> dict[str, Any]:
    """Insert a pending user. Returns the public user document."""
    name_value = _require_plain_string(name, "name").strip()
    if not name_value or len(name_value) > _MAX_NAME_LENGTH:
        raise UserValidationError("Enter a valid name.")

    email_normalized = normalize_email(email)
    password_value = _require_plain_string(password, "password")
    if len(password_value) < _MIN_PASSWORD_LENGTH:
        raise UserValidationError(
            f"password must be at least {_MIN_PASSWORD_LENGTH} characters."
        )

    mobile = normalize_mobile(mobile_number)
    now = _utc_now()
    document: dict[str, Any] = {
        "name": name_value,
        "email": email_normalized,
        "email_normalized": email_normalized,
        "password_hash": make_password(password_value),
        "mobile_verified": False,
        "email_verified": False,
        "account_status": ACCOUNT_STATUS_PENDING,
        "created_at": now,
        "updated_at": now,
        "last_login_at": None,
    }
    if mobile is not None:
        document["mobile_number"] = mobile

    coll = collection if collection is not None else _users()
    try:
        result = coll.insert_one(document)
    except DuplicateKeyError as exc:
        raise _duplicate_user_error(exc) from exc

    document["_id"] = result.inserted_id
    return to_public_user(document)


def get_user_by_email(
    email: str,
    *,
    include_password_hash: bool = False,
    collection: Collection | None = None,
) -> dict[str, Any] | None:
    email_normalized = normalize_email(email)
    coll = collection if collection is not None else _users()
    document = coll.find_one({"email_normalized": email_normalized})
    if include_password_hash:
        return document
    return to_public_user(document)


def get_user_by_mobile(
    mobile_number: str,
    *,
    include_password_hash: bool = False,
    collection: Collection | None = None,
) -> dict[str, Any] | None:
    mobile = normalize_mobile(mobile_number)
    if mobile is None:
        return None
    coll = collection if collection is not None else _users()
    document = coll.find_one({"mobile_number": mobile})
    if include_password_hash:
        return document
    return to_public_user(document)


def get_user_by_id(
    user_id: Any,
    *,
    include_password_hash: bool = False,
    collection: Collection | None = None,
) -> dict[str, Any] | None:
    object_id = _parse_object_id(user_id)
    coll = collection if collection is not None else _users()
    document = coll.find_one({"_id": object_id})
    if include_password_hash:
        return document
    return to_public_user(document)


def update_user(
    user_id: Any,
    updates: dict[str, Any],
    *,
    collection: Collection | None = None,
) -> dict[str, Any] | None:
    """
    Apply a whitelist of user fields. Unknown keys and MongoDB operators
    are rejected. Returns the updated public user, or None if missing.
    """
    if not isinstance(updates, dict) or not updates:
        raise UserValidationError("updates must be a non-empty object.")

    object_id = _parse_object_id(user_id)
    set_fields: dict[str, Any] = {"updated_at": _utc_now()}
    unset_fields: dict[str, str] = {}

    for key, value in updates.items():
        if not isinstance(key, str) or _is_unsafe_key(key):
            raise UserValidationError("updates contain disallowed keys.")
        if key not in _ALLOWED_UPDATE_FIELDS:
            raise UserValidationError(f"Field '{key}' cannot be updated.")

        if key == "name":
            name_value = _require_plain_string(value, "name").strip()
            if not name_value or len(name_value) > _MAX_NAME_LENGTH:
                raise UserValidationError("Enter a valid name.")
            set_fields["name"] = name_value
        elif key == "password":
            password_value = _require_plain_string(value, "password")
            if len(password_value) < _MIN_PASSWORD_LENGTH:
                raise UserValidationError(
                    f"password must be at least {_MIN_PASSWORD_LENGTH} characters."
                )
            set_fields["password_hash"] = make_password(password_value)
        elif key == "mobile_number":
            mobile = normalize_mobile(value)
            if mobile is None:
                unset_fields["mobile_number"] = ""
            else:
                set_fields["mobile_number"] = mobile
        elif key == "mobile_verified":
            if not isinstance(value, bool):
                raise UserValidationError("mobile_verified must be a boolean.")
            set_fields["mobile_verified"] = value
        elif key == "email_verified":
            if not isinstance(value, bool):
                raise UserValidationError(
                    "email_verified must be a boolean."
                )
            set_fields["email_verified"] = value
        elif key == "account_status":
            status = _require_plain_string(value, "account_status").strip()
            if status not in ACCOUNT_STATUSES:
                raise UserValidationError("Invalid account_status.")
            set_fields["account_status"] = status
        elif key == "last_login_at":
            if value is not None and not isinstance(value, datetime):
                raise UserValidationError("last_login_at must be a datetime or None.")
            set_fields["last_login_at"] = value

    operation: dict[str, Any] = {"$set": set_fields}
    if unset_fields:
        operation["$unset"] = unset_fields

    coll = collection if collection is not None else _users()
    try:
        document = coll.find_one_and_update(
            {"_id": object_id},
            operation,
            return_document=ReturnDocument.AFTER,
        )
    except DuplicateKeyError as exc:
        raise _duplicate_user_error(exc) from exc

    return to_public_user(document)


def _duplicate_user_error(exc: DuplicateKeyError) -> DuplicateUserError:
    details = exc.details or {}
    key_pattern = details.get("keyPattern") or {}
    key_value = details.get("keyValue") or {}
    combined = {**key_pattern, **key_value}
    message = str(details) + str(exc)
    if "email_normalized" in combined or "email_normalized" in message:
        return DuplicateUserError("An account with this email already exists.", field="email")
    if "mobile_number" in combined or "mobile_number" in message:
        return DuplicateUserError(
            "An account with this mobile number already exists.",
            field="mobile_number",
        )
    return DuplicateUserError("An account with this email or mobile number already exists.")
