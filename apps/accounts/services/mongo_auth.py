
from django.contrib.auth.models import AnonymousUser

from apps.accounts.services.user_service import get_user_by_id


class MongoAuthenticatedUser:
    """
    Lightweight authenticated-user object backed by MongoDB.
    """

    def __init__(self, user_data):
        self.pk = str(user_data["_id"])
        self.id = self.pk
        self.name = user_data.get("name", "")
        self.email = user_data.get("email", "")
        self.mobile_number = user_data.get("mobile_number", "")

        self.is_active = user_data.get("account_status") == "active"
        self.is_staff = False
        self.is_superuser = False

    @property
    def is_authenticated(self):
        return True

    @property
    def is_anonymous(self):
        return False

    def get_username(self):
        return self.email

    def __str__(self):
        return self.email


class MongoSessionAuthenticationMiddleware:
    """
    Loads MongoDB users from the tourism_user_id session.
    Authentication is based on email verification.
    """

    SESSION_KEY = "tourism_user_id"

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):

        # Never overwrite an authenticated Django user.
        if request.user.is_authenticated:
            return self.get_response(request)

        user_id = request.session.get(self.SESSION_KEY)

        if user_id:
            user_data = get_user_by_id(user_id)

            if (
                user_data
                and user_data.get("account_status") == "active"
                and user_data.get("email_verified") is True
            ):
                request.user = MongoAuthenticatedUser(user_data)

            else:
                request.session.pop(self.SESSION_KEY, None)
                request.session.modified = True
                request.user = AnonymousUser()

        return self.get_response(request)
