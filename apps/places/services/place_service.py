
from __future__ import annotations

import re
from datetime import datetime, timezone, date
from typing import Any

from bson import ObjectId
from pymongo import ASCENDING, GEOSPHERE, TEXT, UpdateOne
from pymongo.errors import DuplicateKeyError

from core.db import get_db
# from apps.places.services.classification_service import classify_place


PLACES_COLLECTION = "places"


class PlaceError(ValueError):
    """Base exception for place operations."""


class PlaceValidationError(PlaceError):
    """Raised when place data is invalid."""


def _collection():
    return get_db()[PLACES_COLLECTION]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


# def ensure_place_indexes() -> None:
#     """Create indexes required for place discovery."""

#     collection = _collection()

#     collection.create_index(
#         [
#             ("source.provider", ASCENDING),
#             ("source.osm_type", ASCENDING),
#             ("source.osm_id", ASCENDING),
#         ],
#         unique=True,
#         partialFilterExpression={
#             "source.provider": {"$type": "string"},
#             "source.osm_type": {"$type": "string"},
#             "source.osm_id": {"$type": "string"},
#         },
#         name="uniq_place_source",
#     )

#     collection.create_index(
#         [("location", GEOSPHERE)],
#         name="idx_place_location_2dsphere",
#     )

#     collection.create_index(
#         [("name", TEXT), ("address.city", TEXT)],
#         name="idx_place_text_search",
#     )

#     collection.create_index(
#         [
#             ("address.city", ASCENDING),
#             ("category", ASCENDING),
#             ("is_active", ASCENDING),
#         ],
#         name="idx_place_city_category",
#     )

#     collection.create_index(
#         [
#             ("is_tourist_attraction", ASCENDING),
#             ("place_type", ASCENDING),
#             ("subcategory", ASCENDING),
#             ("is_active", ASCENDING),
#         ],
#         name="idx_place_discovery",
#     )


# def _validate_place(data: dict[str, Any]) -> dict[str, Any]:
#     """Validate the minimum required fields of a place."""

#     if not isinstance(data, dict):
#         raise PlaceValidationError("Place data must be a dictionary.")

#     name = data.get("name")
#     category = data.get("category")
#     location = data.get("location")

#     if not isinstance(name, str) or not name.strip():
#         raise PlaceValidationError("Place name is required.")

#     if not isinstance(category, str) or not category.strip():
#         raise PlaceValidationError("Place category is required.")

#     if not isinstance(location, dict) or location.get("type") != "Point":
#         raise PlaceValidationError("Location must be a GeoJSON Point.")

#     coordinates = location.get("coordinates")

#     if not isinstance(coordinates, (list, tuple)) or len(coordinates) != 2:
#         raise PlaceValidationError(
#             "Coordinates must contain longitude and latitude."
#         )

#     longitude, latitude = coordinates

#     if (
#         isinstance(longitude, bool)
#         or isinstance(latitude, bool)
#         or not isinstance(longitude, (int, float))
#         or not isinstance(latitude, (int, float))
#     ):
#         raise PlaceValidationError("Coordinates must be numeric.")

#     if not (-180 <= longitude <= 180):
#         raise PlaceValidationError("Invalid longitude.")

#     if not (-90 <= latitude <= 90):
#         raise PlaceValidationError("Invalid latitude.")

#     return {
#         "name": name.strip(),
#         "category": category.strip().lower(),
#         "location": {
#             "type": "Point",
#             "coordinates": [float(longitude), float(latitude)],
#         },
#     }


def _serialize_place(place: dict[str, Any]) -> dict[str, Any]:
    """Convert MongoDB values into JSON-friendly Python values."""

    def convert_value(value):
        if isinstance(value, ObjectId):
            return str(value)

        if isinstance(value, (datetime, date)):
            return value.isoformat()

        if isinstance(value, dict):
            return {
                key: convert_value(item)
                for key, item in value.items()
            }

        if isinstance(value, list):
            return [
                convert_value(item)
                for item in value
            ]

        return value

    result = convert_value(place)
    result["id"] = result.pop("_id")

    return result


# def _build_place_document(data: dict[str, Any]) -> dict[str, Any]:
#     """Build a consistent place document with application classification."""

