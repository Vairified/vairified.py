"""Tests for the OAuth sub-resource and helper functions."""

from __future__ import annotations

import dataclasses
import json
from urllib.parse import parse_qs, urlparse

import pytest
import respx
from httpx import Response

from vairified import (
    DEFAULT_SCOPES,
    SCOPES,
    AuthorizationResponse,
    OAuthConfig,
    OAuthError,
    TokenResponse,
    Vairified,
    describe_scope,
    describe_scopes,
    get_authorization_url,
    validate_scope,
)

# ---------------------------------------------------------------------------
# Pure helper functions in vairified.oauth
# ---------------------------------------------------------------------------


class TestOAuthHelpers:
    def test_validate_scope_known(self):
        for scope in SCOPES:
            assert validate_scope(scope) is True

    def test_validate_scope_unknown(self):
        assert validate_scope("not-a-scope") is False
        assert validate_scope("") is False

    def test_describe_scope_known(self):
        assert "verification" in describe_scope("user:profile:read").lower()

    def test_describe_scope_unknown(self):
        description = describe_scope("foo:bar")
        assert "Unknown scope" in description
        assert "foo:bar" in description

    def test_describe_scopes_returns_list_of_dicts(self):
        result = describe_scopes(["user:profile:read", "user:rating:read"])
        assert len(result) == 2
        assert result[0] == {
            "scope": "user:profile:read",
            "description": SCOPES["user:profile:read"],
        }
        assert result[1]["scope"] == "user:rating:read"

    def test_default_scopes_include_profile_read(self):
        assert "user:profile:read" in DEFAULT_SCOPES


class TestGetAuthorizationUrl:
    def _config(self) -> OAuthConfig:
        return OAuthConfig(
            api_key="vair_pk_test",
            redirect_uri="https://app.example.com/callback",
            base_url="https://api.example.com/api/v1",
            client_id="dinkr",
        )

    def test_defaults(self):
        url = get_authorization_url(self._config())
        assert url.startswith("https://api.example.com/api/v1/partner/oauth/authorize?")
        q = parse_qs(urlparse(url).query)
        assert q["redirect_uri"] == ["https://app.example.com/callback"]
        # RFC 6749 §3.3 — scopes are space-delimited, never comma-joined.
        assert q["scope"] == ["user:profile:read user:rating:read"]
        assert "%2C" not in url  # no encoded comma between scopes
        assert q["response_type"] == ["code"]
        # client_id (PartnerApp slug) identifies the app to the GET endpoint.
        assert q["client_id"] == ["dinkr"]

    def test_client_id_omitted_when_not_configured(self):
        config = OAuthConfig(
            api_key="vair_pk_test",
            redirect_uri="https://app.example.com/callback",
            base_url="https://api.example.com/api/v1",
        )
        q = parse_qs(urlparse(get_authorization_url(config)).query)
        assert "client_id" not in q

    def test_custom_scopes(self):
        url = get_authorization_url(
            self._config(),
            scopes=["user:rating:read", "user:match:submit"],
        )
        q = parse_qs(urlparse(url).query)
        # user:profile:read auto-prepended, space-delimited.
        assert q["scope"] == ["user:profile:read user:rating:read user:match:submit"]

    def test_state_param_included(self):
        url = get_authorization_url(self._config(), state="csrf-token-xyz")
        assert parse_qs(urlparse(url).query)["state"] == ["csrf-token-xyz"]

    def test_state_omitted_when_none(self):
        url = get_authorization_url(self._config())
        assert "state=" not in url


# ---------------------------------------------------------------------------
# OAuthResource — HTTP methods
# ---------------------------------------------------------------------------


