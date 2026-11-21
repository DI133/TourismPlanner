import re

from bson import ObjectId
from bson.errors import InvalidId
from django.contrib import messages
from django.contrib.auth import authenticate, login, logout
from django.shortcuts import render, redirect
from django.views.decorators.http import require_http_methods

from .decorators import admin_required


@require_http_methods(["GET", "POST"])
def admin_login(request):
    if (
        request.user.is_authenticated
        and request.user.is_staff
        and request.user.is_superuser
    ):
        return redirect("adminpanel:dashboard")

    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(
            request,
            username=username,
            password=password,
        )

        if user is None:
            messages.error(request, "Invalid username or password.")
        elif not user.is_staff or not user.is_superuser:
            messages.error(
                request,
                "You are not authorized to access the Admin Panel.",
            )
        else:
            login(request, user)
            messages.success(request, "Admin login successful.")
            return redirect("adminpanel:dashboard")

    return render(request, "adminpanel/login.html")


@admin_required
def admin_dashboard(request):
    from core.db import get_db

    db = get_db()
    users_collection = db["users"]
    trips_collection = db["trips"]
    saved_collection = db["saved_places"]

    total_users = users_collection.count_documents({})
    active_users = users_collection.count_documents(
        {"account_status": "active"}
    )
    disabled_users = users_collection.count_documents(
        {"account_status": "disabled"}
    )

    total_trips = trips_collection.count_documents({})
    total_saved_places = saved_collection.count_documents({})

    popular_destinations = list(
        trips_collection.aggregate([
            {"$unwind": "$days"},
            {"$unwind": "$days.items"},
            {
                "$group": {
                    "_id": "$days.items.name",
                    "total": {"$sum": 1},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "destination": "$_id",
                    "total": 1,
                }
            },
            {"$sort": {"total": -1}},
            {"$limit": 5},
        ])
    )

    popular_saved_places = list(
        saved_collection.aggregate([
            {
                "$group": {
                    "_id": "$place.name",
                    "total": {"$sum": 1},
                }
            },
            {
                "$project": {
                    "_id": 0,
                    "destination": "$_id",
                    "total": 1,
                }
            },
            {"$sort": {"total": -1}},
            {"$limit": 5},
        ])
    )

    recent_users = list(
        users_collection.find(
            {},
            {"password_hash": 0},
        ).sort("created_at", -1).limit(5)
    )

    context = {
        "total_users": total_users,
        "active_users": active_users,
        "disabled_users": disabled_users,
        "total_trips": total_trips,
        "total_saved_places": total_saved_places,
        "popular_destinations": popular_destinations,
        "popular_saved_places": popular_saved_places,
        "recent_users": recent_users,
    }

    return render(request, "adminpanel/dashboard.html", context)


@admin_required
def user_list(request):
    from core.db import get_db

    users_collection = get_db()["users"]
    search = request.GET.get("search", "").strip()
    status = request.GET.get("status", "").strip()

    filters = {}

    if search:
        filters["$or"] = [
            {"name": {"$regex": re.escape(search), "$options": "i"}},
            {"email": {"$regex": re.escape(search), "$options": "i"}},
        ]

    if status in ("active", "disabled", "pending"):
        filters["account_status"] = status

    users = list(
        users_collection.find(
            filters,
            {"password_hash": 0},
        ).sort("created_at", -1).limit(100)
    )

    # Django templates cannot access MongoDB's underscore-prefixed _id.
    for user in users:
        user["id"] = str(user["_id"])

    return render(
        request,
        "adminpanel/users.html",
        {
            "users": users,
            "search": search,
            "selected_status": status,
        },
    )


@admin_required
def user_detail(request, user_id):
    from core.db import get_db

    db = get_db()

    try:
        object_id = ObjectId(user_id)
    except (InvalidId, TypeError):
        messages.error(request, "Invalid user ID.")
        return redirect("adminpanel:users")

    user = db["users"].find_one(
        {"_id": object_id},
        {"password_hash": 0},
    )

    if not user:
        messages.error(request, "User not found.")
        return redirect("adminpanel:users")

    # The templates and URL reversing use this safe string field.
    user["id"] = str(user["_id"])
    mongo_user_id = user["id"]

    trips = list(
        db["trips"].find(
            {"user_id": mongo_user_id},
            {"title": 1, "status": 1, "start_date": 1, "end_date": 1},
        ).sort("created_at", -1)
    )

    saved_count = db["saved_places"].count_documents(
        {"user_id": mongo_user_id}
    )

    return render(
        request,
        "adminpanel/user_detail.html",
        {
            "user": user,
            "trips": trips,
            "saved_count": saved_count,
        },
    )


@require_http_methods(["POST"])
@admin_required
def toggle_user_status(request, user_id):
    from core.db import get_db

    try:
        object_id = ObjectId(user_id)
    except (InvalidId, TypeError):
        messages.error(request, "Invalid user ID.")
        return redirect("adminpanel:users")

    users_collection = get_db()["users"]
    user = users_collection.find_one({"_id": object_id})

    if not user:
        messages.error(request, "User not found.")
        return redirect("adminpanel:users")

    current_status = user.get("account_status")

    if current_status == "active":
        new_status = "disabled"
    elif current_status == "disabled":
        new_status = "active"
    elif current_status == "pending":
        messages.error(
            request,
            "Pending accounts cannot be activated before verification.",
        )
        return redirect("adminpanel:user_detail", user_id=user_id)
    else:
        messages.error(request, "Invalid account status.")
        return redirect("adminpanel:users")

    users_collection.update_one(
        {"_id": object_id},
        {"$set": {"account_status": new_status}},
    )

    messages.success(request, f"User account {new_status} successfully.")
    return redirect("adminpanel:user_detail", user_id=user_id)


@require_http_methods(["POST"])
@admin_required
def delete_user(request, user_id):
    from core.db import get_db

    try:
        object_id = ObjectId(user_id)
    except (InvalidId, TypeError):
        messages.error(request, "Invalid user ID.")
        return redirect("adminpanel:users")

    db = get_db()
    user = db["users"].find_one({"_id": object_id})

    if not user:
        messages.error(request, "User not found.")
        return redirect("adminpanel:users")

    mongo_user_id = str(object_id)

    # Delete this user's application data before deleting the account.
    db["trips"].delete_many({"user_id": mongo_user_id})
    db["saved_places"].delete_many({"user_id": mongo_user_id})
    db["users"].delete_one({"_id": object_id})

    messages.success(
        request,
        "User and associated trips and saved places deleted successfully.",
    )
    return redirect("adminpanel:users")


@require_http_methods(["POST"])
@admin_required
def admin_logout(request):
    logout(request)
    messages.success(request, "Admin logged out successfully.")
    return redirect("adminpanel:login")
