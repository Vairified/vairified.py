"""
Typed models for the partner webhook events.

A separate module from :mod:`vairified.models` on purpose. That file is already
past this project's file-size budget, and its ``__all__`` sits mid-file with
classes defined after it, so appending lands below the export list. The
TypeScript SDK puts its webhook types in their own file too, and a structural
split in one SDK and not the other is itself a parity defect.

**Enum-shaped fields are plain ``str``, never ``Literal``.** These payloads are
produced by a service that ships independently of this package, so a closed set
is wrong the moment the API adds a value -- and it fails in a partner's live
handler rather than at their type-check step. ``connection.revoked`` carried
exactly one ``reason`` for its whole life and a second arrived while this file
was being written. The known values are documented on each field instead.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from .models import SportRating

__all__ = [
    "ConnectionRevokedEvent",
    "ConnectionRevokedEventData",
    "EventCreatedClub",
    "EventCreatedEvent",
    "EventCreatedEventData",
    "MemberStatusEvent",
    "MemberStatusEventData",
    "MemberStatusEventSport",
    "RatingUpdatedEvent",
    "RatingUpdatedEventData",
    "UnknownWebhookEvent",
    "VerifiedWebhookEvent",
    "WebhookEventEnvelope",
]

_EVENT_CONFIG = ConfigDict(frozen=True, populate_by_name=True, extra="allow")
"""``extra="allow"`` is load-bearing: a field the API adds tomorrow is carried
through rather than dropped, which is the same forward-compatibility property
the open string enums give."""


class WebhookEventEnvelope(BaseModel):
    """Fields every webhook event carries, whatever its type."""

    model_config = _EVENT_CONFIG

    event: str
    event_id: str = Field(alias="eventId")
    """Stable event id. **Deduplicate on this** -- delivery is at-least-once.

    :rotating_light: Use *this*, from the body, and never the
    ``X-Vairified-Event-Id`` header. That header is **outside the signature**, so
    an attacker replaying a captured delivery inside the tolerance window can
    change it freely and header-based deduplication will let it through.
    """
    timestamp: str


class MemberStatusEventSport(BaseModel):
    """One sport's VAIR Pro standing, as carried by a ``member.status`` event."""

    model_config = _EVENT_CONFIG

    is_vair_pro: bool = Field(alias="isVairPro")
    """Whether the member is an **active** VAIR Pro (certified rater) **in this
    sport** -- the field to check before letting someone rate.

    :rotating_light: ``False`` means "holds one, awaiting approval", not "may
    rate". Treat only ``True`` as permission. A member certified in pickleball is
    not thereby certified in padel.
    """
    is_rater: bool = Field(alias="isRater")
    """Documented alias of :attr:`is_vair_pro`, matching ``GET /partner/member``."""
    is_vair_pro_status: str = Field(alias="isVairProStatus")
    """``"ACTIVE"`` or ``"PENDING"`` today. Deliberately not a ``Literal``."""


class MemberStatusEventData(BaseModel):
    """The ``data`` block of a ``member.status`` delivery."""

    model_config = _EVENT_CONFIG

    member_id: int = Field(alias="memberId")
    is_vair_plus: bool = Field(alias="isVairPlus")
    """Whether the member currently holds a **paid VAIR+ membership**.

    ``False`` covers both "never bought" and "bought once, no longer active", and
    is ``False`` during the automatic 30-day trial -- a trial is not a paid
    membership. Not to be confused with :attr:`MemberStatusEventSport.is_vair_pro`,
    a different product whose name differs by two characters.
    """
    is_ambassador: bool = Field(alias="isAmbassador")
    sports: dict[str, MemberStatusEventSport] | None = Field(default=None)
    """Per-sport VAIR Pro standing, keyed by sport code.

    :rotating_light: **``None`` when the member did not grant ``user:rating:read``
    -- absent, not empty.** "We were not permitted to tell you" is a different
    claim from "holds no certifications", and defaulting this to ``{}`` silently
    turns the first into the second. It is deliberately **not**
    ``default_factory=dict``, unlike the per-sport map on the member record.

    :rotating_light: A sport appears only while the member holds a **current**
    certification in it. Expired and revoked certifications are not reported, so a
    lapsed rater is indistinguishable here from someone never certified.
    """
    vair_pro_status: str | None = Field(alias="vairProStatus")
    """VAIR Pro standing **collapsed across every sport**.

    :rotating_light: **This cannot answer "may this person rate my padel event".**
    It is ``"ACTIVE"`` when the member is certified in *any* sport, so using it as
    a per-sport permission grants a pickleball rater authority over padel. Read
    :attr:`sports` where the sport matters.
    """
    vairified_rating_status: str = Field(alias="vairifiedRatingStatus")
    changed_at: str = Field(alias="changedAt")
    sequence: str | None = Field(default=None)
    """Monotonic ordering token.

    **Not currently emitted on this event** -- treat an absent value as "cannot be
    ordered", never as zero, and order by :attr:`changed_at` until it appears.
    ``rating.updated`` is different: see :attr:`RatingUpdatedEventData.sequence`.
    """


class MemberStatusEvent(WebhookEventEnvelope):
    """A ``member.status`` delivery."""

    event: Literal["member.status"]
    data: MemberStatusEventData


class ConnectionRevokedEventData(BaseModel):
    """The ``data`` block of a ``connection.revoked`` delivery."""

    model_config = _EVENT_CONFIG

    member_id: int | None = Field(default=None, alias="memberId")
    """``None`` for a legacy row that never had a member number assigned."""
    reason: str
    """``"player_deleted"`` or ``"player_disconnected"`` today. **Never branch on
    this exhaustively** -- the set grows on the API's schedule, not this package's.
    """
    revoked_at: str = Field(alias="revokedAt")


