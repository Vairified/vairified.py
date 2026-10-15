# Changelog

All notable changes to the Vairified Python SDK are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

<!-- towncrier release notes start -->

## [0.9.0] - Unreleased

Mirrors the Partner API v1 rating-tracks release. No field is removed or renamed. Three
changes can affect existing code: `sort_by` / `SearchFilters.sort_field` are narrowed to a
`Literal` (type checkers only, there is no runtime check), `sort_order` is narrowed to
`"asc"` / `"desc"`, and an unset `sort_order` now gives ascending order instead of descending.
Three API behaviour changes need a look too: verified singles' `abbr` is `VS` (it was `S`), the
recreational chain is `R` for every player (`Rv` is gone), and the leaderboard's `verified_only` no longer means "unverified only" when it
is unset or `False`. See the [migration guide](docs/migrating.rst).

### Added

- **`label` on every rating split and on each sport** -- `RatingSplit.label` and
  `SportRating.label` (`str | None`): the label the VAIRified web app shows, bracket suffix
  included. The labels are `VO`, `VG`, `VM`, `VS` (verified tracks), `R` (the recreational
  doubles chain) and `RS` (recreational singles), e.g. `VS12-13`, `RS40+`. Typed `str | None` only
  so an older API, which does not send it, still parses. Use it for display. Also on the webhook's
  `RatingUpdatedSport`.
- **Label lookup** -- `sport_rating.by_label("VS")` and `member.split_by_label("RS40+", sport=...)`,
  alongside `get()` / `split()`.
- **The recreational singles split** `recreational_singles-*` (abbr `RS` plus the bracket
  suffix) appears in `rating_splits`. It never becomes a sport's primary rating. (The engine's
  recreational same-gender and mixed tracks are internal; the API never sends them.)
- **Six leaderboard tracks** -- the `LeaderboardCategory` enum (`OVERALL`, `GENDER`, `SINGLES`,
  `MIXED`, `RECREATIONAL`, `RECREATIONAL_SINGLES`). `category` on `leaderboard.list()` /
  `rank()` also accepts the labels in `LEADERBOARD_CATEGORY_LABELS` (`VO VG VM VS R RS`, any
  case), typed as `LeaderboardCategoryLabel`. Plain strings keep working, and the API still
  resolves the legacy labels `S`, `RO` and `Rv`. `list(LeaderboardCategory)` gives the six
  codes in API order, the equivalent of the TypeScript SDK's `LEADERBOARD_CATEGORIES`.
- **`leaderboard.category_list()`** -- the six tracks from `GET /leaderboard/categories` as
  frozen `LeaderboardCategoryInfo` models (`code`, `name`, `label`, `verified_only`).
  `categories()` still returns the raw dict.
- **`PermissionDeniedError`** (HTTP 403), a `VairifiedError` subclass. A 403 used to arrive as a
  plain `VairifiedError` with `status_code == 403`; existing `except VairifiedError` blocks keep
  working.
- **`ScoreEntryPausedError`** (HTTP 503, `code == "SCORE_ENTRY_PAUSED"`), with `retry_after` in
  seconds. While Vairified pauses score entry for a rating maintenance window,
  `matches.submit()` and `matches.tournament_import()` raise it; reads are unaffected. Nothing
  was saved: resubmit the same payload after `retry_after` seconds (the API asks for 300).
  `retry_after` comes from the `Retry-After` header, or the body's `retryAfter` when the header
  is missing.
- **`ServiceUnavailableError`** (HTTP 503), the parent of `ScoreEntryPausedError`, with
  `retry_after` when the server sends one. A 503 used to arrive as a plain `VairifiedError` with
  `status_code == 503`; existing `except VairifiedError` blocks keep working. The SDK still never
  retries on its own; if you retry, wait at least `retry_after` seconds and cap the attempts.
- **`PARTNER_SEARCH_SORT_FIELDS`** and the `PartnerSearchSortField` literal type.
- **`sport_code` on `leaderboard.list()` and `rank()`**, sent as `sportCode`. Rank and percentile
  are now per sport, so pass it for any player who plays more than one sport.

### Changed

- **Verified-track ratings are no longer sent for a player who is not verified in that sport.**
  This applies to `members.get()`, `get_bulk()`, `get_by_email()` and `search()`. The splits
  `overall-*`, `gender-*`, `mixed-*`, `singles-*` and `asymmetric-*` are missing from
  `rating_splits`. The sport's primary `rating` / `abbr` falls back to the recreational chain
  (`recreational-open`, abbr `R`). A sport with nothing visible is missing from
  `member.sport`, so `rating_for()` returns `None` for it. *For integrators:* do not assume
  `overall-open` exists. Check `key in sport_rating` or `sport_rating.is_vairified` first.
- **`members.rating_updates()`** follows the same rule. `new_rating`, `sport` and `changed_at`
  come from the newest rating a partner may see.
