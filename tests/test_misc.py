"""
Tests for small/misc paths: client construction, env-var fallback,
usage(), test_webhook(), search age filters, and error edge cases.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response
from pydantic import ValidationError as PydanticValidationError

from vairified import (
    AuthenticationError,
    Member,
    NotFoundError,
    RateLimitError,
    TournamentImportResult,
    Vairified,
    VairifiedError,
    ValidationError,
    WebhookDeliveriesResult,
    WebhookDelivery,
)
from vairified.client import _raise_from_response
from vairified.errors import OAuthError


def _member_payload(**overrides):
    payload = {
        "memberId": 1,
        "firstName": "T",
        "lastName": "P",
        "fullName": "T P",
        "displayName": "T",
        "status": {
            "isWheelchair": False,
            "isAmbassador": False,
            "isConnected": False,
        },
        "sport": {},
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Client construction — env var fallbacks
# ---------------------------------------------------------------------------


class TestEnvFallbacks:
    def test_api_key_from_env_var(self, monkeypatch):
        monkeypatch.setenv("VAIRIFIED_API_KEY", "vair_pk_from_env")
        monkeypatch.delenv("VAIRIFIED_ENV", raising=False)
        client = Vairified()
        assert client.api_key == "vair_pk_from_env"
        assert client.env == "production"

    def test_env_from_env_var(self, monkeypatch, api_key):
        monkeypatch.setenv("VAIRIFIED_ENV", "staging")
        client = Vairified(api_key=api_key)
        assert client.env == "staging"
        assert "staging" in client.base_url

    def test_env_var_unknown_falls_back_to_default(self, monkeypatch, api_key):
        monkeypatch.setenv("VAIRIFIED_ENV", "not-a-real-env")
        client = Vairified(api_key=api_key)
        assert client.env == "not-a-real-env"
        # Falls back to production URL rather than raising.
        assert client.base_url.startswith("https://")

    def test_repr(self, api_key):
        client = Vairified(api_key=api_key, env="production")
        rendered = repr(client)
        assert "Vairified" in rendered
        assert "production" in rendered


# ---------------------------------------------------------------------------
# _ensure_http — lazy HTTP client creation without context manager
# ---------------------------------------------------------------------------


class TestLazyHttp:
    @respx.mock
    @pytest.mark.asyncio
    async def test_request_without_context_manager(self, api_key, base_url):
        """Using the client without `async with` should still work."""
        respx.get(f"{base_url}/partner/member").mock(
            return_value=Response(200, json=_member_payload())
        )

        client = Vairified(api_key=api_key, base_url=base_url)
        try:
            member = await client.members.get("vair_mem_xxx")
            assert member.member_id == 1
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_close_is_idempotent(self, api_key, base_url):
        client = Vairified(api_key=api_key, base_url=base_url)
        await client.close()
        await client.close()  # should not raise


# ---------------------------------------------------------------------------
# usage() and matches.test_webhook()
# ---------------------------------------------------------------------------


class TestUsageAndWebhook:
    @respx.mock
    @pytest.mark.asyncio
    async def test_usage(self, api_key, base_url):
        respx.get(f"{base_url}/partner/usage").mock(
            return_value=Response(
                200,
                json={
                    "rateLimit": 10000,
                    "requestsToday": 42,
                    "quotaUsed": 0.42,
                },
            )
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            usage = await client.usage()
        assert usage["requestsToday"] == 42

    @respx.mock
    @pytest.mark.asyncio
    async def test_usage_empty_body(self, api_key, base_url):
        respx.get(f"{base_url}/partner/usage").mock(
            return_value=Response(204, content=b"")
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            usage = await client.usage()
        assert usage == {}

    @respx.mock
    @pytest.mark.asyncio
    async def test_test_webhook(self, api_key, base_url):
        route = respx.post(f"{base_url}/partner/webhook-test").mock(
            return_value=Response(200, json={"delivered": True})
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.matches.test_webhook("https://hook.example.com")
        assert result == {"delivered": True}
        assert b"https://hook.example.com" in route.calls.last.request.content

    @respx.mock
    @pytest.mark.asyncio
    async def test_test_webhook_empty_body(self, api_key, base_url):
        respx.post(f"{base_url}/partner/webhook-test").mock(
            return_value=Response(204, content=b"")
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.matches.test_webhook("https://hook.example.com")
        assert result == {}


# ---------------------------------------------------------------------------
# Search age filter branches
# ---------------------------------------------------------------------------


class TestSearchAgeFilters:
    @respx.mock
    @pytest.mark.asyncio
    async def test_search_exact_age(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/search").mock(
            return_value=Response(200, json=[])
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            async for _ in client.members.search(age=35):
                pass
        params = route.calls.last.request.url.params
        assert params["ageFilterType"] == "exact"
        assert params["age1"] == "35"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_age_range(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/search").mock(
            return_value=Response(200, json=[])
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            async for _ in client.members.search(age_min=30, age_max=40):
                pass
        params = route.calls.last.request.url.params
        assert params["ageFilterType"] == "range"
        assert params["age1"] == "30"
        assert params["age2"] == "40"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_age_above(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/search").mock(
            return_value=Response(200, json=[])
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            async for _ in client.members.search(age_min=50):
                pass
        params = route.calls.last.request.url.params
        assert params["ageFilterType"] == "above"
        assert params["age1"] == "50"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_age_below(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/search").mock(
            return_value=Response(200, json=[])
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            async for _ in client.members.search(age_max=25):
                pass
        params = route.calls.last.request.url.params
        assert params["ageFilterType"] == "below"
        assert params["age1"] == "25"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_by_member_id_and_gender(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/search").mock(
            return_value=Response(200, json=[])
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            async for _ in client.members.search(member_id=12345, gender="female"):
                pass
        params = route.calls.last.request.url.params
        assert params["member"] == "12345"
        assert params["gender"] == "FEMALE"  # Should be uppercased

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_dict_payload_response(self, api_key, base_url):
        """Older server shape returns {players: [...]} instead of a flat list."""
        respx.get(f"{base_url}/partner/search").mock(
            return_value=Response(
                200,
                json={"players": [_member_payload(memberId=1)]},
            )
        )
        collected = []
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            async for m in client.members.search(name="x"):
                collected.append(m)
        assert len(collected) == 1


# ---------------------------------------------------------------------------
# rating_updates non-dict response
# ---------------------------------------------------------------------------


class TestRatingUpdatesEdgeCases:
    @respx.mock
    @pytest.mark.asyncio
    async def test_rating_updates_non_dict(self, api_key, base_url):
        respx.get(f"{base_url}/partner/rating-updates").mock(
            return_value=Response(200, json=[])  # unexpected shape
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            updates = await client.members.rating_updates()
        assert updates == []


# ---------------------------------------------------------------------------
# _raise_from_response edge cases
# ---------------------------------------------------------------------------


class TestRaiseFromResponse:
    def _resp(self, status, body=None, text=None, headers=None):
        from httpx import Response as HResponse

        if body is not None:
            return HResponse(status, json=body, headers=headers or {})
        return HResponse(status, content=text or b"", headers=headers or {})

    def test_400_validation_error(self):
        with pytest.raises(ValidationError) as exc_info:
            _raise_from_response(self._resp(400, body={"message": "bad input"}))
        assert exc_info.value.status_code == 400
        assert exc_info.value.message == "bad input"

    def test_401_authentication_error(self):
        with pytest.raises(AuthenticationError):
            _raise_from_response(self._resp(401, body={"message": "no"}))

    def test_404_not_found(self):
        with pytest.raises(NotFoundError):
            _raise_from_response(self._resp(404, body={"message": "gone"}))

    def test_429_with_retry_after(self):
        with pytest.raises(RateLimitError) as exc_info:
            _raise_from_response(
                self._resp(
                    429,
                    body={"message": "slow"},
                    headers={"Retry-After": "120"},
                )
            )
        assert exc_info.value.retry_after == 120

    def test_429_without_retry_after(self):
        with pytest.raises(RateLimitError) as exc_info:
            _raise_from_response(self._resp(429, body={"message": "slow"}))
        assert exc_info.value.retry_after is None

    def test_500_generic_error(self):
        with pytest.raises(VairifiedError) as exc_info:
            _raise_from_response(self._resp(500, body={"message": "boom"}))
        assert exc_info.value.status_code == 500

    def test_body_error_field_fallback(self):
        """Some endpoints use 'error' instead of 'message'."""
        with pytest.raises(VairifiedError) as exc_info:
            _raise_from_response(self._resp(500, body={"error": "something broke"}))
        assert exc_info.value.message == "something broke"

    def test_non_json_body(self):
        """A non-JSON error body should fall back to response text."""
        with pytest.raises(VairifiedError) as exc_info:
            _raise_from_response(self._resp(500, text=b"not json here"))
        assert "not json here" in exc_info.value.message

    def test_non_dict_json_body(self):
        """A JSON body that isn't a dict should still produce an error."""
        with pytest.raises(VairifiedError):
            _raise_from_response(self._resp(500, body=["unexpected", "list"]))


