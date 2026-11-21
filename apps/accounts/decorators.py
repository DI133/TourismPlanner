

import logging
from functools import wraps

from django.shortcuts import redirect
from django.contrib import messages

logger = logging.getLogger(__name__)


def tourism_login_required(view_func):

    @wraps(view_func)
    def wrapper(request, *args, **kwargs):

        user_id = request.session.get("tourism_user_id")

        if not user_id:
            logger.warning(
                "Dashboard authentication failed. Session keys: %s",
                list(request.session.keys())
            )

            messages.info(
                request,
                "Please log in to access this page."
            )

            return redirect("accounts:login")

        return view_func(request, *args, **kwargs)

    return wrapper