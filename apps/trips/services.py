from datetime import datetime, timezone, date, timedelta
from bson import ObjectId
from pymongo import DESCENDING
from core.db import get_db
from decimal import Decimal, InvalidOperation
from bson.decimal128 import Decimal128

def _collection():
    return get_db()["trips"]


def create_trip(user_id, title, start_date, end_date, budget=0):
    """Create a trip with an empty day-wise itinerary."""

    if not title or not title.strip():
        raise ValueError("Trip title is required.")

    try:
        budget_amount = Decimal(str(budget))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Please enter a valid trip budget.")

    if not budget_amount.is_finite() or budget_amount < 0:
        raise ValueError("Trip budget cannot be negative.")

    start = date.fromisoformat(start_date)
    end = date.fromisoformat(end_date)

    if end < start:
        raise ValueError("End date cannot be before start date.")

    days = []
    current = start
    day_number = 1

    while current <= end:
        days.append({
            "day_number": day_number,
            "date": current.isoformat(),
            "items": [],
        })
        current = date.fromordinal(current.toordinal() + 1)
        day_number += 1

    trip = {
        "user_id": str(user_id),
        "title": title.strip(),
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "status": "planned",
        "days": days,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "budget": Decimal128(budget_amount),
        "expenses": [],
    }

    result = _collection().insert_one(trip)

    trip["budget"] = float(budget_amount)
    trip["_id"] = str(result.inserted_id)

    return trip


def get_user_trips(user_id):
    trips = list(
        _collection().find(
            {"user_id": str(user_id)}
        ).sort("created_at", DESCENDING)
    )

    result = []

    for trip in trips:
        trip["_id"] = str(trip["_id"])

        # Convert trip budget
        budget = trip.get("budget", 0)

        if isinstance(budget, Decimal128):
            trip["budget"] = float(budget.to_decimal())
        else:
            trip["budget"] = float(budget or 0)

        # Convert embedded expense amounts
        for expense in trip.get("expenses", []):
            amount = expense.get("amount", 0)

            if isinstance(amount, Decimal128):
                expense["amount"] = float(amount.to_decimal())
            else:
                expense["amount"] = float(amount or 0)

        result.append(trip)

    return result


def get_trip(user_id, trip_id):
    """Get one trip, enforcing user ownership."""

    if not ObjectId.is_valid(trip_id):
        return None

    trip = _collection().find_one({
        "_id": ObjectId(trip_id),
        "user_id": str(user_id),
    })

    if trip:
        trip["_id"] = str(trip["_id"])

    return trip


def add_place_to_trip(user_id, trip_id, day_number, place):
    """Save a selected live or database place inside a trip."""

    if not ObjectId.is_valid(trip_id):
        raise ValueError("Invalid trip ID.")

    trip = get_trip(user_id, trip_id)

    if not trip:    
        raise ValueError("Trip not found.")

    day = next(
        (
            item for item in trip["days"]
            if item["day_number"] == int(day_number)
        ),
        None,
    )

    if not day:
        raise ValueError("Selected itinerary day does not exist.")
    
    if day.get("completed", False):
        raise ValueError(
            "This day is completed. Mark it incomplete before adding destinations."
        )

    place_item = {
        "place_id": str(place.get("id", "")),
        "name": place.get("name", "Unknown place"),
        "category": place.get("category", ""),
        "subcategory": place.get("subcategory", ""),
        "description": place.get("description", ""),
        "address": place.get("address", {}),
        "location": place.get("location"),
        "images": place.get("images", []),
        "source": place.get("source", {}),
        "added_at": datetime.now(timezone.utc),
        "order": len(day["items"]) + 1,
    }

    result = _collection().update_one(
        {
            "_id": ObjectId(trip_id),
            "user_id": str(user_id),
            "days.day_number": int(day_number),
        },
        {
            "$push": {
                "days.$.items": place_item
            },
            "$set": {
                "updated_at": datetime.now(timezone.utc)
            },
        },
    )

    if result.modified_count != 1:
        raise ValueError("Could not add place to itinerary.")

    return place_item




def remove_place_from_trip(user_id, trip_id, day_number, place_index):
    """Remove one destination from a user's trip day."""

    if not ObjectId.is_valid(trip_id):
        raise ValueError("Invalid trip ID.")

    trip = get_trip(user_id, trip_id)

    if not trip:
        raise ValueError("Trip not found.")

    day = next(
        (
            item for item in trip["days"]
            if item["day_number"] == int(day_number)
        ),
        None,
    )

    if not day:
        raise ValueError("Selected itinerary day does not exist.")

    if day.get("completed", False):
        raise ValueError(
            "This day is completed. Mark it incomplete before removing destinations."
        )

    place_index = int(place_index)

    if place_index < 0 or place_index >= len(day["items"]):
        raise ValueError("Destination not found.")

    # Remove only the selected destination
    day["items"].pop(place_index)

    # Update the order of remaining destinations
    for index, item in enumerate(day["items"], start=1):
        item["order"] = index

    result = _collection().update_one(
        {
            "_id": ObjectId(trip_id),
            "user_id": str(user_id),
        },
        {
            "$set": {
                "days": trip["days"],
                "updated_at": datetime.now(timezone.utc),
            }
        },
    )

    if result.modified_count != 1:
        raise ValueError("Could not remove destination.")

    return True




