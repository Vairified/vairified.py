"""
Vairified SDK Models

Rich model classes with methods for easy API interaction.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any, Optional
from uuid import uuid4

if TYPE_CHECKING:
    from vairified.client import Vairified


@dataclass
class RatingSplit:
    """
    A single rating split with metadata.

    :ivar rating: The rating value.
    :ivar abbr: Abbreviation (e.g., "VG", "50+").
    :ivar date_played: Date of last match in this category.
    """

    rating: float
    abbr: str
    date_played: Optional[str] = None

    @classmethod
    def from_dict(cls, data: dict) -> "RatingSplit":
        """
        Create from API response dict.

        :param data: Rating split data from API.
        :returns: RatingSplit instance.
        """
        rating_val = data.get("rating", 0)
        if isinstance(rating_val, str):
            rating_val = float(rating_val) if rating_val else 0.0
        return cls(
            rating=rating_val,
            abbr=data.get("abbr", ""),
            date_played=data.get("date_played"),
        )


@dataclass
class RatingSplits:
    """
    Rating breakdown by category.

    Access ratings by category name (e.g., "open", "50_and_up") or
    use convenience properties for common categories.

    :ivar splits: Dict mapping category names to RatingSplit objects.
    """

    splits: dict[str, RatingSplit] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: Optional[dict]) -> "RatingSplits":
        """
        Create from API response dict.

        :param data: Rating splits data from API (nested or flat format).
        :returns: RatingSplits instance.
        """
        if not data:
            return cls()

        splits = {}
        for key, value in data.items():
            if isinstance(value, dict):
                # Nested format: { "open": { "rating": "4.25", "abbr": "OP" } }
                splits[key] = RatingSplit.from_dict(value)
            elif isinstance(value, (int, float)):
                # Flat format: { "VG": 4.25, "VM": 4.10 }
                splits[key] = RatingSplit(rating=float(value), abbr=key)
        return cls(splits=splits)

    def get(self, category: str) -> Optional[float]:
        """
        Get rating for a category.

        :param category: Category name (e.g., "open", "VG", "50_and_up").
        :returns: Rating value or None if not found.
        """
        split = self.splits.get(category)
        return split.rating if split else None

    @property
    def open(self) -> Optional[float]:
        """Open division rating."""
        return self.get("open") or self.get("VO")

    @property
    def gender(self) -> Optional[float]:
        """Gender-specific rating (same gender doubles)."""
        return self.get("gender") or self.get("VG")

    @property
    def mixed(self) -> Optional[float]:
        """Mixed doubles rating."""
        return self.get("mixed") or self.get("VM")

    @property
    def recreational(self) -> Optional[float]:
        """Recreational rating."""
        return self.get("recreational") or self.get("R")

    @property
    def singles(self) -> Optional[float]:
        """Singles rating."""
        return self.get("singles") or self.get("S")

    @property
    def best(self) -> Optional[float]:
        """Best available verified rating."""
        ratings = [s.rating for s in self.splits.values() if s.rating > 0]
        return max(ratings) if ratings else None

    def to_dict(self) -> dict:
        """Convert to dict."""
        return {k: {"rating": v.rating, "abbr": v.abbr} for k, v in self.splits.items()}

    def __repr__(self) -> str:
        parts = [f"{k}={v.rating:.2f}" for k, v in self.splits.items() if v.rating > 0]
        return f"RatingSplits({', '.join(parts)})"


@dataclass
class Player:
    """
    A player in the Vairified system.

    From public search, only limited data is available (display name, location, rating).
    For full profile data, use :meth:`Vairified.get_member` with OAuth consent.

    :ivar id: External player ID (vair_mem_xxx format).
    :ivar display_name: Display name (First Name + Last Initial from search).
    :ivar first_name: Player's first name (only from connected member).
    :ivar last_name: Player's last name (only from connected member).
    :ivar rating: Primary/overall rating (2.0-8.0).
    :ivar is_vairified: Whether player is verified.
    :ivar is_connected: Whether player has connected to your app.
    :ivar rating_splits: Ratings by category (only from connected member).
    :ivar city: City.
    :ivar state: State code.
    :ivar country: Country code.
    """

    id: str
    rating: float
    display_name: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    is_vairified: bool = False
    is_connected: bool = False
    rating_splits: RatingSplits = field(default_factory=RatingSplits)
    city: Optional[str] = None
    state: Optional[str] = None
    country: Optional[str] = None
    _client: Optional["Vairified"] = field(default=None, repr=False)

    @property
    def name(self) -> str:
        """Full name (or display name if full name not available)."""
        if self.first_name and self.last_name:
            return f"{self.first_name} {self.last_name}".strip()
        return self.display_name or ""

    @property
    def verified_rating(self) -> Optional[float]:
        """Best verified rating."""
        return self.rating_splits.best

    @classmethod
    def from_dict(cls, data: dict, client: Optional["Vairified"] = None) -> "Player":
        """
        Create from API response dict.

        Handles both search (limited data) and member (full data) formats.

        :param data: Player data from API.
        :param client: Vairified client for back-reference.
        :returns: Player instance.
        """
        # Search format uses displayName
        if "displayName" in data:
            # Public search format (limited data)
            return cls(
                id=data.get("id", ""),
                display_name=data.get("displayName", ""),
                rating=float(data.get("rating", 0.0)) if data.get("rating") else 0.0,
                is_vairified=data.get("isVairified", False),
                is_connected=data.get("isConnected", False),
                city=data.get("city"),
                state=data.get("state"),
                country=data.get("country"),
                _client=client,
            )
        else:
            # Member format (full data)
            return cls(
                id=data.get("id", ""),
                first_name=data.get("firstName", ""),
                last_name=data.get("lastName", ""),
                rating=float(data.get("rating", 0.0)) if data.get("rating") else 0.0,
                is_vairified=data.get("isVairified", False),
                rating_splits=RatingSplits.from_dict(data.get("ratingSplits")),
                city=data.get("city"),
                state=data.get("state"),
                country=data.get("country"),
                _client=client,
            )

    def __str__(self) -> str:
        verified = " ✓" if self.is_vairified else ""
        return f"{self.name} ({self.rating:.2f}){verified}"


@dataclass
class Member(Player):
    """
    A member with full profile access (requires OAuth connection).

    Extends :class:`Player` with additional profile data and methods.
    Only accessible for players who have connected their account via OAuth.

    :ivar email: Email address (only if profile:email scope granted).
    :ivar granted_scopes: List of scopes the player granted to your app.
    """

    email: Optional[str] = None
    granted_scopes: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict, client: Optional["Vairified"] = None) -> "Member":
        """
        Create from API response dict.

        :param data: Member data from API.
        :param client: Vairified client for back-reference.
        :returns: Member instance.
        """
        return cls(
            id=data.get("id", ""),
            first_name=data.get("firstName", ""),
            last_name=data.get("lastName", ""),
            email=data.get("email"),
            rating=float(data.get("rating", 0.0)) if data.get("rating") else 0.0,
            is_vairified=data.get("isVairified", False),
            rating_splits=RatingSplits.from_dict(data.get("ratingSplits")),
            city=data.get("city"),
            state=data.get("state"),
            country=data.get("country"),
            granted_scopes=data.get("grantedScopes", []),
            _client=client,
        )

    def has_scope(self, scope: str) -> bool:
        """
        Check if the player has granted a specific scope.

        :param scope: Scope to check (e.g., 'profile:email', 'match:submit').
        :returns: True if scope is granted.
        """
        return scope in self.granted_scopes

    async def refresh(self) -> "Member":
        """
        Refresh member data from API.

        :returns: Updated Member instance (self).
        :raises RuntimeError: If not connected to client.
        """
        if not self._client:
            raise RuntimeError("Member not connected to client")
        updated = await self._client.get_member(self.id)
        # Update all fields
        for key, value in vars(updated).items():
            if not key.startswith("_"):
                setattr(self, key, value)
        return self


@dataclass
class Match:
    """
    A match to submit to the Vairified Partner API.

    For doubles matches, provide two player IDs per team. For singles,
    provide one player ID per team.

    :ivar event: Event/tournament name (required).
    :ivar bracket: Bracket/division name (required).
    :ivar date: Match date and time (required).
    :ivar team1: Tuple of (player1_id, player2_id) or just (player1_id,) for singles.
    :ivar team2: Tuple of (player1_id, player2_id) or just (player1_id,) for singles.
    :ivar scores: List of (team1_score, team2_score) tuples for each game.
    :ivar match_type: Match type (e.g., "SIDEOUT", "RALLY").
    :ivar source: Match source (e.g., "CLUB", "TOURNAMENT").
    :ivar location: Match location (optional).
    :ivar identifier: Unique match identifier (auto-generated if not provided).

    Example::

        # Doubles match: 11-9, 11-7
        match = Match(
            event="Weekly League",
            bracket="4.0 Doubles",
            date=datetime.now(),
            team1=("player1_id", "player2_id"),
            team2=("player3_id", "player4_id"),
            scores=[(11, 9), (11, 7)],
        )

        # Singles match: 11-8, 9-11, 11-6
        match = Match(
            event="Club Singles",
            bracket="Open Singles",
            date=datetime.now(),
            team1=("player1_id",),
            team2=("player2_id",),
            scores=[(11, 8), (9, 11), (11, 6)],
        )
    """

    event: str
    bracket: str
    date: datetime
    team1: tuple[str, ...]
    team2: tuple[str, ...]
    scores: list[tuple[int, int]]
    match_type: str = "SIDEOUT"
    source: str = "PARTNER"
    location: Optional[str] = None
    identifier: Optional[str] = None
    id: Optional[str] = None

    def __post_init__(self):
        """Generate identifier if not provided."""
        if not self.identifier:
            self.identifier = f"SDK-{uuid4().hex[:12]}"

    @property
    def format(self) -> str:
        """Match format: SINGLES or DOUBLES."""
        return "SINGLES" if len(self.team1) == 1 else "DOUBLES"

    @property
    def winner(self) -> int:
        """
        Team that won (1 or 2).

        :returns: 1 if team 1 won, 2 if team 2 won, 0 if tie.
        """
        t1_wins = sum(1 for s1, s2 in self.scores if s1 > s2)
        t2_wins = sum(1 for s1, s2 in self.scores if s2 > s1)
        if t1_wins > t2_wins:
            return 1
        elif t2_wins > t1_wins:
            return 2
        return 0

    @property
    def score_summary(self) -> str:
        """Score summary like '11-9, 11-7'."""
        return ", ".join(f"{s1}-{s2}" for s1, s2 in self.scores)

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to API request format.

        :returns: Dict matching the MatchInput DTO.
        """
        # Build team objects with embedded scores
        team_a: dict[str, Any] = {"player1": self.team1[0]}
        team_b: dict[str, Any] = {"player1": self.team2[0]}

        if len(self.team1) > 1:
            team_a["player2"] = self.team1[1]
        if len(self.team2) > 1:
            team_b["player2"] = self.team2[1]

        # Add game scores to teams
        for i, (s1, s2) in enumerate(self.scores[:5], start=1):
            team_a[f"game{i}"] = s1
            team_b[f"game{i}"] = s2

        if isinstance(self.date, datetime):
            match_date = self.date.isoformat()
        else:
            match_date = self.date
        return {
            "identifier": self.identifier,
            "bracket": self.bracket,
            "event": self.event,
            "format": self.format,
            "matchDate": match_date,
            "matchSource": self.source,
            "matchType": self.match_type,
            "location": self.location,
            "teamA": team_a,
            "teamB": team_b,
        }


