"""Tests for the Vairified SDK — Partner API v1 shape."""

from __future__ import annotations

import os
from typing import Any

import pytest
import respx
from httpx import Response

from vairified import (
    AuthenticationError,
    Game,
    Gender,
    Match,
    MatchBatch,
    Member,
    NotFoundError,
    RateLimitError,
    RatingUpdate,
    SportRating,
    Vairified,
    VairifiedError,
)

# ---------------------------------------------------------------------------
# Fixtures — realistic API payloads
# ---------------------------------------------------------------------------


def _member_payload(**overrides: Any) -> dict[str, Any]:
    """Build a realistic PartnerMember response body."""
    payload: dict[str, Any] = {
        "memberId": 4873327,
        "id": "0196a2e9-7b11-7f8c-bb3b-5f3d3e8fb4a2",
        "firstName": "Mike",
        "lastName": "Barker",
        "fullName": "Mike Barker",
        "displayName": "Mike B.",
        "age": 42,
        "city": "Austin",
        "state": "TX",
        "zip": "78701",
        "country": "US",
        "gender": "MALE",
        "status": {
            "isWheelchair": False,
            "isAmbassador": False,
            "isConnected": True,
        },
        "sport": {
            "pickleball": {
                "rating": 3.915,
                "abbr": "VO",
                "ratingSplits": {
                    "overall-open": {"rating": 3.915, "abbr": "VO"},
                    "gender-open": {"rating": 3.880, "abbr": "VG"},
                    "singles-open": {"rating": 3.710, "abbr": "S"},
                },
                "isVairified": True,
                "isRater": False,
                "isVairPro": False,
                "isVairProStatus": None,
            },
        },
        "activeLeagues": ["Austin Pickleball Club"],
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# Client construction
# ---------------------------------------------------------------------------


class TestClientConstruction:
    def test_requires_api_key(self):
        os.environ.pop("VAIRIFIED_API_KEY", None)
        with pytest.raises(ValueError, match="API key required"):
            Vairified()

    def test_env_from_kwarg(self, api_key):
        client = Vairified(api_key=api_key, env="staging")
        assert client.env == "staging"
        assert "staging" in client.base_url

    def test_unknown_env_rejected(self, api_key):
        with pytest.raises(ValueError, match="Unknown environment"):
            Vairified(api_key=api_key, env="mars")

    def test_base_url_overrides_env(self, api_key):
        client = Vairified(
            api_key=api_key,
            base_url="http://localhost:3001/api/v1",
        )
        assert client.base_url == "http://localhost:3001/api/v1"

    def test_has_sub_resources(self, api_key):
        client = Vairified(api_key=api_key, env="production")
        assert client.members is not None
        assert client.matches is not None
        assert client.oauth is not None
        assert client.leaderboard is not None
        assert client.webhooks is not None


# ---------------------------------------------------------------------------
# MembersResource
# ---------------------------------------------------------------------------


class TestMembersResource:
    @respx.mock
    @pytest.mark.asyncio
    async def test_get_member(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/member").mock(
            return_value=Response(200, json=_member_payload())
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            member = await client.members.get("vair_mem_xxx")

        # The deployed api-next keys the lookup on `memberId`; sending `id` 404s.
        params = route.calls.last.request.url.params
        assert params["memberId"] == "vair_mem_xxx"
        assert "id" not in params

        assert member.member_id == 4873327
        assert member.name == "Mike Barker"
        assert member.display_name == "Mike B."
        assert member.gender is Gender.MALE
        assert member.sport["pickleball"].is_vairified is True
        assert member.sport["pickleball"].is_vair_pro is False
        assert member.sport["pickleball"].is_vair_pro_status is None
        assert member.sports == ["pickleball"]
        assert member.rating_for("pickleball") == pytest.approx(3.915)
        assert member.rating_for("padel") is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_member_sport_filter(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/member").mock(
            return_value=Response(200, json=_member_payload())
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.members.get("vair_mem_xxx", sport="pickleball")

        assert route.called
        assert route.calls.last.request.url.params["sport"] == "pickleball"

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_member_multiple_sports(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/member").mock(
            return_value=Response(200, json=_member_payload())
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.members.get("vair_mem_xxx", sport=["pickleball", "padel"])

        assert route.calls.last.request.url.params["sport"] == "pickleball,padel"

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_auto_paginates(self, api_key, base_url):
        # First page: 2 results (page_size), second page: 1 result (short).
        page_1 = [_member_payload(memberId=1), _member_payload(memberId=2)]
        page_2 = [_member_payload(memberId=3)]
        responses = [
            Response(200, json=page_1),
            Response(200, json=page_2),
        ]
        respx.get(f"{base_url}/partner/search").mock(side_effect=responses)

        collected: list[int] = []
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            async for m in client.members.search(city="Austin", page_size=2):
                collected.append(m.member_id)

        assert collected == [1, 2, 3]

    @respx.mock
    @pytest.mark.asyncio
    async def test_search_max_results_caps(self, api_key, base_url):
        respx.get(f"{base_url}/partner/search").mock(
            return_value=Response(
                200,
                json=[
                    _member_payload(memberId=1),
                    _member_payload(memberId=2),
                    _member_payload(memberId=3),
                ],
            )
        )

        collected: list[int] = []
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            async for m in client.members.search(name="Mike", max_results=2):
                collected.append(m.member_id)

        assert collected == [1, 2]

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_returns_first(self, api_key, base_url):
        respx.get(f"{base_url}/partner/search").mock(
            return_value=Response(200, json=[_member_payload(memberId=42)])
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            member = await client.members.find("Mike")

        assert member is not None
        assert member.member_id == 42

    @respx.mock
    @pytest.mark.asyncio
    async def test_find_none(self, api_key, base_url):
        respx.get(f"{base_url}/partner/search").mock(
            return_value=Response(200, json=[])
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            member = await client.members.find("Nobody")

        assert member is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_rating_updates(self, api_key, base_url):
        respx.get(f"{base_url}/partner/rating-updates").mock(
            return_value=Response(
                200,
                json={
                    "updates": [
                        {
                            "memberId": 4873327,
                            "displayName": "Mike B.",
                            "sport": "pickleball",
                            "previousRating": 3.800,
                            "newRating": 3.915,
                            "changedAt": "2026-04-10T12:00:00Z",
                        },
                        {
                            "memberId": 999,
                            "sport": "pickleball",
                            "previousRating": 4.200,
                            "newRating": 4.150,
                            "changedAt": "2026-04-10T12:30:00Z",
                        },
                    ]
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            updates = await client.members.rating_updates()

        assert len(updates) == 2
        assert updates[0].improved is True
        assert updates[0].delta == pytest.approx(0.115)
        assert updates[1].improved is False
        assert updates[1].delta == pytest.approx(-0.05)


# ---------------------------------------------------------------------------
# MatchesResource
# ---------------------------------------------------------------------------


class TestMatchesResource:
    @respx.mock
    @pytest.mark.asyncio
    async def test_submit_batch(self, api_key, base_url):
        route = respx.post(f"{base_url}/partner/matches").mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "numMatches": 1,
                    "numGames": 2,
                    "message": "Submitted",
                },
            )
        )

        batch = MatchBatch(
            sport="pickleball",
            win_score=11,
            win_by=2,
            bracket="4.0 Doubles",
            event="Weekly League",
            match_date="2026-04-11T14:00:00Z",
            matches=[
                Match(
                    identifier="m1",
                    teams=[["p1", "p2"], ["p3", "p4"]],
                    games=[Game(scores=[11, 8]), Game(scores=[11, 5])],
                )
            ],
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.matches.submit(batch)

        assert result.ok is True
        assert result.num_matches == 1
        assert result.num_games == 2

        # Verify the request body was serialized with camelCase aliases.
        sent = route.calls.last.request.content
        assert b"winScore" in sent
        assert b"winBy" in sent
        assert b"matchDate" in sent

    @respx.mock
    @pytest.mark.asyncio
    async def test_submit_batch_n_team_n_game(self, api_key, base_url):
        """n-team × n-game batch — 3-team round robin, best-of-5."""
        respx.post(f"{base_url}/partner/matches").mock(
            return_value=Response(
                200,
                json={"success": True, "numMatches": 1, "numGames": 5},
            )
        )

        batch = MatchBatch(
            sport="pickleball",
            win_score=15,
            win_by=2,
            matches=[
                Match(
                    identifier="round-robin-1",
                    teams=[["a"], ["b"], ["c"]],
                    games=[
                        Game(scores=[15, 10, 8]),
                        Game(scores=[12, 15, 9]),
                        Game(scores=[15, 11, 13]),
                        Game(scores=[14, 15, 10]),
                        Game(scores=[15, 12, 11]),
                    ],
                ),
            ],
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.matches.submit(batch)

        assert result.ok is True
        assert batch.matches[0].num_teams == 3
        assert batch.matches[0].num_games == 5


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


class TestErrorMapping:
    @respx.mock
    @pytest.mark.asyncio
    async def test_rate_limit(self, api_key, base_url):
        respx.get(f"{base_url}/partner/member").mock(
            return_value=Response(
                429,
                json={"message": "Rate limit exceeded"},
                headers={"Retry-After": "60"},
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(RateLimitError) as exc_info:
                await client.members.get("vair_mem_xxx")

        assert exc_info.value.retry_after == 60

    @respx.mock
    @pytest.mark.asyncio
    async def test_not_found(self, api_key, base_url):
        respx.get(f"{base_url}/partner/member").mock(
            return_value=Response(404, json={"message": "Not found"})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(NotFoundError):
                await client.members.get("vair_mem_nope")

    @respx.mock
    @pytest.mark.asyncio
    async def test_auth_error(self, api_key, base_url):
        respx.get(f"{base_url}/partner/member").mock(
            return_value=Response(401, json={"message": "Invalid API key"})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(AuthenticationError):
                await client.members.get("vair_mem_xxx")

    @respx.mock
    @pytest.mark.asyncio
    async def test_generic_error(self, api_key, base_url):
        respx.get(f"{base_url}/partner/member").mock(
            return_value=Response(500, json={"message": "Internal error"})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(VairifiedError) as exc_info:
                await client.members.get("vair_mem_xxx")

        assert exc_info.value.status_code == 500


# ---------------------------------------------------------------------------
# Model construction / properties
# ---------------------------------------------------------------------------


class TestModels:
    def test_member_from_payload(self):
        member = Member.model_validate(_member_payload())

        assert member.member_id == 4873327
        assert member.name == "Mike Barker"
        assert member.gender is Gender.MALE
        assert member.sport["pickleball"].is_vairified is True

        # Sport-keyed access
        pb = member.sport["pickleball"]
        assert isinstance(pb, SportRating)
        assert pb.rating == pytest.approx(3.915)
        assert pb.abbr == "VO"

        # SportRating is dict-like
        assert len(pb) == 3
        assert "overall-open" in pb
        assert pb["overall-open"].rating == pytest.approx(3.915)
        assert pb.get("missing") is None
        assert set(pb.keys()) == {"overall-open", "gender-open", "singles-open"}

        # Convenience helpers
        assert member.rating_for("pickleball") == pytest.approx(3.915)
        split = member.split("singles-open")
        assert split is not None
        assert split.rating == pytest.approx(3.710)

    def test_member_is_immutable(self):
        member = Member.model_validate(_member_payload())
        with pytest.raises((TypeError, ValueError)):
            member.first_name = "Changed"  # type: ignore[misc]

    def test_member_tolerates_extra_fields(self):
        payload = _member_payload(someFutureField="value")
        # Should not raise — extra="allow" on response config.
        member = Member.model_validate(payload)
        assert member.member_id == 4873327

    def test_match_batch_serializes_camelcase(self):
        batch = MatchBatch(
            sport="pickleball",
            win_score=11,
            win_by=2,
            match_date="2026-04-11T14:00:00Z",
            matches=[
                Match(
                    identifier="m1",
                    teams=[["a", "b"], ["c", "d"]],
                    games=[Game(scores=[11, 9])],
                )
            ],
        )

        data = batch.model_dump(by_alias=True, exclude_none=True)
        assert data["winScore"] == 11
        assert data["winBy"] == 2
        assert data["matchDate"] == "2026-04-11T14:00:00Z"
        assert data["matches"][0]["teams"] == [["a", "b"], ["c", "d"]]
        assert "win_score" not in data  # snake_case should be aliased out

    def test_rating_update_delta_property(self):
        update = RatingUpdate.model_validate(
            {
                "memberId": 1,
                "previousRating": 4.0,
                "newRating": 4.1,
                "changedAt": "2026-04-10T12:00:00Z",
            }
        )
        assert update.delta == pytest.approx(0.1)
        assert update.improved is True

    def test_rating_update_delta_none_when_missing(self):
        update = RatingUpdate.model_validate(
            {"memberId": 1, "changedAt": "2026-04-10T12:00:00Z"}
        )
        assert update.delta is None
        assert update.improved is False