def update_trip(user_id, trip_id, title, start_date, end_date, budget=None):
    """Update trip details while protecting completed itinerary days."""

    if not ObjectId.is_valid(trip_id):
        raise ValueError("Invalid trip ID.")

    title = title.strip() if title else ""

    if not title:
        raise ValueError("Trip title is required.")

    try:
        start = date.fromisoformat(start_date)
        end = date.fromisoformat(end_date)
    except (ValueError, TypeError):
        raise ValueError("Please provide valid trip dates.")

    if end < start:
        raise ValueError("End date cannot be before start date.")

    # Validate budget when provided.
    if budget is not None:
        try:
            budget_amount = Decimal(str(budget))
        except (InvalidOperation, TypeError, ValueError):
            raise ValueError("Please enter a valid trip budget.")

        if not budget_amount.is_finite() or budget_amount < 0:
            raise ValueError("Trip budget cannot be negative.")

    trip = get_trip(user_id, trip_id)

    if not trip:
        raise ValueError("Trip not found.")

    existing_days = {
        day["date"]: day
        for day in trip.get("days", [])
    }

    # Generate the dates in the updated trip.
    new_dates = set()
    current_date = start

    while current_date <= end:
        new_dates.add(current_date.isoformat())
        current_date += timedelta(days=1)

    # Never allow an existing completed day to be removed.
    for day in trip.get("days", []):
        if day.get("completed", False) and day["date"] not in new_dates:
            raise ValueError(
                f"Cannot remove completed Day {day['day_number']}. "
                "Mark that day incomplete before changing the trip dates."
            )

    # Preserve destinations and completion status for retained dates.
    days = []
    current_date = start

    while current_date <= end:
        date_string = current_date.isoformat()
        existing_day = existing_days.get(date_string, {})

        days.append({
            "day_number": len(days) + 1,
            "date": date_string,
            "items": existing_day.get("items", []),
            "completed": existing_day.get("completed", False)
        })

        current_date += timedelta(days=1)

    # Prepare fields to update.
    update_fields = {
        "title": title,
        "start_date": start.isoformat(),
        "end_date": end.isoformat(),
        "days": days,
        "updated_at": datetime.now(timezone.utc)
    }

    # Update budget only when supplied.
    if budget is not None:
        update_fields["budget"] = Decimal128(budget_amount)

    result = _collection().update_one(
        {
            "_id": ObjectId(trip_id),
            "user_id": str(user_id)
        },
        {
            "$set": update_fields
        }
    )

    if result.matched_count != 1:
        raise ValueError("Could not update trip.")

    return True


