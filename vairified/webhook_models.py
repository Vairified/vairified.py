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

:rotating_light: **Only the fields a partner gates access on are required**: the
envelope's ``event``/``eventId``/``timestamp``, ``member.status``'s
``memberId``/``isVairPlus``/``isAmbassador``, and ``rating.updated``'s
``memberId``/``sequence``. Everything else is optional and unvalidated, at every
depth, so this SDK cannot refuse a delivery the TypeScript one accepts.

Three review rounds found divergences between the two SDKs and **every one was in
validation; none was in signature verification**. A refusal is retried about
thirteen times over three hours and then dropped -- the member's status silently
stops updating at that partner -- so refusing over an informational field costs
far more than handing it over.
"""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "ConnectionRevokedEvent",
    "RatingUpdatedSport",
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

_EVENT_CONFIG = ConfigDict(frozen=True, strict=True, extra="allow")
"""``strict=True`` stops pydantic coercing what the TypeScript SDK refuses.

In lax mode ``"memberId": "42"`` becomes ``42`` and ``"isVairPlus": "false"``
becomes ``False`` -- so on identical malformed input one SDK raises and the other
invents a value for the field that gates paid entry. ``populate_by_name`` is off
for the same reason: the wire is camelCase, and accepting a snake_case body here
would accept something JS rejects.

``extra="allow"`` is load-bearing: a field the API adds tomorrow is carried
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
    """One sport's VAIR Pro standing, as carried by a ``member.status`` event.

    :rotating_light: **Every field is optional, deliberately** (PO decision,
    2026-09-24). The TypeScript SDK validates only the top level of an event and
    hands nested blocks over as they arrive, so requiring anything here would make
    Python refuse deliveries JS accepts. The asymmetry matters: a refusal is
    retried about thirteen times over three hours and then dropped, so the
    member's status silently stops updating at that partner, while handing the
    event over costs them one absent field. The fields that gate entitlement are
    checked at the top level either way.
    """

    model_config = _EVENT_CONFIG

    is_vair_pro: bool | None = Field(default=None, alias="isVairPro")
    """Whether the member is an **active** VAIR Pro (certified rater) **in this
    sport** -- the field to check before letting someone rate.

    :rotating_light: ``False`` means "holds one, awaiting approval", not "may
    rate". Treat only ``True`` as permission. A member certified in pickleball is
    not thereby certified in padel.
    """
    is_rater: bool | None = Field(default=None, alias="isRater")
    """Documented alias of :attr:`is_vair_pro`, matching ``GET /partner/member``."""
    is_vair_pro_status: str | None = Field(default=None, alias="isVairProStatus")
    """``"ACTIVE"`` or ``"PENDING"`` today. Deliberately not a ``Literal``."""