@dataclass
class RatingUpdate:
    """
    A rating change notification.

    :ivar id: External player ID (vair_mem_xxx format).
    :ivar member_name: Member name.
    :ivar previous_rating: Rating before change.
    :ivar new_rating: Rating after change.
    :ivar changed_at: When the change occurred.
    :ivar rating_splits: Updated rating splits.
    """

    id: str
    previous_rating: float
    new_rating: float
    changed_at: datetime
    member_name: Optional[str] = None
    rating_splits: RatingSplits = field(default_factory=RatingSplits)
    _client: Optional["Vairified"] = field(default=None, repr=False)

    @property
    def change(self) -> float:
        """Amount of rating change."""
        return self.new_rating - self.previous_rating

    @property
    def improved(self) -> bool:
        """Whether rating improved."""
        return self.change > 0

    @classmethod
    def from_dict(
        cls, data: dict, client: Optional["Vairified"] = None
    ) -> "RatingUpdate":
        """
        Create from API response dict.

        :param data: Rating update data from API.
        :param client: Vairified client for back-reference.
        :returns: RatingUpdate instance.
        """
        changed_at = data.get("changedAt") or data.get("updatedAt", "")
        if isinstance(changed_at, str) and changed_at:
            changed_at = datetime.fromisoformat(changed_at.replace("Z", "+00:00"))
        else:
            changed_at = datetime.now()

        return cls(
            id=data.get("id", data.get("memberId", data.get("playerId", ""))),
            member_name=data.get("memberName"),
            previous_rating=data.get("previousRating", 0.0),
            new_rating=data.get("newRating", 0.0),
            changed_at=changed_at,
            rating_splits=RatingSplits.from_dict(data.get("ratingSplits")),
            _client=client,
        )

    async def get_member(self) -> Member:
        """
        Fetch the member associated with this update.

        :returns: Member object.
        :raises RuntimeError: If not connected to client.
        """
        if not self._client:
            raise RuntimeError("Update not connected to client")
        return await self._client.get_member(self.id)

    def __str__(self) -> str:
        direction = "↑" if self.improved else "↓"
        name = f" ({self.member_name})" if self.member_name else ""
        prev, new = self.previous_rating, self.new_rating
        return f"{self.id}{name}: {prev:.2f} {direction} {new:.2f}"


