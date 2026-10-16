"""
Partner event models -- the event catalogue, and a partner's own listings.

Read side (``client.events.list`` / ``get`` / ``members``) and write side
(``client.events.submit`` / ``withdraw``). Kept out of :mod:`vairified.models`,
which is already large, the same way the webhook event models live in
:mod:`vairified.webhook_models`.

Response models are frozen and tolerate new server-side fields, exactly like
every other response model in this package. The request models forbid unknown
fields, so a misspelt keyword fails when you build the submission rather than
being sent and silently ignored.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

from vairified.models import _REQUEST_CONFIG, _RESPONSE_CONFIG

# ---------------------------------------------------------------------------
# Read side
# ---------------------------------------------------------------------------


class EventClub(BaseModel):
    """The club an event belongs to, when it has one. Names the organisation."""

    model_config = _RESPONSE_CONFIG

    name: str
    city: str | None = None
    state: str | None = None

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EventClub {self.name!r}>"


class EventLocation(BaseModel):
    """
    Where an event is. Names the place, where :class:`EventClub` names the
    organisation.

    :rotating_light: ``latitude`` and ``longitude`` are ``None`` when the event
    has never been geocoded -- never ``0``. Zero is a real coordinate in the Gulf
    of Guinea, so a zero fallback would put every un-located event on one pin in
    the ocean. Such an event never appears in a radius search.
    """

    model_config = _RESPONSE_CONFIG

    venue_name: str | None = Field(default=None, alias="venueName")
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @property
    def has_coordinates(self) -> bool:
        """Whether this location can be placed on a map."""
        return self.latitude is not None and self.longitude is not None

    def __repr__(self) -> str:  # pragma: no cover
        where = self.venue_name or self.city or "unknown"
        return f"<EventLocation {where!r} coordinates={self.has_coordinates}>"


class EventCreator(BaseModel):
    """The member who created an event. Returned by :meth:`EventsResource.get` only."""

    model_config = _RESPONSE_CONFIG

    member_id: int = Field(alias="memberId")
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")


class PartnerEvent(BaseModel):
    """
    An event in the Vairified catalogue.

    ``event_id`` is the integer every event-scoped endpoint takes; the Partner
    API does not accept UUIDs.

    **Your own listings.** On an event YOUR app submitted with
    :meth:`EventsResource.submit` -- and only there -- the event also carries
    ``partner_event_id``, ``removed`` and the fields you sent, under the names you
    sent them. On anyone else's event every one of those is ``None``. Match your
    listings by ``partner_event_id``, never field by field: dates come back as UTC
    instants and ``status`` is the live status (a finished event reads
    ``COMPLETED``).
    """

    model_config = _RESPONSE_CONFIG

    event_id: int = Field(alias="eventId")
    name: str
    type: str
    """Container type, e.g. ``"TOURNAMENT"``, ``"LEAGUE"``, ``"OPEN_PLAY"``."""
    status: str
    """``UPCOMING``, ``IN_PROGRESS``, ``COMPLETED`` or ``CANCELLED``."""
    sport: str
    start_date: str | None = Field(default=None, alias="startDate")
    end_date: str | None = Field(default=None, alias="endDate")
    club: EventClub | None = None
    location: EventLocation | None = None
    """``None`` when the event records no venue, address or coordinates."""
    host_name: str | None = Field(default=None, alias="hostName")
    win_score: int | None = Field(default=None, alias="winScore")
    win_by: int | None = Field(default=None, alias="winBy")
    is_private: bool = Field(alias="isPrivate")
    max_spots: int | None = Field(default=None, alias="maxSpots")
    max_teams: int | None = Field(default=None, alias="maxTeams")
    created_by: EventCreator | None = Field(default=None, alias="createdBy")
    """Only :meth:`EventsResource.get` resolves the creator; the list never does."""
    created_at: str = Field(alias="createdAt")

    # ---- Your own listings only. None on every other event. ----

    partner_event_id: str | None = Field(default=None, alias="partnerEventId")
    """YOUR identifier for the listing. Never present on another partner's event."""
    removed: bool | None = None
    """
    ``True`` when Vairified took the listing down. Re-submitting it is refused
    (403), so stop sending it. Only ``list(mine=True)`` returns such a listing;
    one you withdrew is not returned at all.
    """
    description: str | None = None
    registration_url: str | None = Field(default=None, alias="registrationUrl")
    registration_deadline: str | None = Field(
        default=None, alias="registrationDeadline"
    )
    contact_email: str | None = Field(default=None, alias="contactEmail")
    contact_phone: str | None = Field(default=None, alias="contactPhone")
    registration_fee: float | None = Field(default=None, alias="registrationFee")
    player_format: str | None = Field(default=None, alias="playerFormat")
    gender: str | None = None
    rating_min: float | None = Field(default=None, alias="ratingMin")
    rating_max: float | None = Field(default=None, alias="ratingMax")
    rating_type: str | None = Field(default=None, alias="ratingType")
    rating_system: str | None = Field(default=None, alias="ratingSystem")
    age_min: int | None = Field(default=None, alias="ageMin")
    age_max: int | None = Field(default=None, alias="ageMax")
    external_url: str | None = Field(default=None, alias="externalUrl")
    sponsor_name: str | None = Field(default=None, alias="sponsorName")
    sponsor_banner_url: str | None = Field(default=None, alias="sponsorBannerUrl")
    logo_source_url: str | None = Field(default=None, alias="logoSourceUrl")
    """The logo URL you sent."""
    logo_url: str | None = Field(default=None, alias="logoUrl")
    """
    Vairified's stored copy of your logo, the one players see. ``None`` until the
    background fetch has stored it, and also when the image could not be used
    (not PNG, JPEG, GIF or WebP, over 2 MB, or unreachable). With nothing
    stored, submitting the same ``logo_url`` again tries again.
    """
    extras: dict[str, Any] | None = None
    """The free-form data you sent, returned as you sent it."""

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PartnerEvent #{self.event_id} {self.name!r} {self.type}>"


