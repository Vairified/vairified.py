"""Tests for ``client.members.provision()`` — a VAIR identity per person."""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response
from pydantic import ValidationError as PydanticValidationError

from vairified import (
    AuthenticationError,
    ProvisionMemberInput,
    ProvisionMembersResult,
    ProvisionResult,
    Vairified,
    VairifiedError,
)
from vairified.errors import ValidationError

PAT = {"email": "Pat@Example.com", "first_name": "Pat", "last_name": "Rivera"}
PAT_WIRE = {"email": "Pat@Example.com", "firstName": "Pat", "lastName": "Rivera"}


def _route(base_url: str, body: object, status: int = 200) -> respx.Route:
    return respx.post(f"{base_url}/partner/members/provision").mock(
        return_value=Response(status, json=body)
    )


class TestProvisionRequestShape:
    @respx.mock
    @pytest.mark.asyncio
    async def test_posts_members_camel_cased_with_sport(self, api_key, base_url):
        route = _route(base_url, {"results": []})

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.members.provision([PAT], sport="pickleball")

        body = json.loads(route.calls.last.request.content)
        assert body == {"sport": "pickleball", "members": [PAT_WIRE]}

    @respx.mock
    @pytest.mark.asyncio
    async def test_omits_sport_and_unset_fields(self, api_key, base_url):
        route = _route(base_url, {"results": []})

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.members.provision(
                [
                    ProvisionMemberInput(
                        phone="+1-555-0100", first_name="Walk", last_name="Up"
                    )
                ]
            )

        body = json.loads(route.calls.last.request.content)
        assert body == {
            "members": [{"phone": "+1-555-0100", "firstName": "Walk", "lastName": "Up"}]
        }


class TestProvisionResults:
    @respx.mock
    @pytest.mark.asyncio
    async def test_created_ghost_carries_member_id(self, api_key, base_url):
        _route(
            base_url,
            {
                "results": [
                    {"ref": "pat@example.com", "status": "created", "memberId": 4900123}
                ]
            },
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.members.provision([PAT])

        assert isinstance(result, ProvisionMembersResult)
        pat = result.get(" Pat@Example.com")
        assert isinstance(pat, ProvisionResult)
        assert pat.is_created
        assert pat.member_id == 4900123
        assert pat.error is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_existing_record_has_no_id(self, api_key, base_url):
        _route(base_url, {"results": [{"ref": "pat@example.com", "status": "exists"}]})

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            pat = (await client.members.provision([PAT])).get("pat@example.com")

        assert pat is not None and pat.exists
        assert pat.member_id is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_never_exposes_an_id_on_a_non_created_result(self, api_key, base_url):
        _route(
            base_url,
            {
                "results": [
                    {"ref": "pat@example.com", "status": "exists", "memberId": 1001}
                ]
            },
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            pat = (await client.members.provision([PAT])).get("pat@example.com")

        assert pat is not None and pat.member_id is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_invalid_entry_carries_the_api_message(self, api_key, base_url):
        message = "An email address or phone number is required."
        _route(
            base_url,
            {
                "results": [
                    {
                        "ref": "#0",
                        "status": "invalid",
                        "error": {"code": "MISSING_CONTACT", "message": message},
                    }
                ]
            },
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.members.provision(
                [{"first_name": "No", "last_name": "Contact"}]
            )

        assert len(result.invalid) == 1
        error = result.invalid[0].error
        assert error is not None
        assert (error.code, error.message) == ("MISSING_CONTACT", message)

    @respx.mock
    @pytest.mark.asyncio
    async def test_splits_a_mixed_batch_and_finds_a_phone_ref(self, api_key, base_url):
        _route(
            base_url,
            {
                "results": [
                    {"ref": "pat@example.com", "status": "created", "memberId": 1},
                    {"ref": "+1-555-0100", "status": "exists"},
                    {
                        "ref": "#2",
                        "status": "invalid",
                        "error": {"code": "MISSING_NAME", "message": "x"},
                    },
                ]
            },
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.members.provision([PAT, PAT, PAT])

        assert (len(result.created), len(result.existing), len(result.invalid)) == (
            1,
            1,
            1,
        )
        found = result.get(" +1-555-0100")
        assert found is not None and found.exists

    @respx.mock
    @pytest.mark.asyncio
    async def test_models_are_frozen(self, api_key, base_url):
        _route(
            base_url,
            {
                "results": [
                    {"ref": "pat@example.com", "status": "created", "memberId": 1}
                ]
            },
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.members.provision([PAT])

        with pytest.raises(PydanticValidationError):
            result.results[0].member_id = 2  # type: ignore[misc]


class TestProvisionClientSideValidation:
    """These reject before any HTTP call — respx would raise on an unmocked request."""

    @pytest.mark.asyncio
    async def test_rejects_empty_list(self, api_key, base_url):
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError):
                await client.members.provision([])

    @pytest.mark.asyncio
    async def test_rejects_more_than_100(self, api_key, base_url):
        members = [{**PAT, "email": f"p{i}@example.com"} for i in range(101)]
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError):
                await client.members.provision(members)

    @respx.mock
    @pytest.mark.asyncio
    async def test_accepts_exactly_100(self, api_key, base_url):
        _route(base_url, {"results": []})
        members = [{**PAT, "email": f"p{i}@example.com"} for i in range(100)]
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            assert isinstance(
                await client.members.provision(members), ProvisionMembersResult
            )

    @pytest.mark.asyncio
    async def test_rejects_an_unknown_field_as_a_typo_guard(self, api_key, base_url):
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError):
                await client.members.provision([{**PAT, "emial": "x@example.com"}])


class TestProvisionErrorMapping:
    @respx.mock
    @pytest.mark.asyncio
    async def test_scope_or_trust_denial_is_a_403_vairified_error(
        self, api_key, base_url
    ):
        _route(
            base_url, {"message": "requires the `key:player:lookup` scope"}, status=403
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(VairifiedError) as info:
                await client.members.provision([PAT])

        assert info.value.status_code == 403

    @respx.mock
    @pytest.mark.asyncio
    async def test_bad_api_key_is_an_authentication_error(self, api_key, base_url):
        _route(base_url, {"message": "Invalid API key"}, status=401)

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(AuthenticationError):
                await client.members.provision([PAT])

    @respx.mock
    @pytest.mark.asyncio
    async def test_rejected_request_shape_is_a_validation_error(
        self, api_key, base_url
    ):
        _route(
            base_url,
            {"message": "members must contain no more than 100 elements"},
            status=400,
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError):
                await client.members.provision([PAT])
