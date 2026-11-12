from typing import Any

from django.contrib.auth import password_validation
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from .humans import HumanFields
from .models import User


def check_password_strength(password: str, user: User | None) -> str:
    try:
        password_validation.validate_password(password, user)
    except DjangoValidationError as exc:
        raise serializers.ValidationError({"password": list(exc.messages)}) from exc
    return password


class LoginSerializer(HumanFields):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class MeSerializer(serializers.ModelSerializer[User]):
    id = serializers.UUIDField(source="public_id", read_only=True)
    email_verified = serializers.SerializerMethodField()
    has_password = serializers.SerializerMethodField()

    class Meta:
        model = User
        fields = ("id", "email", "full_name", "email_verified", "has_password")
        read_only_fields = fields

    def get_email_verified(self, user: User) -> bool:
        return user.email_verified_at is not None

    def get_has_password(self, user: User) -> bool:
        """False for people who only ever signed in with Google or Facebook."""
        return user.has_usable_password()


class ProfileSerializer(serializers.Serializer[None]):
    full_name = serializers.CharField(max_length=150, allow_blank=True, trim_whitespace=True)


class PasswordChangeSerializer(serializers.Serializer[None]):
    current_password = serializers.CharField(
        max_length=128, trim_whitespace=False, allow_blank=True
    )
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class EmailChangeSerializer(serializers.Serializer[None]):
    email = serializers.EmailField(max_length=254)
    current_password = serializers.CharField(
        max_length=128, trim_whitespace=False, allow_blank=True
    )


class SessionSerializer(serializers.Serializer[None]):
    user = MeSerializer(allow_null=True)


class SignUpSerializer(HumanFields):
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(max_length=128, trim_whitespace=False)
    full_name = serializers.CharField(max_length=150, allow_blank=True, required=False)

    def validate(self, attrs: dict[str, Any]) -> dict[str, Any]:
        attrs["email"] = attrs["email"].lower()
        probe = User(email=attrs["email"], full_name=attrs.get("full_name", ""))
        check_password_strength(attrs["password"], probe)
        return attrs


class TokenSerializer(serializers.Serializer[None]):
    token = serializers.CharField(max_length=512)


class EmailSerializer(HumanFields):
    email = serializers.EmailField(max_length=254)


class PasswordResetConfirmSerializer(serializers.Serializer[None]):
    uid = serializers.CharField(max_length=64)
    token = serializers.CharField(max_length=128)
    password = serializers.CharField(max_length=128, trim_whitespace=False)


class DemoAccountSerializer(serializers.Serializer[None]):
    email = serializers.EmailField()
    password = serializers.CharField()


class AuthConfigSerializer(serializers.Serializer[None]):
    recaptcha_v3_site_key = serializers.CharField(allow_blank=True)
    recaptcha_v2_site_key = serializers.CharField(allow_blank=True)
    oauth_providers = serializers.ListField(child=serializers.CharField())
    # The shared demo login, shown on the sign-in page. Only set on a demo server.
    demo = DemoAccountSerializer(allow_null=True)


class AccountDeleteSerializer(serializers.Serializer[None]):
    current_password = serializers.CharField(
        max_length=128, trim_whitespace=False, allow_blank=True
    )
    # Typing the address is the deliberate step: it can't be done by a stray click.
    email = serializers.CharField(max_length=254)
