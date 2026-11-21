
import logging

from django.conf import settings
from django.contrib import messages
from django.shortcuts import render, redirect
from apps.accounts.services.email_service import send_otp_email
from django.views.decorators.http import require_http_methods

from apps.accounts.forms import (
    RegistrationForm,
    OTPVerificationForm,
    LoginForm,
)

from apps.accounts.services.user_service import (
    DuplicateUserError,
    create_user,
    get_user_by_email,
)

from apps.accounts.services.auth_service import (
    authenticate_user,
    InvalidCredentialsError,
    AccountNotActiveError,
    AccountDisabledError,
    EmailNotVerifiedError,
)

from apps.accounts.services.otp_service import (
    OTPError,
    OTPAccountError,
    OTPAttemptsExceededError,
    OTPExpiredError,
    OTPInvalidError,
    OTPResendCooldownError,
    create_otp_challenge,
    verify_otp,
    create_login_otp_challenge,
    verify_login_otp,
    invalidate_otp_challenge,
)


logger = logging.getLogger(__name__)

PENDING_VERIFICATION_SESSION_KEY = "pending_verification_user_id"
PENDING_LOGIN_SESSION_KEY = "pending_login_user_id"
TOURISM_USER_SESSION_KEY = "tourism_user_id"


@require_http_methods(["GET", "POST"])
def register(request):

    print("\n========== REGISTER VIEW REACHED ==========")
    print("REQUEST METHOD:", request.method)
    print("SESSION BEFORE:", dict(request.session))

    form = RegistrationForm(request.POST or None)

    if request.method == "POST":
        print("POST REQUEST RECEIVED")
        print("FORM VALID:", form.is_valid())
        print("FORM ERRORS:", form.errors.as_json())

    if request.method == "POST" and form.is_valid():
        print("REGISTRATION FORM VALIDATED")

     
    form = RegistrationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            # 1. Create the MongoDB user
            created_user = create_user(
                name=form.cleaned_data["name"],
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
                mobile_number=form.cleaned_data["mobile_number"],
            )

            user = created_user or get_user_by_email(
                form.cleaned_data["email"]
            )

            if not user or not user.get("_id"):
                raise OTPAccountError(
                    "Account was created, but verification could not be started."
                )

            # 2. Store the pending verification user ID in session
            request.session[PENDING_VERIFICATION_SESSION_KEY] = str(
                user["_id"]
            )
            request.session.modified = True

            # 3. Generate OTP and send verification email
            challenge = None

            try:
                challenge = create_otp_challenge(user["_id"])

                send_otp_email(
                    email=challenge["email"],
                    otp=challenge["otp"],
                    purpose="verification",
                )

            except Exception:
                logger.exception(
                    "Registration OTP generation or email delivery failed."
                )

                # Invalidate only when OTP creation succeeded
                # but the email operation failed.
                if challenge is not None:
                    invalidate_otp_challenge(
                        user["_id"],
                        "email_verification",
                    )

                messages.error(
                    request,
                    "Your account was created, but the verification email "
                    "could not be sent. Please try again later.",
                )

                return redirect("accounts:verify_otp")

            # 4. Email sent successfully
            messages.success(
                request,
                "Your account was created. Please check your email for the OTP.",
            )

            logger.info(
                "Registration OTP sent. Redirecting to verification page."
            )

            # 5. Redirect to OTP verification
            return redirect("accounts:verify_otp")

        except DuplicateUserError as exc:
            form.add_error(exc.field, str(exc))

        except OTPError:
            logger.exception(
                "Could not start registration verification."
            )

            form.add_error(
                None,
                "Your account was created, but verification could not be "
                "started. Please contact support.",
            )

        except Exception:
            logger.exception("Unexpected registration error.")

            form.add_error(
                None,
                "Registration could not be completed. Please try again.",
            )

    # Render the registration page, not the OTP page,
    # when the form is invalid or registration fails.
    return render(
        request,
        "accounts/register.html",
        {"form": form},
    )


# ---------------------------------------------------------
# Registration OTP verification
# ---------------------------------------------------------


