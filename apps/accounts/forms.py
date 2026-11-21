"""
Registration form for MongoDB-backed users.

This is a Django Form, not a ModelForm: there is no SQL User model.
"""

from __future__ import annotations

from types import SimpleNamespace

from django import forms
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError

from apps.accounts.services.user_service import (
    UserValidationError,
    get_user_by_email,
    get_user_by_mobile,
    normalize_email,
    normalize_mobile,
)

_INPUT_ATTRS = {"class": "field-input", "autocomplete": "on"}


class RegistrationForm(forms.Form):
    name = forms.CharField(
        label="Full name",
        max_length=120,
        widget=forms.TextInput(
            attrs={
                **_INPUT_ATTRS,
                "autocomplete": "name",
                "placeholder": "Your full name",
            }
        ),
    )
    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(
            attrs={
                **_INPUT_ATTRS,
                "autocomplete": "email",
                "placeholder": "you@example.com",
            }
        ),
    )
    mobile_number = forms.CharField(
        label="Mobile number",
        max_length=20,
        help_text="Indian numbers can be entered as 10 digits. Include + and the country code for other countries.",
        widget=forms.TextInput(
            attrs={
                **_INPUT_ATTRS,
                "autocomplete": "tel",
                "inputmode": "tel",
                "placeholder": "9876543210",
            }
        ),
    )
    password = forms.CharField(
        label="Password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "field-input",
                "autocomplete": "new-password",
                "placeholder": "At least 8 characters",
            }
        ),
    )
    confirm_password = forms.CharField(
        label="Confirm password",
        strip=False,
        widget=forms.PasswordInput(
            attrs={
                "class": "field-input",
                "autocomplete": "new-password",
                "placeholder": "Re-enter your password",
            }
        ),
    )

    def clean_name(self) -> str:
        name = (self.cleaned_data.get("name") or "").strip()
        if not name:
            raise ValidationError("Enter your full name.")
        return name

    def clean_email(self) -> str:
        raw = self.cleaned_data.get("email") or ""
        try:
            email = normalize_email(raw)
        except UserValidationError as exc:
            raise ValidationError("Enter a valid email address.") from exc
        if get_user_by_email(email):
            raise ValidationError("An account with this email already exists.")
        return email

    def clean_mobile_number(self) -> str:
        raw = self.cleaned_data.get("mobile_number") or ""
        try:
            mobile = normalize_mobile(raw)
        except UserValidationError as exc:
            raise ValidationError("Enter a valid mobile number.") from exc
        if not mobile:
            raise ValidationError("Enter your mobile number.")
        if get_user_by_mobile(mobile):
            raise ValidationError("An account with this mobile number already exists.")
        return mobile

    def clean_password(self) -> str:
        password = self.cleaned_data.get("password") or ""
        if len(password) < 8:
            raise ValidationError("Password must be at least 8 characters.")
        user_for_validators = SimpleNamespace(
            email=self.data.get("email", ""),
            username=self.data.get("email", ""),
            get_username=lambda: self.data.get("email", ""),
        )
        try:
            validate_password(password, user=user_for_validators)
        except ValidationError:
            raise
        return password

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password")
        confirm = cleaned.get("confirm_password")
        if password and confirm and password != confirm:
            self.add_error("confirm_password", "Passwords do not match.")
        return cleaned




class OTPVerificationForm(forms.Form):
    otp = forms.RegexField(
        regex=r"^\d{6}$",
        label="Verification code",
        error_messages={
            "invalid": "Enter a valid six-digit OTP.",
        },
        widget=forms.TextInput(
            attrs={
                "class": "field-input",
                "autocomplete": "one-time-code",
                "inputmode": "numeric",
                "maxlength": "6",
                "placeholder": "Enter 6-digit OTP",
            }
        ),
    )



class LoginForm(forms.Form):
    email = forms.EmailField(
        label="Email address",
        widget=forms.EmailInput(attrs={
            "class": "field-input",
            "placeholder": "Enter your email",
            "autocomplete": "email",
        }),
    )

    password = forms.CharField(
        label="Password",
        widget=forms.PasswordInput(attrs={
            "class": "field-input",
            "placeholder": "Enter your password",
            "autocomplete": "current-password",
        }),
    )

    def clean_email(self):
        email = self.cleaned_data["email"]
        return email.strip().lower()



