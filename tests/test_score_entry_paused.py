"""
HTTP 503 SCORE_ENTRY_PAUSED -- the operator's score-entry pause during a rating
maintenance window. The body mirrors the API's exception filter:
``{statusCode, message, error, code, retryAfter, timestamp, path}`` plus a
``Retry-After`` header.
"""

from __future__ import annotations

from typing import Any

import pytest
import respx
from httpx import Response

from vairified import (
    Game,
    Match,
    MatchBatch,
    ScoreEntryPausedError,
    ServiceUnavailableError,
    Vairified,
    VairifiedError,
)

PAUSED_MESSAGE = "Score entry is paused for maintenance. Please try again shortly."


class PausedResponses:
    """Builders for the API's paused / unavailable responses."""

    @staticmethod
    def body(path: str, **overrides: Any) -> dict[str, Any]:
        body: dict[str, Any] = {
            "statusCode": 503,
            "message": PAUSED_MESSAGE,
            "error": "SCORE_ENTRY_PAUSED",
            "timestamp": "2026-10-15T12:00:00.000Z",
            "path": f"/api/v1{path}",
            "code": "SCORE_ENTRY_PAUSED",
            "retryAfter": 300,
        }
        body.update(overrides)
        return {k: v for k, v in body.items() if v is not None}

    @classmethod
    def paused(
        cls,
        path: str,
        headers: dict[str, str] | None = None,
        **overrides: Any,
    ) -> Response:
        return Response(
            503,
            json=cls.body(path, **overrides),
            headers={"Retry-After": "300"} if headers is None else headers,
        )

    @staticmethod
    def batch() -> MatchBatch:
        return MatchBatch(
            sport="pickleball",
            win_score=11,
            win_by=2,
            matches=[
                Match(
                    identifier="m1",
                    teams=[["4873327"], ["4873328"]],
                    games=[Game(scores=[11, 8])],
                )
            ],
        )


class TestScoreEntryPaused:
    @respx.mock
    @pytest.mark.asyncio
    async def test_submit_raises_score_entry_paused(self, api_key, base_url):
        route = respx.post(f"{base_url}/partner/matches").mock(
            return_value=PausedResponses.paused("/partner/matches")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ScoreEntryPausedError) as exc_info:
                await client.matches.submit(PausedResponses.batch())

        err = exc_info.value
        assert isinstance(err, ServiceUnavailableError)
        assert isinstance(err, VairifiedError)
        assert err.code == "SCORE_ENTRY_PAUSED"
        assert err.status_code == 503
        assert err.retry_after == 300
        assert err.message == PAUSED_MESSAGE
        assert err.response["code"] == "SCORE_ENTRY_PAUSED"
        # The SDK never retries on its own: one call, one request.
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_tournament_import_raises_score_entry_paused(self, api_key, base_url):
        route = respx.post(f"{base_url}/partner/tournament-import").mock(
            return_value=PausedResponses.paused("/partner/tournament-import")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ScoreEntryPausedError) as exc_info:
                await client.matches.tournament_import(
                    {"tournamentName": "Spring Classic", "matches": []}
                )

        assert exc_info.value.retry_after == 300
        assert route.call_count == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_retry_after_header_wins_over_body(self, api_key, base_url):
        respx.post(f"{base_url}/partner/matches").mock(
            return_value=PausedResponses.paused(
                "/partner/matches", headers={"Retry-After": "120"}
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ScoreEntryPausedError) as exc_info:
                await client.matches.submit(PausedResponses.batch())

        assert exc_info.value.retry_after == 120

    @respx.mock
    @pytest.mark.asyncio
    async def test_falls_back_to_body_retry_after(self, api_key, base_url):
        respx.post(f"{base_url}/partner/matches").mock(
            return_value=PausedResponses.paused("/partner/matches", headers={})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ScoreEntryPausedError) as exc_info:
                await client.matches.submit(PausedResponses.batch())

        assert exc_info.value.retry_after == 300

    @respx.mock
    @pytest.mark.asyncio
    async def test_unusable_retry_after_is_none(self, api_key, base_url):
        respx.post(f"{base_url}/partner/matches").mock(
            return_value=PausedResponses.paused(
                "/partner/matches",
                headers={"Retry-After": "Wed, 21 Oct 2026 07:28:00 GMT"},
                retryAfter=None,
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ScoreEntryPausedError) as exc_info:
                await client.matches.submit(PausedResponses.batch())

        assert exc_info.value.retry_after is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_503_without_code_is_service_unavailable(self, api_key, base_url):
        respx.post(f"{base_url}/partner/matches").mock(
            return_value=Response(
                503,
                json={
                    "statusCode": 503,
                    "message": "Upstream down",
                    "error": "Service Unavailable",
                },
                headers={"Retry-After": "30"},
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ServiceUnavailableError) as exc_info:
                await client.matches.submit(PausedResponses.batch())

        assert not isinstance(exc_info.value, ScoreEntryPausedError)
        assert exc_info.value.status_code == 503
        assert exc_info.value.retry_after == 30

    @respx.mock
    @pytest.mark.asyncio
    async def test_non_json_503_is_service_unavailable(self, api_key, base_url):
        respx.post(f"{base_url}/partner/matches").mock(
            return_value=Response(503, content=b"Service Unavailable")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ServiceUnavailableError) as exc_info:
                await client.matches.submit(PausedResponses.batch())

        assert exc_info.value.message == "Service Unavailable"
        assert exc_info.value.retry_after is None