class RatingUpdatedSport(BaseModel):
    """One sport's rating standing inside a ``rating.updated`` snapshot.

    :rotating_light: **Deliberately NOT :class:`vairified.models.SportRating`.**
    That model types its VAIR Pro status as a closed ``Literal["PENDING",
    "ACTIVE"]``, which *refuses* a value the API may add tomorrow -- and the
    TypeScript SDK accepts it. Reusing it made the two SDKs disagree on the
    highest-traffic event: Python returned a 400 the backend then retried ~13
    times over ~3.4 h before dropping, while JS partners saw nothing wrong.

    Everything here is open or optional for the same reason. The known values are
    documented; the set is the API's to grow.
    """

    model_config = _EVENT_CONFIG

    rating: float | None = None
    abbr: str | None = None
    rating_splits: dict[str, Any] | None = Field(default=None, alias="ratingSplits")
    is_vairified: bool | None = Field(default=None, alias="isVairified")
    is_rater: bool | None = Field(default=None, alias="isRater")
    is_vair_pro: bool | None = Field(default=None, alias="isVairPro")
    is_vair_pro_status: str | None = Field(default=None, alias="isVairProStatus")
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
    sports: Any = Field(default=None)
    """Per-sport VAIR Pro standing, keyed by sport code.
    :rotating_light: **The per-sport values are NOT validated** (PO decision,
    2026-09-24). The TypeScript SDK checks only the top level of an event and
    hands nested blocks over untouched; typing these as models made Python
    reject payloads JS accepted -- and a Python rejection is retried about
    thirteen times over three hours and then dropped, so the member's status
    silently stops updating at that partner. Each value is documented by
    :class:`MemberStatusEventSport` and can be parsed with it if you want the checking.


    An explicit ``null`` on the wire is accepted and read as absent, the same as
    an omitted key (PO decision, 2026-09-24) -- so test the **value**, not the
    key: ``if data.sports is not None``, never ``if "sports" in ...`` -- proxies and
    serialisers do
    normalise missing keys into nulls, and both mean "no per-sport data here".

    :rotating_light: **``None`` when the member did not grant ``user:rating:read``
    -- absent, not empty.** "We were not permitted to tell you" is a different
    claim from "holds no certifications", and defaulting this to ``{}`` silently
    turns the first into the second. It is deliberately **not**
    ``default_factory=dict``, unlike the per-sport map on the member record.

    :rotating_light: A sport appears only while the member holds a **current**
    certification in it. Expired and revoked certifications are not reported, so a
    lapsed rater is indistinguishable here from someone never certified.
    """
    vair_pro_status: Any = Field(default=None, alias="vairProStatus")
    """VAIR Pro standing **collapsed across every sport**.

    :rotating_light: **This cannot answer "may this person rate my padel event".**
    It is ``"ACTIVE"`` when the member is certified in *any* sport, so using it as
    a per-sport permission grants a pickleball rater authority over padel. Read
    :attr:`sports` where the sport matters.
    """
    vairified_rating_status: Any = Field(default=None, alias="vairifiedRatingStatus")
    changed_at: Any = Field(default=None, alias="changedAt")
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

    member_id: Any = Field(default=None, alias="memberId")
    """``None`` for a legacy row that never had a member number assigned."""
    reason: Any = None
    """``"player_deleted"`` or ``"player_disconnected"`` today. **Never branch on
    this exhaustively** -- the set grows on the API's schedule, not this package's.
    """
    revoked_at: Any = Field(default=None, alias="revokedAt")


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
    sports: Any = Field(default=None)
    """The member's complete rating standing, keyed by sport code, at the moment
    the computation finished -- a **snapshot**, not a diff.
    :rotating_light: **The per-sport values are NOT validated** (PO decision,
    2026-09-24). The TypeScript SDK checks only the top level of an event and
    hands nested blocks over untouched; typing these as models made Python
    reject payloads JS accepted -- and a Python rejection is retried about
    thirteen times over three hours and then dropped, so the member's status
    silently stops updating at that partner. Each value is documented by
    :class:`RatingUpdatedSport` and can be parsed with it if you want the checking.


    :rotating_light: **``None`` when the partner lacks ``user:rating:read``.**
    Check :attr:`rating_data_withheld` rather than reading absence as "no ratings".
    """
    changed_at: str | None = Field(default=None, alias="changedAt")
    sequence: str
    """Monotonic ordering token. **Use it to discard stale deliveries.**

    :rotating_light: Because the payload is a **snapshot** rather than a diff, it
    is order-dependent in a way the old diff payload was not. Deliveries run
    concurrently with independent retry backoff, so two events for one member
    **can arrive out of order** -- and applying the older one last leaves you
    holding a rating the member no longer has.

    :rotating_light: **Compare it as an INTEGER, never as a string.** It is an
    unpadded decimal, so a string comparison is lexicographic and
    ``"10000000" > "9999999"`` is ``False``. At every power-of-ten crossing a
    string-comparing receiver would discard every later delivery for that member,
    permanently, and their rating would freeze at the stale value -- which is the
    exact failure this field exists to prevent. Use ``int(a) > int(b)``.

    So: keep the highest ``sequence`` you have applied **per member**, compared as
    an integer, and discard any delivery whose value is lower. Compare it only against
    other values **for
    the same member** -- it comes from a platform-wide counter, so gaps carry no
    meaning and values are not comparable across members. It is a string because
    the value exceeds the safe integer range in some languages.

    Unlike ``member.status``, where the field is declared but not yet emitted,
    ``rating.updated`` carries it on **every** delivery, on both variants -- which
    is why it is required here and optional there.
    """
    rating_data_withheld: Any = Field(default=None, alias="ratingDataWithheld")
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

    event_id: Any = Field(default=None, alias="eventId")
    name: Any = None
    type: Any = None
    status: Any = None
    sport: Any = None
    start_date: Any = Field(default=None, alias="startDate")
    end_date: Any = Field(default=None, alias="endDate")
    club: Any = None
    host_name: Any = Field(default=None, alias="hostName")
    win_score: Any = Field(default=None, alias="winScore")
    win_by: Any = Field(default=None, alias="winBy")
    is_private: Any = Field(default=None, alias="isPrivate")
    max_spots: Any = Field(default=None, alias="maxSpots")
    max_teams: Any = Field(default=None, alias="maxTeams")
    created_by: Any = Field(default=None, alias="createdBy")
    created_at: Any = Field(default=None, alias="createdAt")


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
