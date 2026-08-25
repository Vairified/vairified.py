# Changelog

All notable changes to the Vairified Python SDK are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- towncrier release notes start -->

## [0.6.0] - 2026-08-25

### Added

- `client.members.get_by_email()` resolves up to 100 members by their exact email address, so partners holding an email but not a member ID can link users to their VAIR identity instead of waiting for each player to complete SSO. It requires the new `key:player:lookup` scope, granted per partner on approval — holding `key:player:search` (or `key:read`, or `key:admin`) does not imply it. Matching is exact and case-insensitive, with deliberately no partial, prefix or fuzzy matching. Every address supplied comes back in either `matched` or `not_found`, so `not_found` should be read directly rather than inferred by diffing the input against the results; note that a `not_found` address is not proof the person has no VAIR account, because unclaimed imported records are excluded from this lookup. `MemberEmailMatch.members` is a list, since an email is not a unique key in VAIR — use `.sole` (which returns `None` when the address is ambiguous) or check `.is_ambiguous` rather than assuming a single result. The SDK rejects an empty list, more than 100 addresses, and any address containing a comma before making the request. Adds the frozen models `MembersByEmailResult` (with `.get()`, `.all_resolved` and `.member_count`) and `MemberEmailMatch`. ([#995](https://github.com/Vairified/Vairified/issues/995))
- `client.referrals` is a new sub-resource for ambassador referral credit, covering both halves of event reconciliation.

  `referrals.get(member_ids)` reports who currently earns credit for up to 100 members. This is what lets a partner tell "already credited to my own event host — nothing to do" from "credited to a different ambassador — a person should look, because claiming it takes credit from them". `POST /ambassador/track` could not answer that: it reports that credit exists without saying whose. Each `MemberAttribution` carries `attributed`, the crediting `ambassador_member_id`, and `attributed_at`, with `is_claimable` and `held_by_someone_other_than()` helpers; note that `ambassador_member_id` is `None` both when nobody holds credit and when the holder has no member id of their own, so check `attributed` to tell those apart.

  `referrals.attribute(...)` credits an ambassador for up to 500 players in one authenticated call, replacing a public endpoint capped at five requests a minute — which meant twenty minutes of trickling for a hundred-player field, with no record of which partner submitted it. `registration_published_at` is the date the event's registration page was first published; accounts created before it did not come from the event and are rejected with `account_predates_event`. VAIR applies that rule itself, so every partner is held to the same one, and the date you supply is recorded for audit because VAIR holds no record of your registration pages and cannot verify it. Every member id gets its own outcome — `attributed`, `already_attributed`, `account_predates_event` or `not_found` — with `already_attributed` and `predated_event` helpers; resubmitting is safe, since attribution is one-per-player forever and enforced by a database constraint.

  Both methods need their own API-key permission, granted per partner: `key:referral:read` and `key:referral:write`. Neither is implied by a general read, write or admin key. ([#1130](https://github.com/Vairified/Vairified/issues/1130))
- `Member.member_since` carries the DATE a member's VAIR account was created (`YYYY-MM-DD`, UTC), so a partner can apply a new-accounts-only referral rule — crediting an ambassador only for accounts created because of their event. It is deliberately a date rather than a timestamp: the question it answers is "did this account pre-date my event?", and a timestamp invites tighter heuristics than the rule intends. Present on `members.get()`, `members.get_bulk()` and `members.get_by_email()` — the calls where you already know which member you asked about. It is `None` on `members.search()`, which is discovery, because account age is not a property you should be able to browse strangers by; it is also `None` against an API build that predates the field, so treat absence as "unknown" rather than "new". ([#1132](https://github.com/Vairified/Vairified/issues/1132))
- `client.matches.tournament_import()` now reports which players it created. An import previously returned only a count of ghost players, so a partner could cause dozens of accounts to exist and address none of them — and therefore still could not submit scores for a field containing anyone new. `TournamentImportResult.created_ghost_members` carries a `TournamentImportCreatedGhost` per created player, where `ref` is the email or phone you supplied in `ghost_members` (echoed back so results map onto your own records without a second lookup) and `member_id` is the allocated public id, usable immediately in `matches.submit()`. The list is always present, so it can be iterated without a `None` check: it is empty on a dry-run, which creates nothing, and empty against an older API build that does not send the field. Entries the import matched to a player who already existed are deliberately absent — resolving an existing email to a member requires the `key:player:lookup` scope and `members.get_by_email()`, and this endpoint is not a way around that. ([#1134](https://github.com/Vairified/Vairified/issues/1134))

## [0.4.0] - 2026-07-02

### Breaking Changes

- Per-sport VAIRification & VAIR-Pro status (Vairified#783). `is_vairified`, `is_rater`, `is_vair_pro`, and `is_vair_pro_status` moved off `member.status` onto each per-sport entry — read them via `member.sport["pickleball"].is_vairified`. `member.status` now carries only the genuinely global flags: `is_wheelchair`, `is_ambassador`, `is_connected`. This mirrors the backend: a player can be VAIRified / a VAIR Pro in one sport but not another.

### Added

- `SportRating.is_vairified`, `.is_rater`, `.is_vair_pro`, `.is_vair_pro_status` (`Literal["PENDING", "ACTIVE"] | None`), on every `member.sport` entry.

## [0.3.2] - 2026-07-15

### Fixed

- **OAuth + member requests now match the deployed Partner API.** Earlier versions sent the wrong wire and could not complete the flow against `api-*.vairified.com` without hand-patching ([#844]):
  - `oauth.authorize()`, `oauth.exchange_token()`, `oauth.refresh()`, and `oauth.revoke()` now send snake_case bodies (`redirect_uri`, `refresh_token`, `player_id`), space-delimited `scope` (RFC 6749 §3.3), and the required `grant_type` (`authorization_code` / `refresh_token`).
  - Token responses are read from the API's snake_case fields (`access_token`, `refresh_token`, `expires_in`, `player_id`, space-delimited `scope`), falling back to the deprecated `scopes` array.
  - `oauth.authorize()` reads the API's `authorization_url` field.
  - `members.get()` looks the player up by the `memberId` query parameter (was `id`, which returned 404).

### Added

- `get_authorization_url()` / `OAuthConfig` accept an optional `client_id` (your `PartnerApp` slug) and emit it as `client_id` — required by the browser `GET /partner/oauth/authorize` endpoint. Scopes in the built URL are now space-delimited.

[#844]: https://github.com/Vairified/Vairified/issues/844

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
