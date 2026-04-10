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
from typing import Any

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

    def get(
        self, key: str, default: RatingSplit | None = None
    ) -> RatingSplit | None:
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
    Status flags for a player.

    Grouped into a sub-object rather than top-level booleans so that
    inspection (``pprint``, ``repr``, JSON) keeps all ``is_*`` flags
    visually clustered.
    """

    model_config = _RESPONSE_CONFIG

    is_vairified: bool = Field(alias="isVairified")
    is_wheelchair: bool = Field(alias="isWheelchair")
    is_ambassador: bool = Field(alias="isAmbassador")
    is_rater: bool = Field(alias="isRater")
    is_connected: bool = Field(alias="isConnected")

    def __repr__(self) -> str:  # pragma: no cover
        flags = [
            name
            for name, value in (
                ("vairified", self.is_vairified),
                ("wheelchair", self.is_wheelchair),
                ("ambassador", self.is_ambassador),
                ("rater", self.is_rater),
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
            f"{self.previous_rating:.3f}"
            if self.previous_rating is not None
            else "?"
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


__all__ = [
    "Gender",
    "Game",
    "Match",
    "MatchBatch",
    "MatchBatchResult",
    "Member",
    "MemberStatus",
    "RatingSplit",
    "RatingUpdate",
    "SearchFilters",
    "SportRating",
]
