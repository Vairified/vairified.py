"""
Vairified SDK Models — Partner API v1 shapes.

All response models are :class:`pydantic.BaseModel` with
``model_config = ConfigDict(frozen=True, populate_by_name=True, extra="allow")``
so they're immutable, support both snake_case (Python) and camelCase (wire)
field names, and tolerate new server-side fields without breaking.

The public surface is designed to feel native:

* ``member.name`` is a :func:`property`, not a method — no ``get_name()``.
* ``member.sport["pickleball"]`` is dict-like access; ``SportRating``
  implements ``__getitem__``, ``__iter__``, ``__contains__``, ``__len__``.
* Every model has a human-readable ``__repr__`` so the REPL is useful.
* Models work with :keyword:`match` statements via pydantic field access.

Breaking from v0.1.x:
    The flat single-sport response (``member.rating`` / ``member.rating_splits``)
    has been replaced by a multi-sport ``member.sport`` dict keyed by sport code.
    The :class:`Match` class takes ``teams: list[list[str]]`` and
    ``games: list[Game]`` instead of ``team1/team2`` plus per-game tuples.
"""

from __future__ import annotations

from collections.abc import Iterator
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Response config — shared by every read-side model.
# ---------------------------------------------------------------------------

_RESPONSE_CONFIG = ConfigDict(
    frozen=True,
    populate_by_name=True,
    extra="allow",
)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class Gender(StrEnum):
    """
    Normalized gender enum returned by the Partner API.

    Matches the UPPERCASE tokens emitted by
    ``PartnerMember.gender`` on the backend.
    """

    MALE = "MALE"
    FEMALE = "FEMALE"
    OTHER = "OTHER"
    UNKNOWN = "UNKNOWN"


# ---------------------------------------------------------------------------
# Rating splits + sport ratings
# ---------------------------------------------------------------------------


class RatingSplit(BaseModel):
    """
    One slice of a player's rating for a specific category × age bracket.

    Keys in :attr:`SportRating.rating_splits` are strings like
    ``"overall-open"``, ``"singles-12-13"``, or ``"overall-40+"``.
    """

    model_config = _RESPONSE_CONFIG

    rating: float
    abbr: str

    def __repr__(self) -> str:  # pragma: no cover - REPL affordance
        return f"<RatingSplit {self.rating:.3f} {self.abbr}>"


class SportRating(BaseModel):
    """
    A player's ratings for a single sport.

    The top-level ``rating`` / ``abbr`` is the primary rating for that
    sport (conventionally the overall-open bracket). Every category × age
    bracket the player has played is also available under
    :attr:`rating_splits`, keyed by ``{category}-{bracketCode}``.

    This class is dict-like — you can access splits by subscript,
    iterate them, check membership, and get the length without touching
    ``rating_splits`` directly::

        overall = member.sport["pickleball"]["overall-open"].rating
        for key, split in member.sport["pickleball"]:
            print(key, split.rating)
        if "singles-40+" in member.sport["pickleball"]:
            ...
        print(len(member.sport["pickleball"]), "splits")
    """

    model_config = _RESPONSE_CONFIG

    rating: float
    abbr: str
    rating_splits: dict[str, RatingSplit] = Field(
        default_factory=dict, alias="ratingSplits"
    )

    # Per-sport status (Vairified#783). VAIRification and VAIR-Pro certs are
    # sport-scoped, so these live on each sport rather than the member status.
    # Defaulted so the SDK stays compatible with API responses that predate #783.
    is_vairified: bool = Field(default=False, alias="isVairified")
    """Player is VAIRified in this sport (has a verified, non-recreational rating)."""
    is_rater: bool = Field(default=False, alias="isRater")
    """Active VAIR Pro (can rate) in this sport. Alias of :attr:`is_vair_pro`."""
    is_vair_pro: bool = Field(default=False, alias="isVairPro")
    """Player is an active VAIR Pro (can rate) in this sport."""
    is_vair_pro_status: Literal["PENDING", "ACTIVE"] | None = Field(
        default=None, alias="isVairProStatus"
    )
    """VAIR-Pro lifecycle status here: ``"ACTIVE"``, ``"PENDING"``, or ``None``."""

    def __getitem__(self, key: str) -> RatingSplit:
        return self.rating_splits[key]

    def __iter__(self) -> Iterator[tuple[str, RatingSplit]]:  # type: ignore[override]
        return iter(self.rating_splits.items())

    def __contains__(self, key: object) -> bool:
        return key in self.rating_splits

    def __len__(self) -> int:
        return len(self.rating_splits)

    def keys(self) -> Any:
        """Split keys (e.g. ``"overall-open"``, ``"singles-12-13"``)."""
        return self.rating_splits.keys()

    def get(self, key: str, default: RatingSplit | None = None) -> RatingSplit | None:
        """Dict-style safe lookup."""
        return self.rating_splits.get(key, default)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<SportRating {self.rating:.3f} {self.abbr} "
            f"splits={len(self.rating_splits)}>"
        )