class TestOAuthResource:
    @respx.mock
    @pytest.mark.asyncio
    async def test_authorize(self, api_key, base_url):
        route = respx.post(f"{base_url}/partner/oauth/authorize").mock(
            return_value=Response(
                200,
                json={
                    "authorization_url": "https://vairified.com/connect/xyz",
                    "code": "auth-code-123",
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            auth = await client.oauth.authorize(
                redirect_uri="https://app.example.com/callback",
                scopes=["user:rating:read"],
                state="csrf-xyz",
            )

        assert auth.authorization_url == "https://vairified.com/connect/xyz"
        assert auth.code == "auth-code-123"
        assert auth.state == "csrf-xyz"

        # exact request wire the deployed api-next expects
        body = json.loads(route.calls.last.request.content)
        assert body["redirect_uri"] == "https://app.example.com/callback"
        assert "redirectUri" not in body
        # space-delimited, user:profile:read auto-prepended
        assert body["scope"] == "user:profile:read user:rating:read"
        assert body["state"] == "csrf-xyz"

    @respx.mock
    @pytest.mark.asyncio
    async def test_authorize_invalid_scope(self, api_key, base_url):
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(OAuthError) as exc_info:
                await client.oauth.authorize(
                    redirect_uri="https://app.example.com/callback",
                    scopes=["user:rating:read", "not-a-real-scope"],  # type: ignore[list-item]
                )

        assert exc_info.value.error_code == "invalid_scope"
        assert "not-a-real-scope" in exc_info.value.message

    @respx.mock
    @pytest.mark.asyncio
    async def test_authorize_defaults_when_no_scopes(self, api_key, base_url):
        route = respx.post(f"{base_url}/partner/oauth/authorize").mock(
            return_value=Response(
                200,
                json={"authorization_url": "https://x.example.com", "code": "c"},
            )
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            auth = await client.oauth.authorize(
                redirect_uri="https://app.example.com/callback"
            )
        assert auth.authorization_url == "https://x.example.com"
        body = json.loads(route.calls.last.request.content)
        assert body["scope"] == "user:profile:read user:rating:read"

    @respx.mock
    @pytest.mark.asyncio
    async def test_exchange_token(self, api_key, base_url):
        route = respx.post(f"{base_url}/partner/oauth/token").mock(
            return_value=Response(
                200,
                json={
                    "access_token": "access-xyz",
                    "token_type": "Bearer",
                    "refresh_token": "refresh-xyz",
                    "expires_in": 3600,
                    "scope": "user:profile:read user:rating:read",
                    "player_id": "vair_mem_42",
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            tokens = await client.oauth.exchange_token(
                code="code-123",
                redirect_uri="https://app.example.com/callback",
            )

        # request wire (RFC 6749 §4.1.3)
        body = json.loads(route.calls.last.request.content)
        assert body["grant_type"] == "authorization_code"
        assert body["code"] == "code-123"
        assert body["redirect_uri"] == "https://app.example.com/callback"
        assert "redirectUri" not in body
        # response mapping (snake_case)
        assert tokens.access_token == "access-xyz"
        assert tokens.refresh_token == "refresh-xyz"
        assert tokens.expires_in == 3600
        assert tokens.scope == ["user:profile:read", "user:rating:read"]
        assert tokens.player_id == "vair_mem_42"

    @respx.mock
    @pytest.mark.asyncio
    async def test_exchange_token_empty_scope_falls_back_to_scopes_array(
        self, api_key, base_url
    ):
        """Empty `scope` string falls back to the deprecated `scopes` array."""
        respx.post(f"{base_url}/partner/oauth/token").mock(
            return_value=Response(
                200,
                json={
                    "access_token": "a",
                    "refresh_token": None,
                    "expires_in": 3600,
                    "scope": "",
                    "scopes": ["user:profile:read"],
                    "player_id": "p",
                },
            )
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            tokens = await client.oauth.exchange_token("c", "r")
        assert tokens.scope == ["user:profile:read"]
        assert tokens.refresh_token is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_refresh(self, api_key, base_url):
        route = respx.post(f"{base_url}/partner/oauth/refresh").mock(
            return_value=Response(
                200,
                json={
                    "access_token": "new-access",
                    "refresh_token": "new-refresh",
                    "expires_in": 3600,
                    "scope": "user:profile:read",
                    "player_id": "vair_mem_42",
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            tokens = await client.oauth.refresh("old-refresh-token")

        # request wire (RFC 6749 §6)
        body = json.loads(route.calls.last.request.content)
        assert body["grant_type"] == "refresh_token"
        assert body["refresh_token"] == "old-refresh-token"
        assert "refreshToken" not in body
        assert tokens.access_token == "new-access"
        assert tokens.refresh_token == "new-refresh"

    @respx.mock
    @pytest.mark.asyncio
    async def test_revoke(self, api_key, base_url):
        route = respx.post(f"{base_url}/partner/oauth/revoke").mock(
            return_value=Response(200, json={"success": True})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.oauth.revoke("vair_mem_42")

        body = json.loads(route.calls.last.request.content)
        assert body["player_id"] == "vair_mem_42"
        assert "playerId" not in body
        assert result == {"success": True}

    @respx.mock
    @pytest.mark.asyncio
    async def test_available_scopes(self, api_key, base_url):
        respx.get(f"{base_url}/partner/oauth/scopes").mock(
            return_value=Response(
                200,
                json={
                    "scopes": [
                        {"name": "user:profile:read", "description": "Profile access"},
                        {"name": "user:rating:read", "description": "Rating access"},
                    ]
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            scopes = await client.oauth.available_scopes()

        assert len(scopes) == 2
        assert scopes[0]["name"] == "user:profile:read"

    @respx.mock
    @pytest.mark.asyncio
    async def test_available_scopes_non_dict_response(self, api_key, base_url):
        """Server returning a non-dict should yield an empty list."""
        respx.get(f"{base_url}/partner/oauth/scopes").mock(
            return_value=Response(200, json=[])
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            scopes = await client.oauth.available_scopes()
        assert scopes == []


# ---------------------------------------------------------------------------
# Model immutability (Vairified#858) — parity with the TS SDK's readonly models
# ---------------------------------------------------------------------------


class TestOAuthModelsFrozen:
    """The OAuth value objects are frozen (sdk.md: models stay immutable)."""

    def test_oauth_config_is_frozen(self):
        config = OAuthConfig(api_key="vair_pk_x", redirect_uri="https://app.example/cb")
        with pytest.raises(dataclasses.FrozenInstanceError):
            config.api_key = "vair_pk_y"  # type: ignore[misc]

    def test_authorization_response_is_frozen(self):
        resp = AuthorizationResponse(
            authorization_url="https://x/authorize", code="abc"
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            resp.code = "def"  # type: ignore[misc]

    def test_token_response_is_frozen(self):
        token = TokenResponse(
            access_token="at",
            refresh_token="rt",
            expires_in=3600,
            scope=["user:profile:read"],
            player_id="p1",
        )
        with pytest.raises(dataclasses.FrozenInstanceError):
            token.access_token = "leaked"  # type: ignore[misc]
