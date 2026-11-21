
import logging

from django.shortcuts import render, redirect
from django.contrib import messages

from apps.accounts.decorators import tourism_login_required
from apps.accounts.services.user_service import get_user_by_id
from apps.trips.services import get_user_trips

logger = logging.getLogger(__name__)


@tourism_login_required
def dashboard(request):

    user_id = request.session.get("tourism_user_id")

    # The decorator should already check this, but keep a safety check.
    if not user_id:
        logger.warning("Dashboard access failed: tourism_user_id missing.")
        messages.info(request, "Please log in to access your dashboard.")
        return redirect("accounts:login")

    # Fetch the actual MongoDB user.
    try:
        user = get_user_by_id(user_id)

        if not user:
            logger.error("Dashboard access failed: user not found. ID: %s", user_id)
            request.session.flush()
            messages.error(request, "Your account could not be found. Please log in again.")
            return redirect("accounts:login")

    except Exception:
        logger.exception("Error fetching dashboard user. ID: %s", user_id)
        messages.error(request, "Unable to load your account. Please try again.")
        return redirect("accounts:login")

    # Fetch trips separately so a trips error does not look like an
    # authentication failure.
    try:
        trips = get_user_trips(user_id) or []

        for trip in trips:
            if trip.get("_id") is not None:
                trip["id"] = str(trip["_id"])

    except Exception:
        logger.exception("Error fetching trips for user ID: %s", user_id)
        trips = []
        messages.warning(request, "Your dashboard loaded, but your trips could not be retrieved.")

    total_trips = len(trips)
    destinations_planned = 0
    places_visited = 0

    for trip in trips:
        for day in trip.get("days", []):
            items = day.get("items", [])

            destinations_planned += len(items)

            places_visited += sum(
                1 for place in items
                if place.get("visited", False)
            )

    context = {
        "user": user,
        "total_trips": total_trips,
        "destinations_planned": destinations_planned,
        "places_visited": places_visited,
        "recent_trips": trips[:3],
    }

    return render(request, "accounts/dashboard.html", context)