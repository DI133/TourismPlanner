
from django.urls import path
from apps.trips import views

app_name = "trips"

urlpatterns = [
    path("api/create/", views.create_trip_api, name="create_trip"),
    path("api/list/", views.list_trips_api, name="list_trips"),
    path("api/add-place/", views.add_place_api, name="add_place"),
    path("api/remove-place/", views.remove_place_api, name="api_remove_place"),
    path("api/update/", views.update_trip_api, name="update_trip"),
    path("api/reorder-place/", views.reorder_place_api, name="reorder_place"),
    path("api/delete/", views.delete_trip_api, name="delete_trip"),
    path("api/update-visited/", views.update_place_visited_api, name="update_visited"),

    path(
        "api/update-day-completion/",
        views.update_day_completion_api,
        name="update_day_completion"
    ),
    path(
        "api/optimize-day/",
        views.optimize_day_route_api,
        name="optimize_day_route"
    ),
    path(
        "api/accept-optimized-route/",
        views.accept_optimized_route_api,
        name="accept_optimized_route"
    ),

    # Expense Tracker APIs
    path("api/update-budget/", views.update_trip_budget_api, name="update_trip_budget"),
    path("api/add-expense/", views.add_expense_api, name="add_expense"),
    path("api/expense-summary/", views.expense_summary_api, name="expense_summary"),
    path("api/update-expense/", views.update_expense_api, name="update_expense"),
    path("api/delete-expense/", views.delete_expense_api, name="delete_expense"),

    # Nearby Places Page — before dynamic trip_id route
    path(
        "nearby-places/",
        views.nearby_places_page,
        name="nearby_places_page"
    ),

    path("", views.trips_page, name="list"),

    # Weather API
    path("api/weather/", views.trip_weather_api, name="trip_weather"),

    # Nearby Places API
    path("api/nearby-places/", views.nearby_places_api, name="nearby_places"),

    path(
        "<str:trip_id>/download-pdf/",
        views.download_trip_pdf,
        name="download_trip_pdf"
    ),

    # Dynamic Trip Detail — keep last
    path("<str:trip_id>/", views.trip_detail_page, name="detail"),

]
