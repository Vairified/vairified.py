<h1 align="center">Vairified Python SDK</h1>

<p align="center">
  <strong>Official Python SDK for the Vairified Partner API</strong><br>
  Multi-sport player ratings, search, and bulk match submission
</p>

<p align="center">
  <a href="https://github.com/Vairified/vairified.py/actions/workflows/ci.yml"><img src="https://github.com/Vairified/vairified.py/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/version-0.3.0-green.svg" alt="Version 0.3.0">
  <img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+">
  <a href="https://pypi.org/project/vairified/"><img src="https://img.shields.io/pypi/v/vairified.svg" alt="PyPI"></a>
</p>

---

Async-first Python SDK for the [Vairified](https://vairified.com) Partner API. Built on
`httpx` and `pydantic` v2, with a surface designed to feel native: properties
instead of getters, dict-like access to rating splits, auto-paginating search,
and a sub-resource layout that mirrors the REST API.

## Installation

```bash
pip install vairified
```

Or with [uv](https://docs.astral.sh/uv):

```bash
uv add vairified
```

## Quick Start

```python
import asyncio
from vairified import Vairified

async def main() -> None:
    async with Vairified(api_key="vair_pk_xxx") as client:
        member = await client.members.get("vair_mem_xxx")
        print(member.name, "rated", member.rating_for("pickleball"))

asyncio.run(main())
```

The client is an async context manager — opening it creates an `httpx.AsyncClient`,
closing it releases the underlying connection pool.

## Sub-resources

Every operation lives on a sub-resource that matches the REST path:

| Sub-resource            | Operations                                              |
|-------------------------|---------------------------------------------------------|
| `client.members`        | `get`, `get_bulk`, `search`, `find`, `rating_updates`   |
| `client.matches`        | `submit`, `tournament_import`, `test_webhook`            |
| `client.oauth`          | `authorize`, `exchange_token`, `refresh`, `revoke`      |
| `client.leaderboard`    | `list`, `rank`, `categories`                            |
| `client.webhooks`       | `deliveries`                                            |
| `client.usage()`        | Rate-limit + request-count stats                        |

## Members

### Get a connected member

```python
async with Vairified(api_key="vair_pk_xxx") as client:
    member = await client.members.get("vair_mem_xxx")

    print(member.name)                      # Full name
    print(member.display_name)               # "Mike B."
    print(member.rating_for("pickleball"))   # 3.915
    print(member.status.is_vairified)        # True

    # Dict-like access to rating splits for a specific sport
    pb = member.sport["pickleball"]
    print(pb.rating, pb.abbr)                # 3.915 VO
    print(pb["overall-open"].rating)         # 3.915
    print("singles-open" in pb)              # True
    for key, split in pb:
        print(key, split.rating)
```

### Filter ratings to specific sports

```python
# Just pickleball
member = await client.members.get("vair_mem_xxx", sport="pickleball")

# Multiple sports
member = await client.members.get(
    "vair_mem_xxx",
    sport=["pickleball", "padel"],
)
```

### Auto-paginating search

`search()` is an async iterator — it streams results one member at a time,
fetching pages lazily as you iterate. `break` early when you have what you
need, or cap with `max_results`.

```python
async with Vairified(api_key="vair_pk_xxx") as client:
    async for member in client.members.search(
        city="Austin",
        state="TX",
        rating_min=3.5,
        rating_max=4.5,
        vairified_only=True,
    ):
        print(member.name, member.rating_for("pickleball"))

    # Find first N across pages
    top_20: list = []
    async for m in client.members.search(name="Smith", max_results=20):
        top_20.append(m)
```

### Find by name (first hit only)

```python
mike = await client.members.find("Mike Barker")
if mike:
    print(mike.rating_for("pickleball"))
```

### Bulk member lookup

Fetch up to 100 members in one call by their integer member IDs:

```python
members = await client.members.get_bulk([4873327, 4873328, 4873329])
for m in members:
    print(m.name, m.rating_for("pickleball"))

# Filter to a specific sport
pb = await client.members.get_bulk([4873327], sport="pickleball")
```

Unknown IDs are silently omitted — the list may be shorter than the input.

### Rating change notifications

```python
updates = await client.members.rating_updates()
for update in updates:
    arrow = "↑" if update.improved else "↓"
    print(f"{update.display_name} {arrow} delta={update.delta:+.3f}")
```

## Match Submission

Matches are submitted as a `MatchBatch` — defaults at the batch level apply
to every match unless overridden. The shape is n-team × n-game, so singles,
doubles, and round-robin all go through the same path.

```python
from vairified import Vairified, MatchBatch, Match, Game

async with Vairified(api_key="vair_pk_xxx") as client:
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
            Match(
                identifier="m2",
                teams=[["vair_mem_eee"], ["vair_mem_fff"]],   # singles
                games=[Game(scores=[11, 9]), Game(scores=[11, 7])],
            ),
        ],
    )
    result = await client.matches.submit(batch)
    if result.ok:
        print(f"Submitted {result.num_games} games in {result.num_matches} matches")
```

Set `batch.dry_run = True` to validate without persisting. No special
scope needed — any key with `key:match:submit` can dry-run.

### Tournament import

Import historical tournament results with automatic player matching:

```python
result = await client.matches.tournament_import({
    "tournamentName": "Austin Open 2026",
    "sport": "pickleball",
    "winScore": 11,
    "winBy": 2,
    "matches": [...]
})
print(f"Imported {result.matches_imported} matches, {result.ghost_players_created} ghosts")
```

## Webhook Deliveries

Inspect recent webhook delivery attempts for your app:

```python
result = await client.webhooks.deliveries(status="failed", limit=10)
for d in result.deliveries:
    print(d.event, d.status_code, d.error_message)

# Filter by event type
rating_events = await client.webhooks.deliveries(event="rating.updated")
print(f"{rating_events.total} total rating.updated deliveries")
```

## OAuth Connect Flow

```python
import secrets
from vairified import Vairified, OAuthError

async with Vairified(api_key="vair_pk_xxx") as client:
    # Step 1 — start authorization
    state = secrets.token_urlsafe(32)
    auth = await client.oauth.authorize(
        redirect_uri="https://myapp.com/oauth/callback",
        scopes=["user:profile:read", "user:rating:read", "user:match:submit"],
        state=state,
    )
    redirect_to = auth.authorization_url

    # Step 2 — exchange the callback code
    tokens = await client.oauth.exchange_token(
        code="code-from-callback",
        redirect_uri="https://myapp.com/oauth/callback",
    )
    access = tokens.access_token
    refresh = tokens.refresh_token
    player_id = tokens.player_id

    # Step 3 — refresh when the access token expires
    try:
        new_tokens = await client.oauth.refresh(refresh)
    except OAuthError as e:
        if e.error_code == "invalid_grant":
            ...  # user must re-authorize

    # Step 4 — revoke the connection
    await client.oauth.revoke(player_id)
```

### Available scopes

| Scope                | Description                                    |
|----------------------|------------------------------------------------|
| `user:profile:read`       | Name, location, verification status            |
| `user:profile:email`      | Email address                                  |
| `user:rating:read`        | Current rating and rating splits               |
| `user:rating:history`     | Complete rating history                        |
| `user:match:submit`       | Submit matches on behalf of user               |
| `user:webhook:subscribe`  | Rating change notifications                    |

## Leaderboards

```python
async with Vairified(api_key="vair_pk_xxx") as client:
    # Global doubles leaderboard
    lb = await client.leaderboard.list()

    # Texas singles, verified only
    tx = await client.leaderboard.list(
        category="singles",
        scope="state",
        state="TX",
        verified_only=True,
        limit=50,
    )

    # A specific player's rank with 5 players on either side
    rank = await client.leaderboard.rank(
        "vair_mem_xxx",
        category="doubles",
        context_size=5,
    )
    print(f"#{rank['rank']} (top {rank['percentile']:.1f}%)")

    # Available categories, brackets, scopes
    categories = await client.leaderboard.categories()
```

## Models

All response models are immutable `pydantic` v2 `BaseModel`s. They accept both
snake_case (Python) and camelCase (wire) field names, and tolerate new fields
from the server so your code keeps working across API additions.

### `Member`

```python
member.member_id                     # Numeric member ID
member.id                            # UUID
member.name                          # Full name (property)
member.display_name                  # "Mike B."
member.first_name                    # "Mike"
member.last_name                     # "Barker"
member.gender                        # Gender enum (MALE | FEMALE | OTHER | UNKNOWN)
member.age
member.city / state / zip / country
member.status.is_vairified           # Grouped status flags
member.status.is_connected
member.sport                         # dict[str, SportRating]
member.sports                        # ["pickleball", "padel"] (property)
member.rating_for("pickleball")      # float | None
member.split("overall-open")         # RatingSplit | None
```

### `SportRating` (dict-like)

```python
pb = member.sport["pickleball"]
pb.rating                     # Primary rating for this sport
pb.abbr                       # "VO", "VG", etc.
pb["overall-open"].rating     # Any split key
len(pb)                       # Number of splits
"singles-40+" in pb           # Membership check
for key, split in pb: ...     # Iterate (yields (key, RatingSplit) tuples)
```

### `Match` / `MatchBatch`

Request-side models use camelCase aliases (`winScore`, `winBy`, `matchDate`)
when serialized — write Python in snake_case, the wire stays consistent.

```python
batch = MatchBatch(
    sport="pickleball",
    win_score=11,
    win_by=2,
    match_date="2026-04-11T14:00:00Z",
    matches=[
        Match(
            identifier="m1",
            teams=[["p1", "p2"], ["p3", "p4"]],   # n-team × n-player
            games=[Game(scores=[11, 8]),           # n-game match
                   Game(scores=[11, 5])],
        ),
    ],
)
```

### `RatingUpdate`

```python
update.member_id
update.previous_rating
update.new_rating
update.delta        # new - previous (or None)
update.improved     # True if delta > 0
update.changed_at
```

## Configuration

```python
from vairified import Vairified

# Environment preset
client = Vairified(api_key="vair_pk_xxx", env="production")   # default
client = Vairified(api_key="vair_pk_xxx", env="staging")
client = Vairified(api_key="vair_pk_xxx", env="local")

# Custom base URL (overrides env)
client = Vairified(
    api_key="vair_pk_xxx",
    base_url="http://localhost:3001/api/v1",
    timeout=30.0,
)
```

### Environment variables

```bash
export VAIRIFIED_API_KEY="vair_pk_xxx"
export VAIRIFIED_ENV="staging"   # optional; default: production
```

```python
async with Vairified() as client:   # reads both env vars
    ...
```

## API Key Scopes

| Scope                    | Access                                         |
|--------------------------|------------------------------------------------|
| `key:admin`              | Full access to all endpoints                   |
| `key:write`              | All read + write operations                    |
| `key:read`               | All read operations                            |
| `key:leaderboard:read`   | Leaderboard endpoints only                     |
| `key:player:search`      | Player search only                             |
| `key:member:read`        | Connected member data only                     |
| `key:match:submit`       | Submit match results                           |
| `key:tournament:import`  | Import tournament data                         |

## Error Handling

```python
from vairified import (
    Vairified,
    VairifiedError,
    RateLimitError,
    AuthenticationError,
    NotFoundError,
    ValidationError,
    OAuthError,
)

async with Vairified(api_key="vair_pk_xxx") as client:
    try:
        member = await client.members.get("vair_mem_xxx")
    except RateLimitError as e:
        print(f"Rate limited; retry after {e.retry_after}s")
    except AuthenticationError:
        print("Invalid API key")
    except NotFoundError:
        print("Member not found")
    except ValidationError as e:
        print(f"Bad request: {e.message}")
    except OAuthError as e:
        print(f"OAuth error: {e.message} (code: {e.error_code})")
    except VairifiedError as e:
        print(f"API error: {e.message} (status: {e.status_code})")
```

## Migrating from 0.1.x

Version 0.2.0 is a breaking rewrite. See the
**From 0.2.x → 0.3.0:** All OAuth scope strings gained a `user:` prefix
(`profile:read` → `user:profile:read`). Update any hardcoded scope arrays.
New: `members.get_bulk()`, `matches.tournament_import()`, `webhooks.deliveries()`.

**From 0.1.x → 0.2.0:** Full rewrite — see the
[migration guide](https://vairified.github.io/vairified.py/migrating.html)
for the full diff, and [CHANGELOG.md](CHANGELOG.md) for the release notes.

## Development

```bash
git clone https://github.com/Vairified/vairified.py.git
cd vairified.py
uv sync --all-extras
uv run pytest
```

## License

MIT — see [LICENSE](LICENSE) for details.

---

<p align="center">
  <a href="https://vairified.com">vairified.com</a> ·
  <a href="https://vairified.github.io/vairified.py">Documentation</a> ·
  <a href="mailto:support@vairified.com">Support</a>
</p>
