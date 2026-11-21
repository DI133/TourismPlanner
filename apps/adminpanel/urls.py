
from django.urls import path
from . import views

app_name = "adminpanel"

urlpatterns = [
    path("", views.admin_dashboard, name="dashboard"),
    path("login/", views.admin_login, name="login"),
    path("logout/", views.admin_logout, name="logout"),
    path("users/", views.user_list, name="users"),
    path("users/<str:user_id>/", views.user_detail, name="user_detail"),
    path("users/<str:user_id>/toggle/", views.toggle_user_status, name="toggle_user_status"),
    path("users/<str:user_id>/delete/", views.delete_user, name="delete_user"),
]
