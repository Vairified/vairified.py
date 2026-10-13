"""The rating-tracks release of Partner API v1.

Web labels on every split and sport, the recreational_gender / _mixed / _singles
splits, withheld verified-track splits, the eight leaderboard tracks, and the
leaderboard's 401 / 403 on a bad key. Mirrors ``tests/rating-tracks.test.ts``.
"""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest
import respx
from httpx import Response
from pydantic import ValidationError as PydanticValidationError

from vairified import (
    LEADERBOARD_CATEGORY_LABELS,
    AuthenticationError,
    LeaderboardCategory,
    LeaderboardCategoryInfo,
    Member,
    PermissionDeniedError,
    RatingUpdatedSport,
    Vairified,
    VairifiedError,
    ValidationError,
    is_rating_updated_event,
    verify_webhook,
)


class Payloads:
    """Realistic Partner API bodies for this release."""

    @staticmethod
    def member(sport: dict[str, Any]) -> dict[str, Any]:
        return {
            "memberId": 4873327,
            "firstName": "Mike",
            "lastName": "Barker",
            "fullName": "Mike Barker",
            "displayName": "Mike B.",
            "status": {
                "isWheelchair": False,
                "isAmbassador": False,
                "isVairPlus": False,
                "isConnected": True,
            },
            "sport": sport,
        }

    @classmethod
    def verified_player(cls) -> dict[str, Any]:
        """A player verified in pickleball: verified plus recreational tracks."""
        return cls.member(
            {
                "pickleball": {
                    "rating": 3.915,
                    "abbr": "VO",
                    "label": "VO",
                    "ratingSplits": {
                        "overall-open": {"rating": 3.915, "abbr": "VO", "label": "VO"},
                        "singles-12-13": {
                            "rating": 4.03,
                            "abbr": "S12-13",
                            "label": "VS12-13",
                        },
                        "recreational-open": {
                            "rating": 3.8,
                            "abbr": "Rv",
                            "label": "Rv",
                        },
                        "recreational_gender-open": {
                            "rating": 3.52,
                            "abbr": "RG",
                            "label": "RG",
                        },
                        "recreational_mixed-40+": {
                            "rating": 3.71,
                            "abbr": "RM40+",
                            "label": "RM40+",
                        },
                        "recreational_singles-open": {
                            "rating": 3.6,
                            "abbr": "RS",
                            "label": "RS",
                        },
                        "asymmetric-open": {"rating": 3.9, "abbr": "VA", "label": None},
                    },
                    "isVairified": True,
                    "isRater": False,
                    "isVairPro": False,
                    "isVairProStatus": None,
                }
            }
        )

    @classmethod
    def unverified_player(cls) -> dict[str, Any]:
        """Not verified in pickleball: no verified-track splits, primary is R."""
        return cls.member(
            {
                "pickleball": {
                    "rating": 3.42,
                    "abbr": "R",
                    "label": "RO",
                    "ratingSplits": {
                        "recreational-open": {
                            "rating": 3.42,
                            "abbr": "R",
                            "label": "RO",
                        },
                        "recreational_mixed-open": {
                            "rating": 3.3,
                            "abbr": "RM",
                            "label": "RM",
                        },
                    },
                    "isVairified": False,
                    "isRater": False,
                    "isVairPro": False,
                    "isVairProStatus": None,
                }
            }
        )

    @classmethod
    def legacy_player(cls) -> dict[str, Any]:
        """An older API response: no ``label`` anywhere."""
        return cls.member(
            {
                "pickleball": {
                    "rating": 3.915,
                    "abbr": "VO",
                    "ratingSplits": {"overall-open": {"rating": 3.915, "abbr": "VO"}},
                }
            }
        )

    @staticmethod
    def categories() -> dict[str, Any]:
        return {
            "categories": [
                {
                    "code": "overall",
                    "name": "Doubles",
                    "label": "VO",
                    "verifiedOnly": True,
                },
                {
                    "code": "gender",
                    "name": "Same-Gender Doubles",
                    "label": "VG",
                    "verifiedOnly": True,
                },
                {
                    "code": "singles",
                    "name": "Singles",
                    "label": "VS",
                    "verifiedOnly": True,
                },
                {
                    "code": "mixed",
                    "name": "Mixed Doubles",
                    "label": "VM",
                    "verifiedOnly": True,
                },
                {
                    "code": "recreational",
                    "name": "Recreational",
                    "label": "RO",
                    "verifiedOnly": False,
                    "verifiedLabel": "Rv",
                },
                {
                    "code": "recreational_gender",
                    "name": "Recreational Gender",
                    "label": "RG",
                    "verifiedOnly": False,
                },
                {
                    "code": "recreational_mixed",
                    "name": "Recreational Mixed",
                    "label": "RM",
                    "verifiedOnly": False,
                },
                {
                    "code": "recreational_singles",
                    "name": "Recreational Singles",
                    "label": "RS",
                    "verifiedOnly": False,
                },
            ],
            "ageBrackets": [{"code": "open", "name": "Open", "displayOrder": 0}],
            "scopes": [],
            "ratingTiers": [],
        }