#     validated = _validate_place(data)
#     now = _utc_now()

#     address = data.get("address") or {}
#     contact = data.get("contact") or {}
#     source = data.get("source") or {}
    

#     if not isinstance(address, dict):
#         raise PlaceValidationError("Address must be a dictionary.")

#     if not isinstance(contact, dict):
#         raise PlaceValidationError("Contact must be a dictionary.")

#     if not isinstance(source, dict):
#         raise PlaceValidationError("Source must be a dictionary.")

#     images = data.get("images", [])
#     tags = data.get("tags", {})
#     tourism_details = data.get("tourism_details", {})

#     if not isinstance(tourism_details, dict):
#         raise PlaceValidationError(
#             "Tourism details must be a dictionary."
#         )

#     if not isinstance(images, list) or not isinstance(tags, (list, dict)):
#         raise PlaceValidationError("Images and tags have invalid formats.")

#     base_document = {
#         "name": validated["name"],
#         "category": validated["category"],
#         "subcategory": data.get("subcategory"),
#         "tags": tags,
#         "tourism_details": data.get("tourism_details", {}),
#     }

#     classification = classify_place(base_document)  # classification_service.py

#     document = {
#         "name": validated["name"],
#         "slug": data.get("slug"),
#         "category": validated["category"],
#         "subcategory": data.get("subcategory"),
#         "description": data.get("description"),
#         "address": {
#             "street": address.get("street"),
#             "city": address.get("city"),
#             "district": address.get("district"),
#             "state": address.get("state"),
#             "country": address.get("country"),
#             "postal_code": address.get("postal_code"),
#         },
#         "location": validated["location"],
#         "tags": tags,
#         "contact": {
#             "phone": contact.get("phone"),
#             "website": contact.get("website"),
#             "email": contact.get("email"),
#         },
#         "opening_hours": data.get("opening_hours"),

#         "estimated_visit_duration_minutes": data.get(
#             "estimated_visit_duration_minutes"
#         ),

#         "images": images,
#         "review_status": (
#             "pending"
#             if classification.get("is_tourist_attraction")
#             else "not_applicable"
#         ),

#         "tourism_details": data.get("tourism_details", {}),
#         "source": {
#             "provider": source.get("provider"),
#             "osm_type": source.get("osm_type"),
#             "osm_id": (
#                 str(source["osm_id"])
#                 if source.get("osm_id") is not None
#                 else None
#             ),
#             "attribution": source.get("attribution"),
#             "source_url": source.get("source_url"),
#         },
#         "data_quality": data.get(
#             "data_quality",
#             {
#                 "has_coordinates": True,
#                 "has_address": bool(
#                     address.get("city") or address.get("street")
#                 ),
#                 "has_image": bool(images),
#                 "completeness": "partial",
#             },
#         ),
#         **classification,
#         "is_active": bool(data.get("is_active", True)),
#         "created_at": now,
#         "updated_at": now,
#     }

#     return document


# def create_place(data: dict[str, Any]) -> dict[str, Any]:
#     """Insert one validated and classified place into MongoDB."""

#     document = _build_place_document(data)

#     try:
#         result = _collection().insert_one(document)
#     except DuplicateKeyError as exc:
#         raise PlaceValidationError(
#             "This place already exists in the database."
#         ) from exc

#     saved = _collection().find_one({"_id": result.inserted_id})

#     return _serialize_place(saved)


# def get_place_by_id(place_id: str) -> dict[str, Any] | None:
#     """Retrieve one active place by its MongoDB ID."""

#     try:
#         object_id = ObjectId(place_id)
#     except Exception:
#         return None

#     place = _collection().find_one(
#         {
#             "_id": object_id,
#             "is_active": True,
#         }
#     )

#     return _serialize_place(place) if place else None


