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

* :attr:`Vairified.members` — get/search/get_bulk/get_by_email/rating_updates
* :attr:`Vairified.matches` — submit batch, tournament_import
* :attr:`Vairified.oauth` — OAuth authorization flow
* :attr:`Vairified.leaderboard` — leaderboard queries
* :attr:`Vairified.webhooks` — webhook delivery inspection
* :attr:`Vairified.usage` — API usage stats (method: ``await client.usage()``)
"""

from __future__ import annotations

import os
import re
from collections.abc import AsyncIterator, Sequence
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
    AttributionResult,
    MatchBatch,
    MatchBatchResult,
    Member,
    MembersAttributionResult,
    MembersByEmailResult,
    RatingUpdate,
    SearchFilters,
    TournamentImportResult,
    WebhookDeliveriesResult,
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
_MAX_EMAILS_PER_LOOKUP = 100


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
        self.webhooks = WebhooksResource(self)
        self.referrals = ReferralsResource(self)

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


# Publication dates are exchanged as calendar dates, never timestamps: the rule
# they feed asks "did this account pre-date my event?", nothing finer.
_ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
        params: dict[str, Any] = {"memberId": player_id}
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
        sport_param = (
            sport if isinstance(sport, str) else (",".join(sport) if sport else None)
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
            batch: list[dict[str, Any]] = (
                data
                if isinstance(data, list)
                else (data.get("players", []) if isinstance(data, dict) else [])
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
        connection with the ``user:webhook:subscribe`` scope.
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

    async def get_bulk(
        self,
        ids: Sequence[int],
        *,
        sport: str | None = None,
    ) -> list[Member]:
        """
        Fetch up to 100 members by their member IDs in one call.

        :param ids: Sequence of integer member IDs (max 100).
        :param sport: Optional sport code to filter ratings.
        :returns: List of :class:`Member` objects. Unknown IDs are
            silently omitted -- the list may be shorter than *ids*.
        :raises ValueError: If more than 100 IDs are provided.

        Example::

            members = await client.members.get_bulk([4873327, 4873328])
            for m in members:
                print(m.name, m.rating_for("pickleball"))
        """
        if len(ids) > 100:
            raise ValueError("Maximum 100 member IDs per request")
        params: dict[str, str] = {"ids": ",".join(str(i) for i in ids)}
        if sport:
            params["sport"] = sport
        rows = await self._client._request("GET", "/partner/members", params=params)
        if not isinstance(rows, list):
            return []
        return [Member.model_validate(row) for row in rows]

    async def get_by_email(
        self,
        emails: Sequence[str],
        *,
        sport: str | None = None,
    ) -> MembersByEmailResult:
        """
        Resolve up to 100 members by their **exact** email address.

        Use this to link your users to their VAIR identity when you hold
        their email but not their member ID -- e.g. resolving a tournament
        roster at registration instead of waiting for each player to
        complete SSO.

        **Requires the ``key:player:lookup`` scope**, which is granted per
        partner on approval. Holding ``key:player:search`` does not imply it.

        Matching is exact and case-insensitive; there is deliberately no
        partial, prefix or fuzzy matching. Every address you supply comes
        back in either ``matched`` or ``not_found``, so read ``not_found``
        directly instead of diffing your input against the results.

        A ``not_found`` address is **not** proof the person has no VAIR
        account -- unclaimed imported records are excluded from this lookup.

        :param emails: Email addresses to resolve (max 100).
        :param sport: Optional sport code to scope ratings.
        :returns: A :class:`MembersByEmailResult` envelope.
        :raises ValidationError: If the list is empty, holds more than 100
            addresses, or any address contains a comma.

        Example::

            result = await client.members.get_by_email(
                ["ada@example.com", "nobody@example.com"]
            )

            for match in result.matched:
                member = match.sole  # None when the address is ambiguous
                if member:
                    print(match.email, "->", member.member_id)

            print("no VAIR account found for:", result.not_found)
        """
        # Validate before the round trip so the caller gets a typed error
        # rather than a 400 they have to interpret.
        if not emails:
            raise ValidationError("At least one email address is required")
        if len(emails) > _MAX_EMAILS_PER_LOOKUP:
            raise ValidationError(
                f"Maximum {_MAX_EMAILS_PER_LOOKUP} email addresses per request"
            )
        # A comma inside an entry would split into two addresses server-side
        # and silently shift every result -- reject it rather than send it.
        for email in emails:
            if "," in email:
                raise ValidationError(
                    f"Email address must not contain a comma: {email}"
                )

        params: dict[str, str] = {"emails": ",".join(emails)}
        if sport:
            params["sport"] = sport
        data = await self._client._request(
            "GET", "/partner/members/by-email", params=params
        )
        if not isinstance(data, dict):
            return MembersByEmailResult()
        return MembersByEmailResult.model_validate(data)


class MatchesResource(_Resource):
    """Match submission — one call submits a full batch."""

    async def submit(self, batch: MatchBatch) -> MatchBatchResult:
        """
        Submit a :class:`MatchBatch` for rating calculation.

        All players in every match must have granted the ``user:match:submit``
        scope via OAuth (unless your API key has the
        ``user:match:submit:trusted`` scope, which skips per-player consent).

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

    async def tournament_import(
        self,
        body: dict[str, Any],
    ) -> TournamentImportResult:
        """
        Import tournament results with automatic player matching.

        Players are matched by email first, then name+location. Unmatched
        players become ghost accounts that can be claimed later.

        :param body: Tournament data dict with keys:
            ``tournamentName``, ``sport``, ``winScore``, ``winBy``,
            ``matches`` (list of match dicts with ``identifier``,
            ``event``, ``bracket``, ``format``, ``matchDate``,
            ``teamA``, ``teamB``).
        :returns: :class:`TournamentImportResult` with counts.
        :raises ValidationError: If the payload is malformed.

        Example::

            result = await client.matches.tournament_import({
                "tournamentName": "Austin Open 2026",
                "sport": "pickleball",
                "winScore": 11,
                "winBy": 2,
                "matches": [...]
            })
            print(f"Imported {result.matches_imported} matches")
        """
        data = await self._client._request(
            "POST", "/partner/tournament-import", json=body
        )
        return TournamentImportResult.model_validate(data)

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
            ``["user:profile:read", "user:rating:read"]``. ``user:profile:read`` is
            always added if missing.
        :param state: CSRF protection token — persist and verify on callback.
        :raises OAuthError: If a requested scope is invalid.
        """
        from vairified.errors import OAuthError  # local import to avoid cycle

        scope_list: list[str] = [*(scopes or DEFAULT_SCOPES)]
        if "user:profile:read" not in scope_list:
            scope_list = ["user:profile:read", *scope_list]

        for scope in scope_list:
            if scope not in SCOPES:
                raise OAuthError(f"Invalid scope: {scope}", error_code="invalid_scope")

        data = await self._client._request(
            "POST",
            "/partner/oauth/authorize",
            json={
                # snake_case body; scope space-delimited per RFC 6749 §3.3.
                "redirect_uri": redirect_uri,
                "scope": " ".join(scope_list),
                "state": state,
            },
        )
        payload = data or {}
        return AuthorizationResponse(
            authorization_url=payload.get("authorization_url", ""),
            code=payload.get("code", ""),
            state=state,
        )

    async def exchange_token(self, code: str, redirect_uri: str) -> TokenResponse:
        """Exchange an authorization code for access and refresh tokens."""
        data = await self._client._request(
            "POST",
            "/partner/oauth/token",
            # RFC 6749 §4.1.3 — requires grant_type + snake_case redirect_uri
            # (which must match the authorize request).
            json={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
            },
        )
        return _token_response_from(data or {})

    async def refresh(self, refresh_token: str) -> TokenResponse:
        """Refresh an expired access token using a refresh token."""
        data = await self._client._request(
            "POST",
            "/partner/oauth/refresh",
            # RFC 6749 §6 — refresh grant, snake_case body.
            json={"grant_type": "refresh_token", "refresh_token": refresh_token},
        )
        return _token_response_from(data or {})

    async def revoke(self, player_id: str) -> dict[str, Any]:
        """Revoke a player's OAuth connection to your app."""
        data = await self._client._request(
            "POST",
            "/partner/oauth/revoke",
            json={"player_id": player_id},
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


class WebhooksResource(_Resource):
    """Webhook delivery inspection."""

    async def deliveries(
        self,
        *,
        event: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> WebhookDeliveriesResult:
        """
        List recent webhook delivery attempts.

        :param event: Filter by event type (e.g. ``"rating.updated"``).
        :param status: Filter: ``"all"``, ``"pending"``, ``"success"``,
            or ``"failed"``.
        :param limit: Results per page (1-100, default 20).
        :param offset: Pagination offset.
        :returns: :class:`WebhookDeliveriesResult` with entries and total.

        Example::

            result = await client.webhooks.deliveries(status="failed")
            for d in result.deliveries:
                print(d.event, d.status_code, d.error_message)
        """
        params: dict[str, str | int] = {"limit": limit, "offset": offset}
        if event:
            params["event"] = event
        if status:
            params["status"] = status
        data = await self._client._request(
            "GET", "/partner/webhook-deliveries", params=params
        )
        return WebhookDeliveriesResult.model_validate(data)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _token_response_from(data: dict[str, Any]) -> TokenResponse:
    """Build a TokenResponse from a raw OAuth response dict."""
    # The API returns `scope` as a space-delimited string (RFC 6749 §3.3);
    # fall back to the deprecated `scopes` array for older API builds.
    scope_raw = data.get("scope", "")
    if scope_raw:
        scope_list = scope_raw.split()
    else:
        scopes_field = data.get("scopes")
        scope_list = scopes_field if isinstance(scopes_field, list) else []
    return TokenResponse(
        access_token=data.get("access_token", ""),
        refresh_token=data.get("refresh_token"),
        expires_in=data.get("expires_in", 3600),
        scope=scope_list,
        player_id=data.get("player_id", ""),
    )


__all__ = [
    "ENVIRONMENTS",
    "LeaderboardResource",
    "MatchesResource",
    "MembersResource",
    "OAuthResource",
    "Vairified",
    "WebhooksResource",
]


class ReferralsResource(_Resource):
    """
    Read and record which ambassador earns referral credit for a player.

    Each method needs its own API-key permission, granted per partner:
    ``key:referral:read`` for :meth:`get` and ``key:referral:write`` for
    :meth:`attribute`. Neither is implied by a general read, write or admin
    key -- reading attribution exposes who recruited whom, and writing it
    decides who earns commission.
    """

    async def get(self, member_ids: Sequence[int]) -> MembersAttributionResult:
        """
        Who currently earns referral credit for these members.

        Use this before :meth:`attribute` to tell apart the two cases that
        matter: a member already credited to your own event host (nothing to
        do) and one credited to a different ambassador (a person should look,
        because claiming it takes credit from them).

        :param member_ids: Member ids to look up (max 100).
        :returns: A :class:`MembersAttributionResult` envelope.
        :raises ValidationError: If the list is empty or holds more than 100 ids.

        Example::

            result = await client.referrals.get([4873327, 4873328])

            for a in result.claimable:
                print(a.member_id, "has no credit yet")

            print("no such member:", result.not_found)
        """
        ids = list(member_ids)
        if not ids:
            raise ValidationError("At least one member id is required")
        if len(ids) > 100:
            raise ValidationError("Maximum 100 member ids per request")

        data = await self._client._request(
            "GET",
            "/partner/members/attribution",
            params={"memberIds": ",".join(str(i) for i in ids)},
        )
        if not isinstance(data, dict):
            return MembersAttributionResult()
        return MembersAttributionResult.model_validate(data)

    async def attribute(
        self,
        *,
        referral_code: str,
        registration_published_at: str,
        member_ids: Sequence[int],
    ) -> AttributionResult:
        """
        Credit an ambassador for players their event recruited.

        ``registration_published_at`` is the date the event's registration page
        was **first published**. Accounts created before it did not come from
        the event and are rejected with ``account_predates_event``. VAIR applies
        that rule itself, so every partner is held to the same one.

        VAIR cannot verify the date -- it holds no record of your registration
        pages -- so the value you send is recorded for audit. Send the real one.

        Safe to retry: attribution is one-per-player forever, enforced by the
        database, so a resubmitted player returns ``already_attributed`` and
        nothing changes.

        :param referral_code: The ambassador's public referral code.
        :param registration_published_at: Publication date, ``YYYY-MM-DD``.
        :param member_ids: Member ids to attribute (max 500).
        :returns: An :class:`AttributionResult` with one entry per member id.
        :raises ValidationError: If the code is blank, the list is empty or
            holds more than 500 ids, or the date is not ``YYYY-MM-DD``.

        Example::

            result = await client.referrals.attribute(
                referral_code="hillhurst-open",
                registration_published_at="2026-08-01",
                member_ids=[4873327, 4873328],
            )

            print(result.attributed, "newly credited")
            print("need a human:", result.already_attributed)
            print("too old to credit:", result.predated_event)
        """
        code = referral_code.strip()
        if not code:
            raise ValidationError("A referral code is required")
        # Checked here so a typo fails immediately rather than as a 400 the
        # caller has to interpret -- and because a wrong date silently changes
        # who is creditable, which is worse than an outright rejection.
        if not _ISO_DATE.match(registration_published_at):
            raise ValidationError(
                "registration_published_at must be a calendar date formatted YYYY-MM-DD"
            )
        ids = list(member_ids)
        if not ids:
            raise ValidationError("At least one member id is required")
        if len(ids) > 500:
            raise ValidationError("Maximum 500 member ids per request")

        data = await self._client._request(
            "POST",
            "/partner/ambassador/attribution",
            json={
                "referralCode": code,
                "registrationPublishedAt": registration_published_at,
                "memberIds": ids,
            },
        )
        if not isinstance(data, dict):
            return AttributionResult(attributed=0)
        return AttributionResult.model_validate(data)
