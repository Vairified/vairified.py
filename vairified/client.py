"""
Vairified SDK Client — async-first, sub-resource organized.

Usage::

    async with Vairified(api_key="vair_pk_xxx") as client:
        # Get a connected member
        member = await client.members.get("vair_mem_xxx")
        print(member.display_name, member.rating_for("pickleball"))

        # Auto-paginate a search
        async for member in client.members.search(city="Austin", rating_min=4.0):
            print(member.display_name)

        # Submit a bulk match batch
        result = await client.matches.submit(
            MatchBatch(
                sport="pickleball",
                win_score=11,
                win_by=2,
                bracket="4.0 Doubles",
                event="Weekly League",
                match_date="2026-04-11T14:00:00Z",
                matches=[
                    Match(
                        identifier="m1",
                        teams=[["p1", "p2"], ["p3", "p4"]],
                        games=[Game(scores=[11, 8]), Game(scores=[11, 5])],
                    ),
                ],
            )
        )
        print(f"Submitted {result.num_games} games")

Sub-resources:

* :attr:`Vairified.members` — get/search/rating_updates
* :attr:`Vairified.matches` — submit bulk match batches
* :attr:`Vairified.oauth` — OAuth authorization flow
* :attr:`Vairified.leaderboard` — leaderboard queries
* :attr:`Vairified.usage` — API usage stats (method: ``await client.usage()``)
"""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from typing import TYPE_CHECKING, Any

import httpx

from vairified.errors import (
    AuthenticationError,
    NotFoundError,
    RateLimitError,
    VairifiedError,
    ValidationError,
)
from vairified.models import (
    MatchBatch,
    MatchBatchResult,
    Member,
    RatingUpdate,
    SearchFilters,
)
from vairified.oauth import (
    DEFAULT_SCOPES,
    SCOPES,
    AuthorizationResponse,
    OAuthScope,
    TokenResponse,
)

if TYPE_CHECKING:
    from typing import Self


# ---------------------------------------------------------------------------
# Environment URLs
# ---------------------------------------------------------------------------

ENVIRONMENTS: dict[str, str] = {
    "production": "https://api-next.vairified.com/api/v1",
    "staging": "https://api-staging.vairified.com/api/v1",
    "local": "http://localhost:3001/api/v1",
}

_DEFAULT_BASE_URL = ENVIRONMENTS["production"]
_DEFAULT_TIMEOUT = 30.0
_DEFAULT_SEARCH_LIMIT = 20


# ---------------------------------------------------------------------------
# Main client
# ---------------------------------------------------------------------------


