"""Tests for the OAuth sub-resource and helper functions."""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from vairified import (
    DEFAULT_SCOPES,
    SCOPES,
    OAuthConfig,
    OAuthError,
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
        )

    def test_defaults(self):
        url = get_authorization_url(self._config())
        assert url.startswith("https://api.example.com/api/v1/partner/oauth/authorize?")
        assert "redirect_uri=https%3A%2F%2Fapp.example.com%2Fcallback" in url
        assert "scope=user%3Aprofile%3Aread%2Cuser%3Arating%3Aread" in url
        assert "response_type=code" in url

    def test_custom_scopes(self):
        url = get_authorization_url(
            self._config(),
            scopes=["user:rating:read", "user:match:submit"],
        )
        # user:profile:read should be auto-prepended.
        assert "user%3Aprofile%3Aread" in url
        assert "user%3Amatch%3Asubmit" in url

    def test_state_param_included(self):
        url = get_authorization_url(self._config(), state="csrf-token-xyz")
        assert "state=csrf-token-xyz" in url

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
                    "authorizationUrl": "https://vairified.com/connect/xyz",
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

        body = route.calls.last.request.content
        # user:profile:read auto-prepended
        assert b"user:profile:read" in body
        assert b"user:rating:read" in body
        assert b"csrf-xyz" in body

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
        respx.post(f"{base_url}/partner/oauth/authorize").mock(
            return_value=Response(
                200,
                json={"authorizationUrl": "https://x.example.com", "code": "c"},
            )
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            auth = await client.oauth.authorize(
                redirect_uri="https://app.example.com/callback"
            )
        assert auth.authorization_url == "https://x.example.com"

    @respx.mock
    @pytest.mark.asyncio
    async def test_exchange_token(self, api_key, base_url):
        respx.post(f"{base_url}/partner/oauth/token").mock(
            return_value=Response(
                200,
                json={
                    "accessToken": "access-xyz",
                    "refreshToken": "refresh-xyz",
                    "expiresIn": 3600,
                    "scope": "user:profile:read,user:rating:read",
                    "playerId": "vair_mem_42",
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            tokens = await client.oauth.exchange_token(
                code="code-123",
                redirect_uri="https://app.example.com/callback",
            )

        assert tokens.access_token == "access-xyz"
        assert tokens.refresh_token == "refresh-xyz"
        assert tokens.expires_in == 3600
        assert tokens.scope == ["user:profile:read", "user:rating:read"]
        assert tokens.player_id == "vair_mem_42"

    @respx.mock
    @pytest.mark.asyncio
    async def test_exchange_token_empty_scope(self, api_key, base_url):
        """Server returning empty scope string should produce an empty list."""
        respx.post(f"{base_url}/partner/oauth/token").mock(
            return_value=Response(
                200,
                json={
                    "accessToken": "a",
                    "refreshToken": None,
                    "expiresIn": 3600,
                    "scope": "",
                    "playerId": "p",
                },
            )
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            tokens = await client.oauth.exchange_token("c", "r")
        assert tokens.scope == []
        assert tokens.refresh_token is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_refresh(self, api_key, base_url):
        respx.post(f"{base_url}/partner/oauth/refresh").mock(
            return_value=Response(
                200,
                json={
                    "accessToken": "new-access",
                    "refreshToken": "new-refresh",
                    "expiresIn": 3600,
                    "scope": "user:profile:read",
                    "playerId": "vair_mem_42",
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            tokens = await client.oauth.refresh("old-refresh-token")

        assert tokens.access_token == "new-access"
        assert tokens.refresh_token == "new-refresh"

    @respx.mock
    @pytest.mark.asyncio
    async def test_revoke(self, api_key, base_url):
        respx.post(f"{base_url}/partner/oauth/revoke").mock(
            return_value=Response(200, json={"success": True})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.oauth.revoke("vair_mem_42")

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