class EventsPage(BaseModel):
    """One page of :meth:`EventsResource.list`, with the total before pagination."""

    model_config = _RESPONSE_CONFIG

    events: list[PartnerEvent]
    total: int

    def __repr__(self) -> str:  # pragma: no cover
        return f"<EventsPage {len(self.events)} of {self.total}>"


class EventMember(BaseModel):
    """One enrolled player on an event's roster."""

    model_config = _RESPONSE_CONFIG

    member_id: int = Field(alias="memberId")
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    rating: float | None = None
    """Overall-open rating in the event's sport, truncated to 3 decimals."""
    is_vairified: bool = Field(alias="isVairified")
    is_vair_plus: bool = Field(alias="isVairPlus")
    """
    A **paid VAIR+ membership** -- check it when your event requires VAIR+. Not
    :attr:`is_paid`, which is this event's entry fee; the two are independent.
    """
    enrollment_status: str = Field(alias="enrollmentStatus")
    """``PENDING``, ``CONFIRMED``, ``COMPLETED`` or ``CANCELLED``."""
    is_paid: bool = Field(alias="isPaid")
    """Whether the player paid for their slot on THIS event."""


class EventMembers(BaseModel):
    """The roster returned by :meth:`EventsResource.members`."""

    model_config = _RESPONSE_CONFIG

    event_id: int = Field(alias="eventId")
    sport: str
    """Each member's ``rating`` is their rating in this sport."""
    members: list[EventMember] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Write side
# ---------------------------------------------------------------------------


def _require_zone(value: datetime | str | None) -> datetime | str | None:
    """
    Refuse a naive :class:`~datetime.datetime`.

    The API refuses a date-time that does not state its zone, because guessing
    one stores a different instant depending on whose clock read it. A naive
    ``datetime`` has nothing to send for the zone, so it is refused here rather
    than sent without one. Strings are passed through for the API to judge.
    """
    if isinstance(value, datetime) and value.utcoffset() is None:
        raise ValueError(
            "must be a timezone-aware datetime (e.g. tzinfo=timezone.utc); "
            "the API refuses a date-time with no time zone"
        )
    return value


