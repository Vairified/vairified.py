"""
client.events.list — the event catalogue.

Two things are worth pinning beyond "it parses". First, that the filters actually
reach the wire: a query parameter silently dropped by the SDK looks identical to a
filter the server ignored, and the caller gets a plausible list of the wrong events
either way. Second, that an un-geocoded location surfaces as ``None`` rather than
``0`` — zero is a real coordinate, and a map would happily plot every such event in
the Gulf of Guinea.

Mirrors tests/events.test.ts in vairified.js case for case, since the two SDKs
must not drift.
"""

from __future__ import annotations

import pytest
import respx
from httpx import Response

from vairified import Vairified, ValidationError

EVENT = {
    "eventId": 12345,
    "name": "Fall Open",
    "type": "TOURNAMENT",
    "status": "UPCOMING",
    "sport": "pickleball",
    "startDate": "2026-09-01T18:00:00.000Z",
    "endDate": "2026-09-02T18:00:00.000Z",
    "club": {"name": "Riverside", "city": "Austin", "state": "TX"},
    "location": {
        "venueName": "Riverside Racquet Club",
        "address": "1200 Riverside Dr",
        "city": "Austin",
        "state": "TX",
        "zip": "78703",
        "latitude": 30.2849,
        "longitude": -97.7341,
    },
    "hostName": "Bart Brown",
    "isPrivate": False,
    "maxSpots": 64,
    "createdAt": "2026-08-01T00:00:00.000Z",
}


class TestEventsList:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_events_and_total(self, api_key, base_url):
        respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [EVENT], "total": 143})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            page = await client.events.list()

        assert page.total == 143
        assert len(page.events) == 1
        assert page.events[0].event_id == 12345
        assert page.events[0].name == "Fall Open"

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_every_filter_it_was_given(self, api_key, base_url):
        # A dropped parameter is indistinguishable from a server that ignored it.
        route = respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [], "total": 0})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.list(
                type="LEAGUE",
                date_from="2026-09-01T00:00:00.000Z",
                date_to="2026-12-31T00:00:00.000Z",
                lat=30.2849,
                lng=-97.7341,
                radius_miles=25,
                limit=5,
                offset=10,
            )

        params = route.calls.last.request.url.params
        assert params["type"] == "LEAGUE"
        assert params["dateFrom"] == "2026-09-01T00:00:00.000Z"
        assert params["dateTo"] == "2026-12-31T00:00:00.000Z"
        assert params["lat"] == "30.2849"
        assert params["lng"] == "-97.7341"
        assert params["radiusMiles"] == "25"
        assert params["limit"] == "5"
        assert params["offset"] == "10"

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_no_optional_filters_when_none_given(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [], "total": 0})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.list()

        params = route.calls.last.request.url.params
        # Presence before absence: pagination defaults ARE sent, and within that
        # populated query the optional filters are genuinely unset.
        assert params["limit"] == "20"
        assert params["offset"] == "0"
        assert "type" not in params
        assert "lat" not in params

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_zero_latitude_rather_than_dropping_it(self, api_key, base_url):
        # Latitude 0 is the equator, a real place a caller may search from.
        # `if lat:` would silently drop it and return the whole catalogue.
        route = respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [], "total": 0})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.list(lat=0, lng=0, radius_miles=25)

        params = route.calls.last.request.url.params
        assert params["lat"] == "0"
        assert params["lng"] == "0"


class TestEventLocation:
    @respx.mock
    @pytest.mark.asyncio
    async def test_exposes_venue_and_coordinates(self, api_key, base_url):
        respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [EVENT], "total": 1})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            event = (await client.events.list()).events[0]

        assert event.location is not None
        assert event.location.venue_name == "Riverside Racquet Club"
        assert event.location.latitude == 30.2849
        assert event.location.has_coordinates is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_missing_coordinates_are_none_never_zero(self, api_key, base_url):
        unlocated = {**EVENT, "location": {"city": "Austin", "state": "TX"}}
        respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [unlocated], "total": 1})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            event = (await client.events.list()).events[0]

        # Presence of the parent FIRST — asserting latitude is not 0 against a
        # None location would pass while proving nothing.
        assert event.location is not None
        assert event.location.city == "Austin"
        assert event.location.latitude is None
        assert event.location.longitude is None
        assert event.location.has_coordinates is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_location_is_none_when_absent(self, api_key, base_url):
        no_location = {k: v for k, v in EVENT.items() if k != "location"}
        respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [no_location], "total": 1})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            event = (await client.events.list()).events[0]

        # The event is present; only its place is unknown.
        assert event.event_id == 12345
        assert event.location is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_models_are_immutable(self, api_key, base_url):
        respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [EVENT], "total": 1})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            event = (await client.events.list()).events[0]

        with pytest.raises(Exception):
            event.name = "changed"


class TestEventsErrors:
    @respx.mock
    @pytest.mark.asyncio
    async def test_partial_location_filter_surfaces_as_validation_error(
        self, api_key, base_url
    ):
        # The API refuses lat without lng rather than ignoring it; the SDK must
        # not flatten that into an empty list.
        respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(
                400,
                json={"message": "A radius search needs lat, lng together."},
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError):
                await client.events.list(lat=30.2849)
