"""Tests for ``client.members.get_by_email()`` — email lookup (Vairified#995)."""

from __future__ import annotations

from typing import Any

import pytest
import respx
from httpx import Response

from vairified import (
    AuthenticationError,
    MembersByEmailResult,
    Vairified,
    VairifiedError,
)
from vairified.errors import ValidationError


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
                },
                "isVairified": True,
                "isRater": False,
                "isVairPro": False,
                "isVairProStatus": None,
            },
        },
    }
    payload.update(overrides)
    return payload


class TestGetByEmailRequestShape:
    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_addresses_comma_joined(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(
                200,
                json={"matched": [], "notFound": ["a@example.com", "b@example.com"]},
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.members.get_by_email(["a@example.com", "b@example.com"])

        params = route.calls.last.request.url.params
        assert params["emails"] == "a@example.com,b@example.com"
        assert "sport" not in params

    @respx.mock
    @pytest.mark.asyncio
    async def test_passes_sport_filter(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(
                200, json={"matched": [], "notFound": ["a@example.com"]}
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.members.get_by_email(["a@example.com"], sport="pickleball")

        assert route.calls.last.request.url.params["sport"] == "pickleball"


class TestGetByEmailClientSideValidation:
    """These reject before any HTTP call — respx would raise on an unmocked request."""

    @pytest.mark.asyncio
    async def test_rejects_empty_list(self, api_key, base_url):
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError):
                await client.members.get_by_email([])

    @pytest.mark.asyncio
    async def test_rejects_more_than_100(self, api_key, base_url):
        emails = [f"p{i}@example.com" for i in range(101)]
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError):
                await client.members.get_by_email(emails)

    @respx.mock
    @pytest.mark.asyncio
    async def test_accepts_exactly_100(self, api_key, base_url):
        respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(200, json={"matched": [], "notFound": []})
        )
        emails = [f"p{i}@example.com" for i in range(100)]

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.members.get_by_email(emails)

        assert isinstance(result, MembersByEmailResult)

    @pytest.mark.asyncio
    async def test_rejects_embedded_comma(self, api_key, base_url):
        # Joining on "," means an embedded comma would become two addresses
        # server-side and shift every subsequent result.
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError):
                await client.members.get_by_email(["a@example.com,b@example.com"])


class TestGetByEmailResponseHandling:
    @respx.mock
    @pytest.mark.asyncio
    async def test_accounts_for_every_address(self, api_key, base_url):
        respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(
                200,
                json={
                    "matched": [
                        {"email": "ada@example.com", "members": [_member_payload()]}
                    ],
                    "notFound": ["nobody@example.com"],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.members.get_by_email(
                ["ada@example.com", "nobody@example.com"]
            )

        accounted = sorted([m.email for m in result.matched] + list(result.not_found))
        assert accounted == ["ada@example.com", "nobody@example.com"]
        assert result.all_resolved is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_hydrates_members(self, api_key, base_url):
        respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(
                200,
                json={
                    "matched": [
                        {"email": "ada@example.com", "members": [_member_payload()]}
                    ],
                    "notFound": [],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.members.get_by_email(["ada@example.com"])

        member = result.matched[0].sole
        assert member is not None
        assert member.member_id == 4873327
        assert member.rating_for("pickleball") == pytest.approx(3.915)
        assert result.all_resolved is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_multiple_members_for_one_address(self, api_key, base_url):
        respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(
                200,
                json={
                    "matched": [
                        {
                            "email": "shared@example.com",
                            "members": [
                                _member_payload(),
                                _member_payload(memberId=999),
                            ],
                        }
                    ],
                    "notFound": [],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.members.get_by_email(["shared@example.com"])

        match = result.matched[0]
        assert len(match.members) == 2
        assert match.is_ambiguous is True
        # `sole` refuses to guess when the address is ambiguous — the whole
        # point of the list shape is that a second match can never hide.
        assert match.sole is None
        assert result.member_count == 2

    @respx.mock
    @pytest.mark.asyncio
    async def test_lookup_is_case_insensitive(self, api_key, base_url):
        respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(
                200,
                json={
                    "matched": [
                        {"email": "Ada@Example.com", "members": [_member_payload()]}
                    ],
                    "notFound": [],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.members.get_by_email(["Ada@Example.com"])

        found = result.get("ada@example.com")
        assert found is not None
        assert found.sole is not None
        assert found.sole.member_id == 4873327
        assert result.get("  ADA@EXAMPLE.COM  ") is not None
        assert result.get("someone.else@example.com") is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_tolerates_envelope_missing_arrays(self, api_key, base_url):
        # Defensive: an older or partial deployment must not raise inside the SDK.
        respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(200, json={})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.members.get_by_email(["a@example.com"])

        assert result.matched == []
        assert result.not_found == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_tolerates_a_bare_array_body(self, api_key, base_url):
        # Not hypothetical: the sibling GET /partner/members?ids= returns a bare
        # PartnerMember[], so a routing or gateway mistake can land that shape on
        # this path. The envelope is the whole point of this endpoint, so degrade
        # to an empty result rather than raising a validation error at the caller.
        respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(200, json=[])
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.members.get_by_email(["a@example.com"])

        assert isinstance(result, MembersByEmailResult)
        assert result.matched == []
        assert result.not_found == []
        assert result.all_resolved is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_tolerates_an_empty_body(self, api_key, base_url):
        # A 200 with no body at all — a proxy or a partial deployment. `_request`
        # yields None for an empty response, which must not reach model_validate.
        respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(200, content=b"")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.members.get_by_email(["a@example.com"])

        assert isinstance(result, MembersByEmailResult)
        assert result.matched == []
        assert result.not_found == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_result_is_frozen(self, api_key, base_url):
        respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(
                200,
                json={
                    "matched": [
                        {"email": "ada@example.com", "members": [_member_payload()]}
                    ],
                    "notFound": ["x@example.com"],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.members.get_by_email(
                ["ada@example.com", "x@example.com"]
            )

        with pytest.raises(Exception):
            result.not_found = []  # type: ignore[misc]
        with pytest.raises(Exception):
            result.matched[0].email = "other@example.com"  # type: ignore[misc]


class TestGetByEmailErrorMapping:
    @respx.mock
    @pytest.mark.asyncio
    async def test_scope_denial(self, api_key, base_url):
        # The endpoint requires key:player:lookup, which is NOT implied by
        # key:player:search — a partner with only search access gets a 403.
        respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(
                403, json={"message": "Insufficient scope. Required: key:player:lookup"}
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(VairifiedError):
                await client.members.get_by_email(["a@example.com"])

    @respx.mock
    @pytest.mark.asyncio
    async def test_bad_api_key(self, api_key, base_url):
        respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(401, json={"message": "Invalid API key"})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(AuthenticationError):
                await client.members.get_by_email(["a@example.com"])

    @respx.mock
    @pytest.mark.asyncio
    async def test_server_side_cap_rejection(self, api_key, base_url):
        respx.get(f"{base_url}/partner/members/by-email").mock(
            return_value=Response(
                400, json={"message": "Too many emails: 101. Maximum 100 per request."}
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError):
                await client.members.get_by_email(["a@example.com"])