# ---------------------------------------------------------------------------
# Member / player
# ---------------------------------------------------------------------------


class MemberStatus(BaseModel):
    """
    Global status flags for a player.

    Grouped into a sub-object rather than top-level booleans so that
    inspection (``pprint``, ``repr``, JSON) keeps all ``is_*`` flags
    visually clustered.

    Only the genuinely global flags live here. VAIRification and VAIR-Pro
    status are per-sport (Vairified#783) and live on each
    :class:`SportRating` (``member.sport["pickleball"].is_vairified``).
    """

    model_config = _RESPONSE_CONFIG

    is_wheelchair: bool = Field(alias="isWheelchair")
    is_ambassador: bool = Field(alias="isAmbassador")
    is_connected: bool = Field(alias="isConnected")

    def __repr__(self) -> str:  # pragma: no cover
        flags = [
            name
            for name, value in (
                ("wheelchair", self.is_wheelchair),
                ("ambassador", self.is_ambassador),
                ("connected", self.is_connected),
            )
            if value
        ]
        return f"<MemberStatus {' '.join(flags) or '(none)'}>"


class Member(BaseModel):
    """
    A partner-facing player record.

    Returned by :meth:`Vairified.members.get` (full detail, requires an
    active OAuth connection) and :meth:`Vairified.members.search` (limited
    detail for public search).

    Rating data lives under :attr:`sport` — a dict keyed by sport code.
    The backend returns only the sports the player has ratings in, or
    only the sports requested via the ``?sport=`` query filter. Use
    :meth:`rating_for` to fetch the primary rating for a specific sport
    with a sensible default.
    """

    model_config = _RESPONSE_CONFIG

    member_id: int = Field(alias="memberId")
    id: str | None = None
    first_name: str = Field(alias="firstName")
    last_name: str = Field(alias="lastName")
    full_name: str = Field(alias="fullName")
    display_name: str = Field(alias="displayName")
    age: int | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    country: str | None = None
    #: The DATE this member's VAIR account was created (``YYYY-MM-DD``, UTC), or
    #: ``None`` when the endpoint does not supply it.
    #:
    #: Present on ``members.get()``, ``members.get_bulk()`` and
    #: ``members.get_by_email()`` -- the calls where you already know which member
    #: you asked about. **Never on** ``members.search()``, which is discovery:
    #: account age is not something you can browse strangers by.
    #:
    #: Deliberately a date, not a timestamp. It exists so you can apply a
    #: new-accounts-only referral rule -- crediting an ambassador only for
    #: accounts created because of their event.
    member_since: str | None = Field(default=None, alias="memberSince")
    gender: Gender | None = None
    status: MemberStatus
    sport: dict[str, SportRating] = Field(default_factory=dict)
    active_leagues: list[str] | None = Field(default=None, alias="activeLeagues")
    email: str | None = None
    granted_scopes: list[str] | None = Field(default=None, alias="grantedScopes")

    # ---- Convenience properties ----

    @property
    def name(self) -> str:
        """Full name — alias for :attr:`full_name`, matching common usage."""
        return self.full_name

    @property
    def sports(self) -> list[str]:
        """The list of sport codes this player has ratings in."""
        return list(self.sport.keys())

    def rating_for(self, sport: str = "pickleball") -> float | None:
        """
        Primary rating for a given sport.

        :param sport: Sport code, defaults to ``"pickleball"``.
        :returns: The primary rating value, or ``None`` if the player has
            no ratings for that sport.

        Example::

            member.rating_for()              # pickleball
            member.rating_for("padel")       # padel
        """
        sport_rating = self.sport.get(sport)
        return sport_rating.rating if sport_rating else None

    def split(
        self,
        key: str,
        sport: str = "pickleball",
    ) -> RatingSplit | None:
        """
        Get a specific rating split for a sport.

        :param key: Split key, e.g. ``"overall-open"`` or ``"singles-12-13"``.
        :param sport: Sport code, defaults to ``"pickleball"``.
        """
        sport_rating = self.sport.get(sport)
        if sport_rating is None:
            return None
        return sport_rating.get(key)

    def __repr__(self) -> str:  # pragma: no cover
        primary = next(iter(self.sport.values()), None)
        if primary:
            return (
                f"<Member #{self.member_id} '{self.display_name}' "
                f"rating={primary.rating:.3f} {primary.abbr}>"
            )
        return f"<Member #{self.member_id} '{self.display_name}'>"