@require_http_methods(["GET", "POST"])
def verify_otp_view(request):

    user_id = request.session.get(
        PENDING_VERIFICATION_SESSION_KEY
    )

    logger.info(
        "OTP verification page accessed. Session key: %s, pending user exists: %s",
        request.session.session_key,
        bool(user_id),
    )

    if not user_id:
        messages.info(
            request,
            "Please register first to verify your email address.",
        )
        return redirect("accounts:register")

    form = OTPVerificationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():
        try:
            verify_otp(
                user_id=user_id,
                submitted_otp=form.cleaned_data["otp"],
            )

            # Prevent session fixation.
            request.session.cycle_key()

            # Establish MongoDB-backed authenticated session.
            request.session["tourism_user_id"] = str(user_id)

            # Clear pending verification sessions.
            request.session.pop("pending_verification_user_id", None)
            request.session.pop("pending_login_user_id", None)

            # Ensure session changes are saved.
            request.session.modified = True

            messages.success(
                request,
                "Verification successful. Welcome to TourismPlanner!"
            )

            return redirect("accounts:dashboard")

        except (
            OTPInvalidError,
            OTPExpiredError,
            OTPAttemptsExceededError,
            OTPAccountError,
        ) as exc:
            form.add_error(None, str(exc))

        except OTPError:
            logger.exception("OTP verification failed.")

            form.add_error(
                None,
                "Something went wrong. Please try again.",
            )

    return render(
        request,
        "accounts/verify_otp.html",
        {
            "form": form,
            "verified": False,
        },
    )


# ---------------------------------------------------------
# Resend registration OTP
# ---------------------------------------------------------

@require_http_methods(["POST"])
def resend_otp(request):

    user_id = request.session.get(
        PENDING_VERIFICATION_SESSION_KEY
    )

    if not user_id:
        messages.error(
            request,
            "Your verification session has expired. Please register again.",
        )
        return redirect("accounts:register")

    challenge = None

    try:
        challenge = create_otp_challenge(user_id)

        send_otp_email(
            email=challenge["email"],
            otp=challenge["otp"],
            purpose="verification",
        )

        messages.success(
            request,
            "A new verification OTP has been sent to your email address."
        )

    except OTPResendCooldownError as exc:
        messages.error(request, str(exc))

    except Exception:
        logger.exception("Registration OTP resend or email delivery failed.")

        if challenge is not None:
            invalidate_otp_challenge(
                user_id,
                "email_verification",
            )

        messages.error(
            request,
            "Unable to send the verification email. Please try again later."
        )
    
    return redirect("accounts:verify_otp")


# ---------------------------------------------------------
# Login
# ---------------------------------------------------------

@require_http_methods(["GET", "POST"])
def login_view(request):

    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    form = LoginForm(request.POST or None)
    challenge = None

    if request.method == "POST" and form.is_valid():

        try:
            user = authenticate_user(
                email=form.cleaned_data["email"],
                password=form.cleaned_data["password"],
            )

            challenge = create_login_otp_challenge(user["_id"])

            request.session[PENDING_LOGIN_SESSION_KEY] = str(
                user["_id"]
            )

            send_otp_email(
                email=challenge["email"],
                otp=challenge["otp"],
                purpose="login",
            )

            messages.success(
                request,
                "Login OTP sent to your registered email address."
            )

            return redirect("accounts:verify_login_otp")

        except InvalidCredentialsError as exc:
            form.add_error(None, str(exc))

        except EmailNotVerifiedError:
            try:
                user = get_user_by_email(form.cleaned_data["email"])

                if not user or not user.get("_id"):
                    raise OTPAccountError("Account not found.")

                request.session[PENDING_VERIFICATION_SESSION_KEY] = str(
                    user["_id"]
                )
                challenge = None
                challenge = create_otp_challenge(user["_id"])

                send_otp_email(
                    email=challenge["email"],
                    otp=challenge["otp"],
                    purpose="verification",
                )

                messages.info(
                    request,
                    "Your email is not verified. We have sent you a verification OTP."
                )

                return redirect("accounts:verify_otp")

            except OTPResendCooldownError as exc:
                messages.info(request, str(exc))
                return redirect("accounts:verify_otp")

            except Exception:
                logger.exception("Unable to start existing account email verification.")
                if challenge is not None:
                    invalidate_otp_challenge(
                        user["_id"],
                       "email_verification",
                    )
                form.add_error(
                    None,
                    "Unable to send verification email. Please try again later.",
                )

        except (
            AccountNotActiveError,
            AccountDisabledError,
        ) as exc:
            form.add_error(None, str(exc))

        except OTPResendCooldownError as exc:
            form.add_error(None, str(exc))

        except Exception:
            logger.exception(
                "Login OTP generation or email delivery failed."
            )
            if challenge is not None:
                invalidate_otp_challenge(
                    user["_id"],
                    "login",
                )
            form.add_error(
                None,
                "Unable to send the login verification email. Please try again later.",
            )

    return render(
        request,
        "accounts/login.html",
        {"form": form},
    )


