<h1 align="center">Vairified Python SDK</h1>

<p align="center">
  <strong>Official Python SDK for the Vairified Partner API</strong><br>
  Player ratings, search, and match submission
</p>

<p align="center">
  <a href="https://github.com/Vairified/vairified.py/actions/workflows/ci.yml"><img src="https://github.com/Vairified/vairified.py/actions/workflows/ci.yml/badge.svg" alt="CI"></a>
  <img src="https://img.shields.io/badge/version-0.1.0-green.svg" alt="Version 0.1.0">
  <img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+">
  <a href="https://pypi.org/project/vairified/"><img src="https://img.shields.io/pypi/v/vairified.svg" alt="PyPI"></a>
</p>

---

Python SDK for integrating with the [Vairified](https://vairified.com) player rating platform. Async-first, object-oriented design for easy integration.

## Installation

```bash
pip install vairified
```

Or with [UV](https://docs.astral.sh/uv):

```bash
uv add vairified
```

## Quick Start

```python
import asyncio
from vairified import Vairified

async def main():
    async with Vairified(api_key="vair_pk_xxx") as client:
        # Get a member - automatically subscribes to their rating updates
        member = await client.get_member("clerk_user_123")
        print(f"{member.name}: {member.rating}")
        print(f"Verified: {member.is_vairified}")
        print(f"Best rating: {member.rating_splits.best}")

asyncio.run(main())
```

## Features

### Search for Players

```python
async with Vairified(api_key="vair_pk_xxx") as client:
    # Search with filters
    results = await client.search(
        city="Austin",
        state="TX",
        rating_min=3.5,
        rating_max=4.5,
        vairified_only=True,
        limit=20,
    )

    # Iterate over results
    for player in results:
        print(f"{player.name}: {player.rating}")

    # Pagination
    print(f"Page {results.page} of {results.pages}")
    if results.has_more:
        next_page = await results.next_page()
```

### Find a Player by Name

```python
async with Vairified(api_key="vair_pk_xxx") as client:
    player = await client.find_player("John Smith")
    if player:
        print(f"Found: {player.name} ({player.rating})")
```

### Submit Match Results

```python
from datetime import datetime
from vairified import Vairified, Match

async with Vairified(api_key="vair_pk_xxx") as client:
    # Doubles match: 11-9, 11-7
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

    # Singles match
    singles = Match(
        event="Club Singles",
        bracket="Open Singles",
        date=datetime.now(),
        team1=("player1_id",),
        team2=("player2_id",),
        scores=[(11, 8), (9, 11), (11, 6)],
    )
    await client.submit_match(singles)
```

### Get Rating Updates

```python
async with Vairified(api_key="vair_pk_xxx") as client:
    # First, look up members to subscribe to their updates
    await client.get_member("user_1")
    await client.get_member("user_2")

    # Later, check for rating changes
    updates = await client.get_rating_updates()
    for update in updates:
        direction = "improved" if update.improved else "dropped"
        print(f"{update.member_id} {direction}: {update.previous_rating:.2f} -> {update.new_rating:.2f}")

        # Get the full member profile
        member = await update.get_member()
```

### OAuth Connect Flow

Connect players to your application using OAuth to access their profile and rating data.

```python
import secrets
from vairified import Vairified, OAuthError

async with Vairified(api_key="vair_pk_xxx") as client:
    # Step 1: Start authorization
    state = secrets.token_urlsafe(32)  # CSRF protection
    auth = await client.start_oauth(
        redirect_uri="https://myapp.com/oauth/callback",
        scopes=["profile:read", "rating:read", "match:submit"],
        state=state,
    )
    
    # Redirect user to auth.authorization_url
    print(f"Redirect to: {auth.authorization_url}")
```

```python
# Step 2: Handle callback (in your /oauth/callback route)
async with Vairified(api_key="vair_pk_xxx") as client:
    # Exchange code for tokens
    tokens = await client.exchange_token(
        code=request.query_params["code"],
        redirect_uri="https://myapp.com/oauth/callback",
    )
    
    # Store tokens securely
    player_id = tokens.player_id
    access_token = tokens.access_token
    refresh_token = tokens.refresh_token
    
    # Now you can access the player's data
    member = await client.get_member(player_id)
    print(f"Connected: {member.name} ({member.rating})")
```

```python
# Step 3: Refresh expired tokens
async with Vairified(api_key="vair_pk_xxx") as client:
    try:
        new_tokens = await client.refresh_access_token(stored_refresh_token)
        # Update stored tokens
    except OAuthError as e:
        if e.error_code == "invalid_grant":
            # Token revoked, user needs to re-authorize
            pass
```

### Available OAuth Scopes

| Scope | Description |
|-------|-------------|
| `profile:read` | Name, location, verification status |
| `profile:email` | Email address |
| `rating:read` | Current rating and rating splits |
| `rating:history` | Complete rating history |
| `match:submit` | Submit matches on behalf of user |
| `webhook:subscribe` | Rating change notifications |

### Revoke Connection

```python
async with Vairified(api_key="vair_pk_xxx") as client:
    await client.revoke_connection("vair_mem_xxx")
```

## Models

### Player

```python
player.id              # UUID or member ID
player.member_id       # Legacy member ID
player.name            # "John Smith"
player.first_name      # "John"
player.last_name       # "Smith"
player.rating          # 4.25
player.is_vairified    # True/False
player.rating_splits   # RatingSplits object
player.city            # "Austin"
player.state           # "TX"
player.verified_rating # Best verified rating
```

### Member (extends Player)

```python
member.email           # Email address
await member.refresh() # Refresh data from API
```

### RatingSplits

Access ratings by category:

```python
splits = member.rating_splits
splits.open           # Open division rating
splits.gender         # Same-gender doubles rating
splits.mixed          # Mixed doubles rating
splits.recreational   # Recreational rating
splits.singles        # Singles rating
splits.best           # Best available rating
splits.get("50_and_up")  # Age bracket rating
```

### Match

```python
match = Match(
    event="Weekly League",
    bracket="4.0 Doubles",
    date=datetime.now(),
    team1=("id1", "id2"),        # Player IDs for team 1
    team2=("id3", "id4"),        # Player IDs for team 2
    scores=[(11, 9), (11, 7)],   # Game scores
    location="Austin Club",      # Optional
    match_type="SIDEOUT",        # Default: "SIDEOUT"
    source="PARTNER",            # Default: "PARTNER"
)

match.format         # "DOUBLES" or "SINGLES"
match.winner         # 1 or 2 (0 if tie)
match.score_summary  # "11-9, 11-7"
match.identifier     # Auto-generated unique ID
```

### MatchResult

```python
result = await client.submit_matches([match1, match2])
result.success       # True/False
result.num_matches   # Number processed
result.num_games     # Games recorded
result.dry_run       # True if validation only
result.message       # Human-readable message
result.errors        # List of errors
bool(result)         # True if successful
```

### SearchResults

```python
results.players      # List of Player objects
results.total        # Total matching players
results.page         # Current page
results.pages        # Total pages
results.has_more     # More pages available
await results.next_page()  # Get next page
bool(results)        # True if has players
```

## Configuration

```python
from vairified import Vairified

# Basic usage
client = Vairified(api_key="vair_pk_xxx")

# Use staging for development/testing
client = Vairified(api_key="vair_pk_xxx", env="staging")

# Custom configuration
client = Vairified(
    api_key="vair_pk_xxx",
    timeout=30.0,
)
```

### Environment Variables

```bash
export VAIRIFIED_API_KEY="vair_pk_xxx"
```

```python
# API key read from environment
async with Vairified() as client:
    ...
```

## Dry-Run Mode (Dev Keys)

If your API key has the `dry-run` scope, match submissions are **validated but not persisted**. This is useful for testing integrations without affecting production data.

```python
# With a dry-run API key
async with Vairified(api_key="vair_pk_dev_xxx") as client:
    result = await client.submit_matches([match1, match2])
    
    if result.dry_run:
        print(f"Validation passed: {result.num_games} games would be created")
        print(result.message)
```

Request a dry-run API key from your Vairified partner contact for integration testing.

## Error Handling

```python
from vairified import (
    Vairified,
    VairifiedError,
    RateLimitError,
    AuthenticationError,
    NotFoundError,
    OAuthError,
)

async with Vairified(api_key="vair_pk_xxx") as client:
    try:
        member = await client.get_member("user_123")
    except RateLimitError as e:
        print(f"Rate limited. Retry after {e.retry_after} seconds")
    except AuthenticationError:
        print("Invalid API key")
    except NotFoundError:
        print("Member not found")
    except OAuthError as e:
        print(f"OAuth error: {e.message} (code: {e.error_code})")
    except VairifiedError as e:
        print(f"API error: {e.message} (status: {e.status_code})")
```

## Development

```bash
git clone https://github.com/Vairified/vairified.py.git
cd vairified.py
uv sync --all-extras
uv run pytest
```

## License

MIT License - see [LICENSE](LICENSE) for details.

---

<p align="center">
  <a href="https://vairified.com">vairified.com</a> · 
  <a href="https://docs.vairified.com">Documentation</a> · 
  <a href="mailto:support@vairified.com">Support</a>
</p>