# ---------------------------------------------------------------------------
# Rating updates (webhook / polling)
# ---------------------------------------------------------------------------


class RatingUpdate(BaseModel):
    """
    A single rating change notification.

    Returned by :meth:`Vairified.members.rating_updates` (polling) and
    delivered via webhook callbacks to partners that have registered a
    webhook URL.
    """

    model_config = _RESPONSE_CONFIG

    member_id: int = Field(alias="memberId")
    id: str | None = None
    display_name: str | None = Field(default=None, alias="displayName")
    sport: str | None = None
    previous_rating: float | None = Field(default=None, alias="previousRating")
    new_rating: float | None = Field(default=None, alias="newRating")
    changed_at: str | None = Field(default=None, alias="changedAt")
    rating_splits: dict[str, RatingSplit] | None = Field(
        default=None, alias="ratingSplits"
    )

    @property
    def delta(self) -> float | None:
        """Rating change amount. ``None`` when either rating is missing."""
        if self.previous_rating is None or self.new_rating is None:
            return None
        return self.new_rating - self.previous_rating

    @property
    def improved(self) -> bool:
        """True when the new rating is strictly higher than the previous."""
        delta = self.delta
        return delta is not None and delta > 0

    def __repr__(self) -> str:  # pragma: no cover
        arrow = "↑" if self.improved else "↓"
        prev = (
            f"{self.previous_rating:.3f}" if self.previous_rating is not None else "?"
        )
        new = f"{self.new_rating:.3f}" if self.new_rating is not None else "?"
        name = f" '{self.display_name}'" if self.display_name else ""
        return f"<RatingUpdate #{self.member_id}{name} {prev} {arrow} {new}>"


# ---------------------------------------------------------------------------
# Match submission — request side (input models)
# ---------------------------------------------------------------------------

_REQUEST_CONFIG = ConfigDict(populate_by_name=True, extra="forbid")


class Game(BaseModel):
    """
    One scored game within a :class:`Match`.

    ``scores`` is one integer per team, in the same order as the parent
    match's ``teams`` list. For a standard 2-team game ``scores`` is
    ``[team1_score, team2_score]``. The API supports n-team matches by
    setting a longer list.

    All fields except ``scores`` are optional overrides of the parent
    match's defaults — use them only when a specific game inside the
    match differs from the rest (e.g. a championship game played to 15
    when the rest of the match was to 11).
    """

    model_config = _REQUEST_CONFIG

    scores: list[int]
    identifier: str | None = None
    win_score: int | None = Field(default=None, alias="winScore")
    win_by: int | None = Field(default=None, alias="winBy")


