# Changelog

All notable changes to the Vairified Python SDK are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- towncrier release notes start -->

## [0.3.1] - 2026-04-14

### Changed

- Removed `key:dry-run` scope — `dryRun` is now a request-body-only toggle. Any key with `key:match:submit` can dry-run; no special scope needed.

### Fixed

- Recreational rating abbreviation: unverified players now correctly show `R` instead of `Rv` in partner API responses.
- Numeric member ID strings in compressed match `teams` arrays are no longer coerced to integers by the backend.

## [0.3.0] - 2026-04-12

### Breaking Changes

- All 6 OAuth scope strings now carry the `user:` prefix (`profile:read` → `user:profile:read`, etc.) to match the backend scope-namespace split.

### Added

- `members.get_bulk(ids, *, sport=None)` — fetch up to 100 members by ID in one call (`GET /partner/members`).
- `matches.tournament_import(body)` — import tournament results with automatic player matching and ghost creation (`POST /partner/tournament-import`).
- `webhooks.deliveries(*, event=None, status=None, limit=20, offset=0)` — inspect recent webhook delivery attempts (`GET /partner/webhook-deliveries`).
- New `WebhooksResource` sub-resource accessible via `client.webhooks`.
- New models: `TournamentImportResult`, `WebhookDelivery`, `WebhookDeliveriesResult`.

## [0.2.0] - 2026-04-10

### Breaking Changes

- Client operations are now organized as sub-resources that mirror the REST layout: `client.members.get/search/find/rating_updates`, `client.matches.submit`, `client.oauth.authorize/exchange_token/refresh/revoke`, and `client.leaderboard.list/rank/categories`. Flat methods like `client.get_member()`, `client.search()`, and `client.submit_match()` have been removed.
- Complete SDK rewrite to match the multi-sport Partner API v1 shape. Flat single-sport fields like `member.rating` and `member.rating_splits.gender` are gone — rating data now lives under `member.sport[sport_code]` as a dict-like `SportRating`. Use `member.rating_for("pickleball")` for the primary rating and `member.split("overall-open")` to access specific brackets.
- `Match` now takes `teams: list[list[str]]` and `games: list[Game]` instead of `team1`/`team2` and per-game score tuples. This natively supports n-team × n-game matches (singles, doubles, round-robin, best-of-N) through a single shape. Match submission goes through a new `MatchBatch` wrapper that carries shared defaults (`sport`, `win_score`, `win_by`, `bracket`, `event`, `match_date`) for every match in the batch.

### Added

- All models are now `pydantic` v2 `BaseModel`s. Response models are frozen (immutable), accept both snake_case and camelCase field names via aliases, and tolerate unknown server fields so the SDK stays forward-compatible with API additions. Request models use `extra="forbid"` to catch typos at construction time.
- Every model has a useful `__repr__` for REPL exploration — e.g. `<Member #4873327 'Mike B.' rating=3.915 VO>`, `<RatingUpdate #42 'Jane D.' 4.000 ↑ 4.100>`, `<MatchBatch sport='pickleball' matches=3 games=7>`.
- `Gender` is now a `StrEnum` (`Gender.MALE`, `Gender.FEMALE`, `Gender.OTHER`, `Gender.UNKNOWN`). `OAuthScope` is a `Literal` type alias covering every valid scope string, so IDEs and type checkers catch typos in scope lists at authoring time.
- `SportRating` is dict-like — access rating splits via subscript (`pb["overall-open"]`), check membership with `in`, iterate with `for key, split in pb`, and use `len()`, `.keys()`, and `.get()`. No need to reach into `.rating_splits` directly.
- `Vairified` accepts `env=` (`"production"`, `"staging"`, `"local"`) as a convenience over passing a full `base_url`. Reads `VAIRIFIED_ENV` from the environment when not supplied. The `ENVIRONMENTS` dict is exported for callers that want to inspect the mapping.
- `client.members.get()` and `client.members.search()` accept a `sport=` parameter (single code or list) to restrict the ratings returned on each member. Omit to get every sport each player has ratings in.
- `client.members.search()` is now an auto-paginating async iterator. Iterate results directly with `async for member in client.members.search(...)` — pages are fetched lazily, so memory usage stays bounded regardless of result count. Use `max_results=N` to cap the total, or `break` out of the loop to stop early.
