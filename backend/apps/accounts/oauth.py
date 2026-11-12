"""Sign in with Google or Facebook using the OAuth 2.0 authorization code flow.

The browser is sent to the provider with a random `state` (and a PKCE challenge for Google)
kept in the session. The callback checks that state, swaps the code for a token over a direct
TLS call with our client secret, reads the profile, and signs the user in with the normal
Django session, so nothing about the provider's tokens ever reaches the browser or is stored.

Linking rules, chosen so an identity can't take over someone else's account:
- a provider identity seen before signs in its own user;
- Google identities with a verified email sign in, or are linked to, the user with that email;
- Facebook identities only create new users: Facebook doesn't promise the email was verified,
  so an existing account with that email must be signed into with its password.
"""

import base64
import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from urllib.parse import urlencode

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.platform.http import OutboundError, get_json, post_form
from apps.platform.locking import lock_rows

from .models import SocialAccount, User

SESSION_KEY = "oauth"


class OAuthError(Exception):
    """The sign-in can't go ahead; `code` goes back to the sign-in page as ?error=."""

    def __init__(self, code: str = "oauth_failed") -> None:
        super().__init__(code)
        self.code = code


@dataclass(frozen=True)
class Provider:
    name: str
    authorize_url: str
    token_url: str
    profile_url: str
    scope: str
    pkce: bool

    @property
    def client_id(self) -> str:
        value: str = getattr(settings, CREDENTIALS[self.name][0])
        return value

    @property
    def client_secret(self) -> str:
        value: str = getattr(settings, CREDENTIALS[self.name][1])
        return value

    @property
    def enabled(self) -> bool:
        # Facebook stays off unless switched on: it doesn't vouch for the email, and confirming
        # the email proves who holds the inbox, not who holds the Facebook account, so a
        # stranger's Facebook could stay linked to someone else's address. Off until linking
        # Facebook needs a signed-in account (see docs/security.md).
        if self.name == "facebook" and not settings.FACEBOOK_SIGN_IN:
            return False
        return bool(self.client_id and self.client_secret)

    @property
    def redirect_uri(self) -> str:
        return f"{settings.SITE_URL.rstrip('/')}/api/accounts/oauth/{self.name}/callback/"


GRAPH = "https://graph.facebook.com/v21.0"
PROVIDERS = {
    "google": Provider(
        "google",
        "https://accounts.google.com/o/oauth2/v2/auth",
        "https://oauth2.googleapis.com/token",
        "https://openidconnect.googleapis.com/v1/userinfo",
        "openid email profile",
        pkce=True,
    ),
    "facebook": Provider(
        "facebook",
        "https://www.facebook.com/v21.0/dialog/oauth",
        f"{GRAPH}/oauth/access_token",
        f"{GRAPH}/me?fields=id,name,email",
        "email public_profile",
        pkce=False,
    ),
}
CREDENTIALS = {
    "google": ("GOOGLE_OAUTH_CLIENT_ID", "GOOGLE_OAUTH_CLIENT_SECRET"),
    "facebook": ("FACEBOOK_APP_ID", "FACEBOOK_APP_SECRET"),
}


@dataclass(frozen=True)
class Profile:
    uid: str
    email: str
    email_verified: bool
    name: str


def enabled_providers() -> list[str]:
    return [name for name, provider in PROVIDERS.items() if provider.enabled]


def get_provider(name: str) -> Provider:
    provider = PROVIDERS.get(name)
    if provider is None or not provider.enabled:
        raise OAuthError("provider_unavailable")
    return provider


def safe_next(value: str | None) -> str:
    """Only paths inside the app; anything else could send people to another site."""
    if (
        value
        and value.startswith(("/app", "/accept-invite"))
        and "//" not in value
        and "\\" not in value
    ):
        return value[:300]
    return "/app"


def _challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def start(session: Any, provider: Provider, next_path: str | None) -> str:
    """Remember a fresh state in the session and return the provider's sign-in URL."""
    state = secrets.token_urlsafe(32)
    flow = {"provider": provider.name, "state": state, "next": safe_next(next_path)}
    params = {
        "client_id": provider.client_id,
        "redirect_uri": provider.redirect_uri,
        "response_type": "code",
        "scope": provider.scope,
        "state": state,
    }
    if provider.pkce:
        verifier = secrets.token_urlsafe(48)
        flow["verifier"] = verifier
        params.update(code_challenge=_challenge(verifier), code_challenge_method="S256")
    if provider.name == "google":
        params["prompt"] = "select_account"
    session[SESSION_KEY] = flow
    return f"{provider.authorize_url}?{urlencode(params)}"


