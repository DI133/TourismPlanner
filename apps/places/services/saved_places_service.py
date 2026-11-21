
from datetime import datetime, timezone
from uuid import uuid4

from core.db import get_db


def _collection():
    return get_db()["saved_places"]


def _get_place_key(place):
    place_id = place.get("id") or place.get("osm_id")

    if place_id:
        return str(place_id)

    location = place.get("location") or {}
    coordinates = location.get("coordinates") or []

    return (
        f"{place.get('name', '').strip().lower()}_"
        f"{coordinates}"
    )


def save_place(user_id, place):
    if not user_id:
        raise ValueError("User authentication is required.")

    if not isinstance(place, dict) or not place.get("name"):
        raise ValueError("Valid destination details are required.")

    place_key = _get_place_key(place)

    existing = _collection().find_one({
        "user_id": str(user_id),
        "place_key": place_key
    })

    if existing:
        raise ValueError("This destination is already saved.")

    saved_place = {
        "saved_place_id": str(uuid4()),
        "user_id": str(user_id),
        "place_key": place_key,
        "place": place,
        "saved_at": datetime.now(timezone.utc)
    }

    _collection().insert_one(saved_place)

    return saved_place


def get_saved_places(user_id):
    if not user_id:
        raise ValueError("User authentication is required.")

    records = _collection().find(
        {"user_id": str(user_id)}
    ).sort("saved_at", -1)

    return [
        {
            "saved_place_id": record["saved_place_id"],
            "place": record["place"],
            "saved_at": record["saved_at"].isoformat()
        }
        for record in records
    ]


def remove_saved_place(user_id, saved_place_id):
    if not user_id or not saved_place_id:
        raise ValueError("Invalid saved destination.")

    result = _collection().delete_one({
        "user_id": str(user_id),
        "saved_place_id": saved_place_id
    })

    if result.deleted_count == 0:
        raise ValueError("Saved destination not found.")

    return True