class ConnectionRevokedEvent(WebhookEventEnvelope):
    """A ``connection.revoked`` delivery."""

    event: Literal["connection.revoked"]
    data: ConnectionRevokedEventData


class RatingUpdatedEventData(BaseModel):
    """The ``data`` block of a ``rating.updated`` delivery.

    :rotating_light: **This is NOT :class:`vairified.models.RatingUpdate`.** That
    model is the shape ``GET /partner/rating-updates`` returns when you *poll*, and
    it still carries the old per-sport diff (``previous_rating`` /
    ``new_rating``). The webhook has sent a **full multi-sport snapshot** since
    Vairified#899 and the two have not matched since. Reusing the poll model here
    is a mistake the TypeScript SDK made once, and the reason this docstring
    exists.

    :rotating_light: **Two variants, distinguished by
    :attr:`rating_data_withheld`.** An app holding ``user:webhook:subscribe`` but
    not ``user:rating:read`` is told *that* a member's rating changed and not
    *what it changed to*.
    """

    model_config = _EVENT_CONFIG

    member_id: int = Field(alias="memberId")
    sports: dict[str, SportRating] | None = Field(default=None)
    """The member's complete rating standing, keyed by sport code, at the moment
    the computation finished -- a **snapshot**, not a diff.

    :rotating_light: **``None`` when the partner lacks ``user:rating:read``.**
    Check :attr:`rating_data_withheld` rather than reading absence as "no ratings".
    """
    changed_at: str = Field(alias="changedAt")
    sequence: str
    """Monotonic ordering token. **Use it to discard stale deliveries.**

    :rotating_light: Because the payload is a **snapshot** rather than a diff, it
    is order-dependent in a way the old diff payload was not. Deliveries run
    concurrently with independent retry backoff, so two events for one member
    **can arrive out of order** -- and applying the older one last leaves you
    holding a rating the member no longer has.

    So: keep the highest ``sequence`` you have applied **per member**, and discard
    any delivery whose value is lower. Compare it only against other values **for
    the same member** -- it comes from a platform-wide counter, so gaps carry no
    meaning and values are not comparable across members. It is a string because
    the value exceeds the safe integer range in some languages.

    Unlike ``member.status``, where the field is declared but not yet emitted,
    ``rating.updated`` carries it on **every** delivery, on both variants -- which
    is why it is required here and optional there.
    """
    rating_data_withheld: bool | None = Field(default=None, alias="ratingDataWithheld")
    """``True`` only on the notification variant, where :attr:`sports` is absent by
    design rather than because nothing changed."""


class RatingUpdatedEvent(WebhookEventEnvelope):
    """A ``rating.updated`` delivery."""

    event: Literal["rating.updated"]
    data: RatingUpdatedEventData


class EventCreatedClub(BaseModel):
    """The club an event belongs to, when it has one."""

    model_config = _EVENT_CONFIG

    name: str
    city: str | None = None
    state: str | None = None


class EventCreatedEventData(BaseModel):
    """The ``data`` block of an ``event.created`` delivery.

    :rotating_light: **:attr:`event_id` here is an INT and is not the envelope's
    :attr:`WebhookEventEnvelope.event_id`.** The envelope's is the delivery's own
    string id, used for deduplication; this one is the event's public number, the
    id a partner uses to refer to the event itself. They shadow each other by name
    and share nothing else.

    This is the only **app-scoped** event -- it concerns no particular member, so
    it carries no member id.
    """

    model_config = _EVENT_CONFIG

    event_id: int = Field(alias="eventId")
    name: str
    type: str
    status: str
    sport: str
    start_date: str | None = Field(default=None, alias="startDate")
    end_date: str | None = Field(default=None, alias="endDate")
    club: EventCreatedClub | None = None
    host_name: str | None = Field(default=None, alias="hostName")
    win_score: int | None = Field(default=None, alias="winScore")
    win_by: int | None = Field(default=None, alias="winBy")
    is_private: bool = Field(default=False, alias="isPrivate")
    max_spots: int | None = Field(default=None, alias="maxSpots")
    max_teams: int | None = Field(default=None, alias="maxTeams")
    created_by: str | None = Field(default=None, alias="createdBy")
    created_at: str = Field(alias="createdAt")


class EventCreatedEvent(WebhookEventEnvelope):
    """An ``event.created`` delivery."""

    event: Literal["event.created"]
    data: EventCreatedEventData


class UnknownWebhookEvent(WebhookEventEnvelope):
    """Any event this SDK version does not model richly.

    Verification succeeds and :attr:`data` is handed over untouched. This is
    deliberate: the signature is checked *before* the body is typed, so an
    unrecognised event that reaches your handler is an authenticated one. If this
    raised instead, every partner would break the day the API adds an event.
    """

    data: Any = None


VerifiedWebhookEvent = (
    MemberStatusEvent
    | ConnectionRevokedEvent
    | RatingUpdatedEvent
    | EventCreatedEvent
    | UnknownWebhookEvent
)
"""A verified webhook event.

Narrow with ``isinstance``, or with the ``is_*_event`` helpers in
:mod:`vairified.webhooks`.

:rotating_light: **Deliberately not a pydantic discriminated union.**
``Field(discriminator=...)`` fails closed on an unfamiliar tag, which is the exact
opposite of what this SDK promises -- an event type we do not model yet must still
verify and be handed over. The dispatch is hand-rolled in
:func:`vairified.webhooks.verify_webhook` for that reason.
"""
