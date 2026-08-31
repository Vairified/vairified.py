"""
client.events.submit — putting one of your own events into the directory.

The property worth pinning hardest is that the SDK sends ``partnerEventId``
through unchanged. It is the key the server upserts on, so an SDK that dropped or
renamed it would turn every republish into a NEW listing — and that failure is
invisible from the caller's side: each call returns 200 with a plausible listing,
and the directory quietly fills with duplicates.

Mirrors tests/event-submission.test.ts in vairified.js case for case, since the
two SDKs must not drift.
"""

from __future__ import annotations

import json

import pytest
import respx
from httpx import Response

from vairified import Vairified

SUBMISSION = {
    "partner_event_id": "autumn-doubles-avon",
    "sport_code": "pickleball",
    "name": "Autumn Doubles - Avon",
    "type": "TOURNAMENT",
    "registration_url": "https://example.com/register/autumn-doubles",
}

LISTED = {
    "partnerEventId": "autumn-doubles-avon",
    "eventId": 48213,
    "created": True,
}


class TestEventsSubmit:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_the_listing(self, api_key, base_url):
        respx.post(f"{base_url}/partner/events").mock(
            return_value=Response(200, json=LISTED)
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            listing = await client.events.submit(**SUBMISSION)

        assert listing.partner_event_id == "autumn-doubles-avon"
        assert listing.event_id == 48213
        assert listing.created is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_reports_an_update_as_created_false(self, api_key, base_url):
        # How a caller tells a republish from a first publish. A partner that
        # always sees False is reusing an identifier it did not mean to.
        respx.post(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={**LISTED, "created": False})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            listing = await client.events.submit(**SUBMISSION)

        assert listing.created is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_partner_event_id_unchanged(self, api_key, base_url):
        # The key the server upserts on. Renamed or dropped, every republish
        # becomes a new listing.
        route = respx.post(f"{base_url}/partner/events").mock(
            return_value=Response(200, json=LISTED)
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.submit(**SUBMISSION)

        # Presence before absence: the request must have been made at all.
        assert route.called
        body = json.loads(route.calls[0].request.content)
        assert body["partnerEventId"] == "autumn-doubles-avon"

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_the_sport_code(self, api_key, base_url):
        # A submitted event carries no sport of its own, so an SDK that dropped
        # this would have every listing read as pickleball whatever was passed.
        route = respx.post(f"{base_url}/partner/events").mock(
            return_value=Response(200, json=LISTED)
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.submit(**{**SUBMISSION, "sport_code": "padel"})

        assert route.called
        body = json.loads(route.calls[0].request.content)
        assert body["sportCode"] == "padel"

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_every_optional_field_it_was_given(self, api_key, base_url):
        # A field silently dropped by the SDK looks exactly like a field the
        # server ignored, and the listing is wrong in a way nobody is told about.
        route = respx.post(f"{base_url}/partner/events").mock(
            return_value=Response(200, json=LISTED)
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.submit(
                **SUBMISSION,
                description="Eight weeks of rotating partners.",
                start_date="2026-09-26T13:00:00Z",
                end_date="2026-09-27T22:00:00Z",
                host_name="SYNC United",
                max_spots=128,
                registration_fee="$65",
                registration_deadline="2026-09-20T00:00:00Z",
                location={
                    "venueName": "Picklr Avon",
                    "city": "Avon",
                    "state": "IN",
                    "latitude": 39.7628,
                    "longitude": -86.3997,
                },
            )

        assert route.called
        body = json.loads(route.calls[0].request.content)

        assert body["description"] == "Eight weeks of rotating partners."
        assert body["startDate"] == "2026-09-26T13:00:00Z"
        assert body["endDate"] == "2026-09-27T22:00:00Z"
        assert body["hostName"] == "SYNC United"
        assert body["maxSpots"] == 128
        assert body["registrationFee"] == "$65"
        assert body["registrationDeadline"] == "2026-09-20T00:00:00Z"
        assert body["location"]["latitude"] == 39.7628
        assert body["location"]["longitude"] == -86.3997

    @respx.mock
    @pytest.mark.asyncio
    async def test_omits_fields_it_was_not_given(self, api_key, base_url):
        # An explicit null is not the same as "unset"; sending one would clear
        # the field on a listing the caller only meant to rename.
        route = respx.post(f"{base_url}/partner/events").mock(
            return_value=Response(200, json=LISTED)
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.submit(**SUBMISSION)

        assert route.called
        body = json.loads(route.calls[0].request.content)

        # Presence first: the required fields must be there.
        assert body["name"] == "Autumn Doubles - Avon"
        assert "description" not in body
        assert "location" not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_posts_rather_than_gets(self, api_key, base_url):
        # The listing endpoint is a GET on the same path; a method mix-up would
        # read the catalogue instead of writing to it.
        route = respx.post(f"{base_url}/partner/events").mock(
            return_value=Response(200, json=LISTED)
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.submit(**SUBMISSION)

        assert route.called
        assert route.calls[0].request.method == "POST"

    @respx.mock
    @pytest.mark.asyncio
    async def test_the_model_is_frozen(self, api_key, base_url):
        respx.post(f"{base_url}/partner/events").mock(
            return_value=Response(200, json=LISTED)
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            listing = await client.events.submit(**SUBMISSION)

        with pytest.raises(Exception):
            listing.event_id = 1  # type: ignore[misc]
