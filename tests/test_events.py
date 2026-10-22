"""
client.events -- the event catalogue, and a partner's own listings
(Vairified#1194, #1195, #1320).

What is pinned here is what a partner acts on: the omit-versus-null rule on a
re-submission (an older integration must never erase a field it does not
know), the zone a date carries, the owner-only fields appearing on your own
listings and nowhere else, and each refusal arriving as the SDK's usual
exception rather than a bare HTTP error.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest
import respx
from httpx import Response

from vairified import (
    AuthenticationError,
    EventSubmission,
    EventSubmissionLocation,
    NotFoundError,
    RateLimitError,
    Vairified,
    VairifiedError,
    ValidationError,
)

CATALOGUE_EVENT = {
    "eventId": 12345,
    "name": "Austin Open",
    "type": "TOURNAMENT",
    "status": "UPCOMING",
    "sport": "pickleball",
    "startDate": "2026-11-14T14:00:00.000Z",
    "endDate": "2026-11-15T22:00:00.000Z",
    "club": {"name": "Riverside Club", "city": "Austin", "state": "TX"},
    "location": {
        "venueName": "Riverside Racquet Club",
        "address": "1200 Riverside Dr",
        "city": "Austin",
        "state": "TX",
        "zip": "78703",
        "latitude": 30.2849,
        "longitude": -97.7341,
    },
    "isPrivate": False,
    "maxSpots": 128,
    "createdAt": "2026-10-01T12:00:00.000Z",
}

OWN_LISTING = {
    "eventId": 48213,
    "partnerEventId": "autumn-doubles-avon",
    "name": "Autumn Doubles",
    "type": "TOURNAMENT",
    "status": "UPCOMING",
    "sport": "pickleball",
    "startDate": "2026-11-14T14:00:00.000Z",
    "location": {"city": "Avon", "state": "CO", "country": "US"},
    "isPrivate": False,
    "maxSpots": 100000,
    "maxTeams": 32,
    "createdAt": "2026-10-01T12:00:00.000Z",
    "removed": False,
    "registrationUrl": "https://example.com/register/autumn",
    "registrationFee": 65,
    "logoSourceUrl": "https://example.com/logo.png",
    "logoUrl": None,
    "extras": {"internalId": 7},
}

SUBMISSION_REQUIRED = {
    "partner_event_id": "autumn-doubles-avon",
    "sport_code": "pickleball",
    "name": "Autumn Doubles",
    "type": "TOURNAMENT",
    "registration_url": "https://example.com/register/autumn",
    "start_date": "2026-11-14T09:00:00-05:00",
    "end_date": "2026-11-15T17:00:00-05:00",
}


def _error(status: int, message: str) -> Response:
    return Response(
        status, json={"statusCode": status, "error": "Error", "message": message}
    )


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


class TestEventsList:
    @respx.mock
    @pytest.mark.asyncio
    async def test_parses_a_page_with_location_and_club(self, api_key, base_url):
        respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [CATALOGUE_EVENT], "total": 1})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            page = await client.events.list()

        assert page.total == 1
        event = page.events[0]
        assert event.event_id == 12345
        assert event.club is not None and event.club.name == "Riverside Club"
        assert event.location is not None
        assert event.location.venue_name == "Riverside Racquet Club"
        assert event.location.has_coordinates
        assert event.max_spots == 128
        # Another partner's (or VAIR's) event carries none of the owner fields.
        assert event.partner_event_id is None
        assert event.removed is None
        assert event.logo_url is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_an_ungeocoded_location_has_no_coordinates_not_zero(
        self, api_key, base_url
    ):
        unlocated = {**CATALOGUE_EVENT, "location": {"city": "Austin"}}
        respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [unlocated], "total": 1})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            page = await client.events.list()

        location = page.events[0].location
        assert location is not None
        assert location.latitude is None and location.longitude is None
        assert not location.has_coordinates

    @respx.mock
    @pytest.mark.asyncio
    async def test_mine_returns_owner_fields_including_removed(self, api_key, base_url):
        removed = {**OWN_LISTING, "partnerEventId": "gone", "removed": True}
        route = respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(
                200, json={"events": [OWN_LISTING, removed], "total": 2}
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            page = await client.events.list(mine=True)

        assert route.calls.last.request.url.params["mine"] == "true"
        own, taken_down = page.events
        assert own.partner_event_id == "autumn-doubles-avon"
        assert own.removed is False
        assert own.registration_url == "https://example.com/register/autumn"
        assert own.registration_fee == 65
        assert own.max_spots == 100000
        assert own.logo_source_url == "https://example.com/logo.png"
        assert own.logo_url is None  # not stored yet
        assert own.extras == {"internalId": 7}
        assert own.location is not None and own.location.country == "US"
        assert taken_down.removed is True

    @respx.mock
    @pytest.mark.asyncio
    async def test_sends_every_filter_under_its_wire_name(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [], "total": 0})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.list(
                type="TOURNAMENT",
                date_from=datetime(2026, 9, 1, tzinfo=timezone.utc),
                date_to="2026-12-31T23:59:59-05:00",
                lat=0.0,
                lng=-97.7341,
                radius_miles=250,
            )

        params = route.calls.last.request.url.params
        assert params["type"] == "TOURNAMENT"
        assert params["dateFrom"] == "2026-09-01T00:00:00+00:00"
        assert params["dateTo"] == "2026-12-31T23:59:59-05:00"
        # Latitude 0 is the equator, not "no filter".
        assert params["lat"] == "0.0"
        assert params["lng"] == "-97.7341"
        assert params["radiusMiles"] == "250"
        assert "mine" not in params

    @respx.mock
    @pytest.mark.asyncio
    async def test_an_offset_date_keeps_its_offset(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [], "total": 0})
        )
        eastern = timezone(timedelta(hours=-5))

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.list(
                date_from=datetime(2026, 11, 14, 9, tzinfo=eastern)
            )

        assert route.calls.last.request.url.params["dateFrom"] == (
            "2026-11-14T09:00:00-05:00"
        )

    @respx.mock
    @pytest.mark.asyncio
    async def test_a_naive_datetime_is_refused_before_sending(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [], "total": 0})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError, match="date_to"):
                await client.events.list(date_to=datetime(2026, 12, 31))

        assert not route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_pages_with_limit_and_offset(self, api_key, base_url):
        first = [{**CATALOGUE_EVENT, "eventId": n} for n in (1, 2)]
        second = [{**CATALOGUE_EVENT, "eventId": 3}]
        route = respx.get(f"{base_url}/partner/events").mock(
            side_effect=[
                Response(200, json={"events": first, "total": 3}),
                Response(200, json={"events": second, "total": 3}),
            ]
        )

        seen: list[int] = []
        async with Vairified(api_key=api_key, base_url=base_url) as client:
            offset = 0
            while True:
                page = await client.events.list(limit=2, offset=offset)
                seen.extend(e.event_id for e in page.events)
                offset += len(page.events)
                if not page.events or offset >= page.total:
                    break

        assert seen == [1, 2, 3]
        sent = [call.request.url.params for call in route.calls]
        assert [(p["limit"], p["offset"]) for p in sent] == [("2", "0"), ("2", "2")]

    @respx.mock
    @pytest.mark.asyncio
    async def test_defaults_to_the_first_page_of_twenty(self, api_key, base_url):
        route = respx.get(f"{base_url}/partner/events").mock(
            return_value=Response(200, json={"events": [], "total": 0})
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.list()

        params = route.calls.last.request.url.params
        assert (params["limit"], params["offset"]) == ("20", "0")

    @respx.mock
    @pytest.mark.asyncio
    async def test_a_refused_filter_is_a_validation_error(self, api_key, base_url):
        respx.get(f"{base_url}/partner/events").mock(
            return_value=_error(400, "radiusMiles must not be greater than 250")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError) as exc:
                await client.events.list(lat=30.0, lng=-97.0, radius_miles=500)

        assert exc.value.status_code == 400
        assert "250" in exc.value.message

    @respx.mock
    @pytest.mark.asyncio
    async def test_catalogue_without_read_scope_is_a_403(self, api_key, base_url):
        respx.get(f"{base_url}/partner/events").mock(
            return_value=_error(403, "Listing the event catalogue needs key:event:read")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(VairifiedError) as exc:
                await client.events.list()

        assert exc.value.status_code == 403

    @respx.mock
    @pytest.mark.asyncio
    async def test_bad_key_and_rate_limit_map_to_their_errors(self, api_key, base_url):
        respx.get(f"{base_url}/partner/events").mock(
            side_effect=[
                _error(401, "Invalid or expired API key"),
                Response(
                    429,
                    headers={"Retry-After": "30"},
                    json={"statusCode": 429, "message": "Too many requests"},
                ),
            ]
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(AuthenticationError):
                await client.events.list()
            with pytest.raises(RateLimitError) as exc:
                await client.events.list()

        assert exc.value.retry_after == 30


# ---------------------------------------------------------------------------
# get / members
# ---------------------------------------------------------------------------


class TestEventsGet:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_the_event_with_creator_and_rules(self, api_key, base_url):
        body = {
            **CATALOGUE_EVENT,
            "hostName": "Bart Brown",
            "winScore": 11,
            "winBy": 2,
            "createdBy": {"memberId": 5717273, "firstName": "Bart", "lastName": "B"},
        }
        respx.get(f"{base_url}/partner/event/12345").mock(
            return_value=Response(200, json=body)
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            event = await client.events.get(12345)

        assert event.event_id == 12345
        assert (event.win_score, event.win_by) == (11, 2)
        assert event.created_by is not None
        assert event.created_by.member_id == 5717273
        assert event.partner_event_id is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_your_own_listing_carries_what_you_sent(self, api_key, base_url):
        respx.get(f"{base_url}/partner/event/48213").mock(
            return_value=Response(200, json=OWN_LISTING)
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            event = await client.events.get(48213)

        assert event.partner_event_id == "autumn-doubles-avon"
        assert event.removed is False
        assert event.max_teams == 32

    @respx.mock
    @pytest.mark.asyncio
    async def test_an_event_you_may_not_read_is_not_found(self, api_key, base_url):
        respx.get(f"{base_url}/partner/event/999").mock(
            return_value=_error(404, "Event 999 not found.")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(NotFoundError):
                await client.events.get(999)


class TestEventsMembers:
    @respx.mock
    @pytest.mark.asyncio
    async def test_returns_the_roster(self, api_key, base_url):
        respx.get(f"{base_url}/partner/event/12345/members").mock(
            return_value=Response(
                200,
                json={
                    "eventId": 12345,
                    "sport": "pickleball",
                    "members": [
                        {
                            "memberId": 4873327,
                            "firstName": "Mike",
                            "lastName": "Barker",
                            "rating": 3.915,
                            "isVairified": True,
                            "isVairPlus": False,
                            "enrollmentStatus": "CONFIRMED",
                            "isPaid": True,
                        },
                        {
                            "memberId": 4873328,
                            "firstName": "New",
                            "lastName": "Player",
                            "isVairified": False,
                            "isVairPlus": True,
                            "enrollmentStatus": "PENDING",
                            "isPaid": False,
                        },
                    ],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            roster = await client.events.members(12345)

        assert roster.event_id == 12345
        assert roster.sport == "pickleball"
        rated, unrated = roster.members
        assert rated.rating == 3.915
        # VAIR+ membership and this event's entry fee are independent.
        assert (rated.is_vair_plus, rated.is_paid) == (False, True)
        assert unrated.rating is None
        assert unrated.enrollment_status == "PENDING"

    @respx.mock
    @pytest.mark.asyncio
    async def test_your_listing_roster_parses_a_number_only_row(
        self, api_key, base_url
    ):
        """
        On your own listing a member who disconnected your app, or never shared
        their profile, comes back as member number and status only. One such
        row must not fail the whole roster (review finding C AR-7), and the
        absent profile fields read as None -- "not shared", never "no".
        """
        respx.get(f"{base_url}/partner/event/48213/members").mock(
            return_value=Response(
                200,
                json={
                    "eventId": 48213,
                    "sport": "pickleball",
                    "members": [
                        {
                            "memberId": 4873327,
                            "firstName": "Mike",
                            "lastName": "Barker",
                            "rating": 3.915,
                            "isVairified": True,
                            "isVairPlus": True,
                            "enrollmentStatus": "CONFIRMED",
                            "isPaid": False,
                            "source": "PARTNER_LIST",
                            "lapsed": False,
                        },
                        {
                            "memberId": 4873399,
                            "enrollmentStatus": "PENDING",
                            "isPaid": False,
                            "source": "VAIR_SIGNUP",
                            "lapsed": True,
                        },
                    ],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            roster = await client.events.members(48213)

        full, number_only = roster.members
        assert full.source == "PARTNER_LIST"
        assert full.lapsed is False
        assert full.is_vair_plus is True
        assert number_only.member_id == 4873399
        assert number_only.enrollment_status == "PENDING"
        assert number_only.source == "VAIR_SIGNUP"
        assert number_only.lapsed is True
        assert number_only.is_paid is False
        assert (
            number_only.first_name,
            number_only.last_name,
            number_only.is_vairified,
            number_only.is_vair_plus,
            number_only.rating,
        ) == (None, None, None, None, None)

    @respx.mock
    @pytest.mark.asyncio
    async def test_another_events_rows_carry_no_listing_fields(self, api_key, base_url):
        respx.get(f"{base_url}/partner/event/12345/members").mock(
            return_value=Response(
                200,
                json={
                    "eventId": 12345,
                    "sport": "pickleball",
                    "members": [
                        {
                            "memberId": 1,
                            "firstName": "A",
                            "lastName": "B",
                            "isVairified": False,
                            "isVairPlus": False,
                            "enrollmentStatus": "CONFIRMED",
                            "isPaid": True,
                        }
                    ],
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            roster = await client.events.members(12345)

        member = roster.members[0]
        assert member.source is None
        assert member.lapsed is None

    @respx.mock
    @pytest.mark.asyncio
    async def test_unknown_event_is_not_found(self, api_key, base_url):
        respx.get(f"{base_url}/partner/event/999/members").mock(
            return_value=_error(404, "Event 999 not found.")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(NotFoundError):
                await client.events.members(999)


# ---------------------------------------------------------------------------
# submit
# ---------------------------------------------------------------------------


class TestEventsSubmit:
    @respx.mock
    @pytest.mark.asyncio
    async def test_creates_and_sends_only_the_fields_set(self, api_key, base_url):
        route = respx.post(f"{base_url}/partner/events").mock(
            return_value=Response(
                200,
                json={
                    "partnerEventId": "autumn-doubles-avon",
                    "eventId": 48213,
                    "created": True,
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.events.submit(
                EventSubmission(
                    **SUBMISSION_REQUIRED,
                    max_spots=100000,
                    max_teams=32,
                    logo_url="https://example.com/logo.png?v=2",
                    location=EventSubmissionLocation(city="Avon", state="CO"),
                )
            )

        assert result.created is True
        assert result.event_id == 48213
        assert result.partner_event_id == "autumn-doubles-avon"
        assert json.loads(route.calls.last.request.content) == {
            "partnerEventId": "autumn-doubles-avon",
            "sportCode": "pickleball",
            "name": "Autumn Doubles",
            "type": "TOURNAMENT",
            "registrationUrl": "https://example.com/register/autumn",
            "startDate": "2026-11-14T09:00:00-05:00",
            "endDate": "2026-11-15T17:00:00-05:00",
            "maxSpots": 100000,
            "maxTeams": 32,
            "logoUrl": "https://example.com/logo.png?v=2",
            "location": {"city": "Avon", "state": "CO"},
        }

    @respx.mock
    @pytest.mark.asyncio
    async def test_none_clears_a_field_and_omitting_keeps_it(self, api_key, base_url):
        """
        The rule an older integration depends on: a field it does not know is
        never sent, so a re-submission cannot erase it. Only an explicit None
        clears.
        """
        route = respx.post(f"{base_url}/partner/events").mock(
            return_value=Response(
                200,
                json={
                    "partnerEventId": "autumn-doubles-avon",
                    "eventId": 48213,
                    "created": False,
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.events.submit(
                EventSubmission(**SUBMISSION_REQUIRED, logo_url=None, location=None)
            )

        assert result.created is False
        body = json.loads(route.calls.last.request.content)
        assert body["logoUrl"] is None
        assert body["location"] is None
        for untouched in ("description", "maxSpots", "extras", "status"):
            assert untouched not in body

    @respx.mock
    @pytest.mark.asyncio
    async def test_aware_datetimes_are_sent_with_their_zone(self, api_key, base_url):
        route = respx.post(f"{base_url}/partner/events").mock(
            return_value=Response(
                200, json={"partnerEventId": "x", "eventId": 1, "created": True}
            )
        )
        eastern = timezone(timedelta(hours=-5))

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.submit(
                EventSubmission(
                    **{
                        **SUBMISSION_REQUIRED,
                        "start_date": datetime(2026, 11, 14, 14, tzinfo=timezone.utc),
                        "end_date": datetime(2026, 11, 15, 17, tzinfo=eastern),
                    },
                    status="CANCELLED",
                )
            )

        body = json.loads(route.calls.last.request.content)
        assert body["startDate"] == "2026-11-14T14:00:00Z"
        assert body["endDate"] == "2026-11-15T17:00:00-05:00"
        assert body["status"] == "CANCELLED"

    def test_a_naive_datetime_is_refused_when_building(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            EventSubmission(
                **{**SUBMISSION_REQUIRED, "start_date": datetime(2026, 11, 14, 9)}
            )

    def test_a_naive_end_date_is_refused_when_building(self):
        with pytest.raises(ValueError, match="timezone-aware"):
            EventSubmission(
                **{**SUBMISSION_REQUIRED, "end_date": datetime(2026, 11, 15, 17)}
            )

    @respx.mock
    @pytest.mark.asyncio
    async def test_end_date_is_required_and_nothing_is_sent_without_it(
        self, api_key, base_url
    ):
        """
        A listing must carry an end date (Vairified#1320): the API refuses one
        without it, so the submission refuses to be built rather than spending a
        round trip on the same answer. ``None`` cannot clear it either.
        """
        route = respx.post(f"{base_url}/partner/events").mock(
            return_value=Response(
                200, json={"partnerEventId": "x", "eventId": 1, "created": True}
            )
        )
        without = {k: v for k, v in SUBMISSION_REQUIRED.items() if k != "end_date"}

        # pydantic names a missing field by its wire name and a wrong value by
        # its Python name, so either spelling is the field.
        with pytest.raises(ValueError, match="endDate|end_date"):
            EventSubmission(**without)
        with pytest.raises(ValueError, match="endDate|end_date"):
            EventSubmission(**without, end_date=None)

        assert not route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_the_apis_end_date_refusal_is_a_validation_error(
        self, api_key, base_url
    ):
        respx.post(f"{base_url}/partner/events").mock(
            return_value=_error(
                400, "endDate is required, and a listing's end date cannot be cleared."
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError) as exc:
                await client.events.submit(EventSubmission(**SUBMISSION_REQUIRED))

        assert exc.value.status_code == 400
        assert "endDate" in exc.value.message

    def test_a_misspelt_field_is_refused_when_building(self):
        with pytest.raises(ValueError, match="max_spot"):
            EventSubmission(**SUBMISSION_REQUIRED, max_spot=10)

    @respx.mock
    @pytest.mark.asyncio
    async def test_a_refused_field_is_a_validation_error(self, api_key, base_url):
        respx.post(f"{base_url}/partner/events").mock(
            return_value=_error(400, "maxSpots must not be greater than 100000")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError) as exc:
                await client.events.submit(
                    EventSubmission(**SUBMISSION_REQUIRED, max_spots=9999999999)
                )

        assert "100000" in exc.value.message

    @respx.mock
    @pytest.mark.asyncio
    async def test_a_listing_vairified_removed_is_a_403(self, api_key, base_url):
        respx.post(f"{base_url}/partner/events").mock(
            return_value=_error(
                403,
                "That listing was removed by Vairified and cannot be restored by "
                "re-submitting it.",
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(VairifiedError) as exc:
                await client.events.submit(EventSubmission(**SUBMISSION_REQUIRED))

        assert exc.value.status_code == 403
        assert "removed by Vairified" in exc.value.message

    @respx.mock
    @pytest.mark.asyncio
    async def test_a_concurrent_change_is_a_409(self, api_key, base_url):
        respx.post(f"{base_url}/partner/events").mock(
            return_value=_error(409, "The listing changed while this submission ...")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(VairifiedError) as exc:
                await client.events.submit(EventSubmission(**SUBMISSION_REQUIRED))

        assert exc.value.status_code == 409


# ---------------------------------------------------------------------------
# withdraw
# ---------------------------------------------------------------------------


class TestEventsWithdraw:
    @respx.mock
    @pytest.mark.asyncio
    async def test_withdraws_by_your_own_id(self, api_key, base_url):
        route = respx.delete(f"{base_url}/partner/events/autumn-doubles-avon").mock(
            return_value=Response(
                200,
                json={
                    "partnerEventId": "autumn-doubles-avon",
                    "eventId": 48213,
                    "withdrawn": True,
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.events.withdraw("autumn-doubles-avon")

        assert route.called
        assert result.withdrawn is True
        assert result.event_id == 48213

    @respx.mock
    @pytest.mark.asyncio
    async def test_already_withdrawn_is_a_success(self, api_key, base_url):
        respx.delete(f"{base_url}/partner/events/autumn-doubles-avon").mock(
            return_value=Response(
                200,
                json={
                    "partnerEventId": "autumn-doubles-avon",
                    "eventId": 48213,
                    "withdrawn": False,
                },
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.events.withdraw("autumn-doubles-avon")

        assert result.withdrawn is False

    @respx.mock
    @pytest.mark.asyncio
    async def test_the_id_is_escaped_as_one_path_segment(self, api_key, base_url):
        route = respx.delete(f"{base_url}/partner/events/a%2Fb").mock(
            return_value=_error(404, "No listing found for 'a/b'.")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(NotFoundError):
                await client.events.withdraw("a/b")

        assert route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_an_id_you_never_submitted_is_not_found(self, api_key, base_url):
        respx.delete(f"{base_url}/partner/events/someone-elses").mock(
            return_value=_error(404, "No listing found for 'someone-elses'.")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(NotFoundError):
                await client.events.withdraw("someone-elses")

    @respx.mock
    @pytest.mark.asyncio
    async def test_a_key_without_an_app_is_a_403(self, api_key, base_url):
        respx.delete(f"{base_url}/partner/events/x").mock(
            return_value=_error(
                403, "This API key is not linked to a partner application"
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(VairifiedError) as exc:
                await client.events.withdraw("x")

        assert exc.value.status_code == 403


# ---------------------------------------------------------------------------
# set_members
# ---------------------------------------------------------------------------


def _roster_result(**overrides) -> dict:
    return {
        "partnerEventId": "autumn-doubles-avon",
        "eventId": 48213,
        "added": 0,
        "confirmed": 0,
        "unchanged": 0,
        "removed": 0,
        "refused": [],
        **overrides,
    }


class TestEventsSetMembers:
    @respx.mock
    @pytest.mark.asyncio
    async def test_puts_the_whole_list_and_returns_counts_and_refusals(
        self, api_key, base_url
    ):
        route = respx.put(
            f"{base_url}/partner/events/autumn-doubles-avon/members"
        ).mock(
            return_value=Response(
                200,
                json=_roster_result(
                    added=3,
                    confirmed=1,
                    unchanged=20,
                    removed=2,
                    refused=[
                        {
                            "memberId": 4873399,
                            "reason": "NO_EVENTS_PERMISSION",
                            "message": (
                                "This member hasn't given you the events permission."
                            ),
                        },
                        {
                            "memberId": 4873400,
                            "reason": "DISCONNECTED",
                            "message": (
                                "This member has disconnected your app, and holds no "
                                "current VAIR sign-up on this listing."
                            ),
                        },
                        {
                            "memberId": 9999999,
                            "reason": "UNKNOWN_MEMBER",
                            "message": "No VAIR member has this number.",
                        },
                    ],
                ),
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.events.set_members(
                "autumn-doubles-avon", [4873327, 4873330]
            )

        assert route.calls.last.request.method == "PUT"
        assert json.loads(route.calls.last.request.content) == {
            "memberIds": [4873327, 4873330]
        }
        assert result.partner_event_id == "autumn-doubles-avon"
        assert result.event_id == 48213
        assert (result.added, result.confirmed, result.unchanged, result.removed) == (
            3,
            1,
            20,
            2,
        )
        permission, disconnected, unknown = result.refused
        assert (permission.member_id, permission.reason) == (
            4873399,
            "NO_EVENTS_PERMISSION",
        )
        assert (disconnected.member_id, disconnected.reason) == (
            4873400,
            "DISCONNECTED",
        )
        assert disconnected.message.startswith("This member has disconnected")
        assert unknown.reason == "UNKNOWN_MEMBER"

    @respx.mock
    @pytest.mark.asyncio
    async def test_an_empty_list_is_sent_as_an_empty_list(self, api_key, base_url):
        """An empty list clears the roster, so it must be sent, never dropped."""
        route = respx.put(
            f"{base_url}/partner/events/autumn-doubles-avon/members"
        ).mock(return_value=Response(200, json=_roster_result(removed=4)))

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.events.set_members("autumn-doubles-avon", [])

        assert json.loads(route.calls.last.request.content) == {"memberIds": []}
        assert result.removed == 4
        assert result.refused == []

    @respx.mock
    @pytest.mark.asyncio
    async def test_any_iterable_of_numbers_is_sent_as_a_list(self, api_key, base_url):
        route = respx.put(
            f"{base_url}/partner/events/autumn-doubles-avon/members"
        ).mock(return_value=Response(200, json=_roster_result(added=2)))

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            await client.events.set_members(
                "autumn-doubles-avon", (n for n in (4873327, 4873330))
            )

        assert json.loads(route.calls.last.request.content) == {
            "memberIds": [4873327, 4873330]
        }

    @respx.mock
    @pytest.mark.asyncio
    async def test_a_reason_this_version_does_not_know_is_handed_over(
        self, api_key, base_url
    ):
        """A new refusal reason must not fail the whole response."""
        respx.put(f"{base_url}/partner/events/x/members").mock(
            return_value=Response(
                200,
                json=_roster_result(
                    partnerEventId="x",
                    refused=[
                        {"memberId": 1, "reason": "SOMETHING_NEW", "message": "..."}
                    ],
                ),
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            result = await client.events.set_members("x", [1])

        assert result.refused[0].reason == "SOMETHING_NEW"

    @respx.mock
    @pytest.mark.asyncio
    async def test_the_id_is_escaped_as_one_path_segment(self, api_key, base_url):
        route = respx.put(f"{base_url}/partner/events/a%2Fb/members").mock(
            return_value=_error(404, "No listing found for 'a/b'.")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(NotFoundError):
                await client.events.set_members("a/b", [1])

        assert route.called

    @respx.mock
    @pytest.mark.asyncio
    async def test_over_the_cap_is_a_validation_error(self, api_key, base_url):
        respx.put(f"{base_url}/partner/events/x/members").mock(
            return_value=_error(400, "memberIds holds at most 2000 member numbers.")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(ValidationError) as exc:
                await client.events.set_members("x", list(range(1, 2002)))

        assert "2000" in exc.value.message

    @respx.mock
    @pytest.mark.asyncio
    async def test_a_withdrawn_listing_is_a_409(self, api_key, base_url):
        respx.put(f"{base_url}/partner/events/x/members").mock(
            return_value=_error(
                409, "This listing is withdrawn; send the event again first."
            )
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(VairifiedError) as exc:
                await client.events.set_members("x", [1])

        assert exc.value.status_code == 409

    @respx.mock
    @pytest.mark.asyncio
    async def test_a_listing_vairified_removed_is_a_403(self, api_key, base_url):
        respx.put(f"{base_url}/partner/events/x/members").mock(
            return_value=_error(403, "That listing was removed by Vairified.")
        )

        async with Vairified(api_key=api_key, base_url=base_url) as client:
            with pytest.raises(VairifiedError) as exc:
                await client.events.set_members("x", [1])

        assert exc.value.status_code == 403
