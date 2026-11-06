import logging
from typing import cast

from django.conf import settings
from django.contrib.auth import authenticate, login, logout
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from kombu.exceptions import OperationalError  # type: ignore[import-untyped]
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from . import emails, humans, oauth
from .models import User
from .serializers import (
    AuthConfigSerializer,
    EmailSerializer,
    LoginSerializer,
    MeSerializer,
    PasswordResetConfirmSerializer,
    SessionSerializer,
    SignUpSerializer,
    TokenSerializer,
    check_password_strength,
)
from .tokens import read_email_token, read_reset_token

logger = logging.getLogger(__name__)

INVALID_LINK = "This link is invalid or has expired."


@method_decorator(ensure_csrf_cookie, name="get")
class CsrfView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(responses={204: None})
    def get(self, request: Request) -> Response:
        return Response(status=status.HTTP_204_NO_CONTENT)


# DRF exempts APIViews from CSRF and only checks it for signed-in users, which would leave the
# anonymous forms below open to cross-site posts (login CSRF, sign-up spam). Check it here.
@method_decorator(csrf_protect, name="dispatch")
class AnonymousFormView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"
    # The reCAPTCHA v3 action the form's token must carry.
    captcha_action = ""

    def is_bot(self, request: Request, data: dict[str, object]) -> bool:
        """Honeypot first (bots get a normal-looking answer), then reCAPTCHA if configured."""
        if humans.is_bot(data):
            return True
        humans.check(data, self.captcha_action, AnonRateThrottle().get_ident(request))
        return False


class LoginView(AnonymousFormView):
    captcha_action = "login"

    @extend_schema(request=LoginSerializer, responses=MeSerializer)
    def post(self, request: Request) -> Response:
        data = LoginSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if self.is_bot(request, data.validated_data):
            raise AuthenticationFailed("Email or password is incorrect.")
        user = authenticate(
            request._request,
            username=data.validated_data["email"].lower(),
            password=data.validated_data["password"],
        )
        # Same message whether the email exists or not, so the form can't be used to find
        # out who has an account.
        if user is None:
            raise AuthenticationFailed("Email or password is incorrect.")
        login(request._request, user)
        return Response(MeSerializer(user).data)


class SignUpView(AnonymousFormView):
    captcha_action = "signup"

    @extend_schema(request=SignUpSerializer, responses={202: None})
    def post(self, request: Request) -> Response:
        data = SignUpSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if self.is_bot(request, data.validated_data):
            return Response(status=status.HTTP_202_ACCEPTED)
        email = data.validated_data["email"]
        # New and existing addresses get the same answer; the owner of an existing one gets an
        # email instead, so sign-up can't be used to find out who has an account.
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    email,
                    data.validated_data["password"],
                    full_name=data.validated_data.get("full_name", ""),
                )
        except IntegrityError:
            emails.send_already_registered(email)
        else:
            emails.send_verification(user)
        return Response(status=status.HTTP_202_ACCEPTED)


class VerifyEmailView(AnonymousFormView):
    @extend_schema(request=TokenSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        data = TokenSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = read_email_token(data.validated_data["token"])
        if user is None:
            raise ValidationError({"token": [INVALID_LINK]})
        if user.email_verified_at is None:
            user.email_verified_at = timezone.now()
            user.save(update_fields=["email_verified_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResendVerificationView(APIView):
    throttle_scope = "auth"

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        user = cast(User, request.user)
        if user.email_verified_at is None:
            emails.send_verification(user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetView(AnonymousFormView):
    captcha_action = "password_reset"

    @extend_schema(request=EmailSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        data = EmailSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        if self.is_bot(request, data.validated_data):
            return Response(status=status.HTTP_204_NO_CONTENT)
        email = data.validated_data["email"].lower()
        user = User.objects.filter(email=email, is_active=True).first()
        if user is not None:
            # A failed send must look like an unknown address, or this form would tell a stranger
            # which emails have accounts whenever the queue is down.
            try:
                emails.send_password_reset(user)
            except OperationalError:
                logger.exception("Could not queue a password reset email")
        return Response(status=status.HTTP_204_NO_CONTENT)


class PasswordResetConfirmView(AnonymousFormView):
    @extend_schema(request=PasswordResetConfirmSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        data = PasswordResetConfirmSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = read_reset_token(data.validated_data["uid"], data.validated_data["token"])
        if user is None:
            raise ValidationError({"token": [INVALID_LINK]})
        password = check_password_strength(data.validated_data["password"], user)
        # A new password changes the session hash, which signs out every other session.
        user.set_password(password)
        # Opening the emailed link proves the address, so it also counts as verification.
        user.email_verified_at = user.email_verified_at or timezone.now()
        user.save(update_fields=["password", "email_verified_at"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class LogoutView(APIView):
    throttle_scope = "session"

    @extend_schema(request=None, responses={204: None})
    def post(self, request: Request) -> Response:
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    throttle_scope = "session"

    @extend_schema(responses=MeSerializer)
    def get(self, request: Request) -> Response:
        return Response(MeSerializer(cast(User, request.user)).data)


class SessionView(APIView):
    """Who is signed in, if anyone.

    The app asks this on every sign-in screen, where nobody being signed in is the normal case,
    so that is a 200 with a null user. /me/ answering 403 there filled the console with errors.
    """

    permission_classes = [AllowAny]
    throttle_scope = "session"

    @extend_schema(responses=SessionSerializer)
    def get(self, request: Request) -> Response:
        user = request.user if request.user.is_authenticated else None
        return Response({"user": MeSerializer(user).data if user else None})


class AuthConfigView(APIView):
    """Public keys the sign-in screens need. Site keys are public by design; secrets stay here."""

    permission_classes = [AllowAny]
    throttle_scope = "session"

    @extend_schema(responses=AuthConfigSerializer)
    def get(self, request: Request) -> Response:
        return Response(
            {
                "recaptcha_v3_site_key": settings.RECAPTCHA_V3_SITE_KEY,
                "recaptcha_v2_site_key": settings.RECAPTCHA_V2_SITE_KEY,
                "oauth_providers": oauth.enabled_providers(),
            }
        )


def _back_to_sign_in(code: str) -> HttpResponseRedirect:
    return HttpResponseRedirect(f"{settings.SITE_URL.rstrip('/')}/login?error={code}")


class OAuthStartView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(responses={302: None})
    def get(self, request: Request, provider: str) -> HttpResponseRedirect:
        try:
            chosen = oauth.get_provider(provider)
        except oauth.OAuthError as exc:
            return _back_to_sign_in(exc.code)
        url = oauth.start(request.session, chosen, request.query_params.get("next"))
        return HttpResponseRedirect(url)


class OAuthCallbackView(APIView):
    permission_classes = [AllowAny]
    throttle_scope = "auth"

    @extend_schema(responses={302: None})
    def get(self, request: Request, provider: str) -> HttpResponseRedirect:
        params = {
            key: str(request.query_params.get(key, ""))[:2000]
            for key in ("state", "code", "error")
        }
        try:
            user, next_path = oauth.finish(request.session, provider, params)
        except oauth.OAuthError as exc:
            return _back_to_sign_in(exc.code)
        login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
        return HttpResponseRedirect(f"{settings.SITE_URL.rstrip('/')}{next_path}")