class EventSubmissionLocation(BaseModel):
    """
    Where a submitted event is. Sent as ONE field: on a re-submission, leaving
    ``location`` out keeps the stored one and ``location=None`` clears it.

    Send ``latitude`` WITH ``longitude`` or neither. Coordinates you send are
    used exactly as given; without them Vairified places the event from its
    address.
    """

    model_config = _REQUEST_CONFIG

    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None
    latitude: float | None = None
    longitude: float | None = None


class EventSubmission(BaseModel):
    """
    One of your events, for :meth:`EventsResource.submit`.

    :rotating_light: **Leave a field out to keep its current value; set it to
    ``None`` to clear it.** Only the fields you actually set are sent, so an
    older integration that does not know a newer field can never erase it by
    re-submitting. ``location`` counts as one field.

    ``partner_event_id`` is YOUR identifier: submitting the same one again
    updates that listing (and restores it if you withdrew it). One submission is
    one place at one time -- an event at four venues is four submissions.

    **Dates** (``start_date``, ``end_date``, ``registration_deadline``) must
    carry a time zone. Pass a timezone-aware :class:`~datetime.datetime`, or an
    ISO 8601 string with ``Z`` or an offset (``2026-11-14T09:00:00-05:00``). A
    naive ``datetime`` is refused when you build the submission; a string with
    no zone, or a plain date, is refused by the API with a 400.

    Bounds the API enforces (a value outside them is a 400): ``max_spots`` and
    ``max_teams`` 1 to 100,000; ``registration_fee`` 0 to 100,000;
    ``rating_min``/``rating_max`` 2.0 to 8.0; ``age_min``/``age_max`` 1 to 99;
    ``extras`` at most 8 KB of JSON.

    Example::

        EventSubmission(
            partner_event_id="autumn-doubles-avon",
            sport_code="pickleball",
            name="Autumn Doubles",
            type="TOURNAMENT",
            registration_url="https://example.com/register/autumn-doubles",
            start_date=datetime(2026, 11, 14, 14, 0, tzinfo=timezone.utc),
            max_spots=128,
            location=EventSubmissionLocation(city="Austin", state="TX"),
        )
    """

    model_config = _REQUEST_CONFIG

    # ---- Required on every submission ----

    partner_event_id: str = Field(alias="partnerEventId")
    """
    YOUR id for the event: letters, digits and ``. _ : ~ -``, starting with a
    letter or digit, at most 200 characters. Unique per partner app.
    """
    sport_code: str = Field(alias="sportCode")
    """The Vairified sport code, e.g. ``"pickleball"``. No default; unknown is a 400."""
    name: str
    type: str
    """
    ``LEAGUE``, ``TOURNAMENT``, ``EVENT``, ``LADDER``, ``CLINIC``, ``SOCIAL`` or
    ``OPEN_PLAY``.
    """
    registration_url: str = Field(alias="registrationUrl")
    """Where a player registers (http or https). Nothing is paid on Vairified."""
    start_date: datetime | str = Field(alias="startDate")
    """Required, and it cannot be cleared."""

    # ---- Optional: omitted keeps the stored value, None clears it ----

    status: str | None = None
    """``UPCOMING`` lists the event (and un-cancels it); ``CANCELLED`` cancels it."""
    description: str | None = None
    end_date: datetime | str | None = Field(default=None, alias="endDate")
    """
    An event whose end has passed can no longer be submitted or updated, only
    withdrawn. With no end date that is 24 hours after its start.
    """
    registration_deadline: datetime | str | None = Field(
        default=None, alias="registrationDeadline"
    )
    host_name: str | None = Field(default=None, alias="hostName")
    contact_email: str | None = Field(default=None, alias="contactEmail")
    contact_phone: str | None = Field(default=None, alias="contactPhone")
    registration_fee: float | None = Field(default=None, alias="registrationFee")
    """Entry fee in USD, 0 to 100,000. Vairified takes no payment."""
    max_spots: int | None = Field(default=None, alias="maxSpots")
    """Capacity in individual players, 1 to 100,000."""
    max_teams: int | None = Field(default=None, alias="maxTeams")
    """Capacity in teams, 1 to 100,000."""
    player_format: str | None = Field(default=None, alias="playerFormat")
    """``singles``, ``doubles`` or ``mixed``."""
    gender: str | None = None
    """``male``, ``female`` or ``mixed``."""
    rating_min: float | None = Field(default=None, alias="ratingMin")
    rating_max: float | None = Field(default=None, alias="ratingMax")
    rating_type: str | None = Field(default=None, alias="ratingType")
    rating_system: str | None = Field(default=None, alias="ratingSystem")
    age_min: int | None = Field(default=None, alias="ageMin")
    age_max: int | None = Field(default=None, alias="ageMax")
    win_score: int | None = Field(default=None, alias="winScore")
    win_by: int | None = Field(default=None, alias="winBy")
    external_url: str | None = Field(default=None, alias="externalUrl")
    sponsor_name: str | None = Field(default=None, alias="sponsorName")
    sponsor_banner_url: str | None = Field(default=None, alias="sponsorBannerUrl")
    logo_url: str | None = Field(default=None, alias="logoUrl")
    """
    An https URL to a PNG, JPEG, GIF or WebP of at most 2 MB. Vairified fetches
    it in the background and shows its own stored copy; the listing is saved
    whether or not the logo can be used. To replace the image at the same
    address, send a new URL (a query-string version is enough).
    """
    location: EventSubmissionLocation | None = None
    extras: dict[str, Any] | None = None
    """Free-form data of your own, returned to you and never shown to players."""

    @field_validator("start_date", "end_date", "registration_deadline")
    @classmethod
    def dates_state_their_zone(
        cls, value: datetime | str | None
    ) -> datetime | str | None:
        """A naive datetime is refused here; see :func:`_require_zone`."""
        return _require_zone(value)

    def to_body(self) -> dict[str, Any]:
        """The JSON body: only the fields you set, under their wire names."""
        return self.model_dump(by_alias=True, exclude_unset=True, mode="json")


