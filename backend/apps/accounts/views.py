import logging
from collections.abc import Callable
from typing import Any, cast

from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.utils import timezone
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from kombu.exceptions import OperationalError  # type: ignore[import-untyped, unused-ignore]
from rest_framework import status
from rest_framework.exceptions import AuthenticationFailed, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from apps.platform.locking import lock_rows
from apps.tenancy import services as tenancy

from . import emails, humans, oauth
from .models import User
from .serializers import (
    AccountDeleteSerializer,
    AuthConfigSerializer,
    EmailChangeSerializer,
    EmailSerializer,
    LoginSerializer,
    MeSerializer,
    PasswordChangeSerializer,
    PasswordResetConfirmSerializer,
    ProfileSerializer,
    SessionSerializer,
    SignUpSerializer,
    TokenSerializer,
    check_password_strength,
)
from .tokens import read_email_change_token, read_email_token, read_reset_token

logger = logging.getLogger(__name__)

INVALID_LINK = "This link is invalid or has expired."
SET_ONE_FIRST = (
    "Your account has no password yet. Sign out and use Forgot password to set one, then try "
    "again."
)
NOT_CURRENT = "That isn't your current password."
SAME_EMAIL = "That is already your email."
EMAIL_TAKEN = "That email now belongs to another account."
TYPE_YOUR_EMAIL = "Type your email exactly as shown to confirm."


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
        with transaction.atomic():
            # Reading again under the lock makes the second of two racing uses of a link fail:
            # the token hashes the password, so the first use has already spent it.
            lock_rows(User.objects.filter(pk=user.pk))
            user = read_reset_token(data.validated_data["uid"], data.validated_data["token"])
            if user is None:
                raise ValidationError({"token": [INVALID_LINK]})
            # Nobody had proved this address, so a linked provider may be a stranger who claimed
            # it. The owner has now proved it: drop the link, as oauth._claim does.
            if user.email_verified_at is None:
                user.social_accounts.all().delete()
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

    @extend_schema(request=ProfileSerializer, responses=MeSerializer)
    def patch(self, request: Request) -> Response:
        data = ProfileSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = cast(User, request.user)
        user.full_name = data.validated_data["full_name"]
        user.save(update_fields=["full_name"])
        return Response(MeSerializer(user).data)


def _notify_after_commit(send: Callable[..., None], *args: Any) -> None:
    # The change is already saved. A queue failure here must not turn it into an error, or a
    # retry would fail with a wrong password or a used link and confuse the person.
    try:
        send(*args)
    except OperationalError:
        logger.exception("Could not queue an account notice")


def _check_current_password(user: User, password: str) -> None:
    # Someone at an unlocked computer must not be able to take the account over.
    if not user.has_usable_password():
        raise ValidationError({"current_password": [SET_ONE_FIRST]})
    if not user.check_password(password):
        raise ValidationError({"current_password": [NOT_CURRENT]})


class PasswordChangeView(APIView):
    # Tight, because it can be used to guess the current password.
    throttle_scope = "auth"

    @extend_schema(request=PasswordChangeSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        data = PasswordChangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = cast(User, request.user)
        _check_current_password(user, data.validated_data["current_password"])
        password = check_password_strength(data.validated_data["password"], user)
        with transaction.atomic():
            user = lock_rows(User.objects.filter(pk=user.pk))[0]
            user.set_password(password)
            user.save(update_fields=["password"])
        # The new hash signs out every other session; this keeps the one that made the change.
        update_session_auth_hash(request._request, user)
        _notify_after_commit(emails.send_password_changed, user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class EmailChangeView(APIView):
    throttle_scope = "auth"

    @extend_schema(request=EmailChangeSerializer, responses={202: None})
    def post(self, request: Request) -> Response:
        data = EmailChangeSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = cast(User, request.user)
        _check_current_password(user, data.validated_data["current_password"])
        new = data.validated_data["email"].lower()
        if new == user.email:
            raise ValidationError({"email": [SAME_EMAIL]})
        # The same answer either way, so this can't be used to find out who has an account. The
        # owner of a taken address hears about it by email instead.
        if User.objects.filter(email=new).exists():
            emails.send_email_taken(new)
        else:
            emails.send_email_change(user, new)
        return Response(status=status.HTTP_202_ACCEPTED)


class EmailChangeConfirmView(AnonymousFormView):
    """Opened from the link sent to the new address, maybe on a device that isn't signed in."""

    @extend_schema(request=TokenSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        data = TokenSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        found = read_email_change_token(data.validated_data["token"])
        if found is None:
            raise ValidationError({"token": [INVALID_LINK]})
        user, new = found
        try:
            with transaction.atomic():
                lock_rows(User.objects.filter(pk=user.pk))
                # Read again under the lock: a link used twice at once, or racing a password
                # change, fails here, because the account state it was signed for has moved on.
                again = read_email_change_token(data.validated_data["token"])
                if again is None or again[0].pk != user.pk:
                    raise ValidationError({"token": [INVALID_LINK]})
                user = again[0]
                old = user.email
                user.email = new
                user.email_verified_at = timezone.now()
                user.save(update_fields=["email", "email_verified_at"])
        except IntegrityError as exc:
            raise ValidationError({"token": [EMAIL_TAKEN]}) from exc
        _notify_after_commit(emails.send_email_changed, old, new)
        return Response(status=status.HTTP_204_NO_CONTENT)


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
                "demo": (
                    {"email": settings.DEMO_EMAIL, "password": settings.DEMO_PASSWORD}
                    if settings.DEMO_MODE and settings.DEMO_PASSWORD
                    else None
                ),
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


class AccountDeleteView(APIView):
    throttle_scope = "auth"

    @extend_schema(request=AccountDeleteSerializer, responses={204: None})
    def post(self, request: Request) -> Response:
        data = AccountDeleteSerializer(data=request.data)
        data.is_valid(raise_exception=True)
        user = cast(User, request.user)
        _check_current_password(user, data.validated_data["current_password"])
        if data.validated_data["email"].strip().lower() != user.email:
            raise ValidationError({"email": [TYPE_YOUR_EMAIL]})
        old = user.email
        try:
            tenancy.delete_account(user)
        except tenancy.OwnsBusinessError as exc:
            names = ", ".join(exc.names)
            raise ValidationError(
                {
                    "detail": f"You own {names}. Hand each one to another member first, on its "
                    "Members screen."
                }
            ) from exc
        logout(request._request)
        _notify_after_commit(emails.send_account_deleted, old)
        return Response(status=status.HTTP_204_NO_CONTENT)
