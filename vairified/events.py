"""
``client.events`` -- the event catalogue, and your own event listings.

Two scopes, held separately:

* ``key:event:read`` lists the catalogue and reads any public event and its
  roster.
* ``key:event:submit`` lists, updates, cancels and withdraws YOUR OWN events in
  Vairified's events directory, and sends each listing's confirmed members.
  ``key:write`` and ``key:admin`` do not imply it.
  A key holding only this scope can still read back its own listings --
  ``list(mine=True)``, and ``get`` / ``members`` on its own event ids -- so it
  can reconcile what it listed.

Kept in its own module rather than in :mod:`vairified.client`, which is already
large; reached as ``client.events`` exactly like every other sub-resource.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from vairified.errors import ValidationError
from vairified.event_models import (
    EventMembers,
    EventRosterResult,
    EventsPage,
    EventSubmission,
    PartnerEvent,
    SubmittedEvent,
    WithdrawnEvent,
)

if TYPE_CHECKING:
    from vairified.client import Vairified


def _zoned_param(value: datetime | str, name: str) -> str:
    """
    A ``dateFrom``/``dateTo`` query value.

    An aware ``datetime`` is sent as ISO 8601 with its offset. A naive one is
    refused before the round trip: the API refuses a date-time with no zone, and
    sending one without it would only move that same refusal a round trip later.
    Strings are passed through for the API to judge.
    """
    if isinstance(value, datetime):
        if value.utcoffset() is None:
            raise ValidationError(
                f"{name} must be a timezone-aware datetime; "
                "the API refuses a date-time with no time zone"
            )
        return value.isoformat()
    return value


class EventsResource:
    """
    Event catalogue reads; submitting or withdrawing your own listings, and
    sending their confirmed members.

    Errors map onto the SDK's usual exceptions: a 400 is a
    :class:`~vairified.errors.ValidationError`, a 404 a
    :class:`~vairified.errors.NotFoundError`, and a 403 or 409 a
    :class:`~vairified.errors.VairifiedError` whose ``status_code`` says which.
    """

    def __init__(self, client: Vairified) -> None:
        self._client = client

    async def list(
        self,
        *,
        mine: bool = False,
        type: str | None = None,
        date_from: datetime | str | None = None,
        date_to: datetime | str | None = None,
        lat: float | None = None,
        lng: float | None = None,
        radius_miles: float | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> EventsPage:
        """
        One page of events: what is on, near a point, within a date range.

        **Location.** ``lat``, ``lng`` and ``radius_miles`` go together; sending
        one or two of them is a 400 rather than a silently ignored filter.
        ``radius_miles`` is 1 to 250, and a larger radius is a 400, never
        narrowed. An event with no coordinates is excluded from a radius search.

        **Dates.** ``date_from``/``date_to`` match on OVERLAP, so a multi-day
        event is returned when the window falls anywhere inside it. Each must
        carry a time zone: a timezone-aware ``datetime``, or an ISO 8601 string
        with ``Z`` or an offset. A plain date is a 400.

        **Your own listings.** ``mine=True`` returns only the listings your app
        submitted, each with its ``partner_event_id``, ``removed`` and the fields
        you sent. A listing you withdrew is not returned; one Vairified removed
        is, with ``removed=True``, because re-sending it is refused. Needs an API
        key linked to a partner app (400 otherwise).

        :param mine: Only your own listings.
        :param type: Container type, e.g. ``"TOURNAMENT"``, ``"LEAGUE"``,
            ``"OPEN_PLAY"``. An unknown type is a 400, not an empty list.
        :param date_from: Only events that have not ended before this instant.
        :param date_to: Only events that have not started after this instant.
        :param lat: Latitude of the search centre.
        :param lng: Longitude of the search centre.
        :param radius_miles: Search radius in miles, 1 to 250.
        :param limit: Results per page, 1 to 100.
        :param offset: Pagination offset.
        :returns: An :class:`~vairified.event_models.EventsPage` with ``total``
            counted before pagination.
        :raises ValidationError: A naive ``datetime`` (before sending), or any
            filter the API refuses.
        :raises VairifiedError: 403 when the key lacks ``key:event:read`` -- a
            key holding only ``key:event:submit`` must pass ``mine=True``.

        Example::

            page = await client.events.list(
                type="TOURNAMENT", lat=30.2849, lng=-97.7341, radius_miles=25
            )
            for event in page.events:
                print(event.event_id, event.name, event.location)

            # Walk your own listings, a page at a time.
            offset = 0
            while True:
                page = await client.events.list(mine=True, offset=offset)
                ...
                offset += len(page.events)
                if not page.events or offset >= page.total:
                    break
        """
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        if mine:
            params["mine"] = "true"
        if type is not None:
            params["type"] = type
        if date_from is not None:
            params["dateFrom"] = _zoned_param(date_from, "date_from")
        if date_to is not None:
            params["dateTo"] = _zoned_param(date_to, "date_to")
        # `is not None`, never truthiness: latitude 0 is the equator, a real
        # place to search from, and `if lat:` would silently drop it.
        if lat is not None:
            params["lat"] = lat
        if lng is not None:
            params["lng"] = lng
        if radius_miles is not None:
            params["radiusMiles"] = radius_miles

        data = await self._client._request("GET", "/partner/events", params=params)
        return EventsPage.model_validate(data)

    async def get(self, event_id: int) -> PartnerEvent:
        """
        One event, by its integer id -- e.g. the ``event_id`` of an
        ``event.created`` webhook, or of :meth:`submit`'s result.

        On your own listing it also carries ``partner_event_id``, ``removed`` and
        the fields you sent.

        :param event_id: The integer event id. UUIDs are not accepted.
        :raises NotFoundError: No such event; a deleted one; a private one and
            your app is not TRUSTED; a listing Vairified removed; or, for a key
            holding only ``key:event:submit``, any event that is not your own.
        :raises VairifiedError: 403 when the key holds neither event scope.
        """
        data = await self._client._request("GET", f"/partner/event/{event_id}")
        return PartnerEvent.model_validate(data)

    async def members(self, event_id: int) -> EventMembers:
        """
        The players enrolled in an event, deduplicated, to seed your own
        brackets and pairings.

        Cancelled enrollments and deleted players are excluded. Each member's
        ``rating`` is their overall-open rating in the event's sport.

        **Your own listings.** The roster of a listing your app submitted is
        readable by your app only; to any other app it is a 404. It includes
        members who signed up on Vairified and are **waiting for you**
        (``enrollment_status="PENDING"``), with ``source`` and ``lapsed`` on
        every row: send them in :meth:`set_members` to confirm them. This read
        is also how you recover an ``event.registration`` notice you missed. A
        member who has not shared their profile with you, or who disconnected
        your app, comes back with their member number and status only, so
        ``first_name``, ``last_name``, ``is_vairified`` and ``is_vair_plus`` can
        be ``None``.

        :param event_id: The integer event id.
        :raises NotFoundError: Under the same conditions as :meth:`get`.
        :raises VairifiedError: 403 when the key holds neither event scope.
        """
        data = await self._client._request("GET", f"/partner/event/{event_id}/members")
        return EventMembers.model_validate(data)

    async def submit(self, submission: EventSubmission) -> SubmittedEvent:
        """
        List one of your events in Vairified's events directory, or bring the
        listing up to date.

        Players see it on that sport's events pages under your app's public name,
        and "Register" sends them to your ``registration_url``. No registration
        or payment happens on Vairified.

        **Send it again whenever anything changes.** The listing is keyed by your
        ``partner_event_id``: the same id updates the same listing and keeps its
        Vairified event id. A listing you withdrew is restored by submitting it
        again. Only the fields you set on the
        :class:`~vairified.event_models.EventSubmission` are sent -- leave one
        out to keep its current value, set it to ``None`` to clear it.

        Cancel with ``status="CANCELLED"``; ``status="UPCOMING"`` lists it again.
        ``end_date`` is required on every submission, like ``start_date``. An
        event whose end has passed can no longer be submitted or updated.

        Requires ``key:event:submit`` and an API key linked to your partner app.

        :returns: A :class:`~vairified.event_models.SubmittedEvent`; ``created``
            says whether this call created the listing or updated one.
        :raises ValidationError: 400 -- a field the API refuses (a missing
            ``end_date`` included), an unknown ``sport_code``, or an event that
            has already finished.
        :raises VairifiedError: 403 when the key lacks ``key:event:submit``, is
            not linked to a partner app, or the listing was removed by
            Vairified (contact Vairified; re-sending will not restore it).
            409 when the listing changed while saving -- send it again.

        Example::

            result = await client.events.submit(
                EventSubmission(
                    partner_event_id="autumn-doubles-avon",
                    sport_code="pickleball",
                    name="Autumn Doubles",
                    type="TOURNAMENT",
                    registration_url="https://example.com/register/autumn",
                    start_date=datetime(2026, 11, 14, 14, tzinfo=timezone.utc),
                    end_date=datetime(2026, 11, 15, 22, tzinfo=timezone.utc),
                )
            )
            print(result.event_id, "created" if result.created else "updated")
        """
        data = await self._client._request(
            "POST", "/partner/events", json=submission.to_body()
        )
        return SubmittedEvent.model_validate(data)

    async def withdraw(self, partner_event_id: str) -> WithdrawnEvent:
        """
        Take one of your listings out of the directory, by your own
        ``partner_event_id``.

        Reversible: submitting the same ``partner_event_id`` again restores it
        at the same Vairified event id. Withdrawing a listing that is already
        out of the directory succeeds with ``withdrawn=False``, so a batch is
        safe to retry.

        Requires ``key:event:submit``.

        :raises NotFoundError: You have no listing with that id.
        :raises VairifiedError: 403 when the key lacks ``key:event:submit`` or
            is not linked to a partner app.
        """
        data = await self._client._request(
            "DELETE", f"/partner/events/{quote(partner_event_id, safe='')}"
        )
        return WithdrawnEvent.model_validate(data)

    async def set_members(
        self, partner_event_id: str, member_ids: Iterable[int]
    ) -> EventRosterResult:
        """
        Send the WHOLE confirmed list for one of your listings, by Vairified
        member number. Send it whenever your roster changes; the listing's
        Vairified page then shows these members as going.

        **The whole list, every time.** A member confirmed before and missing
        now is cancelled (their Vairified page shows it as cancelled by your
        app, and they can register again). An empty list clears the roster.
        Sending the same list again changes nothing. A list longer than the
        listing's capacity is accepted. At most 2,000 member numbers; repeated
        numbers count once.

        **Members who signed up on Vairified** and are waiting for you
        (``PENDING`` in :meth:`members`) are confirmed when your list includes
        them, and left waiting when it does not.

        **Who you may list:** a member who gave your app the events permission
        (``user:event:register``, asked for in your Connect link), a player your
        app created, or anyone with a current Vairified sign-up on this listing.
        A TRUSTED app may list any member who has not disconnected it. A member
        who disconnected your app, TRUSTED or not, can be listed only where they
        hold a current Vairified sign-up. Anyone
        else comes back in ``refused`` with its reason, and everyone else on the
        list is still applied -- so check ``refused`` on every call.

        No ``event.registration`` notice is sent for changes your own list
        makes. Requires ``key:event:submit``.

        :param partner_event_id: Your own id for the listing, as you submitted it.
        :param member_ids: Every member confirmed on the listing.
        :returns: An :class:`~vairified.event_models.EventRosterResult` with the
            counts and every refused member number.
        :raises ValidationError: 400 -- more than 2,000 numbers, or a value that
            is not a whole member number.
        :raises NotFoundError: You have no listing with that id.
        :raises VairifiedError: 403 when the key lacks ``key:event:submit``, is
            not linked to a partner app, or the listing was removed by
            Vairified. 409 when the listing is withdrawn (submit it again first)
            or cancelled.

        Example::

            result = await client.events.set_members(
                "autumn-doubles-avon", [4873327, 4873330]
            )
            for refusal in result.refused:
                print(refusal.member_id, refusal.reason, refusal.message)
        """
        data = await self._client._request(
            "PUT",
            f"/partner/events/{quote(partner_event_id, safe='')}/members",
            json={"memberIds": list(member_ids)},
        )
        return EventRosterResult.model_validate(data)


__all__ = ["EventsResource"]
