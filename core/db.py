"""
Shared MongoDB access for TourismPlanner.

A single MongoClient is created and reused for the process lifetime.
Django still uses SQLite for sessions; application data lives in MongoDB.
"""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.database import Database
from pymongo.errors import ConnectionFailure, ServerSelectionTimeoutError

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_PROJECT_ROOT / ".env")

_SERVER_SELECTION_TIMEOUT_MS = 5000

_client: MongoClient | None = None


class MongoConfigError(RuntimeError):
    """Raised when required MongoDB environment variables are missing."""


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value:
        raise MongoConfigError(
            f"Missing required environment variable '{name}'. "
            "Set it in the project .env file."
        )
    return value


def get_client() -> MongoClient:
    """Return the process-wide MongoClient, creating it on first use."""
    global _client
    if _client is None:
        uri = _require_env("MONGODB_URI")
        _client = MongoClient(
            uri,
            serverSelectionTimeoutMS=_SERVER_SELECTION_TIMEOUT_MS,
        )
    return _client


def get_db() -> Database:
    """Return the TourismPlanner MongoDB database."""
    db_name = _require_env("MONGODB_DB")
    return get_client()[db_name]


def check_connection() -> bool:
    """
    Ping MongoDB.

    Returns True on success. Raises ConnectionFailure or
    ServerSelectionTimeoutError if the server cannot be reached.
    """
    get_db().command("ping")
    return True


def close_client() -> None:
    """Close the shared client. Useful in tests; not required per request."""
    global _client
    if _client is not None:
        _client.close()
        _client = None


# Re-export error types so callers can catch them without importing pymongo.
__all__ = [
    "MongoConfigError",
    "check_connection",
    "close_client",
    "get_client",
    "get_db",
    "ConnectionFailure",
    "ServerSelectionTimeoutError",
]