class SubmittedEvent(BaseModel):
    """Result of :meth:`EventsResource.submit`."""

    model_config = _RESPONSE_CONFIG

    partner_event_id: str = Field(alias="partnerEventId")
    """The identifier you supplied, echoed back."""
    event_id: int = Field(alias="eventId")
    """
    Vairified's integer id for the listing -- the one :meth:`EventsResource.get`
    takes. Stable across re-submissions, withdrawal and restore.
    """
    created: bool
    """
    ``True`` when this call created the listing; ``False`` when it updated (or
    restored) one you had already submitted under this ``partner_event_id``.
    """

    def __repr__(self) -> str:  # pragma: no cover
        what = "created" if self.created else "updated"
        return f"<SubmittedEvent {self.partner_event_id!r} #{self.event_id} {what}>"


class WithdrawnEvent(BaseModel):
    """Result of :meth:`EventsResource.withdraw`."""

    model_config = _RESPONSE_CONFIG

    partner_event_id: str = Field(alias="partnerEventId")
    """The identifier you asked to withdraw."""
    event_id: int = Field(alias="eventId")
    """Vairified's integer id for the listing."""
    withdrawn: bool
    """
    ``True`` when this call withdrew the listing; ``False`` when it was already
    out of the directory. Already-withdrawn is a success, so a batch is safe to
    retry.
    """

    def __repr__(self) -> str:  # pragma: no cover
        what = "withdrawn" if self.withdrawn else "already out"
        return f"<WithdrawnEvent {self.partner_event_id!r} #{self.event_id} {what}>"


__all__ = [
    "EventClub",
    "EventCreator",
    "EventLocation",
    "EventMember",
    "EventMembers",
    "EventSubmission",
    "EventSubmissionLocation",
    "EventsPage",
    "PartnerEvent",
    "SubmittedEvent",
    "WithdrawnEvent",
]