def _build_search_filters(
    query: str = "",
    city: str | None = None,
    category: str | None = None,
    place_type: str | None = None,
    subcategory: str | None = None,
    attractions_only: bool = False,
    tourist_places_only: bool = False,
    state: str | None = None,
    district: str | None = None,
) -> dict[str, Any]:

    filters = {"is_active": True}

    if attractions_only:
        filters["is_tourist_attraction"] = True
        # filters["review_status"] = "verified"

    if tourist_places_only:
        filters["is_tourist_attraction"] = True

    # Address fields are stored under `address` in current documents.
    # The $or clauses also support older records that used top-level fields.
    extra_conditions = []

    if city:
        city_pattern = {"$regex": f"^{re.escape(city.strip())}$", "$options": "i"}
        extra_conditions.append({"$or": [{"address.city": city_pattern}]})

    if state:
        state_pattern = {"$regex": f"^{re.escape(state.strip())}$", "$options": "i"}
        extra_conditions.append({"$or": [{"address.state": state_pattern}]})

    if district:
        district_pattern = {"$regex": f"^{re.escape(district.strip())}$", "$options": "i"}
        extra_conditions.append({"$or": [{"address.district": district_pattern}]})

    if extra_conditions:
        filters["$and"] = extra_conditions

    if category:
        filters["category"] = category.strip().lower()

    if place_type:
        filters["place_type"] = place_type.strip().lower()

    if subcategory:
        filters["subcategory"] = subcategory.strip().lower()

    if query:
        filters["name"] = {
            "$regex": query.strip(),
            "$options": "i",
        }

    return filters


def search_places_paginated(
    query: str = "",
    city: str | None = None,
    category: str | None = None,
    place_type: str | None = None,
    subcategory: str | None = None,
    page: int = 1,
    page_size: int = 12,
    attractions_only: bool = True,
    tourist_places_only: bool = False,
    state: str | None = None,
    district: str | None = None,
) -> dict[str, Any]:
    """
    Search places and return results with pagination metadata.

    Attractions are included by default.
    """

    if isinstance(page, bool) or not isinstance(page, int) or page < 1:
        raise PlaceValidationError("Page must be a positive integer.")

    if (
        isinstance(page_size, bool)
        or not isinstance(page_size, int)
        or page_size < 1
    ):
        raise PlaceValidationError("Page size must be a positive integer.")

    page_size = min(page_size, 100)

    filters = _build_search_filters(
        query=query,
        city=city,
        category=category,
        place_type=place_type,
        subcategory=subcategory,
        attractions_only=attractions_only,
        tourist_places_only=tourist_places_only,
        state=state,
        district=district,
    )

    collection = _collection()
    total_count = collection.count_documents(filters)
    total_pages = (total_count + page_size - 1) // page_size

    places = (
        collection.find(filters)
        .sort("name", ASCENDING)
        .skip((page - 1) * page_size)
        .limit(page_size)
    )

    results = [_serialize_place(place) for place in places]

    return {
        "results": results,
        "pagination": {
            "current_page": page,
            "page_size": page_size,
            "total_count": total_count,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages,
        },
    }



def find_nearby_places(
    longitude: float,
    latitude: float,
    max_distance_meters: int = 10000,
    limit: int = 20,
    *,
    attractions_only: bool = False,
    place_type: str | None = None,
) -> list[dict[str, Any]]:
    """Find active places within a specified radius."""

    if (
        isinstance(longitude, bool)
        or isinstance(latitude, bool)
        or not isinstance(longitude, (int, float))
        or not isinstance(latitude, (int, float))
        or not (-180 <= longitude <= 180)
        or not (-90 <= latitude <= 90)
    ):
        raise PlaceValidationError("Invalid coordinates.")

    if (
        isinstance(max_distance_meters, bool)
        or not isinstance(max_distance_meters, int)
        or not 1 <= max_distance_meters <= 100000
    ):
        raise PlaceValidationError("Invalid search radius.")

    if isinstance(limit, bool) or not isinstance(limit, int):
        raise PlaceValidationError("Limit must be an integer.")

    limit = max(1, min(limit, 100))

    filters: dict[str, Any] = {
        "is_active": True,
        "location": {
            "$near": {
                "$geometry": {
                    "type": "Point",
                    "coordinates": [longitude, latitude],
                },
                "$maxDistance": max_distance_meters,
            }
        },
    }

    # if attractions_only:
    #     filters["is_tourist_attraction"] = True
    #     filters["review_status"] = "verified"

    if place_type and place_type.strip():
        filters["place_type"] = place_type.strip().lower()

    places = _collection().find(filters).limit(limit)

    return [_serialize_place(place) for place in places]