class Match(BaseModel):
    """
    One match to submit in a :class:`MatchBatch`.

    A match has:

    * ``teams`` — a list of teams, each a list of player IDs (external
      ``vair_mem_xxx``, numeric member IDs, or UUIDs). Supports n-team
      × n-player matches natively: ``[[p1, p2], [p3, p4]]`` for standard
      doubles, ``[[p1], [p2]]`` for singles, ``[[p1], [p2], [p3]]``
      for a 3-way round robin.
    * ``games`` — one or more scored games (e.g. best-of-3 has 2 or 3
      entries). Scores in each game are parallel to the ``teams`` order.

    Every other field is an optional override of the parent
    :class:`MatchBatch` default.
    """

    model_config = _REQUEST_CONFIG

    identifier: str
    teams: list[list[str]]
    games: list[Game]

    # Optional per-match overrides of batch-level defaults
    sport: str | None = None
    bracket: str | None = None
    event: str | None = None
    location: str | None = None
    match_date: str | None = Field(default=None, alias="matchDate")
    match_source: str | None = Field(default=None, alias="matchSource")
    match_type: str | None = Field(default=None, alias="matchType")
    win_score: int | None = Field(default=None, alias="winScore")
    win_by: int | None = Field(default=None, alias="winBy")
    extras: dict[str, Any] | None = None
    original_id: str | None = Field(default=None, alias="originalId")
    original_type: str | None = Field(default=None, alias="originalType")
    club_id: int | None = Field(default=None, alias="clubId")

    @property
    def num_games(self) -> int:
        """Number of scored games in this match (best-of-N count)."""
        return len(self.games)

    @property
    def num_teams(self) -> int:
        """Number of teams in this match."""
        return len(self.teams)

    def __repr__(self) -> str:  # pragma: no cover
        shape = "×".join(str(len(t)) for t in self.teams)
        return f"<Match {self.identifier!r} teams={shape} games={self.num_games}>"


class MatchBatch(BaseModel):
    """
    Compressed bulk match submission.

    Top-level fields are defaults applied to every match in the
    :attr:`matches` list. Any match can override any field. ``sport``,
    ``win_score``, and ``win_by`` are **required** at the batch level —
    partners must tell the rater which sport the matches are in and what
    the winning conditions were so scores can be interpreted correctly.

    Example::

        batch = MatchBatch(
            sport="pickleball",
            win_score=11,
            win_by=2,
            bracket="4.0 Doubles",
            event="Weekly League",
            match_date="2026-04-11T14:00:00Z",
            matches=[
                Match(
                    identifier="m1",
                    teams=[["vair_mem_aaa", "vair_mem_bbb"],
                           ["vair_mem_ccc", "vair_mem_ddd"]],
                    games=[Game(scores=[11, 8]),
                           Game(scores=[11, 5])],
                ),
            ],
        )
        result = await client.matches.submit(batch)
    """

    model_config = _REQUEST_CONFIG

    sport: str
    win_score: int = Field(alias="winScore")
    win_by: int = Field(alias="winBy")
    matches: list[Match]

    # Optional batch-level defaults inherited by every match
    bracket: str | None = None
    event: str | None = None
    location: str | None = None
    match_date: str | None = Field(default=None, alias="matchDate")
    match_source: str | None = Field(default=None, alias="matchSource")
    match_type: str | None = Field(default=None, alias="matchType")
    extras: dict[str, Any] | None = None
    identifier: str | None = None
    original_id: str | None = Field(default=None, alias="originalId")
    original_type: str | None = Field(default=None, alias="originalType")
    club_id: int | None = Field(default=None, alias="clubId")
    dry_run: bool | None = Field(default=None, alias="dryRun")

    def __repr__(self) -> str:  # pragma: no cover
        total_games = sum(m.num_games for m in self.matches)
        return (
            f"<MatchBatch sport={self.sport!r} "
            f"matches={len(self.matches)} games={total_games}>"
        )


# ---------------------------------------------------------------------------
# Match submission — response side
# ---------------------------------------------------------------------------


class MatchBatchResult(BaseModel):
    """
    Result of a :meth:`Vairified.matches.submit` call.

    ``success`` is ``True`` only when every match in the batch was
    accepted. Check :attr:`errors` for per-match validation failures.
    """

    model_config = _RESPONSE_CONFIG

    success: bool
    num_matches: int = Field(alias="numMatches")
    num_games: int = Field(alias="numGames")
    dry_run: bool | None = Field(default=None, alias="dryRun")
    message: str | None = None
    errors: list[str] | None = None

    @property
    def ok(self) -> bool:
        """Shorthand: successful submission with zero errors."""
        return self.success and not self.errors

    @property
    def is_dry_run(self) -> bool:
        """Whether this was a dry-run (validation only, nothing persisted)."""
        return bool(self.dry_run)

    def __repr__(self) -> str:  # pragma: no cover
        mode = " [dry-run]" if self.dry_run else ""
        errs = f" errors={len(self.errors)}" if self.errors else ""
        return (
            f"<MatchBatchResult {'ok' if self.ok else 'FAILED'}{mode} "
            f"matches={self.num_matches} games={self.num_games}{errs}>"
        )


