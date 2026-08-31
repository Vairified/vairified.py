"""
client.events.withdraw and the ``mine`` filter — the two halves of reconciling a
catalogue. Without ``mine`` a partner cannot discover what it has listed; without
withdraw it cannot take anything down. Either one missing leaves stale listings
pointing at dead pages.

Mirrors tests/event-withdrawal.test.ts in vairified.js case for case.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from vairified import Vairified

WITHDRAWN = {
    "partnerEventId": "autumn-doubles-avon",
    "eventId": 48213,
    "withdrawn": True,
}


class TestEventsWithdraw:
    @respx.mock
    @pytest.mark.asyncio
    async def test_reports_the_listing_it_withdrew(self, api_key, base_url):
        respx.delete(f"{base_url}/partner/events/autumn-doubles-avon").mock(
            return_value=Response(200, json=WITHDRAWN)
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.events.withdraw("autumn-doubles-avon")

        assert result.partner_event_id == "autumn-doubles-avon"
        assert result.event_id == 48213
        assert result.withdrawn is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_already_withdrawn_is_a_success(self, api_key, base_url):
        # A reconciler retries whole batches; "already gone" is the expected
        # state, not a failure to handle.
        respx.delete(f"{base_url}/partner/events/autumn-doubles-avon").mock(
            return_value=Response(200, json={**WITHDRAWN, "withdrawn": False})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.events.withdraw("autumn-doubles-avon")

        assert result.withdrawn is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_url_encodes_the_identifier(self, api_key, base_url):
        # A partner's own identifier is free text and may contain a slash;
        # unencoded, it would change which path is requested.
        route = respx.delete(f"{base_url}/partner/events/a%2Fb").mock(
            return_value=Response(200, json={**WITHDRAWN, "partnerEventId": "a/b"})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.withdraw("a/b")

        assert route.called
        # ⚠️ Read the RAW url, not `.path` — httpx decodes `.path` back to
        # "a/b", so asserting on it reports a correct encoding as a failure.
        assert str(route.calls[0].request.url).endswith("/partner/events/a%2Fb")


class TestEventsListMine:
    PAGE = {"events": [], "total": 0}

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_mine_when_asked(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json=self.PAGE)
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.list(mine=True)

        assert route.called
        assert route.calls[0].request.url.params.get("mine") == "true"

    @respx.mock
    @pytest.mark.asyncio
    async def test_does_not_send_it_otherwise(self, api_key, base_url):
        # A filter sent by accident returns an empty catalogue to a caller
        # browsing the public one, which looks exactly like "there are no events".
        route = respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json=self.PAGE)
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.list(type="TOURNAMENT")

        assert route.called
        assert "mine" not in route.calls[0].request.url.params

    @respx.mock
    @pytest.mark.asyncio
    async def test_does_not_send_it_for_mine_false(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json=self.PAGE)
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.list(mine=False)

        assert route.called
        assert "mine" not in route.calls[0].request.url.params