def _profile(provider: Provider, code: str, verifier: str | None) -> Profile:
    fields = {
        "client_id": provider.client_id,
        "client_secret": provider.client_secret,
        "code": code,
        "redirect_uri": provider.redirect_uri,
        "grant_type": "authorization_code",
    }
    if verifier:
        fields["code_verifier"] = verifier
    try:
        if provider.name == "facebook":
            # Facebook documents the code exchange as a GET.
            token = get_json(f"{provider.token_url}?{urlencode(fields)}")
        else:
            token = post_form(provider.token_url, fields)
        access = token.get("access_token")
        if not isinstance(access, str) or not access:
            raise OAuthError
        profile_url = provider.profile_url
        if provider.name == "facebook":
            # appsecret_proof ties the Graph call to our app, so a leaked token alone is useless.
            proof = hmac.new(provider.client_secret.encode(), access.encode(), hashlib.sha256)
            profile_url += f"&appsecret_proof={proof.hexdigest()}"
        data = get_json(profile_url, bearer=access)
    except OutboundError as exc:
        raise OAuthError from exc
    uid = str(data.get("sub") if provider.name == "google" else data.get("id") or "")
    email = str(data.get("email") or "").strip().lower()
    if not uid or uid == "None":
        raise OAuthError
    # Only Google states whether it checked the address; Facebook's is treated as unverified.
    verified = provider.name == "google" and data.get("email_verified") is True
    return Profile(uid, email, verified, str(data.get("name") or "")[:150])


def finish(session: Any, name: str, params: dict[str, str]) -> tuple[User, str]:
    """Check the callback, resolve the user, and return it with where to send them next."""
    flow = session.pop(SESSION_KEY, None)
    state = params.get("state", "")
    if (
        not isinstance(flow, dict)
        or flow.get("provider") != name
        or not state
        or not secrets.compare_digest(str(flow.get("state", "")), state)
    ):
        raise OAuthError("oauth_state")
    if params.get("error"):
        raise OAuthError("oauth_cancelled")
    code = params.get("code", "")
    if not code:
        raise OAuthError
    provider = get_provider(name)
    profile = _profile(provider, code, flow.get("verifier"))
    return _user_for(provider.name, profile), safe_next(flow.get("next"))


@transaction.atomic
def _user_for(provider: str, profile: Profile) -> User:
    now = timezone.now()
    link = (
        SocialAccount.objects.select_for_update()
        .select_related("user")
        .filter(provider=provider, uid=profile.uid)
        .first()
    )
    if link is not None:
        if not link.user.is_active:
            raise OAuthError("account_disabled")
        link.last_login_at = now
        link.save(update_fields=["last_login_at"])
        return link.user
    if not profile.email:
        raise OAuthError("email_missing")
    existing = User.objects.filter(email=profile.email).first()
    if existing is not None:
        if not profile.email_verified:
            raise OAuthError("email_in_use")
        if not existing.is_active:
            raise OAuthError("account_disabled")
    # One savepoint for the account and its link: whoever loses a race leaves nothing behind.
    try:
        with transaction.atomic():
            user = _claim(existing, now) if existing else _create(profile, now)
            SocialAccount.objects.create(
                user=user, provider=provider, uid=profile.uid, last_login_at=now
            )
    except IntegrityError as exc:
        # A double click on the consent screen: the other callback linked this identity first.
        winner = SocialAccount.objects.filter(provider=provider, uid=profile.uid).first()
        if winner is None:
            raise OAuthError("email_in_use") from exc
        return winner.user
    return user


def _claim(user: User, now: datetime) -> User:
    # Locked and read again, so a reset finishing at this moment can't lose its new password.
    user = lock_rows(User.objects.filter(pk=user.pk))[0]
    if user.email_verified_at is None:
        # Nobody ever proved they own this address, so whatever opens this account may be a
        # stranger's who signed up with it first. The provider has now proved who does: drop the
        # password, which also ends any session it opened, and any provider already linked. A real
        # owner can set a new password by reset.
        user.social_accounts.all().delete()
        user.set_unusable_password()
        user.email_verified_at = now
        user.save(update_fields=["password", "email_verified_at"])
    return user


def _create(profile: Profile, now: datetime) -> User:
    return User.objects.create_user(
        profile.email,
        None,
        full_name=profile.name,
        # Google vouches for the address; Facebook's must still be confirmed by us.
        email_verified_at=now if profile.email_verified else None,
    )
