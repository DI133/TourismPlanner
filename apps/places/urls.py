

from django.urls import path
from apps.places import views

app_name = "places"

urlpatterns = [
    path("", views.explore_page, name="explore"),
    path("api/explore/", views.explore_places, name="explore_places"),
  
    path("api/place-image/", views.place_image, name="place_image"),
    path("api/weather/", views.explore_weather_api, name="explore_weather"),

    path(
        "api/nearby-attractions/",
        views.nearby_attractions_api,
        name="nearby_attractions"
    ),

    path("api/save-place/", views.save_place_api, name="save_place"),
    path("api/saved-places/", views.saved_places_api, name="saved_places"),
    path("api/remove-saved-place/", views.remove_saved_place_api, name="remove_saved_place"),
    path("saved/", views.saved_places_page, name="saved_places_page"),

    path(
        "api/explore/suggestions/",
        views.explore_place_suggestions,
        name="explore_place_suggestions",
    ),
]