# ---------------------------------------------------------------------------
# Search filters (request-side)
# ---------------------------------------------------------------------------


class SearchFilters(BaseModel):
    """
    Filters accepted by :meth:`Vairified.members.search`.

    Most users won't construct this directly — the ``search()`` method
    accepts keyword arguments and builds it internally. But it's exposed
    so you can inspect the full set of available filters in one place.
    """

    model_config = _REQUEST_CONFIG

    # Multi-sport filter — comma-separated list of sport codes. When
    # omitted, the server returns every sport each player has ratings in.
    sport: str | None = None

    # Name / ID — partial match on first/last name, or exact numeric memberId
    member: str | None = None

    # Location filters
    location: str | None = None
    country: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None

    # Age filters
    age_filter_type: str | None = Field(default=None, alias="ageFilterType")
    age1: int | None = None
    age2: int | None = None

    # Gender + verified
    gender: str | None = None
    wheelchair: bool | None = None
    vairified: bool | None = None

    # Rating range
    rating1: float | None = None
    rating2: float | None = None

    # Sort + pagination
    sort_field: str | None = Field(default=None, alias="sortField")
    sort_direction: str | None = Field(default=None, alias="sortDirection")
    offset: int | None = None
    limit: int | None = None

    def to_query_params(self) -> dict[str, Any]:
        """Serialize to the wire-format dict expected by httpx params=."""
        return self.model_dump(by_alias=True, exclude_none=True)


# ---------------------------------------------------------------------------
# Tournament import — response side
# ---------------------------------------------------------------------------


class TournamentImportCreatedGhost(BaseModel):
    """One ghost player created by a tournament import."""

    model_config = _RESPONSE_CONFIG

    #: The email or phone you supplied for this person in ``ghost_members``,
    #: echoed back so results map onto your own records without a second lookup.
    ref: str
    #: The public member id allocated to them, usable in ``matches.submit()``.
    member_id: int = Field(alias="memberId")


class TournamentImportResult(BaseModel):
    """Result of a tournament import submission."""

    model_config = _RESPONSE_CONFIG

    success: bool
    matches_imported: int = Field(alias="matchesImported")
    games_recorded: int = Field(alias="gamesRecorded")
    ghost_players_created: int = Field(alias="ghostPlayersCreated")
    existing_players_matched: int = Field(alias="existingPlayersMatched")
    dry_run: bool | None = Field(default=None, alias="dryRun")
    message: str | None = None
    errors: list[str] | None = None
    #: Public member ids for the ghost players THIS import created.
    #:
    #: Always a list, so it can be iterated without a ``None`` check. Empty on a
    #: dry-run, which creates nothing, and empty against an older API build.
    #:
    #: **Created only.** Entries matched to a player who already existed are
    #: deliberately absent -- resolving an existing email to a member requires the
    #: ``key:player:lookup`` scope and ``members.get_by_email()``, and this
    #: endpoint is not a way around that.
    created_ghost_members: list[TournamentImportCreatedGhost] = Field(
        default_factory=list, alias="createdGhostMembers"
    )


# ---------------------------------------------------------------------------
# Webhook deliveries — response side
# ---------------------------------------------------------------------------


class MemberEmailMatch(BaseModel):
    """
    One requested address that resolved to at least one member.

    ``members`` is always a list. An email address is not a unique key in
    VAIR -- an unclaimed imported record can share an address with a
    claimed account -- so never assume a single element without checking.
    """

    model_config = _RESPONSE_CONFIG

    #: The address exactly as you supplied it, not as stored.
    email: str
    #: Every member holding this address. Never empty.
    members: list[Member]

    @property
    def sole(self) -> Member | None:
        """
        The single member for this address, or ``None`` when the address
        is ambiguous (more than one match).

        Use this rather than ``members[0]`` when a wrong link is worse
        than no link -- it refuses to guess instead of silently picking
        one.
        """
        return self.members[0] if len(self.members) == 1 else None

    @property
    def is_ambiguous(self) -> bool:
        """Whether this address resolved to more than one member."""
        return len(self.members) > 1


