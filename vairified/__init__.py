"""
Vairified Python SDK

Official Python SDK for the Vairified Partner API.
Async-first, object-oriented design for easy integration.

Features:
- Opaque external IDs (vair_mem_xxx format) for privacy
- OAuth-based player consent for data access
- Tiered access: public search vs connected member data
"""

from vairified.client import Vairified
from vairified.errors import (
    AuthenticationError,
    NotFoundError,
    OAuthError,
    RateLimitError,
    VairifiedError,
    ValidationError,
)
from vairified.models import (
    Match,
    MatchResult,
    Member,
    Player,
    RatingSplits,
    RatingUpdate,
    SearchResults,
)
from vairified.oauth import (
    DEFAULT_SCOPES,
    SCOPES,
    AuthorizationResponse,
    OAuthConfig,
    TokenResponse,
    describe_scope,
    describe_scopes,
    get_authorization_url,
    validate_scope,
)

__version__ = "0.1.0"
__all__ = [
    # Client
    "Vairified",
    # Models
    "Match",
    "MatchResult",
    "Member",
    "Player",
    "RatingSplits",
    "RatingUpdate",
    "SearchResults",
    # OAuth
    "AuthorizationResponse",
    "OAuthConfig",
    "SCOPES",
    "DEFAULT_SCOPES",
    "TokenResponse",
    "get_authorization_url",
    "validate_scope",
    "describe_scope",
    "describe_scopes",
    # Errors
    "VairifiedError",
    "RateLimitError",
    "AuthenticationError",
    "NotFoundError",
    "ValidationError",
    "OAuthError",
]
