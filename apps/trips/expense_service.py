from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from bson import ObjectId
from core.db import get_db
from bson.decimal128 import Decimal128


def _collection():
    return get_db()["trips"]


def update_trip_budget(user_id, trip_id, budget):
    """Set or update the overall budget for a trip."""

    if not ObjectId.is_valid(trip_id):
        raise ValueError("Invalid trip ID.")

    try:
        amount = Decimal(str(budget))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Please enter a valid budget.")

    if not amount.is_finite() or amount < 0:
        raise ValueError("Budget cannot be negative or invalid.")

    result = _collection().update_one(
        {
            "_id": ObjectId(trip_id),
            "user_id": str(user_id)
        },
        {
            "$set": {
                "budget": Decimal128(amount),
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )

    if result.matched_count != 1:
        raise ValueError("Trip not found.")

    return True


def add_expense(user_id, trip_id, amount, category, description, expense_date, day_number=None):
    """Add an expense to a trip."""

    if not ObjectId.is_valid(trip_id):
        raise ValueError("Invalid trip ID.")

    try:
        expense_amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Please enter a valid expense amount.")

    if not expense_amount.is_finite() or expense_amount <= 0:
        raise ValueError("Expense amount must be greater than zero.")

    category = str(category).strip()
    description = str(description).strip()

    allowed_categories = [
        "Food",
        "Accommodation",
        "Transport",
        "Activities",
        "Shopping",
        "Other"
    ]

    if category not in allowed_categories:
        raise ValueError("Invalid expense category.")

    try:
        parsed_date = datetime.strptime(expense_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValueError("Please provide a valid expense date.")

    trip = _collection().find_one({
        "_id": ObjectId(trip_id),
        "user_id": str(user_id)
    })

    if not trip:
        raise ValueError("Trip not found.")

    if not (trip["start_date"] <= parsed_date.isoformat() <= trip["end_date"]):
        raise ValueError("Expense date must be within the trip dates.")

    if day_number is not None:
        day = next(
            (
                item for item in trip.get("days", [])
                if item["day_number"] == int(day_number)
            ),
            None
        )

        if not day or day["date"] != parsed_date.isoformat():
            raise ValueError(
               "The selected itinerary day does not match the expense date. "
                "Please select the correct day or choose 'Not linked to a day'."
            )

    expense = {
        "expense_id": str(ObjectId()),
        "amount": Decimal128(expense_amount),
        "category": category,
        "description": description,
        "date": parsed_date.isoformat(),
        "day_number": int(day_number) if day_number is not None else None,
        "created_at": datetime.now(timezone.utc)
    }

    result = _collection().update_one(
        {
            "_id": ObjectId(trip_id),
            "user_id": str(user_id)
        },
        {
            "$push": {"expenses": expense},
            "$set": {"updated_at": datetime.now(timezone.utc)}
        }
    )

    if result.modified_count != 1:
        raise ValueError("Could not save expense.")

    return expense




def get_expense_summary(user_id, trip_id):
    """Calculate overall, day-wise and category-wise trip expenses."""

    if not ObjectId.is_valid(trip_id):
        raise ValueError("Invalid trip ID.")

    trip = _collection().find_one({
        "_id": ObjectId(trip_id),
        "user_id": str(user_id)
    })

    if not trip:
        raise ValueError("Trip not found.")

    expenses = trip.get("expenses", [])

    total_spent = Decimal("0")
    category_totals = {}
    daily_totals = {}
    expense_history = []

    for expense in expenses:
        amount_value = expense["amount"]

        if hasattr(amount_value, "to_decimal"):
            amount = amount_value.to_decimal()
        else:
            amount = Decimal(str(amount_value))

        total_spent += amount

        category = expense["category"]
        category_totals[category] = (
            category_totals.get(category, Decimal("0")) + amount
        )

        expense_date = expense["date"]
        daily_totals[expense_date] = (
            daily_totals.get(expense_date, Decimal("0")) + amount
        )

        expense_history.append({
            "expense_id": str(expense.get("expense_id", "")),
            "amount": float(amount),
            "category": category,
            "description": expense.get("description", ""),
            "expense_date": expense_date,
            "day_number": expense.get("day_number")
        })

    budget_value = trip.get("budget", 0)

    if hasattr(budget_value, "to_decimal"):
        budget = budget_value.to_decimal()
    else:
        budget = Decimal(str(budget_value))

    remaining_budget = budget - total_spent

    budget_used_percentage = (
        float((total_spent / budget) * 100)
        if budget > 0 else 0
    )

    return {
        "budget": float(budget),
        "total_spent": float(total_spent),
        "remaining_budget": float(remaining_budget),
        "budget_used_percentage": round(budget_used_percentage, 2),

        "daily_totals": {
            day: float(amount)
            for day, amount in sorted(daily_totals.items())
        },

        "category_totals": {
            category: float(amount)
            for category, amount in category_totals.items()
        },

        "expense_count": len(expenses),
        "expenses": expense_history
    }



def update_expense(
    user_id,
    trip_id,
    expense_id,
    amount,
    category,
    description,
    expense_date,
    day_number=None
):
    """Update an existing trip expense."""

    if not ObjectId.is_valid(trip_id):
        raise ValueError("Invalid trip ID.")

    try:
        expense_amount = Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        raise ValueError("Please enter a valid expense amount.")

    if not expense_amount.is_finite() or expense_amount <= 0:
        raise ValueError("Expense amount must be greater than zero.")

    category = str(category).strip()
    description = str(description).strip()

    allowed_categories = [
        "Food",
        "Accommodation",
        "Transport",
        "Activities",
        "Shopping",
        "Other"
    ]

    if category not in allowed_categories:
        raise ValueError("Invalid expense category.")

    try:
        parsed_date = datetime.strptime(expense_date, "%Y-%m-%d").date()
    except (ValueError, TypeError):
        raise ValueError("Please provide a valid expense date.")

    trip = _collection().find_one({
        "_id": ObjectId(trip_id),
        "user_id": str(user_id)
    })

    if not trip:
        raise ValueError("Trip not found.")

    if not (trip["start_date"] <= parsed_date.isoformat() <= trip["end_date"]):
        raise ValueError("Expense date must be within the trip dates.")

    if day_number is not None:
        day = next(
            (
                item for item in trip.get("days", [])
                if item["day_number"] == int(day_number)
            ),
            None
        )

        if not day or day["date"] != parsed_date.isoformat():
            raise ValueError(
                "The selected itinerary day does not match the expense date. "
                "Please select the correct day or choose 'Not linked to a day'."
            )

    result = _collection().update_one(
        {
            "_id": ObjectId(trip_id),
            "user_id": str(user_id),
            "expenses.expense_id": str(expense_id)
        },
        {
            "$set": {
                "expenses.$.amount": Decimal128(expense_amount),
                "expenses.$.category": category,
                "expenses.$.description": description,
                "expenses.$.date": parsed_date.isoformat(),
                "expenses.$.day_number": (
                    int(day_number) if day_number is not None else None
                ),
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )

    if result.matched_count != 1:
        raise ValueError("Expense not found.")

    return True



def delete_expense(user_id, trip_id, expense_id):
    """Delete an expense from a trip."""

    if not ObjectId.is_valid(trip_id):
        raise ValueError("Invalid trip ID.")

    result = _collection().update_one(
        {
            "_id": ObjectId(trip_id),
            "user_id": str(user_id),
            "expenses.expense_id": str(expense_id)
        },
        {
            "$pull": {
                "expenses": {
                    "expense_id": str(expense_id)
                }
            },
            "$set": {
                "updated_at": datetime.now(timezone.utc)
            }
        }
    )

    if result.modified_count != 1:
        raise ValueError("Expense not found or could not be deleted.")

    return True