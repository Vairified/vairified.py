"""Tests for the leaderboard sub-resource."""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from vairified import Vairified

# The backend's DTO field lists (Vairified src/domain/leaderboard/dto,
# LeaderboardQueryDto / PlayerRankQueryDto). The global ValidationPipe runs with
# forbidNonWhitelisted, so any key outside these is a 400 -- which is how rank()
# failed on every call while it sent ``contextSize``.
LEADERBOARD_QUERY_DTO_FIELDS = frozenset(
    {
        "sportCode",
        "category",
        "ageBracket",
        "scope",
        "state",
        "city",
        "gender",
        "verifiedOnly",
        "minGames",
        "limit",
        "offset",
        "search",
        "sortBy",
        "lat",
        "lng",
        "maxDistance",
        "ratingTier",
    }
)
PLAYER_RANK_DTO_FIELDS = frozenset(
    {
        "playerId",
        "sportCode",
        "category",
        "ageBracket",
        "scope",
        "state",
        "gender",
        "verifiedOnly",
        "minGames",
        "context",
    }
)


class TestLeaderboardResource:
    @respx.mock
    @pytest.mark.asyncio
    async def test_list_defaults(self, api_key, base_url):
        route = respx.get(f"{base_url}/leaderboard").mock(
            return_value=Response(
                200,
                json={
                    "players": [
                        {"rank": 1, "displayName": "A", "rating": 5.5},
                        {"rank": 2, "displayName": "B", "rating": 5.4},
                    ],
                    "total": 2,
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            data = await client.leaderboard.list()

        assert len(data["players"]) == 2
        params = route.calls.last.request.url.params
        assert params["limit"] == "50"
        assert params["offset"] == "0"
        assert "verifiedOnly" not in params

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_with_filters(self, api_key, base_url):
        route = respx.get(f"{base_url}/leaderboard").mock(
            return_value=Response(200, json={"players": []})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.leaderboard.list(
                category="singles",
                age_bracket="50+",
                scope="state",
                state="TX",
                city="Austin",
                sport_code="padel",
                gender="MALE",
                verified_only=True,
                min_games=10,
                limit=20,
                offset=40,
                search="Mike",
            )

        params = route.calls.last.request.url.params
        assert params["category"] == "singles"
        assert params["ageBracket"] == "50+"
        assert params["scope"] == "state"
        assert params["state"] == "TX"
        assert params["city"] == "Austin"
        assert params["sportCode"] == "padel"
        assert set(params.keys()) <= LEADERBOARD_QUERY_DTO_FIELDS
        assert params["gender"] == "MALE"
        assert params["minGames"] == "10"
        assert params["search"] == "Mike"
        assert params["limit"] == "20"
        assert params["offset"] == "40"
        assert params["verifiedOnly"] == "true"

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_empty_response(self, api_key, base_url):
        respx.get(f"{base_url}/leaderboard").mock(
            return_value=Response(204, content=b"")
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            data = await client.leaderboard.list()
        assert data == {}

    @respx.mock
    @pytest.mark.asyncio
    async def test_rank(self, api_key, base_url):
        route = respx.post(f"{base_url}/leaderboard/rank").mock(
            return_value=Response(
                200,
                json={
                    "rank": 42,
                    "percentile": 93.7,
                    "player": {"id": "vair_mem_42"},
                    "context": [],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.leaderboard.rank(
                "vair_mem_42",
                sport_code="padel",
                category="singles",
                age_bracket="open",
                scope="state",
                state="TX",
                context_size=10,
            )

        assert result["rank"] == 42
        assert result["percentile"] == pytest.approx(93.7)

        body = json.loads(route.calls.last.request.content)
        assert body == {
            "playerId": "vair_mem_42",
            "sportCode": "padel",
            "category": "singles",
            "ageBracket": "open",
            "scope": "state",
            "state": "TX",
            "context": 10,
        }
        assert set(body) <= PLAYER_RANK_DTO_FIELDS

    @respx.mock
    @pytest.mark.asyncio
    async def test_rank_defaults_send_exactly_the_dto_body(self, api_key, base_url):
        route = respx.post(f"{base_url}/leaderboard/rank").mock(
            return_value=Response(200, json={"rank": 1})
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.leaderboard.rank("vair_mem_42")

        assert json.loads(route.calls.last.request.content) == {
            "playerId": "vair_mem_42",
            "category": "overall",
            "ageBracket": "open",
            "scope": "global",
            "context": 5,
        }

    @respx.mock
    @pytest.mark.asyncio
    async def test_rank_deprecated_city_and_club_id(self, api_key, base_url):
        route = respx.post(f"{base_url}/leaderboard/rank").mock(
            return_value=Response(200, json={"rank": 1})
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.warns(DeprecationWarning) as record:
                await client.leaderboard.rank(
                    "vair_mem_42", city="Austin", club_id="club_1"
                )

        messages = [str(w.message) for w in record]
        assert any(m.startswith("city is deprecated") for m in messages)
        assert any(m.startswith("club_id is deprecated") for m in messages)
        body = json.loads(route.calls.last.request.content)
        assert "city" not in body and "clubId" not in body
        assert set(body) <= PLAYER_RANK_DTO_FIELDS

    @respx.mock
    @pytest.mark.asyncio
    async def test_list_deprecated_club_id(self, api_key, base_url):
        route = respx.get(f"{base_url}/leaderboard").mock(
            return_value=Response(200, json={"players": []})
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.warns(DeprecationWarning, match="club_id is deprecated"):
                await client.leaderboard.list(club_id="club_1")

        params = route.calls.last.request.url.params
        assert "clubId" not in params
        assert set(params.keys()) <= LEADERBOARD_QUERY_DTO_FIELDS

    @respx.mock
    @pytest.mark.asyncio
    async def test_rank_minimal(self, api_key, base_url):
        """Rank call without state/city/club — should still succeed."""
        respx.post(f"{base_url}/leaderboard/rank").mock(
            return_value=Response(200, json={"rank": 1})
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.leaderboard.rank("vair_mem_42")
        assert result["rank"] == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_categories(self, api_key, base_url):
        respx.get(f"{base_url}/leaderboard/categories").mock(
            return_value=Response(
                200,
                json={
                    "categories": ["singles", "doubles", "mixed"],
                    "ageBrackets": ["open", "40+", "50+"],
                    "scopes": ["global", "state", "city"],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            data = await client.leaderboard.categories()

        assert "singles" in data["categories"]
        assert "50+" in data["ageBrackets"]