# ---------------------------------------------------------------------------
# Exception classes — defaults and string rendering
# ---------------------------------------------------------------------------


class TestExceptionClasses:
    def test_base_error_str_with_status(self):
        err = VairifiedError("boom", status_code=500)
        assert str(err) == "[500] boom"

    def test_base_error_str_without_status(self):
        err = VairifiedError("boom")
        assert str(err) == "boom"

    def test_rate_limit_default_message(self):
        err = RateLimitError()
        assert err.status_code == 429
        assert "Rate limit" in err.message

    def test_authentication_default_message(self):
        err = AuthenticationError()
        assert err.status_code == 401
        assert "Invalid API key" in err.message

    def test_not_found_default_message(self):
        err = NotFoundError()
        assert err.status_code == 404

    def test_validation_default_message(self):
        err = ValidationError()
        assert err.status_code == 400

    def test_oauth_error_with_code(self):
        err = OAuthError("bad grant", error_code="invalid_grant")
        assert err.error_code == "invalid_grant"
        assert err.message == "bad grant"

    def test_oauth_error_default(self):
        err = OAuthError()
        assert err.error_code is None


# ---------------------------------------------------------------------------
# Model edge cases — iteration, Member.split with missing sport, dry_run
# ---------------------------------------------------------------------------


class TestModelEdgeCases:
    def test_sport_rating_iteration(self):
        """Exercise SportRating.__iter__."""
        payload = _member_payload(
            sport={
                "pickleball": {
                    "rating": 4.0,
                    "abbr": "VO",
                    "ratingSplits": {
                        "overall-open": {"rating": 4.0, "abbr": "VO"},
                        "gender-open": {"rating": 3.9, "abbr": "VG"},
                    },
                }
            }
        )
        member = Member.model_validate(payload)
        pb = member.sport["pickleball"]

        collected = [(k, s.rating) for k, s in pb]
        assert ("overall-open", 4.0) in collected
        assert ("gender-open", 3.9) in collected

    def test_member_split_missing_sport_returns_none(self):
        """Member.split for a sport the player doesn't have."""
        member = Member.model_validate(_member_payload(sport={}))
        assert member.split("overall-open", sport="padel") is None

    def test_member_split_missing_key_returns_none(self):
        member = Member.model_validate(
            _member_payload(
                sport={
                    "pickleball": {
                        "rating": 4.0,
                        "abbr": "VO",
                        "ratingSplits": {
                            "overall-open": {"rating": 4.0, "abbr": "VO"},
                        },
                    }
                }
            )
        )
        assert member.split("nonexistent") is None

    def test_match_batch_result_is_dry_run_property(self):
        from vairified import MatchBatchResult

        result = MatchBatchResult.model_validate(
            {
                "success": True,
                "numMatches": 1,
                "numGames": 2,
                "dryRun": True,
            }
        )
        assert result.is_dry_run is True

        result_live = MatchBatchResult.model_validate(
            {"success": True, "numMatches": 1, "numGames": 2}
        )
        assert result_live.is_dry_run is False


