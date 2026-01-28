"""
Vairified SDK Client

Async-first client for the Vairified Partner API.
"""

from __future__ import annotations

import os
from typing import Any, Optional

import httpx

from vairified.errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    VairifiedError,
    ValidationError,
)
from vairified.models import (
    Match,
    MatchResult,
    Member,
    Player,
    RatingUpdate,
    SearchResults,
)
from vairified.oauth import (
    DEFAULT_SCOPES,
    SCOPES,
    AuthorizationResponse,
    TokenResponse,
)

# Environment URLs
# Note: "production" points to current active API
ENVIRONMENTS = {
    "production": "https://api-next.vairified.com/api/v1",
    "staging": "https://api-staging.vairified.com/api/v1",
    "local": "http://localhost:3001/api/v1",
}

DEFAULT_BASE_URL = ENVIRONMENTS["production"]
DEFAULT_TIMEOUT = 30.0


class Vairified:
    """
    Async client for the Vairified Partner API.

    :ivar api_key: Your Partner API key
    :ivar base_url: API base URL
    :ivar env: Environment name (production, staging, local)

    Example::

        async with Vairified(api_key="vair_pk_xxx") as client:
            member = await client.get_member("user_123")
            print(member.name, member.rating)

    Example with staging environment::

        async with Vairified(api_key="vair_pk_xxx", env="staging") as client:
            member = await client.get_member("user_123")

    .. note::
        If your API key has the "dry-run" scope, match submissions will be
        validated but not persisted. This is useful for testing integrations.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        *,
        env: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout: float = DEFAULT_TIMEOUT,
    ):
        """
        Initialize the Vairified client.

        :param api_key: Partner API key. Falls back to ``VAIRIFIED_API_KEY`` env var.
        :param env: Environment: "production" (default), "staging", or "local".
        :param base_url: Override API base URL. Takes precedence over ``env``.
        :param timeout: Request timeout in seconds.
        :raises ValueError: If no API key is provided.
        """
        self.api_key = api_key or os.environ.get("VAIRIFIED_API_KEY", "")
        if not self.api_key:
            raise ValueError("API key required. Pass api_key or set VAIRIFIED_API_KEY.")

        # Resolve base URL from env or explicit base_url
        if base_url:
            self.base_url = base_url.rstrip("/")
        elif env:
            if env not in ENVIRONMENTS:
                valid = ", ".join(ENVIRONMENTS.keys())
                raise ValueError(f"Unknown environment: {env}. Use: {valid}")
            self.base_url = ENVIRONMENTS[env]
        else:
            # Default to VAIRIFIED_ENV or 'production'
            default_env = os.environ.get("VAIRIFIED_ENV", "production")
            self.base_url = ENVIRONMENTS.get(default_env, DEFAULT_BASE_URL)

        self.env = env or os.environ.get("VAIRIFIED_ENV", "production")
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> "Vairified":
        """Enter async context."""
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, *args) -> None:
        """Exit async context."""
        if self._client:
            await self._client.aclose()
            self._client = None

    async def close(self) -> None:
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None

    def _headers(self) -> dict[str, str]:
        """Get request headers."""
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _ensure_client(self) -> httpx.AsyncClient:
        """Ensure client is initialized."""
        if not self._client:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout,
            )
        return self._client

    def _handle_error(self, response: httpx.Response) -> None:
        """Handle error responses."""
        status = response.status_code

        try:
            body = response.json()
            message = body.get("message", response.text)
        except Exception:
            body = None
            message = response.text

        if status == 401:
            raise AuthenticationError(message, response=body)
        elif status == 404:
            raise NotFoundError(message, response=body)
        elif status == 429:
            retry_after = response.headers.get("Retry-After")
            raise RateLimitError(
                message,
                retry_after=int(retry_after) if retry_after else None,
                response=body,
            )
        elif status == 400:
            raise ValidationError(message, response=body)
        else:
            raise VairifiedError(message, status_code=status, response=body)

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Optional[dict] = None,
        json: Optional[Any] = None,
    ) -> dict:
        """Make HTTP request."""
        client = self._ensure_client()
        response = await client.request(method, path, params=params, json=json)

        if response.status_code >= 400:
            self._handle_error(response)

        return response.json()

    # -------------------------------------------------------------------------
    # Member Operations
    # -------------------------------------------------------------------------

    async def get_member(self, player_id: str) -> Member:
        """
        Get a connected member by their external ID.

        **Requires OAuth Connection**: The player must have connected their
        account to your application via OAuth before you can access their data.

        :param player_id: External player ID (vair_mem_xxx format).
        :returns: Member object with profile and rating data.
        :raises NotFoundError: If member is not found or invalid ID format.
        :raises ForbiddenError: If player has not connected to your app.

        Example::

            member = await client.get_member("vair_mem_0ABC123def456GHI789jk")
            print(f"{member.name}: {member.rating}")
        """
        data = await self._request(
            "GET",
            "/partner/member",
            params={"id": player_id},
        )
        return Member.from_dict(data, client=self)

    # -------------------------------------------------------------------------
    # Search Operations
    # -------------------------------------------------------------------------

    async def search(
        self,
        *,
        name: Optional[str] = None,
        city: Optional[str] = None,
        state: Optional[str] = None,
        country: Optional[str] = None,
        zip_code: Optional[str] = None,
        rating_min: Optional[float] = None,
        rating_max: Optional[float] = None,
        gender: Optional[str] = None,
        vairified_only: bool = False,
        age: Optional[int] = None,
        age_min: Optional[int] = None,
        age_max: Optional[int] = None,
        sort_by: Optional[str] = None,
        sort_order: str = "desc",
        page: int = 1,
        limit: int = 20,
    ) -> SearchResults:
        """
        Search for players.

        :param name: Name to search for (partial match).
        :param city: City filter.
        :param state: State code (e.g., "TX", "CA").
        :param country: Country code (e.g., "US").
        :param zip_code: ZIP/postal code.
        :param rating_min: Minimum rating (2.0-8.0).
        :param rating_max: Maximum rating (2.0-8.0).
        :param gender: "MALE" or "FEMALE".
        :param vairified_only: Only return verified players.
        :param age: Exact age filter.
        :param age_min: Minimum age (for range).
        :param age_max: Maximum age (for range).
        :param sort_by: Field to sort by.
        :param sort_order: "asc" or "desc".
        :param page: Page number (1-indexed).
        :param limit: Results per page (max 100).
        :returns: SearchResults with players and pagination info.

        Example::

            results = await client.search(city="Austin", rating_min=4.0)
            for player in results:
                print(f"{player.name}: {player.rating}")

            # Pagination
            if results.has_more:
                next_results = await results.next_page()
        """
        # Build params
        params: dict[str, Any] = {"limit": limit}

        if name:
            params["member"] = name
        if city:
            params["city"] = city
        if state:
            params["state"] = state
        if country:
            params["country"] = country
        if zip_code:
            params["zip"] = zip_code
        if rating_min is not None:
            params["rating1"] = rating_min
        if rating_max is not None:
            params["rating2"] = rating_max
        if gender:
            params["gender"] = gender.upper()
        if vairified_only:
            params["vairified"] = True
        if sort_by:
            params["sortField"] = sort_by
            params["sortDirection"] = sort_order

        # Age handling
        if age is not None:
            params["ageFilterType"] = "exact"
            params["age1"] = age
        elif age_min is not None and age_max is not None:
            params["ageFilterType"] = "range"
            params["age1"] = age_min
            params["age2"] = age_max
        elif age_min is not None:
            params["ageFilterType"] = "above"
            params["age1"] = age_min
        elif age_max is not None:
            params["ageFilterType"] = "below"
            params["age1"] = age_max

        # Pagination (API uses offset internally)
        if page > 1:
            params["offset"] = (page - 1) * limit

        # Store filters for pagination
        filters = {
            "name": name,
            "city": city,
            "state": state,
            "country": country,
            "zip_code": zip_code,
            "rating_min": rating_min,
            "rating_max": rating_max,
            "gender": gender,
            "vairified_only": vairified_only,
            "age": age,
            "age_min": age_min,
            "age_max": age_max,
            "sort_by": sort_by,
            "sort_order": sort_order,
            "limit": limit,
        }

        data = await self._request("GET", "/partner/search", params=params)

        # Handle both array and object responses
        if isinstance(data, list):
            data = {"players": data, "total": len(data), "page": page, "limit": limit}

        return SearchResults.from_dict(data, client=self, filters=filters)

    async def find_player(self, name: str) -> Optional[Player]:
        """
        Find a single player by name.

        Convenience method that returns the first match.

        :param name: Player name to search for.
        :returns: Player if found, None otherwise.
        """
        results = await self.search(name=name, limit=1)
        return results[0] if results.players else None

    # -------------------------------------------------------------------------
    # Match Operations
    # -------------------------------------------------------------------------

    async def submit_match(self, match: Match) -> MatchResult:
        """
        Submit a single match.

        :param match: Match object with teams and scores.
        :returns: MatchResult with submission status.
        :raises VairifiedError: If submission fails.

        Example::

            match = Match(
                event="Weekly League",
                bracket="4.0 Doubles",
                date=datetime.now(),
                team1=("player1_id", "player2_id"),
                team2=("player3_id", "player4_id"),
                scores=[(11, 9), (11, 7)],
            )
            result = await client.submit_match(match)
            if result:
                print(f"Submitted {result.num_games} games")
        """
        return await self.submit_matches([match])

    async def submit_matches(self, matches: list[Match]) -> MatchResult:
        """
        Submit multiple matches in a batch.

        :param matches: List of Match objects.
        :returns: MatchResult with ``success``, ``num_matches``, ``num_games``,
            and optionally ``dry_run``, ``message``, ``errors``.

        Example::

            matches = [match1, match2, match3]
            result = await client.submit_matches(matches)
            if result:
                print(f"Submitted {result.num_games} games")
            if result.dry_run:
                print("This was a dry run - no data persisted")
        """
        data = await self._request(
            "POST",
            "/partner/matches",
            json={"matches": [m.to_dict() for m in matches]},
        )
        return MatchResult.from_dict(data)

    # -------------------------------------------------------------------------
    # Rating Updates
    # -------------------------------------------------------------------------

    async def get_rating_updates(self) -> list[RatingUpdate]:
        """
        Get rating updates for subscribed members.

        Members are subscribed when you call :meth:`get_member`.

        :returns: List of RatingUpdate objects.

        Example::

            updates = await client.get_rating_updates()
            for update in updates:
                print(f"{update.member_id}: {update.previous_rating}")
        """
        data = await self._request("GET", "/partner/rating-updates")
        return [RatingUpdate.from_dict(u, client=self) for u in data.get("updates", [])]

    async def test_webhook(self, webhook_url: str) -> dict:
        """
        Test webhook endpoint.

        :param webhook_url: URL to send test webhook to.
        :returns: Test result dict.
        """
        return await self._request(
            "POST",
            "/partner/webhook-test",
            json={"webhookUrl": webhook_url},
        )

    # -------------------------------------------------------------------------
    # OAuth Operations
    # -------------------------------------------------------------------------

    async def start_oauth(
        self,
        redirect_uri: str,
        scopes: Optional[list[str]] = None,
        state: Optional[str] = None,
    ) -> AuthorizationResponse:
        """
        Start an OAuth authorization flow.

        This creates a pending authorization and returns the URL where
        users should be redirected to approve access.

        :param redirect_uri: Your application's callback URL.
        :param scopes: Permission scopes to request.
            Defaults to profile:read, rating:read.
        :param state: CSRF protection state parameter (recommended).
        :returns: AuthorizationResponse with the URL to redirect users to.
        :raises OAuthError: If the authorization fails to start.

        Example::

            auth = await client.start_oauth(
                redirect_uri="https://myapp.com/callback",
                scopes=["profile:read", "rating:read", "match:submit"],
                state="random_csrf_token",
            )
            # Redirect user to auth.authorization_url
        """
        from vairified.errors import OAuthError  # noqa: F811

        if scopes is None:
            scopes = list(DEFAULT_SCOPES)

        # Ensure profile:read is always included
        if "profile:read" not in scopes:
            scopes = ["profile:read"] + scopes

        # Validate scopes
        for scope in scopes:
            if scope not in SCOPES:
                raise OAuthError(f"Invalid scope: {scope}", error_code="invalid_scope")

        data = await self._request(
            "POST",
            "/partner/oauth/authorize",
            json={
                "redirectUri": redirect_uri,
                "scope": ",".join(scopes),
                "state": state,
            },
        )

        return AuthorizationResponse(
            authorization_url=data.get("authorizationUrl", ""),
            code=data.get("code", ""),
            state=state,
        )

    async def exchange_token(
        self,
        code: str,
        redirect_uri: str,
    ) -> TokenResponse:
        """
        Exchange an authorization code for access and refresh tokens.

        Call this after the user approves access and is redirected back
        to your application with a code parameter.

        :param code: Authorization code from the callback URL.
        :param redirect_uri: Must match the redirect_uri used in start_oauth.
        :returns: TokenResponse with access_token, refresh_token, and player_id.
        :raises OAuthError: If the code is invalid or expired.

        Example::

            # After user is redirected to: https://myapp.com/callback?code=xxx
            tokens = await client.exchange_token(
                code=request.query_params["code"],
                redirect_uri="https://myapp.com/callback",
            )
            # Store tokens.access_token and tokens.refresh_token securely
            # Use tokens.player_id to identify the connected player
        """
        data = await self._request(
            "POST",
            "/partner/oauth/token",
            json={
                "code": code,
                "redirectUri": redirect_uri,
            },
        )

        return TokenResponse(
            access_token=data.get("accessToken", ""),
            refresh_token=data.get("refreshToken"),
            expires_in=data.get("expiresIn", 3600),
            scope=data.get("scope", "").split(",") if data.get("scope") else [],
            player_id=data.get("playerId", ""),
        )

    async def refresh_access_token(
        self,
        refresh_token: str,
    ) -> TokenResponse:
        """
        Refresh an expired access token.

        Use this when an access token expires to obtain a new one
        without requiring the user to re-authorize.

        :param refresh_token: The refresh token from a previous token exchange.
        :returns: TokenResponse with new access_token and optionally
            a new refresh_token.
        :raises OAuthError: If the refresh token is invalid or revoked.

        Example::

            try:
                new_tokens = await client.refresh_access_token(stored_refresh_token)
                # Update stored tokens
            except OAuthError as e:
                if e.error_code == "invalid_grant":
                    # Refresh token revoked, user needs to re-authorize
                    pass
        """
        data = await self._request(
            "POST",
            "/partner/oauth/refresh",
            json={"refreshToken": refresh_token},
        )

        return TokenResponse(
            access_token=data.get("accessToken", ""),
            refresh_token=data.get("refreshToken"),
            expires_in=data.get("expiresIn", 3600),
            scope=data.get("scope", "").split(",") if data.get("scope") else [],
            player_id=data.get("playerId", ""),
        )

    async def revoke_connection(self, player_id: str) -> dict:
        """
        Revoke a player's OAuth connection.

        This disconnects the player from your application. You will no
        longer be able to access their data or submit matches on their behalf.

        :param player_id: The player's external ID (vair_mem_xxx format).
        :returns: Dict with success status.
        :raises OAuthError: If the revocation fails.

        Example::

            await client.revoke_connection("vair_mem_0ABC123def456GHI789jk")
            # Player is now disconnected
        """
        return await self._request(
            "POST",
            "/partner/oauth/revoke",
            json={"playerId": player_id},
        )

    async def get_available_scopes(self) -> list[dict[str, str]]:
        """
        Get a list of available OAuth scopes.

        :returns: List of scope objects with id, name, and description.

        Example::

            scopes = await client.get_available_scopes()
            for scope in scopes:
                print(f"{scope['id']}: {scope['description']}")
        """
        data = await self._request("GET", "/partner/oauth/scopes")
        return data.get("scopes", [])

    async def get_usage(self) -> dict:
        """
        Get API usage statistics for your partner account.

        :returns: Dict with usage statistics (requests, limits, etc.).

        Example::

            usage = await client.get_usage()
            print(f"Requests today: {usage['requestsToday']}")
            print(f"Rate limit: {usage['rateLimit']}/hour")
        """
        return await self._request("GET", "/partner/usage")