class Vairified:
    """
    Async client for the Vairified Partner API.

    The client is organized around sub-resources that mirror the REST
    structure — ``client.members``, ``client.matches``, ``client.oauth``,
    ``client.leaderboard``. Each sub-resource is a thin wrapper around
    the HTTP layer on this object.

    :param api_key: Partner API key (``vair_pk_...``). Falls back to the
        ``VAIRIFIED_API_KEY`` environment variable if not supplied.
    :param env: Environment preset — ``"production"`` (default),
        ``"staging"``, or ``"local"``. Overridden by ``base_url``.
    :param base_url: Explicit base URL. Takes precedence over ``env``.
    :param timeout: Request timeout in seconds.
    :raises ValueError: If no API key is provided.
    """

    def __init__(
        self,
        api_key: str | None = None,
        *,
        env: str | None = None,
        base_url: str | None = None,
        timeout: float = _DEFAULT_TIMEOUT,
    ) -> None:
        resolved_key = api_key or os.environ.get("VAIRIFIED_API_KEY", "")
        if not resolved_key:
            raise ValueError(
                "API key required. Pass api_key=... or set VAIRIFIED_API_KEY."
            )
        self.api_key = resolved_key

        if base_url:
            self.base_url = base_url.rstrip("/")
            resolved_env = env or "production"
        elif env:
            if env not in ENVIRONMENTS:
                valid = ", ".join(ENVIRONMENTS)
                raise ValueError(f"Unknown environment: {env!r}. Use one of: {valid}")
            self.base_url = ENVIRONMENTS[env]
            resolved_env = env
        else:
            resolved_env = os.environ.get("VAIRIFIED_ENV", "production")
            self.base_url = ENVIRONMENTS.get(resolved_env, _DEFAULT_BASE_URL)
        self.env = resolved_env
        self.timeout = timeout

        self._http: httpx.AsyncClient | None = None

        # Sub-resources — lazy-init would work but these are cheap and
        # let callers type `client.members` without a property ceremony.
        self.members = MembersResource(self)
        self.matches = MatchesResource(self)
        self.oauth = OAuthResource(self)
        self.leaderboard = LeaderboardResource(self)

    # ---- Context manager ----

    async def __aenter__(self) -> "Self":
        self._http = httpx.AsyncClient(
            base_url=self.base_url,
            headers=self._headers(),
            timeout=self.timeout,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        await self.close()

    async def close(self) -> None:
        """Close the underlying HTTP client. Safe to call multiple times."""
        if self._http is not None:
            await self._http.aclose()
            self._http = None

    # ---- HTTP plumbing (used by sub-resources) ----

    def _headers(self) -> dict[str, str]:
        return {
            "X-API-Key": self.api_key,
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def _ensure_http(self) -> httpx.AsyncClient:
        if self._http is None:
            self._http = httpx.AsyncClient(
                base_url=self.base_url,
                headers=self._headers(),
                timeout=self.timeout,
            )
        return self._http

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: Any | None = None,
    ) -> Any:
        """Make an HTTP request, raising a typed exception on non-2xx."""
        http = self._ensure_http()
        response = await http.request(method, path, params=params, json=json)
        if response.status_code >= 400:
            _raise_from_response(response)
        return response.json() if response.content else None

    # ---- Usage (direct method — doesn't warrant its own resource) ----

    async def usage(self) -> dict[str, Any]:
        """
        API usage statistics for the current API key.

        Returns rate-limit status, request counts, and quota usage for
        monitoring purposes.
        """
        data = await self._request("GET", "/partner/usage")
        return data or {}

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Vairified env={self.env!r} base_url={self.base_url!r}>"


# ---------------------------------------------------------------------------
# Error mapping
# ---------------------------------------------------------------------------


def _raise_from_response(response: httpx.Response) -> None:
    """Convert an httpx error response into the right typed exception."""
    status = response.status_code
    try:
        body = response.json()
    except Exception:
        body = None

    if isinstance(body, dict):
        message = body.get("message") or body.get("error") or response.text
    else:
        message = response.text or f"HTTP {status}"

    if status == 401:
        raise AuthenticationError(message, response=body)
    if status == 404:
        raise NotFoundError(message, response=body)
    if status == 429:
        retry_after_hdr = response.headers.get("Retry-After")
        retry_after = int(retry_after_hdr) if retry_after_hdr else None
        raise RateLimitError(message, retry_after=retry_after, response=body)
    if status == 400:
        raise ValidationError(message, response=body)
    raise VairifiedError(message, status_code=status, response=body)


# ---------------------------------------------------------------------------
# Sub-resources
# ---------------------------------------------------------------------------


class _Resource:
    """Base class for sub-resources — just holds a back-reference."""

    def __init__(self, client: Vairified) -> None:
        self._client = client


class MembersResource(_Resource):
    """
    Member operations — get a single member, auto-paginating search,
    and polling for rating change notifications.
    """

    async def get(
        self,
        player_id: str,
        *,
        sport: str | list[str] | None = None,
    ) -> Member:
        """
        Get a connected member by external ID.

        **Requires an active OAuth connection** between your partner app
        and the player. Use the OAuth flow on ``client.oauth`` first.

        :param player_id: External player ID in ``vair_mem_xxx`` format.
        :param sport: Optional sport filter. Pass a single sport code to
            get ratings for just that sport, or a list to get multiple.
            When omitted, the response contains every sport the player
            has ratings in.
        :raises NotFoundError: If the external ID is invalid or unknown.
        :raises VairifiedError: If the player has not connected to your app
            (403) or if the API request otherwise fails.

        Example::

            member = await client.members.get("vair_mem_xxx")
            print(member.display_name, member.rating_for("pickleball"))

            # Just pickleball
            member = await client.members.get("vair_mem_xxx", sport="pickleball")

            # Multiple sports
            member = await client.members.get(
                "vair_mem_xxx",
                sport=["pickleball", "padel"],
            )
        """
        params: dict[str, Any] = {"id": player_id}
        if sport is not None:
            params["sport"] = sport if isinstance(sport, str) else ",".join(sport)
        data = await self._client._request("GET", "/partner/member", params=params)
        return Member.model_validate(data)

    async def search(
        self,
        *,
        sport: str | list[str] | None = None,
        name: str | None = None,
        member_id: int | str | None = None,
        city: str | None = None,
        state: str | None = None,
        country: str | None = None,
        zip: str | None = None,
        location: str | None = None,
        gender: str | None = None,
        vairified_only: bool | None = None,
        wheelchair: bool | None = None,
        rating_min: float | None = None,
        rating_max: float | None = None,
        age: int | None = None,
        age_min: int | None = None,
        age_max: int | None = None,
        sort_by: str | None = None,
        sort_order: str = "desc",
        page_size: int = _DEFAULT_SEARCH_LIMIT,
        max_results: int | None = None,
    ) -> AsyncIterator[Member]:
        """
        Search for players, yielding each match as an :class:`Member`.

        This is an **auto-paginating async iterator** — it fetches pages
        from the server lazily as you iterate, so you can stream through
        thousands of results without holding them all in memory::

            async for member in client.members.search(city="Austin"):
                print(member.display_name, member.rating_for("pickleball"))

        Stop early by ``break``-ing out of the loop, or cap the total
        number of results with ``max_results``.

        :param sport: Sport code (or list of codes) to filter ratings by.
            Omit to get every sport each player has ratings in.
        :param name: Name partial-match (first or last name).
        :param member_id: Exact numeric member ID.
        :param city: City filter (partial match, case-insensitive).
        :param state: State code (e.g. ``"TX"``).
        :param country: ISO 3166 alpha-2 country code.
        :param zip: ZIP/postal code (exact match).
        :param location: General location search.
        :param gender: ``"MALE"``, ``"FEMALE"``, or ``None`` for any.
        :param vairified_only: When ``True``, only verified players.
        :param wheelchair: When ``True``, only wheelchair players.
        :param rating_min: Lower rating bound (2.0-8.0).
        :param rating_max: Upper rating bound (2.0-8.0).
        :param age: Exact age filter.
        :param age_min: Lower age bound.
        :param age_max: Upper age bound.
        :param sort_by: Field to sort by.
        :param sort_order: ``"asc"`` or ``"desc"``.
        :param page_size: Results per HTTP request. Server cap is 100.
        :param max_results: Optional cap on total results to iterate.
        """
        # Build the filter model so we serialize consistently.
        sport_param = sport if isinstance(sport, str) else (
            ",".join(sport) if sport else None
        )
        member_param: str | None
        if member_id is not None:
            member_param = str(member_id)
        elif name is not None:
            member_param = name
        else:
            member_param = None

        # Figure out the age filter shape from the kwargs.
        age_filter_type: str | None = None
        age1: int | None = None
        age2: int | None = None
        if age is not None:
            age_filter_type = "exact"
            age1 = age
        elif age_min is not None and age_max is not None:
            age_filter_type = "range"
            age1 = age_min
            age2 = age_max
        elif age_min is not None:
            age_filter_type = "above"
            age1 = age_min
        elif age_max is not None:
            age_filter_type = "below"
            age1 = age_max

        filters = SearchFilters(
            sport=sport_param,
            member=member_param,
            city=city,
            state=state,
            country=country,
            zip=zip,
            location=location,
            gender=gender.upper() if gender else None,
            vairified=vairified_only,
            wheelchair=wheelchair,
            rating1=rating_min,
            rating2=rating_max,
            age_filter_type=age_filter_type,
            age1=age1,
            age2=age2,
            sort_field=sort_by,
            sort_direction=sort_order,
            limit=min(page_size, 100),
        )

        offset = 0
        yielded = 0
        limit = filters.limit or _DEFAULT_SEARCH_LIMIT

        while True:
            page_params = filters.to_query_params()
            page_params["offset"] = offset

            data = await self._client._request(
                "GET", "/partner/search", params=page_params
            )

            # Partner API returns a plain list of results.
            batch: list[dict[str, Any]] = data if isinstance(data, list) else (
                data.get("players", []) if isinstance(data, dict) else []
            )

            if not batch:
                return

            for raw in batch:
                yield Member.model_validate(raw)
                yielded += 1
                if max_results is not None and yielded >= max_results:
                    return

            # Stop when the last page was short (no more results upstream).
            if len(batch) < limit:
                return
            offset += limit

    async def rating_updates(self) -> list[RatingUpdate]:
        """
        Poll for rating change notifications for subscribed members.

        Returns a list of :class:`RatingUpdate` objects for every player
        whose rating has changed since the last poll. Members are
        considered "subscribed" when they have an active OAuth
        connection with the ``webhook:subscribe`` scope.
        """
        data = await self._client._request("GET", "/partner/rating-updates")
        if not isinstance(data, dict):
            return []
        return [RatingUpdate.model_validate(u) for u in data.get("updates", [])]

    async def find(self, name: str) -> Member | None:
        """
        Return the first search hit for a name, or ``None``.

        Convenience method for the common "look up by name" case::

            mike = await client.members.find("Mike Barker")
            if mike:
                print(mike.rating_for("pickleball"))
        """
        async for member in self.search(name=name, page_size=1, max_results=1):
            return member
        return None


class MatchesResource(_Resource):
    """Match submission — one call submits a full batch."""

    async def submit(self, batch: MatchBatch) -> MatchBatchResult:
        """
        Submit a :class:`MatchBatch` for rating calculation.

        All players in every match must have granted the ``match:submit``
        scope via OAuth (unless your API key has the
        ``match:submit:trusted`` scope, which skips per-player consent).

        Set ``batch.dry_run = True`` to validate without persisting.

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
                        games=[Game(scores=[11, 8]), Game(scores=[11, 5])],
                    ),
                ],
            )
            result = await client.matches.submit(batch)
            if result.ok:
                print(f"Submitted {result.num_games} games")
        """
        body = batch.model_dump(by_alias=True, exclude_none=True)
        data = await self._client._request("POST", "/partner/matches", json=body)
        return MatchBatchResult.model_validate(data)

    async def test_webhook(self, webhook_url: str) -> dict[str, Any]:
        """Send a test payload to a webhook URL."""
        data = await self._client._request(
            "POST", "/partner/webhook-test", json={"webhookUrl": webhook_url}
        )
        return data or {}


class OAuthResource(_Resource):
    """
    OAuth 2.0 flow for obtaining player consent.

    Typical flow:

    1. Call :meth:`authorize` to start an authorization — you get a URL
       to redirect the player to.
    2. The player approves on the Vairified site and gets redirected to
       your ``redirect_uri`` with a ``code`` query parameter.
    3. Call :meth:`exchange_token` to swap the code for access and
       refresh tokens plus the player's UUID.
    4. Store the refresh token and call :meth:`refresh` when the
       access token expires.
    5. Call :meth:`revoke` to disconnect a player from your app.
    """

    async def authorize(
        self,
        redirect_uri: str,
        *,
        scopes: list[OAuthScope] | None = None,
        state: str | None = None,
    ) -> AuthorizationResponse:
        """
        Start an OAuth authorization flow.

        :param redirect_uri: Your application's callback URL.
        :param scopes: Scopes to request. Defaults to
            ``["profile:read", "rating:read"]``. ``profile:read`` is
            always added if missing.
        :param state: CSRF protection token — persist and verify on callback.
        :raises OAuthError: If a requested scope is invalid.
        """
        from vairified.errors import OAuthError  # local import to avoid cycle

        scope_list: list[str] = [*(scopes or DEFAULT_SCOPES)]
        if "profile:read" not in scope_list:
            scope_list = ["profile:read", *scope_list]

        for scope in scope_list:
            if scope not in SCOPES:
                raise OAuthError(
                    f"Invalid scope: {scope}", error_code="invalid_scope"
                )

        data = await self._client._request(
            "POST",
            "/partner/oauth/authorize",
            json={
                "redirectUri": redirect_uri,
                "scope": ",".join(scope_list),
                "state": state,
            },
        )
        payload = data or {}
        return AuthorizationResponse(
            authorization_url=payload.get("authorizationUrl", ""),
            code=payload.get("code", ""),
            state=state,
        )

    async def exchange_token(self, code: str, redirect_uri: str) -> TokenResponse:
        """Exchange an authorization code for access and refresh tokens."""
        data = await self._client._request(
            "POST",
            "/partner/oauth/token",
            json={"code": code, "redirectUri": redirect_uri},
        )
        return _token_response_from(data or {})

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Refresh an expired access token using a refresh token."""
        data = await self._client._request(
            "POST",
            "/partner/oauth/refresh",
            json={"refreshToken": refresh_token},
        )
        return _token_response_from(data or {})

    async def revoke(self, player_id: str) -> dict[str, Any]:
        """Revoke a player's OAuth connection to your app."""
        data = await self._client._request(
            "POST",
            "/partner/oauth/revoke",
            json={"playerId": player_id},
        )
        return data or {}

    async def available_scopes(self) -> list[dict[str, str]]:
        """Return the list of OAuth scopes the server currently supports."""
        data = await self._client._request("GET", "/partner/oauth/scopes")
        if not isinstance(data, dict):
            return []
        return data.get("scopes", [])


class LeaderboardResource(_Resource):
    """Read-only leaderboard queries."""

    async def list(
        self,
        *,
        category: str | None = None,
        age_bracket: str | None = None,
        scope: str | None = None,
        state: str | None = None,
        city: str | None = None,
        club_id: str | None = None,
        gender: str | None = None,
        verified_only: bool = False,
        min_games: int | None = None,
        limit: int = 50,
        offset: int = 0,
        search: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a leaderboard page with optional filters."""
        params: dict[str, Any] = {"limit": limit, "offset": offset}
        for key, value in (
            ("category", category),
            ("ageBracket", age_bracket),
            ("scope", scope),
            ("state", state),
            ("city", city),
            ("clubId", club_id),
            ("gender", gender),
            ("minGames", min_games),
            ("search", search),
        ):
            if value is not None:
                params[key] = value
        if verified_only:
            params["verifiedOnly"] = True
        data = await self._client._request("GET", "/leaderboard", params=params)
        return data or {}

    async def rank(
        self,
        player_id: str,
        *,
        category: str = "doubles",
        age_bracket: str = "open",
        scope: str = "global",
        state: str | None = None,
        city: str | None = None,
        club_id: str | None = None,
        context_size: int = 5,
    ) -> dict[str, Any]:
        """Fetch a specific player's rank + nearby players."""
        body: dict[str, Any] = {
            "playerId": player_id,
            "category": category,
            "ageBracket": age_bracket,
            "scope": scope,
            "contextSize": context_size,
        }
        if state:
            body["state"] = state
        if city:
            body["city"] = city
        if club_id:
            body["clubId"] = club_id
        data = await self._client._request("POST", "/leaderboard/rank", json=body)
        return data or {}

    async def categories(self) -> dict[str, Any]:
        """List available leaderboard categories, brackets, and scopes."""
        data = await self._client._request("GET", "/leaderboard/categories")
        return data or {}


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _token_response_from(data: dict[str, Any]) -> TokenResponse:
    """Build a TokenResponse from a raw OAuth response dict."""
    scope_raw = data.get("scope", "")
    scope_list = scope_raw.split(",") if scope_raw else []
    return TokenResponse(
        access_token=data.get("accessToken", ""),
        refresh_token=data.get("refreshToken"),
        expires_in=data.get("expiresIn", 3600),
        scope=scope_list,
        player_id=data.get("playerId", ""),
    )


__all__ = [
    "ENVIRONMENTS",
    "LeaderboardResource",
    "MatchesResource",
    "MembersResource",
    "OAuthResource",
    "Vairified",
]
