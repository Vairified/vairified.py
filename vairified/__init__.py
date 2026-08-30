"""
Vairified Python SDK — Partner API v1.

The Vairified Partner API lets you read player ratings, submit match
results, and subscribe to rating change notifications for integrations
in leagues, tournaments, and club-management software.

Quickstart::

    from vairified import Vairified, Match, MatchBatch, Game

    async with Vairified(api_key="vair_pk_...") as client:
        # Look up a connected player
        member = await client.members.get("vair_mem_xxx")
        print(member.display_name, member.rating_for("pickleball"))

        # Auto-paginating search
        async for player in client.members.search(city="Austin", rating_min=4.0):
            print(player.display_name)

        # Submit a bulk match batch
        result = await client.matches.submit(MatchBatch(
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
                    games=[Game(scores=[11, 8]), Game(scores=[11, 5])],
                ),
            ],
        ))
        print(f"Submitted {result.num_games} games in {result.num_matches} matches")

See https://vairified.github.io/vairified.py for full documentation.
"""

from vairified.client import (
    ENVIRONMENTS,
    LeaderboardResource,
    MatchesResource,
    MembersResource,
    OAuthResource,
    Vairified,
    WebhooksResource,
)
from vairified.errors import (
    AuthenticationError,
    NotFoundError,
    OAuthError,
    RateLimitError,
    VairifiedError,
    ValidationError,
)
from vairified.models import (
    AttributionOutcomeEntry,
    AttributionResult,
    Event,
    EventClub,
    EventLocation,
    EventsPage,
    Game,
    Gender,
    Match,
    MatchBatch,
    MatchBatchResult,
    Member,
    MemberAttribution,
    MemberEmailMatch,
    MembersAttributionResult,
    MembersByEmailResult,
    MemberStatus,
    RatingSplit,
    RatingUpdate,
    SearchFilters,
    SportRating,
    TournamentImportCreatedGhost,
    TournamentImportResult,
    WebhookDeliveriesResult,
    WebhookDelivery,
)
from vairified.oauth import (
    DEFAULT_SCOPES,
    SCOPES,
    AuthorizationResponse,
    OAuthConfig,
    OAuthScope,
    TokenResponse,
    describe_scope,
    describe_scopes,
    get_authorization_url,
    validate_scope,
)

__version__ = "0.5.0"

__all__ = [
    # Version
    "__version__",
    # Client + sub-resources
    "Vairified",
    "ENVIRONMENTS",
    "LeaderboardResource",
    "MatchesResource",
    "MembersResource",
    "OAuthResource",
    "WebhooksResource",
    # Response models
    "Gender",
    "Member",
    "MemberEmailMatch",
    "MemberStatus",
    "AttributionOutcomeEntry",
    "AttributionResult",
    "MemberAttribution",
    "MembersAttributionResult",
    "MembersByEmailResult",
    "RatingSplit",
    "RatingUpdate",
    "SportRating",
    "TournamentImportCreatedGhost",
    "TournamentImportResult",
    "Event",
    "EventClub",
    "EventLocation",
    "EventsPage",
    "WebhookDelivery",
    "WebhookDeliveriesResult",
    # Request models
    "Game",
    "Match",
    "MatchBatch",
    "MatchBatchResult",
    "SearchFilters",
    # OAuth primitives
    "AuthorizationResponse",
    "DEFAULT_SCOPES",
    "OAuthConfig",
    "OAuthScope",
    "SCOPES",
    "TokenResponse",
    "describe_scope",
    "describe_scopes",
    "get_authorization_url",
    "validate_scope",
    # Errors
    "AuthenticationError",
    "NotFoundError",
    "OAuthError",
    "RateLimitError",
    "ValidationError",
    "VairifiedError",
]
