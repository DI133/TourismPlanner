
from django.urls import path

from apps.accounts import views
from apps.accounts.dashboard_views import dashboard


app_name = "accounts"


urlpatterns = [

    # Registration
    path(
        "register/",
        views.register,
        name="register"
    ),
    path(
        "verify-otp/",
        views.verify_otp_view,
        name="verify_otp"
    ),
    path(
        "resend-otp/",
        views.resend_otp,
        name="resend_otp"
    ),

    # Login
    path(
        "login/",
        views.login_view,
        name="login"
    ),
    path(
        "verify-login-otp/",
        views.verify_login_otp_view,
        name="verify_login_otp"
    ),
    path(
        "resend-login-otp/",
        views.resend_login_otp,
        name="resend_login_otp"
    ),

    # Dashboard and logout
    path(
        "dashboard/",
        dashboard,
        name="dashboard"
    ),
    path(
        "logout/",
        views.logout_view,
        name="logout"
    ),
]
