
import logging

from django.conf import settings
from django.core.mail import send_mail

logger = logging.getLogger(__name__)


def send_otp_email(email, otp, purpose="verification"):
    if purpose == "login":
        subject = "TourismPlanner - Login Verification"
        message = "Use this OTP to complete your login."
    else:
        subject = "TourismPlanner - Email Verification"
        message = "Use this OTP to verify your email address."

    email_message = f"""
Hello,

{message}

Your OTP is: {otp}

This OTP is valid for 5 minutes.

Please do not share this OTP with anyone.

Regards,
TourismPlanner Team
"""

    try:
        result = send_mail(
            subject=subject,
            message=email_message,
            from_email=settings.DEFAULT_FROM_EMAIL,
            recipient_list=[email],
            fail_silently=False,
        )

        if result != 1:
            raise RuntimeError("OTP email could not be sent.")

        return True

    except Exception:
        logger.exception("Failed to send OTP email.")
        raise