# ---------------------------------------------------------
# Login OTP verification
# ---------------------------------------------------------

@require_http_methods(["GET", "POST"])
def verify_login_otp_view(request):

    user_id = request.session.get(
        PENDING_LOGIN_SESSION_KEY
    )

    if not user_id:
        messages.error(
            request,
            "Please log in first.",
        )
        return redirect("accounts:login")

    if request.user.is_authenticated:
        return redirect("accounts:dashboard")

    form = OTPVerificationForm(request.POST or None)

    if request.method == "POST" and form.is_valid():

        try:
            verify_login_otp(
                user_id=user_id,
                submitted_otp=form.cleaned_data["otp"],
            )

            # Prevent session fixation.
            request.session.cycle_key()

            # Establish MongoDB-backed authenticated session.
            request.session["tourism_user_id"] = str(user_id)

            # Clear pending verification sessions.
            request.session.pop("pending_verification_user_id", None)
            request.session.pop("pending_login_user_id", None)

            # Ensure session changes are saved. 
            request.session.modified = True
            print("DEBUG AFTER OTP:", dict(request.session))
            print("DEBUG SESSION KEY:", request.session.session_key)

            messages.success(
                request,
                "Verification successful. Welcome to TourismPlanner!"
            )
            print("DEBUG REDIRECT SESSION:", dict(request.session))
            return redirect("accounts:dashboard")

        except (
            OTPInvalidError,
            OTPExpiredError,
            OTPAttemptsExceededError,
            OTPAccountError,
        ) as exc:
            form.add_error(None, str(exc))

        except OTPError:
            logger.exception("Login OTP verification failed.")

            form.add_error(
                None,
                "Unable to verify OTP. Please try again.",
            )

    return render(
        request,
        "accounts/verify_login_otp.html",
        {"form": form},
    )


# ---------------------------------------------------------
# Resend login OTP
# ---------------------------------------------------------

@require_http_methods(["POST"])
def resend_login_otp(request):

    user_id = request.session.get(
        PENDING_LOGIN_SESSION_KEY
    )

    if not user_id:
        messages.error(
            request,
            "Please log in first.",
        )
        return redirect("accounts:login")
    challenge = None

    try:
        challenge = create_login_otp_challenge(user_id)

        send_otp_email(
            email=challenge["email"],
            otp=challenge["otp"],
            purpose="login",
        )

        messages.success(
            request,
            "A new login OTP has been sent to your registered email address."
        )

    except OTPResendCooldownError as exc:
        messages.error(request, str(exc))

    except Exception:
        logger.exception(
            "Login OTP resend or email delivery failed."
        )
        if challenge is not None:
            invalidate_otp_challenge(
                user_id,
                "login",
            )
        messages.error(
            request,
            "Unable to send the login verification email. Please try again later.",
        )

    return redirect("accounts:verify_login_otp")


# ---------------------------------------------------------
# Logout
# ---------------------------------------------------------

@require_http_methods(["POST"])
def logout_view(request):

    request.session.flush()

    messages.success(
        request,
        "You have been logged out successfully.",
    )

    return redirect("accounts:login")