class MembersByEmailResult(BaseModel):
    """
    Result of a :meth:`MembersResource.get_by_email` call.

    Every address you supplied appears in exactly one of ``matched`` or
    ``not_found`` -- the endpoint never silently drops one, so consume
    ``not_found`` directly rather than diffing your input against the
    results.

    A ``not_found`` address is not proof the person has no VAIR account:
    unclaimed imported records are deliberately excluded from this lookup.
    """

    model_config = _RESPONSE_CONFIG

    matched: list[MemberEmailMatch] = Field(default_factory=list)
    #: Addresses that resolved to nothing, echoed as you supplied them.
    not_found: list[str] = Field(default_factory=list, alias="notFound")

    def get(self, email: str) -> MemberEmailMatch | None:
        """
        Look up one address's match, case-insensitively.

        Saves callers a linear scan and, more importantly, saves them
        from matching case-sensitively against an address the server
        echoed back in whatever case they originally sent.
        """
        needle = email.strip().lower()
        for match in self.matched:
            if match.email.lower() == needle:
                return match
        return None

    @property
    def all_resolved(self) -> bool:
        """Whether every requested address resolved to at least one member."""
        return not self.not_found

    @property
    def member_count(self) -> int:
        """Total number of members across every matched address."""
        return sum(len(m.members) for m in self.matched)


class WebhookDelivery(BaseModel):
    """A single webhook delivery attempt."""

    model_config = _RESPONSE_CONFIG

    id: str
    event: str
    url: str
    status_code: int | None = Field(default=None, alias="statusCode")
    response_body: str | None = Field(default=None, alias="responseBody")
    error_message: str | None = Field(default=None, alias="errorMessage")
    attempts: int
    max_attempts: int = Field(alias="maxAttempts")
    last_attempt_at: str = Field(alias="lastAttemptAt")
    next_retry_at: str | None = Field(default=None, alias="nextRetryAt")
    completed_at: str | None = Field(default=None, alias="completedAt")
    created_at: str = Field(alias="createdAt")
    payload: dict[str, Any]


class EventLocation(BaseModel):
    """
    Where an event is held.

    ⛔ ``latitude`` and ``longitude`` are ``None`` when the event has never been
    geocoded — never ``0``. Zero is a real coordinate in the Gulf of Guinea, so a
    zero fallback would cluster every un-located event on one pin in the ocean,
    and a map would look like it were working.
    """

    model_config = _RESPONSE_CONFIG

    venue_name: str | None = Field(default=None, alias="venueName")
    address: str | None = None
    city: str | None = None
    state: str | None = None
    zip: str | None = None
    latitude: float | None = None
    longitude: float | None = None

    @property
    def has_coordinates(self) -> bool:
        """Whether this location can be placed on a map."""
        return self.latitude is not None and self.longitude is not None

    def __repr__(self) -> str:
        where = self.venue_name or self.city or "unknown"
        return f"EventLocation({where!r}, coordinates={self.has_coordinates})"


class EventClub(BaseModel):
    """The club organising an event."""

    model_config = _RESPONSE_CONFIG

    name: str
    city: str | None = None
    state: str | None = None

    def __repr__(self) -> str:
        return f"EventClub({self.name!r})"


class Event(BaseModel):
    """
    An event in the Vairified catalogue.

    ``event_id`` is the integer identifier every event-scoped endpoint takes —
    the partner API does not accept UUIDs.
    """

    model_config = _RESPONSE_CONFIG

    event_id: int = Field(alias="eventId")
    name: str
    type: str
    status: str
    sport: str
    start_date: str | None = Field(default=None, alias="startDate")
    end_date: str | None = Field(default=None, alias="endDate")
    club: EventClub | None = None
    location: EventLocation | None = None
    host_name: str | None = Field(default=None, alias="hostName")
    is_private: bool = Field(alias="isPrivate")
    max_spots: int | None = Field(default=None, alias="maxSpots")
    max_teams: int | None = Field(default=None, alias="maxTeams")
    created_at: str = Field(alias="createdAt")

    def __repr__(self) -> str:
        return f"Event({self.event_id}, {self.name!r}, {self.type})"


