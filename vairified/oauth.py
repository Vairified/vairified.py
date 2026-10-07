"""
Vairified OAuth Helpers

Utilities for implementing the "Connect with Vairified" OAuth flow.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional
from urllib.parse import urlencode

#: Scope string literal — the union of every scope name the Vairified
#: OAuth server accepts. Use this type in your own signatures to get
#: autocomplete and type-checking for the scope strings you pass.
OAuthScope = Literal[
    "user:profile:read",
    "user:profile:email",
    "user:rating:read",
    "user:rating:history",
    "user:match:submit",
    "user:webhook:subscribe",
]

# Available OAuth scopes
SCOPES: dict[str, str] = {
    "user:profile:read": "Access your name, location, and verification status",
    "user:profile:email": "Access your email address",
    "user:rating:read": "View your current rating and rating splits",
    "user:rating:history": "View your complete rating history",
    "user:match:submit": "Submit match results on your behalf",
    "user:webhook:subscribe": "Receive notifications when your rating changes",
}

# Default scopes requested
DEFAULT_SCOPES: list[OAuthScope] = ["user:profile:read", "user:rating:read"]


@dataclass(frozen=True)
class OAuthConfig:
    """
    OAuth configuration for a partner application.

    :ivar api_key: Partner API key.
    :ivar redirect_uri: Your application's callback URL.
    :ivar base_url: Vairified API base URL.
    """

    api_key: str
    redirect_uri: str
    base_url: str = "https://api-next.vairified.com/api/v1"
    #: Your app's ``client_id`` — the ``PartnerApp.slug`` Vairified assigned
    #: you (e.g. ``"dinkr"``). Required by the browser
    #: ``GET /partner/oauth/authorize`` endpoint to identify your app; without
    #: it the authorization page rejects the request. Only needed for this
    #: pure-frontend URL helper — the recommended
    #: :meth:`OAuthResource.authorize` flow identifies your app by API key.
    client_id: Optional[str] = None


@dataclass(frozen=True)
class AuthorizationResponse:
    """
    Response from starting an OAuth authorization.

    :ivar authorization_url: Full URL to redirect the user to.
    :ivar code: Authorization code (for internal tracking).
    :ivar state: CSRF state parameter.
    """

    authorization_url: str
    code: str
    state: Optional[str] = None


@dataclass(frozen=True)
class TokenResponse:
    """
    Response from exchanging an authorization code for tokens.

    :ivar access_token: Access token for API requests.
    :ivar refresh_token: Refresh token for obtaining new access tokens.
    :ivar expires_in: Token expiration in seconds.
    :ivar scope: Granted scopes.
    :ivar player_id: Connected player's external ID.
    """

    access_token: str
    refresh_token: Optional[str]
    expires_in: int
    scope: list[str]
    player_id: str


def get_authorization_url(
    config: OAuthConfig,
    scopes: Optional[list[str]] = None,
    state: Optional[str] = None,
) -> str:
    """
    Build the URL to redirect users to for OAuth authorization.

    This is a helper for building the URL manually. In most cases,
    you should use the Vairified client's OAuth methods instead.

    :param config: OAuth configuration.
    :param scopes: Permission scopes to request.
    :param state: CSRF protection state parameter.
    :returns: URL to redirect the user to.

    Example::

        config = OAuthConfig(
            api_key="vair_pk_xxx",
            redirect_uri="https://myapp.com/oauth/callback",
        )
        url = get_authorization_url(
            config, scopes=["user:profile:read", "user:rating:read"]
        )
        # Redirect user to this URL
    """
    if scopes is None:
        scopes = DEFAULT_SCOPES

    # Ensure user:profile:read is always included
    if "user:profile:read" not in scopes:
        scopes = ["user:profile:read"] + scopes

    # Scope is space-delimited per RFC 6749 §3.3 — the deployed authorization
    # server splits on whitespace, not commas.
    params = {
        "redirect_uri": config.redirect_uri,
        "scope": " ".join(scopes),
        "response_type": "code",
    }

    # client_id (the PartnerApp slug) identifies the app to the browser
    # authorize endpoint; the URL is rejected without it.
    if config.client_id:
        params["client_id"] = config.client_id

    if state:
        params["state"] = state

    # The actual authorization is done via API call, this builds the frontend URL
    # Partners should POST to /partner/oauth/authorize to get the actual auth URL
    return f"{config.base_url}/partner/oauth/authorize?{urlencode(params)}"


def validate_scope(scope: str) -> bool:
    """
    Check if a scope is valid.

    :param scope: Scope string to validate.
    :returns: True if scope is valid.
    """
    return scope in SCOPES


def describe_scope(scope: str) -> str:
    """
    Get a human-readable description of a scope.

    :param scope: Scope string.
    :returns: Description of what the scope grants access to.
    """
    return SCOPES.get(scope, f"Unknown scope: {scope}")


def describe_scopes(scopes: list[str]) -> list[dict[str, str]]:
    """
    Get descriptions for multiple scopes.

    :param scopes: List of scope strings.
    :returns: List of dicts with 'scope' and 'description' keys.
    """
    return [{"scope": s, "description": describe_scope(s)} for s in scopes]