def reorder_trip_places(user_id, trip_id, day_number, place_index, direction):
    """Move a destination up or down within a trip day."""

    if not ObjectId.is_valid(trip_id):
        raise ValueError("Invalid trip ID.")

    trip = get_trip(user_id, trip_id)

    if not trip:
        raise ValueError("Trip not found.")

    day = next(
        (item for item in trip["days"]
         if item["day_number"] == int(day_number)),
        None
    )

    if not day:
        raise ValueError("Selected itinerary day does not exist.")

    if day.get("completed", False):
        raise ValueError(
            "This day is completed. Mark it incomplete before reordering destinations."
        )

    items = day["items"]
    place_index = int(place_index)

    if place_index < 0 or place_index >= len(items):
        raise ValueError("Destination not found.")

    if direction not in ("up", "down"):
        raise ValueError("Invalid reorder direction.")

    new_index = place_index - 1 if direction == "up" else place_index + 1

    if new_index < 0 or new_index >= len(items):
        raise ValueError("Destination cannot be moved further.")

    items[place_index], items[new_index] = items[new_index], items[place_index]

    for index, item in enumerate(items, start=1):
        item["order"] = index

    result = _collection().update_one(
        {
            "_id": ObjectId(trip_id),
            "user_id": str(user_id)
        },
        {
            "$set": {
                "days": trip["days"],
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )

    if result.matched_count != 1:
        raise ValueError("Could not reorder destinations.")

    return True



def delete_trip(user_id, trip_id):
    """Delete a trip belonging to the logged-in user."""

    if not ObjectId.is_valid(trip_id):
        raise ValueError("Invalid trip ID.")

    result = _collection().delete_one({
        "_id": ObjectId(trip_id),
        "user_id": str(user_id)
    })

    if result.deleted_count != 1:
        raise ValueError("Trip not found or could not be deleted.")

    return True


def update_place_visited(user_id, trip_id, day_number, place_index, visited):
    """Track visited destinations in sequential trip order."""

    if not ObjectId.is_valid(trip_id):
        raise ValueError("Invalid trip ID.")

    if not isinstance(visited, bool):
        raise ValueError("Invalid visited status.")

    trip = get_trip(user_id, trip_id)

    if not trip:
        raise ValueError("Trip not found.")

    day_number = int(day_number)
    place_index = int(place_index)

    # Find the selected destination.
    selected_day = next(
        (
            day for day in trip["days"]
            if day["day_number"] == day_number
        ),
        None
    )

    if not selected_day:
        raise ValueError("Selected itinerary day does not exist.")

    if place_index < 0 or place_index >= len(selected_day["items"]):
        raise ValueError("Destination not found.")

    # Flatten all destinations in chronological itinerary order.
    all_places = []

    for day in trip["days"]:
        for index, item in enumerate(day["items"]):
            all_places.append({
                "day": day,
                "item": item,
                "index": index
            })

    selected_position = next(
        (
            i for i, entry in enumerate(all_places)
            if entry["day"]["day_number"] == day_number
            and entry["index"] == place_index
        ),
        None
    )

    if selected_position is None:
        raise ValueError("Destination not found.")

    visited_positions = [
        i for i, entry in enumerate(all_places)
        if entry["item"].get("visited", False)
    ]

    if visited:
        # Only the first unvisited destination can be marked visited.
        expected_position = len(visited_positions)

        if selected_position != expected_position:
            raise ValueError(
                "Please visit the destinations in itinerary order."
            )

    else:
        # Only the most recently visited destination can be unchecked.
        if not visited_positions or selected_position != visited_positions[-1]:
            raise ValueError(
                "You can only undo the most recently visited destination."
            )

    selected_day["items"][place_index]["visited"] = visited

    result = _collection().update_one(
        {
            "_id": ObjectId(trip_id),
            "user_id": str(user_id)
        },
        {
            "$set": {
                "days": trip["days"],
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )

    if result.matched_count != 1:
        raise ValueError("Could not update destination status.")

    return True


def update_day_completion(user_id, trip_id, day_number, completed):
    """Mark an entire itinerary day as completed or incomplete."""

    if not ObjectId.is_valid(trip_id):
        raise ValueError("Invalid trip ID.")

    if not isinstance(completed, bool):
        raise ValueError("Invalid completion status.")

    trip = get_trip(user_id, trip_id)

    if not trip:
        raise ValueError("Trip not found.")

    day = next(
        (
            item for item in trip["days"]
            if item["day_number"] == int(day_number)
        ),
        None
    )

    if not day:
        raise ValueError("Selected itinerary day does not exist.")

    day["completed"] = completed

    result = _collection().update_one(
        {
            "_id": ObjectId(trip_id),
            "user_id": str(user_id)
        },
        {
            "$set": {
                "days": trip["days"],
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )

    if result.matched_count != 1:
        raise ValueError("Could not update day completion.")

    return True


def apply_optimized_order(
    user_id,
    trip_id,
    day_number,
    ordered_indices,
    start_location
    ):
    if not ObjectId.is_valid(trip_id):
        raise ValueError("Invalid trip ID.")

    if not isinstance(ordered_indices, list):
        raise ValueError("Invalid destination order.")

    if not isinstance(start_location, dict):
        raise ValueError("Invalid starting location.")

    longitude = float(start_location["longitude"])
    latitude = float(start_location["latitude"])

    if not (-180 <= longitude <= 180):
        raise ValueError("Invalid starting longitude.")

    if not (-90 <= latitude <= 90):
        raise ValueError("Invalid starting latitude.")

    collection = _collection()

    trip = collection.find_one({
        "_id": ObjectId(trip_id),
        "user_id": user_id
    })

    if not trip:
        raise ValueError("Trip not found.")

    day = next(
        (
            item for item in trip.get("days", [])
            if item["day_number"] == day_number
        ),
        None
    )

    if not day:
        raise ValueError("Selected day does not exist.")

    if day.get("completed", False):
        raise ValueError("Completed days cannot be reordered.")

    items = day.get("items", [])

    if (
        len(ordered_indices) != len(items)
        or sorted(ordered_indices) != list(range(len(items)))
    ):
        raise ValueError("Invalid optimized destination sequence.")

    reordered_items = [
        items[index] for index in ordered_indices
    ]

    for index, item in enumerate(reordered_items):
        item["order"] = index

    result = collection.update_one(
        {
            "_id": ObjectId(trip_id),
            "user_id": user_id,
            "days.day_number": day_number,
            "days.completed": {"$ne": True}
        },
        {
            "$set": {
                "days.$.items": reordered_items,
                "days.$.start_location": {
                    "longitude": longitude,
                    "latitude": latitude
                },
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )

    if result.matched_count == 0:
        raise ValueError("Unable to update the itinerary.")

    return True