- **`rating.updated` webhook** follows the same rule. No event is sent when only withheld ratings
  change. A change confined to `RS` now sends one. The snapshot carries the new `label` and the
  `recreational_singles-*` keys; `verify_webhook()` already passes unknown keys through, so no
  receiver change is needed.
- **Event members** (`GET /partner/event/{eventId}/members`, which this SDK does not wrap):
  `rating` is the verified overall-open value, otherwise recreational-open, otherwise absent.
- **Verified singles' `abbr` is `VS`, matching the web app** (it was `S`). The `singles-*`
  split's `abbr`, and a sport's primary `abbr` when it is verified singles, are now `VS` plus the
  bracket suffix (`VS`, `VS50+`, `VS12-13`) instead of `S` (`S`, `S50+`). Same field, same type;
  only the value changes, in `members.*`, `rating_updates()`, `rating.updated` webhooks and the
  release refresh. `abbr` now equals `label` for every verified track. *For integrators:* if you
  match on `S`, match on `VS` (see the migration guide). As a leaderboard `category`, `"S"` still
  resolves to `singles`.
- **The recreational chain's `abbr` is `R` for every player.** It used to be `Rv` for a player
  verified in the sport; `Rv` (and the label `RO`) is no longer sent anywhere: not by
  `members.*`, not by `rating_updates()`, not in `rating.updated`. *For integrators:* code that
  matched `abbr == "Rv"` to spot a verified player never matches now. Use
  `sport_rating.is_vairified`.
- **`is_vairified` means a verified `VO` / `VG` / `VM` / `VS` rating in the sport.** Recreational
  ratings (`R`, `RS`) never make a player VAIRified. No existing player changes.
- **Leaderboard:** verified boards (`overall`, `gender`, `mixed`, `singles`) list only players
  verified in the sport, for API keys too. The recreational boards (`R`, `RS`) rank every player.
  Rank and percentile are scoped to the sport.
- **Leaderboard: `verified_only` is an optional narrowing filter.** `True` lists only VAIRified
  players; unset or `False` applies no filter. Before, the API read an unset or `False` value as
  "unverified players only", so a call that left it out got an empty verified board and half of
  the recreational one. `verified_only` on `leaderboard.list()` now defaults to `None` (was
  `False`) and is sent only when you set it, so an explicit `False` goes out instead of being
  dropped. *For integrators:* if you relied on the old default to list unverified players, that
  filter no longer exists.
- **Leaderboard: the key the SDK sends is now checked on the public routes.** On
  `leaderboard.list()`, `categories()` and `category_list()`, an invalid or revoked key raises
  `AuthenticationError` (401). A key without `leaderboard:read` raises `PermissionDeniedError`
  (403). Before, these routes ignored the key.
- **Rating splits: `rating_splits` never contains provisional (`provisional-*`) or asymmetric
  (`asymmetric-*`) splits** -- in member lookups, `rating_updates()`, `rating.updated` webhooks and
  the release refresh. Earlier 0.9.0 builds received them with `label: None`. A sport whose only
  ratings were on those tracks no longer appears. `label` is always one of `VO`, `VG`, `VM`, `VS`,
  `R`, `RS` (plus the age-bracket suffix); it stays typed `str | None` so older APIs still parse.
- **`members.search()` sorting is limited to `lastName`, `firstName`, `memberId`, `city`, `state`
  and `country`.** The default is `lastName` ascending. `sort_by` and
  `SearchFilters.sort_field` are now typed `PartnerSearchSortField`, a `Literal`. This applies to
  type checkers only. A value outside the list is still sent, as in the TypeScript SDK, and the
  API answers it with a 400 (`ValidationError`). `sort_order` / `SearchFilters.sort_direction`
  are typed `Literal["asc", "desc"]`.
  `rating` was never a real sort: it always failed with a server error (500), and now gets the 400.

### Deprecated

- **`club_id` on `leaderboard.list()`, and `city` / `club_id` on `leaderboard.rank()`.** The API
  does not accept these fields and refused any request that carried them with a 400. They are
  still accepted so existing calls keep working, but they are no longer sent, and passing one
  raises a `DeprecationWarning`. They will be removed in a future release. (`city` on
  `leaderboard.list()` is supported and unchanged.)

### Fixed

- **Docs: member ids.** Every README, guide, quickstart, migration-guide and docstring example
  used `vair_mem_…` ids, which the Partner API no longer has. The member id (e.g. `"4873327"`)
  is the only canonical id, and the examples now use it. `leaderboard.rank()` documents that
  `player_id` takes a member id, a UUID or `"@username"`; anything else is a 404. No code
  changed.
- **`leaderboard.rank()` always failed with a 400.** It sent `contextSize`, which the API rejects
  as an unknown field; the request body now matches the API exactly, and `context_size` goes out
  as `context`. Its default `category` was also `"doubles"`, a code the API retired; it is now
  `"overall"`.