# ---------------------------------------------------------------------------
# members.get_bulk()
# ---------------------------------------------------------------------------


class TestGetBulk:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_bulk(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/members").mock(
            return_value=Response(
                200,
                json=[
                    _member_payload(memberId=1, fullName="A A", displayName="A"),
                    _member_payload(memberId=2, fullName="B B", displayName="B"),
                ],
            )
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            members = await client.members.get_bulk([1, 2])
        assert len(members) == 2
        assert members[0].member_id == 1
        assert members[1].member_id == 2
        assert route.calls.last.request.url.params["ids"] == "1,2"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_bulk_with_sport(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/members").mock(
            return_value=Response(200, json=[_member_payload(memberId=5)])
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            members = await client.members.get_bulk([5], sport="pickleball")
        assert len(members) == 1
        assert route.calls.last.request.url.params["sport"] == "pickleball"

    @pytest.mark.asyncio
    async def test_get_bulk_over_100_raises(self, api_key, base_url):
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValueError, match="Maximum 100"):
                await client.members.get_bulk(list(range(101)))

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_bulk_non_list_response(self, api_key, base_url):
        """Server returning a non-list should yield an empty list."""
        respx.get(f"{base_url}/partner/members").mock(
            return_value=Response(200, json={"unexpected": "shape"})
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            members = await client.members.get_bulk([1])
        assert members == []


# ---------------------------------------------------------------------------
# matches.tournament_import()
# ---------------------------------------------------------------------------


class TestTournamentImport:
    @respx.mock
    @pytest.mark.asyncio
    async def test_tournament_import(self, api_key, base_url):
        route = respx.post(f"{base_url}/partner/tournament-import").mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "matchesImported": 5,
                    "gamesRecorded": 12,
                    "ghostPlayersCreated": 2,
                    "existingPlayersMatched": 8,
                    "dryRun": False,
                    "message": "Import complete",
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.matches.tournament_import(
                {
                    "tournamentName": "Austin Open 2026",
                    "sport": "pickleball",
                    "winScore": 11,
                    "winBy": 2,
                    "matches": [],
                }
            )

        assert isinstance(result, TournamentImportResult)
        assert result.success is True
        assert result.matches_imported == 5
        assert result.games_recorded == 12
        assert result.ghost_players_created == 2
        assert result.existing_players_matched == 8
        assert result.dry_run is False
        assert result.message == "Import complete"
        assert result.errors is None
        assert b"Austin Open 2026" in route.calls.last.request.content
        # Absent field must still be iterable — parity with the TypeScript SDK.
        assert result.created_ghost_members == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_created_ghost_members_are_returned(self, api_key, base_url):
        """
        An import used to report only a COUNT of ghosts created, so a partner
        could cause accounts to exist and address none of them. The ids now come
        back keyed by the ref the caller supplied (Vairified#1134).
        """
        respx.post(f"{base_url}/partner/tournament-import").mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "matchesImported": 4,
                    "gamesRecorded": 12,
                    "ghostPlayersCreated": 2,
                    "existingPlayersMatched": 6,
                    "createdGhostMembers": [
                        {"ref": "player.one@example.com", "memberId": 900001},
                        {"ref": "+15551234567", "memberId": 900002},
                    ],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.matches.tournament_import(
                {"sport": "pickleball", "matches": []}
            )

        assert [(g.ref, g.member_id) for g in result.created_ghost_members] == [
            ("player.one@example.com", 900001),
            ("+15551234567", 900002),
        ]

    @respx.mock
    @pytest.mark.asyncio
    async def test_created_ghost_members_are_immutable(self, api_key, base_url):
        """Models are frozen — parity with the TypeScript SDK's Object.freeze."""
        respx.post(f"{base_url}/partner/tournament-import").mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "matchesImported": 1,
                    "gamesRecorded": 1,
                    "ghostPlayersCreated": 1,
                    "existingPlayersMatched": 0,
                    "createdGhostMembers": [
                        {"ref": "a@example.com", "memberId": 900003}
                    ],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.matches.tournament_import(
                {"sport": "pickleball", "matches": []}
            )

        with pytest.raises(PydanticValidationError):
            result.created_ghost_members[0].member_id = 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_tournament_import_with_errors(self, api_key, base_url):
        respx.post(f"{base_url}/partner/tournament-import").mock(
            return_value=Response(
                200,
                json={
                    "success": False,
                    "matchesImported": 3,
                    "gamesRecorded": 6,
                    "ghostPlayersCreated": 0,
                    "existingPlayersMatched": 5,
                    "errors": ["Match 4: invalid format", "Match 5: missing teams"],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.matches.tournament_import({"matches": []})

        assert result.success is False
        assert result.errors is not None
        assert len(result.errors) == 2

    def test_tournament_import_result_model(self):
        result = TournamentImportResult.model_validate(
            {
                "success": True,
                "matchesImported": 1,
                "gamesRecorded": 2,
                "ghostPlayersCreated": 0,
                "existingPlayersMatched": 1,
                "dryRun": True,
            }
        )
        assert result.dry_run is True
        assert result.message is None
        assert result.errors is None


# ---------------------------------------------------------------------------
# webhooks.deliveries()
# ---------------------------------------------------------------------------


def _delivery_payload(**overrides):
    payload = {
        "id": "del_001",
        "event": "rating.updated",
        "url": "https://hook.example.com/webhook",
        "statusCode": 200,
        "responseBody": '{"ok": true}',
        "errorMessage": None,
        "attempts": 1,
        "maxAttempts": 3,
        "lastAttemptAt": "2026-04-12T10:00:00Z",
        "nextRetryAt": None,
        "completedAt": "2026-04-12T10:00:00Z",
        "createdAt": "2026-04-12T09:59:00Z",
        "payload": {"memberId": 123, "newRating": 4.5},
    }
    payload.update(overrides)
    return payload


class TestWebhookDeliveries:
    @respx.mock
    @pytest.mark.asyncio
    async def test_deliveries_defaults(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/webhook-deliveries").mock(
            return_value=Response(
                200,
                json={
                    "deliveries": [_delivery_payload()],
                    "total": 1,
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.webhooks.deliveries()

        assert isinstance(result, WebhookDeliveriesResult)
        assert result.total == 1
        assert len(result.deliveries) == 1

        d = result.deliveries[0]
        assert isinstance(d, WebhookDelivery)
        assert d.id == "del_001"
        assert d.event == "rating.updated"
        assert d.url == "https://hook.example.com/webhook"
        assert d.status_code == 200
        assert d.response_body == '{"ok": true}'
        assert d.error_message is None
        assert d.attempts == 1
        assert d.max_attempts == 3
        assert d.last_attempt_at == "2026-04-12T10:00:00Z"
        assert d.next_retry_at is None
        assert d.completed_at == "2026-04-12T10:00:00Z"
        assert d.created_at == "2026-04-12T09:59:00Z"
        assert d.payload == {"memberId": 123, "newRating": 4.5}

        params = route.calls.last.request.url.params
        assert params["limit"] == "20"
        assert params["offset"] == "0"

    @respx.mock
    @pytest.mark.asyncio
    async def test_deliveries_with_filters(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/webhook-deliveries").mock(
            return_value=Response(
                200,
                json={"deliveries": [], "total": 0},
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.webhooks.deliveries(
                event="rating.updated",
                status="failed",
                limit=50,
                offset=10,
            )

        assert result.total == 0
        assert result.deliveries == []

        params = route.calls.last.request.url.params
        assert params["event"] == "rating.updated"
        assert params["status"] == "failed"
        assert params["limit"] == "50"
        assert params["offset"] == "10"

    @respx.mock
    @pytest.mark.asyncio
    async def test_deliveries_no_optional_filters(self, api_key, base_url):
        """When event and status are omitted, they shouldn't appear in params."""
        route = respx.get(f"{base_url}/partner/webhook-deliveries").mock(
            return_value=Response(
                200,
                json={"deliveries": [], "total": 0},
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.webhooks.deliveries()

        params = route.calls.last.request.url.params
        assert "event" not in params
        assert "status" not in params

    def test_webhook_delivery_model(self):
        d = WebhookDelivery.model_validate(_delivery_payload())
        assert d.id == "del_001"
        assert d.event == "rating.updated"
        assert d.attempts == 1

    def test_webhook_deliveries_result_model(self):
        result = WebhookDeliveriesResult.model_validate(
            {
                "deliveries": [_delivery_payload(), _delivery_payload(id="del_002")],
                "total": 2,
            }
        )
        assert result.total == 2
        assert len(result.deliveries) == 2
        assert result.deliveries[1].id == "del_002"