@dataclass
class MatchResult:
    """
    Result of a match submission.

    :ivar success: Whether submission succeeded.
    :ivar num_matches: Number of matches processed.
    :ivar num_games: Number of games recorded.
    :ivar dry_run: Whether this was a dry-run (validation only).
    :ivar message: Human-readable result message.
    :ivar errors: List of validation/processing errors.
    """

    success: bool
    num_matches: int
    num_games: int
    dry_run: bool = False
    message: Optional[str] = None
    errors: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "MatchResult":
        """
        Create from API response dict.

        :param data: Match result data from API.
        :returns: MatchResult instance.
        """
        return cls(
            success=data.get("success", False),
            num_matches=data.get("numMatches", 0),
            num_games=data.get("numGames", 0),
            dry_run=data.get("dryRun", False),
            message=data.get("message"),
            errors=data.get("errors", []),
        )

    @property
    def is_dry_run(self) -> bool:
        """Alias for dry_run."""
        return self.dry_run

    def __bool__(self) -> bool:
        return self.success and not self.errors


@dataclass
class SearchResults:
    """
    Paginated search results.

    Supports iteration and async pagination.

    :ivar players: List of Player objects.
    :ivar total: Total matching players.
    :ivar page: Current page number.
    :ivar limit: Results per page.
    """

    players: list[Player]
    total: int
    page: int
    limit: int
    _client: Optional["Vairified"] = field(default=None, repr=False)
    _filters: dict = field(default_factory=dict, repr=False)

    @property
    def has_more(self) -> bool:
        """Whether more results are available."""
        return (self.page * self.limit) < self.total

    @property
    def pages(self) -> int:
        """Total number of pages."""
        if self.limit <= 0:
            return 0
        return (self.total + self.limit - 1) // self.limit

    def __iter__(self):
        return iter(self.players)

    def __len__(self) -> int:
        return len(self.players)

    def __getitem__(self, index: int) -> Player:
        return self.players[index]

    def __bool__(self) -> bool:
        return len(self.players) > 0

    async def next_page(self) -> "SearchResults":
        """
        Fetch next page of results.

        :returns: SearchResults for the next page.
        :raises RuntimeError: If not connected to client.
        :raises StopIteration: If no more pages.
        """
        if not self._client:
            raise RuntimeError("Results not connected to client")
        if not self.has_more:
            raise StopIteration("No more pages")

        filters = self._filters.copy()
        filters["page"] = self.page + 1
        return await self._client.search(**filters)

    @classmethod
    def from_dict(
        cls,
        data: dict,
        client: Optional["Vairified"] = None,
        filters: Optional[dict] = None,
    ) -> "SearchResults":
        """
        Create from API response dict.

        :param data: Search results data from API.
        :param client: Vairified client for back-reference.
        :param filters: Original search filters for pagination.
        :returns: SearchResults instance.
        """
        players = [Player.from_dict(p, client) for p in data.get("players", [])]
        return cls(
            players=players,
            total=data.get("total", len(players)),
            page=data.get("page", 1),
            limit=data.get("limit", 20),
            _client=client,
            _filters=filters or {},
        )
