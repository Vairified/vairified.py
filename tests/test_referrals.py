"""
client.referrals — reading and recording ambassador credit
(Vairified#1130, #1131).

The behaviour worth pinning is the part a caller acts on: telling "already
credited to my own host" from "credited to a stranger", and the four distinct
write outcomes. A boolean would leave them unable to decide anything.

Mirrors tests/referrals.test.ts in vairified.js case for case, since the two
SDKs must not drift.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from vairified import Vairified, ValidationError


class TestReferralsGet:
    @respx.mock
    @pytest.mark.asyncio
    async def test_reports_holders_and_claimable(self, api_key, base_url):
        respx.get(f"{base_url}/partner/members/attribution").mock(
            return_value=Response(
                200,
                json={
                    "attributions": [
                        {
                            "memberId": 4873327,
                            "attributed": True,
                            "ambassadorMemberId": 4873001,
                            "attributedAt": "2026-08-14",
                        },
                        {"memberId": 4873328, "attributed": False},
                    ],
                    "notFound": [999],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.referrals.get([4873327, 4873328, 999])

        held = result.get(4873327)
        assert held is not None
        assert held.ambassador_member_id == 4873001
        assert held.attributed_at == "2026-08-14"
        assert [a.member_id for a in result.claimable] == [4873328]
        assert result.not_found == [999]

    @respx.mock
    @pytest.mark.asyncio
    async def test_distinguishes_my_host_from_a_stranger(self, api_key, base_url):
        """
        The distinction the whole endpoint exists for: one is "nothing to do",
        the other is "a person must look before taking it".
        """
        respx.get(f"{base_url}/partner/members/attribution").mock(
            return_value=Response(
                200,
                json={
                    "attributions": [
                        {"memberId": 1, "attributed": True, "ambassadorMemberId": 500},
                        {"memberId": 2, "attributed": True, "ambassadorMemberId": 999},
                    ],
                    "notFound": [],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.referrals.get([1, 2])

        assert result.get(1).held_by_someone_other_than(500) is False
        assert result.get(2).held_by_someone_other_than(500) is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_held_credit_with_unknown_holder_is_not_claimable(
        self, api_key, base_url
    ):
        respx.get(f"{base_url}/partner/members/attribution").mock(
            return_value=Response(
                200,
                json={
                    "attributions": [
                        {"memberId": 1, "attributed": True, "ambassadorMemberId": None}
                    ],
                    "notFound": [],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.referrals.get([1])

        # "Held, but I cannot say by whom" must not read as claimable.
        entry = result.get(1)
        assert entry.attributed is True
        assert entry.is_claimable is False
        assert entry.ambassador_member_id is None

    @pytest.mark.asyncio
    async def test_rejects_empty_and_oversized_lists(self, api_key, base_url):
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError):
                await client.referrals.get([])
            with pytest.raises(ValidationError):
                await client.referrals.get(list(range(1, 102)))


class TestReferralsAttribute:
    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_code_date_and_ids(self, api_key, base_url):
        route = respx.post(f"{base_url}/partner/ambassador/attribution").mock(
            return_value=Response(
                200,
                json={
                    "attributed": 1,
                    "results": [{"memberId": 4873327, "outcome": "attributed"}],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.referrals.attribute(
                referral_code="  hillhurst-open  ",
                registration_published_at="2026-08-01",
                member_ids=[4873327],
            )

        assert result.attributed == 1
        # Trimmed, so a copy-pasted code with padding still resolves.
        assert b'"hillhurst-open"' in route.calls.last.request.content
        assert b'"2026-08-01"' in route.calls.last.request.content

    @respx.mock
    @pytest.mark.asyncio
    async def test_separates_the_four_outcomes(self, api_key, base_url):
        respx.post(f"{base_url}/partner/ambassador/attribution").mock(
            return_value=Response(
                200,
                json={
                    "attributed": 1,
                    "results": [
                        {"memberId": 1, "outcome": "attributed"},
                        {"memberId": 2, "outcome": "already_attributed"},
                        {"memberId": 3, "outcome": "account_predates_event"},
                        {"memberId": 4, "outcome": "not_found"},
                    ],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.referrals.attribute(
                referral_code="code",
                registration_published_at="2026-08-01",
                member_ids=[1, 2, 3, 4],
            )

        assert result.already_attributed == [2]
        assert result.predated_event == [3]
        assert result.with_outcome("not_found") == [4]
        assert result.with_outcome("attributed") == [1]

    @pytest.mark.asyncio
    async def test_rejects_a_non_iso_date(self, api_key, base_url):
        """
        A wrong date silently changes who is creditable, which is worse than an
        outright rejection.
        """
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError):
                await client.referrals.attribute(
                    referral_code="code",
                    registration_published_at="01/08/2026",
                    member_ids=[1],
                )

    @pytest.mark.asyncio
    async def test_rejects_blank_code_empty_and_oversized_lists(
        self, api_key, base_url
    ):
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError):
                await client.referrals.attribute(
                    referral_code="   ",
                    registration_published_at="2026-08-01",
                    member_ids=[1],
                )
            with pytest.raises(ValidationError):
                await client.referrals.attribute(
                    referral_code="c",
                    registration_published_at="2026-08-01",
                    member_ids=[],
                )
            with pytest.raises(ValidationError):
                await client.referrals.attribute(
                    referral_code="c",
                    registration_published_at="2026-08-01",
                    member_ids=list(range(1, 502)),
                )
