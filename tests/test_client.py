"""Tests for Vairified client."""

from datetime import datetime

import pytest
import respx
from httpx import Response

from vairified import Match, Player, RateLimitError, Vairified, VairifiedError


@pytest.fixture
def api_key():
    return "vair_pk_test123456789"


@pytest.fixture
def base_url():
    return "https://api-next.vairified.com/api/v1"


class TestVairified:
    """Tests for the Vairified client."""

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_member(self, api_key, base_url):
        """Test getting a member by ID."""
        respx.get(f"{base_url}/partner/member").mock(
            return_value=Response(
                200,
                json={
                    "id": "uuid-123",
                    "firstName": "John",
                    "lastName": "Doe",
                    "rating": 4.25,
                    "isVairified": True,
                    "ratingSplits": {"VG": 4.25, "VO": 4.10},
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            member = await client.get_member("clerk_user_123")

        assert member.id == "uuid-123"
        assert member.name == "John Doe"
        assert member.rating == 4.25
        assert member.is_vairified is True
        assert member.rating_splits.gender == 4.25  # VG maps to gender

    @respx.mock
    @pytest.mark.asyncio
    async def test_search(self, api_key, base_url):
        """Test searching for players."""
        respx.get(f"{base_url}/partner/search").mock(
            return_value=Response(
                200,
                json={
                    "players": [
                        {
                            "id": "uuid-1",
                            "firstName": "Jane",
                            "lastName": "Smith",
                            "city": "Austin",
                            "state": "TX",
                            "rating": 4.0,
                            "isVairified": True,
                            "ratingSplits": {},
                        }
                    ],
                    "total": 1,
                    "page": 1,
                    "limit": 20,
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            results = await client.search(city="Austin", state="TX")

        assert len(results) == 1
        assert results[0].name == "Jane Smith"
        assert results[0].city == "Austin"
        assert results.total == 1

    @respx.mock
    @pytest.mark.asyncio
    async def test_submit_match(self, api_key, base_url):
        """Test submitting a match."""
        respx.post(f"{base_url}/partner/matches").mock(
            return_value=Response(
                200,
                json={
                    "success": True,
                    "message": "1 match submitted, 2 games recorded",
                    "numMatches": 1,
                    "numGames": 2,
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            match = Match(
                event="Test League",
                bracket="4.0 Doubles",
                date=datetime.now(),
                team1=("p1", "p2"),
                team2=("p3", "p4"),
                scores=[(11, 9), (11, 7)],
            )
            result = await client.submit_match(match)

        assert result.success is True
        assert result.num_matches == 1
        assert result.num_games == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_get_rating_updates(self, api_key, base_url):
        """Test getting rating updates."""
        respx.get(f"{base_url}/partner/rating-updates").mock(
            return_value=Response(
                200,
                json={
                    "updates": [
                        {
                            "memberId": "uuid-1",
                            "previousRating": 4.0,
                            "newRating": 4.1,
                            "changedAt": "2026-01-21T12:00:00Z",
                        }
                    ]
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            updates = await client.get_rating_updates()

        assert len(updates) == 1
        assert updates[0].id == "uuid-1"
        assert updates[0].improved is True
        assert updates[0].change == pytest.approx(0.1)

    @respx.mock
    @pytest.mark.asyncio
    async def test_rate_limit_error(self, api_key, base_url):
        """Test rate limit handling."""
        respx.get(f"{base_url}/partner/member").mock(
            return_value=Response(
                429,
                json={"message": "Rate limit exceeded"},
                headers={"Retry-After": "60"},
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(RateLimitError) as exc_info:
                await client.get_member("user_123")

        assert exc_info.value.retry_after == 60

    @respx.mock
    @pytest.mark.asyncio
    async def test_api_error(self, api_key, base_url):
        """Test generic API error handling."""
        respx.get(f"{base_url}/partner/member").mock(
            return_value=Response(500, json={"message": "Internal server error"})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(VairifiedError) as exc_info:
                await client.get_member("user_123")

        assert exc_info.value.status_code == 500


class TestModels:
    """Tests for model classes."""

    def test_player_from_dict(self):
        """Test creating Player from dict."""
        data = {
            "id": "uuid-1",
            "firstName": "John",
            "lastName": "Doe",
            "rating": 4.25,
            "isVairified": True,
            "city": "Austin",
            "state": "TX",
            "ratingSplits": {"VG": 4.25, "VM": 4.1},
        }

        player = Player.from_dict(data)

        assert player.id == "uuid-1"
        assert player.name == "John Doe"
        assert player.rating == 4.25
        assert player.is_vairified is True
        assert player.rating_splits.gender == 4.25  # VG maps to gender
        assert player.rating_splits.mixed == 4.1  # VM maps to mixed
        assert player.verified_rating == 4.25

    def test_match_properties(self):
        """Test Match computed properties."""
        match = Match(
            event="Test",
            bracket="4.0 Doubles",
            date=datetime.now(),
            team1=("p1", "p2"),
            team2=("p3", "p4"),
            scores=[(11, 9), (9, 11), (11, 7)],
        )

        assert match.format == "DOUBLES"
        assert match.winner == 1
        assert match.score_summary == "11-9, 9-11, 11-7"

    def test_match_singles(self):
        """Test singles match format."""
        match = Match(
            event="Singles Tourney",
            bracket="Open Singles",
            date=datetime.now(),
            team1=("p1",),
            team2=("p2",),
            scores=[(11, 8), (11, 6)],
        )

        assert match.format == "SINGLES"
        assert match.winner == 1

    def test_match_to_dict(self):
        """Test Match serialization."""
        now = datetime(2026, 1, 21, 12, 0, 0)
        match = Match(
            event="Test League",
            bracket="4.0 Doubles",
            date=now,
            team1=("p1", "p2"),
            team2=("p3", "p4"),
            scores=[(11, 9)],
        )

        data = match.to_dict()

        assert data["event"] == "Test League"
        assert data["bracket"] == "4.0 Doubles"
        assert data["format"] == "DOUBLES"
        assert data["teamA"]["player1"] == "p1"
        assert data["teamA"]["player2"] == "p2"
        assert data["teamA"]["game1"] == 11
        assert data["teamB"]["game1"] == 9


def test_missing_api_key():
    """Test error when API key is missing."""
    import os

    os.environ.pop("VAIRIFIED_API_KEY", None)

    with pytest.raises(ValueError, match="API key required"):
        Vairified()
