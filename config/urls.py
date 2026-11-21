from django.contrib import admin
from django.urls import path, include
from django.views.generic import RedirectView

urlpatterns = [

    path(
        "admin-panel/",
        include("apps.adminpanel.urls")
    ),

    path(
      "",
        RedirectView.as_view(
            pattern_name="accounts:login",
            permanent=False
        ),
        name="home"
    ),
    path("admin/", admin.site.urls),
    path("accounts/", include("apps.accounts.urls")),
    path("places/", include("apps.places.urls")),
    path("trips/", include("apps.trips.urls")),
]