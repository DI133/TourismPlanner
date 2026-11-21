from functools import wraps
from django.shortcuts import redirect
from django.core.exceptions import PermissionDenied


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        if not request.user.is_authenticated:
            return redirect("adminpanel:login")

        if not request.user.is_staff or not request.user.is_superuser:
            raise PermissionDenied(
                "You are not authorized to access this page."
            )

        return view_func(request, *args, **kwargs)

    return wrapper