- **`members.search()` always sent `sortDirection=desc`.** `sort_order` defaulted to `"desc"`,
  unlike the TypeScript SDK, which sends nothing when unset. It now defaults to `None` and is
  sent only when you set it, so an unset search gets the API's default, ascending. Pass
  `sort_order="desc"` to keep the old order.
- **`leaderboard.list(club_id=...)` failed with a 400**, for the same reason. `club_id` is no
  longer sent (see Deprecated).
- **Wheelchair ratings no longer overwrite standard splits** (API fix). A wheelchair rating
  shares its standard split's key (`{category}-{bracket}`), so for a player with both it could
  replace the standard value. Wheelchair rows are no longer sent to partners, and the standard
  splits always carry the standard rating. No SDK change.

## [0.8.0] - 2026-09-24

### Added

- **`verify_webhook()` — verify a webhook delivery and get it back typed.** A partner receiving
  webhooks previously had to implement the signature scheme from prose and hand-write the event
  shapes; both now ship in the package. It takes no client and no API key, because a webhook receiver
  is an inbound HTTP handler that often never calls the Partner API at all, and it is synchronous, so
  it reads the same inside an `async` handler and outside one. Pass several secrets as a sequence
  during a rotation — deliveries queued before you rotated were signed with the old secret and keep
  arriving for hours, so a verifier that knows only the new one discards them silently. The timestamp
  window applies in **both** directions, so a forged future timestamp is refused exactly as a stale
  one is. Every refusal is a `WebhookSignatureError` carrying a `reason`, and the message contains
  neither the secret nor either digest. ([#1275](https://github.com/Vairified/Vairified/issues/1275))
- **Typed models and type guards for all four webhook event types** — `member.status`,
  `rating.updated`, `connection.revoked` and `event.created`, reached through
  `is_member_status_event()`, `is_rating_updated_event()`, `is_connection_revoked_event()` and
  `is_event_created_event()`. An event type this package does not know **verifies successfully and
  is handed over as-is**, and so does an unfamiliar value inside one it does know; both grow on the
  API's schedule rather than this package's, and refusing one would break a working receiver over a
  change that is not a break. Only the fields a partner gates access on are checked for presence and
  type — `event`, `eventId` and `timestamp` on every event, plus
  `memberId`/`isVairPlus`/`isAmbassador` on `member.status` and `memberId`/`sequence` on
  `rating.updated`. Everything else arrives exactly as sent. A refused delivery is retried and then
  dropped, so the member's status stops updating at that partner entirely; an unexpected
  informational field is not worth that. ([#1275](https://github.com/Vairified/Vairified/issues/1275))
- **`is_newer_sequence()`, `compare_sequence()` and `dedupe_key()` — the ordering and
  deduplication the documentation used to only describe.** `sequence` is an unpadded decimal string,
  so the obvious implementation compares strings, and `"10000000" > "9999999"` is `False`: a
  receiver following the written instruction would discard every later delivery for that member from
  the first power-of-ten crossing onward, permanently and with no error anywhere. These helpers
  compare as integers. `dedupe_key()` returns the id from the **signed body**, not the
  `X-Vairified-Event-Id` header — that header carries the same value but is outside the signature,
  so a replayed delivery can present a fresh one and header-based deduplication admits it every time.
  Delivery is at-least-once, so deduplication is the receiver's to do. ([#1275](https://github.com/Vairified/Vairified/issues/1275))

### Fixed

- `vairified.__version__` now tracks the released version. It had read `"0.5.0"`
  against a tagged `v0.7.0` — two minors stale — because `pyproject.toml` and `__init__.py` are
  two separate version sources and only one of them was being bumped. Anything reporting the SDK
  version at runtime, such as a support diagnostic, was naming a release from two versions back.

## [0.7.0] - 2026-09-11

### Added

- `MemberStatus.is_vair_plus` reports whether a member currently holds a **paid VAIR+ membership**, so a partner whose events require VAIR+ — NCPA, whose tournaments do — can check entitlement at lookup time instead of keeping its own record of who paid. It is `False` for a member who never bought and for one whose membership has ended, and — deliberately — also `False` during the automatic 30-day trial every new VAIR account receives, since a trial is not a paid membership and treating it as one would admit every brand-new signup. Do not confuse it with the per-sport `is_vair_pro` / `is_rater` on each `SportRating`: that is the VAIR **Pro** certified-rater programme, a different product whose name differs by two characters. Unlike those per-sport flags, which are defaulted as a migration shim, this field is required rather than defaulted — a partner writing `if not member.status.is_vair_plus` would otherwise have a response that omits the field read as a definitive "not a member". This release therefore requires the Partner API deployment that added the field. ([#1236](https://github.com/Vairified/Vairified/issues/1236))

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