class EventsPage(BaseModel):
    """A page of events, with the total before pagination."""

    model_config = _RESPONSE_CONFIG

    events: list[Event]
    total: int

    def __repr__(self) -> str:
        return f"EventsPage({len(self.events)} of {self.total})"


class WebhookDeliveriesResult(BaseModel):
    """Paginated list of webhook delivery attempts."""

    model_config = _RESPONSE_CONFIG

    deliveries: list[WebhookDelivery]
    total: int


__all__ = [
    "Event",
    "EventClub",
    "EventLocation",
    "EventsPage",
    "Gender",
    "Game",
    "Match",
    "MatchBatch",
    "MatchBatchResult",
    "Member",
    "MemberEmailMatch",
    "MemberStatus",
    "MembersByEmailResult",
    "RatingSplit",
    "RatingUpdate",
    "SearchFilters",
    "SportRating",
    "TournamentImportResult",
    "WebhookDelivery",
    "WebhookDeliveriesResult",
]


# ---------------------------------------------------------------------------
# Ambassador referral attribution — Vairified#1130, #1131
# ---------------------------------------------------------------------------


class MemberAttribution(BaseModel):
    """Who currently earns referral credit for one member."""

    model_config = _RESPONSE_CONFIG

    member_id: int = Field(alias="memberId")
    #: True when some ambassador already holds credit for this member.
    attributed: bool
    #: The member id of the ambassador holding the credit.
    #:
    #: Compare it against your own event host's member id to tell "already
    #: credited to my host -- nothing to do" from "credited to somebody else --
    #: a person needs to look, because claiming it takes credit from them".
    #:
    #: ``None`` both when nobody holds credit and when credit is held by a record
    #: with no member id of its own, so check :attr:`attributed` to tell those
    #: apart.
    ambassador_member_id: int | None = Field(default=None, alias="ambassadorMemberId")
    #: The date the credit was established (``YYYY-MM-DD``), or ``None``.
    attributed_at: str | None = Field(default=None, alias="attributedAt")

    @property
    def is_claimable(self) -> bool:
        """True when nobody holds credit yet, so this member can be claimed."""
        return not self.attributed

    def held_by_someone_other_than(self, ambassador_member_id: int) -> bool:
        """True when credit is held by an ambassador OTHER than the one given."""
        return self.attributed and self.ambassador_member_id != ambassador_member_id


class MembersAttributionResult(BaseModel):
    """Attribution for a batch of members, plus the ids that matched nothing."""

    model_config = _RESPONSE_CONFIG

    attributions: list[MemberAttribution] = Field(default_factory=list)
    #: Member ids that matched no member. Read this rather than diffing your
    #: input against the results -- every id you sent lands in one bucket.
    not_found: list[int] = Field(default_factory=list, alias="notFound")

    def get(self, member_id: int) -> MemberAttribution | None:
        """Attribution for one member id, or ``None`` if it was not returned."""
        return next((a for a in self.attributions if a.member_id == member_id), None)

    @property
    def claimable(self) -> list[MemberAttribution]:
        """Members nobody holds credit for yet."""
        return [a for a in self.attributions if a.is_claimable]


class AttributionOutcomeEntry(BaseModel):
    """What happened to one member in an attribution submission."""

    model_config = _RESPONSE_CONFIG

    member_id: int = Field(alias="memberId")
    outcome: str


class AttributionResult(BaseModel):
    """Outcome of submitting attribution for a batch of members."""

    model_config = _RESPONSE_CONFIG

    #: How many members were newly attributed by this request.
    attributed: int
    #: One entry per member id supplied, in the order supplied.
    results: list[AttributionOutcomeEntry] = Field(default_factory=list)

    def with_outcome(self, outcome: str) -> list[int]:
        """Member ids with the given outcome."""
        return [r.member_id for r in self.results if r.outcome == outcome]

    @property
    def already_attributed(self) -> list[int]:
        """
        Members already credited to somebody. These are the ones worth a human
        look -- it may be your own host, or it may be another ambassador.
        """
        return self.with_outcome("already_attributed")

    @property
    def predated_event(self) -> list[int]:
        """
        Members rejected because their account pre-dates the event's
        registration page. The event did not recruit them, so no credit is due.
        """
        return self.with_outcome("account_predates_event")