class TestSplitLabels:
    def test_label_on_sport_and_every_split(self):
        pb = Member.model_validate(Payloads.verified_player()).sport["pickleball"]
        assert pb.label == "VO"
        split = pb["singles-12-13"]
        assert (split.rating, split.abbr, split.label) == (4.03, "S12-13", "VS12-13")
        assert pb["asymmetric-open"].label is None

    def test_recreational_track_keys(self):
        pb = Member.model_validate(Payloads.verified_player()).sport["pickleball"]
        assert pb["recreational_gender-open"].abbr == "RG"
        assert pb["recreational_mixed-40+"].label == "RM40+"
        assert pb["recreational_singles-open"].rating == 3.6
        assert len(pb) == 7

    def test_lookup_by_label(self):
        member = Member.model_validate(Payloads.verified_player())
        pb = member.sport["pickleball"]
        # ``abbr`` keeps the legacy ``S``; the label is what the web app shows.
        assert pb.by_label("VS12-13").abbr == "S12-13"
        assert pb.by_label("RM40+").rating == 3.71
        assert pb.by_label("XX") is None
        # Exact match, as the API sends it.
        assert pb.by_label("rv") is None
        assert member.split_by_label("RG").rating == 3.52
        assert member.split_by_label("RG", sport="padel") is None

    def test_label_defaults_to_none_on_an_older_api(self):
        pb = Member.model_validate(Payloads.legacy_player()).sport["pickleball"]
        assert pb.label is None
        assert pb["overall-open"].label is None
        assert pb.by_label("VO") is None

    def test_splits_are_immutable(self):
        split = Member.model_validate(Payloads.verified_player()).split("overall-open")
        with pytest.raises(PydanticValidationError):
            split.label = "XX"

    @respx.mock
    async def test_withheld_verified_splits_pass_through(self, api_key, base_url):
        respx.get(f"{base_url}/partner/member").mock(
            return_value=Response(200, json=Payloads.unverified_player())
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            member = await client.members.get("vair_mem_xxx")

        pb = member.sport["pickleball"]
        assert "overall-open" not in pb
        assert member.split("overall-open") is None
        # The primary is the recreational chain now, and rating_for() follows it.
        assert member.rating_for("pickleball") == 3.42
        assert (pb.abbr, pb.label, pb.is_vairified) == ("R", "RO", False)

    @respx.mock
    async def test_sport_with_nothing_visible_is_absent(self, api_key, base_url):
        respx.get(f"{base_url}/partner/member").mock(
            return_value=Response(200, json=Payloads.member({}))
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            member = await client.members.get("vair_mem_xxx")

        assert "pickleball" not in member.sport
        assert member.rating_for("pickleball") is None
        assert member.sports == []


class TestRatingUpdatesLabels:
    @respx.mock
    async def test_polled_update_carries_labels(self, api_key, base_url):
        respx.get(f"{base_url}/partner/rating-updates").mock(
            return_value=Response(
                200,
                json={
                    "updates": [
                        {
                            "memberId": 4873327,
                            "sport": "pickleball",
                            "previousRating": 3.5,
                            "newRating": 3.52,
                            "changedAt": "2026-10-13T10:00:00.000Z",
                            "ratingSplits": {
                                "recreational_gender-open": {
                                    "rating": 3.52,
                                    "abbr": "RG",
                                    "label": "RG",
                                },
                                "recreational-open": {"rating": 3.4, "abbr": "R"},
                            },
                        }
                    ]
                },
            )
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            [update] = await client.members.rating_updates()

        assert update.rating_splits["recreational_gender-open"].label == "RG"
        assert update.rating_splits["recreational-open"].label is None


class TestLeaderboardTracks:
    def test_exposes_the_eight_codes_and_the_labels(self):
        assert [c.value for c in LeaderboardCategory] == [
            "overall",
            "gender",
            "singles",
            "mixed",
            "recreational",
            "recreational_gender",
            "recreational_mixed",
            "recreational_singles",
        ]
        assert LEADERBOARD_CATEGORY_LABELS == (
            "VO",
            "VG",
            "VM",
            "VS",
            "S",
            "RO",
            "Rv",
            "R",
            "RG",
            "RM",
            "RS",
        )

    @pytest.mark.parametrize(
        ("category", "sent"),
        [
            ("recreational_gender", "recreational_gender"),
            ("recreational_mixed", "recreational_mixed"),
            ("recreational_singles", "recreational_singles"),
            (LeaderboardCategory.RECREATIONAL_SINGLES, "recreational_singles"),
            ("RG", "RG"),
            ("vs", "vs"),
        ],
    )
    @respx.mock
    async def test_list_forwards_category(self, api_key, base_url, category, sent):
        route = respx.get(f"{base_url}/leaderboard").mock(
            return_value=Response(200, json={"players": []})
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.leaderboard.list(category=category)

        assert route.calls.last.request.url.params["category"] == sent

    @respx.mock
    async def test_rank_defaults_to_overall(self, api_key, base_url):
        route = respx.post(f"{base_url}/leaderboard/rank").mock(
            return_value=Response(200, json={"qualified": True, "rank": 3})
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.leaderboard.rank("vair_mem_42")

        body = json.loads(route.calls.last.request.content)
        assert body["category"] == "overall"

    @respx.mock
    async def test_rank_serializes_an_enum_member(self, api_key, base_url):
        route = respx.post(f"{base_url}/leaderboard/rank").mock(
            return_value=Response(200, json={"qualified": True})
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.leaderboard.rank(
                "vair_mem_42", category=LeaderboardCategory.RECREATIONAL_GENDER
            )

        body = json.loads(route.calls.last.request.content)
        assert body["category"] == "recreational_gender"

    @respx.mock
    async def test_unknown_category_is_a_validation_error(self, api_key, base_url):
        respx.get(f"{base_url}/leaderboard").mock(
            return_value=Response(
                400,
                json={
                    "message": [
                        "category must be one of the following values: overall, gender"
                    ]
                },
            )
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError):
                await client.leaderboard.list(category="doubles")

    @respx.mock
    async def test_category_list_returns_models(self, api_key, base_url):
        respx.get(f"{base_url}/leaderboard/categories").mock(
            return_value=Response(200, json=Payloads.categories())
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            tracks = await client.leaderboard.category_list()

        assert len(tracks) == 8
        assert [t.code for t in tracks] == [c.value for c in LeaderboardCategory]
        assert all(isinstance(t, LeaderboardCategoryInfo) for t in tracks)
        singles = tracks[2]
        assert (singles.code, singles.label, singles.verified_only) == (
            "singles",
            "VS",
            True,
        )
        assert singles.verified_label is None
        rec = tracks[4]
        assert (rec.label, rec.verified_label, rec.verified_only) == ("RO", "Rv", False)
        with pytest.raises(PydanticValidationError):
            rec.label = "XX"

    @respx.mock
    async def test_category_list_empty_without_array(self, api_key, base_url):
        respx.get(f"{base_url}/leaderboard/categories").mock(
            return_value=Response(200, json={})
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            assert await client.leaderboard.category_list() == []


class TestLeaderboardKeyChecks:
    """A key that is sent is checked, even on the public routes."""

    ROUTES = [
        ("get", "/leaderboard", lambda c: c.leaderboard.list()),
        ("get", "/leaderboard/categories", lambda c: c.leaderboard.categories()),
        ("get", "/leaderboard/categories", lambda c: c.leaderboard.category_list()),
        ("post", "/leaderboard/rank", lambda c: c.leaderboard.rank("vair_mem_42")),
    ]

    @pytest.mark.parametrize(("method", "path", "call"), ROUTES)
    @respx.mock
    async def test_invalid_key_is_authentication_error(
        self, api_key, base_url, method, path, call
    ):
        respx.route(method=method.upper(), url=f"{base_url}{path}").mock(
            return_value=Response(
                401, json={"statusCode": 401, "message": "Invalid or expired API key"}
            )
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(AuthenticationError) as exc:
                await call(client)

        assert exc.value.status_code == 401
        assert exc.value.message == "Invalid or expired API key"

    @pytest.mark.parametrize(("method", "path", "call"), ROUTES)
    @respx.mock
    async def test_missing_scope_is_permission_denied(
        self, api_key, base_url, method, path, call
    ):
        respx.route(method=method.upper(), url=f"{base_url}{path}").mock(
            return_value=Response(
                403,
                json={
                    "statusCode": 403,
                    "message": (
                        "Insufficient scope. Required: leaderboard:read. "
                        "Your key has: none"
                    ),
                },
            )
        )
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(PermissionDeniedError) as exc:
                await call(client)

        # Still a VairifiedError, so existing ``except`` blocks keep working.
        assert isinstance(exc.value, VairifiedError)
        assert exc.value.status_code == 403


class TestRatingUpdatedWebhookTracks:
    SECRET = "whsec_rating_tracks_test"
    NOW = 1760350000

    def _sign(self, body: str) -> str:
        digest = hmac.new(
            self.SECRET.encode(), f"{self.NOW}.{body}".encode(), hashlib.sha256
        ).hexdigest()
        return f"t={self.NOW},v1={digest}"

    def test_snapshot_with_labels_and_recreational_tracks_parses(self):
        body = json.dumps(
            {
                "event": "rating.updated",
                "eventId": "evt_tracks",
                "timestamp": "2026-10-13T10:00:00.000Z",
                "data": {
                    "memberId": 7204743,
                    "sports": {
                        "pickleball": {
                            "rating": 3.42,
                            "abbr": "R",
                            "label": "RO",
                            "ratingSplits": {
                                "recreational-open": {
                                    "rating": 3.42,
                                    "abbr": "R",
                                    "label": "RO",
                                },
                                "recreational_gender-open": {
                                    "rating": 3.52,
                                    "abbr": "RG",
                                    "label": "RG",
                                },
                                "recreational_singles-40+": {
                                    "rating": 3.3,
                                    "abbr": "RS40+",
                                    "label": "RS40+",
                                    "someFutureKey": 1,
                                },
                            },
                            "isVairified": False,
                            "isRater": False,
                            "isVairPro": False,
                            "isVairProStatus": None,
                            "someFutureSportKey": "kept",
                        }
                    },
                    "changedAt": "2026-10-13T10:00:00.000Z",
                    "sequence": "40300",
                },
            }
        )

        event = verify_webhook(
            body, self._sign(body), self.SECRET, now_seconds=self.NOW
        )
        assert is_rating_updated_event(event)
        raw = event.data.sports["pickleball"]
        assert raw["ratingSplits"]["recreational_gender-open"]["label"] == "RG"
        assert "overall-open" not in raw["ratingSplits"]

        pb = RatingUpdatedSport.model_validate(raw)
        assert pb.label == "RO"
        assert pb.rating_splits["recreational_singles-40+"]["abbr"] == "RS40+"
        assert pb.model_extra == {"someFutureSportKey": "kept"}
