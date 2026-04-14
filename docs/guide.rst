User Guide
==========

This guide covers the SDK features in depth. For a fast tour, see the
:doc:`quickstart`. For porting code from 0.1.x, see :doc:`migrating`.

Client Lifecycle
----------------

``Vairified`` is an async context manager — the preferred way to use it:

.. code-block:: python

   async with Vairified(api_key="vair_pk_xxx") as client:
       member = await client.members.get("vair_mem_xxx")

Under the hood this creates a shared ``httpx.AsyncClient`` and closes it
on exit. For manual lifecycle control:

.. code-block:: python

   client = Vairified(api_key="vair_pk_xxx")
   try:
       member = await client.members.get("vair_mem_xxx")
   finally:
       await client.close()

Configuration
-------------

.. code-block:: python

   # Environment preset
   Vairified(api_key="vair_pk_xxx", env="production")   # default
   Vairified(api_key="vair_pk_xxx", env="staging")
   Vairified(api_key="vair_pk_xxx", env="local")

   # Explicit base URL (overrides env)
   Vairified(
       api_key="vair_pk_xxx",
       base_url="http://localhost:3001/api/v1",
       timeout=60.0,
   )

Environment variables:

.. code-block:: bash

   export VAIRIFIED_API_KEY="vair_pk_xxx"
   export VAIRIFIED_ENV="staging"

The ``ENVIRONMENTS`` dict is exported if you want to inspect the mapping:

.. code-block:: python

   from vairified import ENVIRONMENTS
   print(ENVIRONMENTS)
   # {'production': '...', 'staging': '...', 'local': '...'}

Working with Members
--------------------

``client.members.get()`` returns a :class:`~vairified.models.Member` — a frozen
pydantic model that represents a partner-facing player record.

.. code-block:: python

   member = await client.members.get("vair_mem_xxx")

   # Identity
   member.member_id            # Numeric member ID (public)
   member.id                   # UUID (internal PK)
   member.name                 # Full name (property)
   member.display_name         # "Mike B."
   member.first_name
   member.last_name

   # Profile
   member.age
   member.gender               # Gender.MALE | FEMALE | OTHER | UNKNOWN
   member.city
   member.state
   member.zip
   member.country

   # Status flags
   member.status.is_vairified
   member.status.is_wheelchair
   member.status.is_ambassador
   member.status.is_rater
   member.status.is_connected

Multi-sport ratings
^^^^^^^^^^^^^^^^^^^

Rating data lives under ``member.sport``, keyed by sport code. The
backend returns only the sports the player has ratings in, or only the
sports you requested via the ``sport=`` query filter.

.. code-block:: python

   # All sports this player has ratings in
   member.sport                       # dict[str, SportRating]
   member.sports                      # ["pickleball"] (list of keys)

   # Convenience helper — primary rating for a sport
   member.rating_for("pickleball")    # 3.915
   member.rating_for("padel")         # None (no padel rating)

   # Full SportRating object
   pb = member.sport["pickleball"]
   pb.rating                          # 3.915 (primary)
   pb.abbr                            # "VO" (primary category)

   # Access a specific split
   member.split("overall-open")                         # RatingSplit | None
   member.split("gender-open", sport="pickleball")      # Explicit sport

``SportRating`` is dict-like
""""""""""""""""""""""""""""

Access splits by subscript, iterate, check membership, and use ``len()``
without reaching into ``.rating_splits`` directly:

.. code-block:: python

   pb = member.sport["pickleball"]

   pb["overall-open"].rating         # 3.915
   pb["singles-open"].rating         # 3.710

   len(pb)                           # 3 splits
   "singles-40+" in pb               # False
   pb.get("missing")                 # None
   set(pb.keys())                    # {"overall-open", "gender-open", "singles-open"}

   for key, split in pb:
       print(key, split.rating, split.abbr)

Filtering ratings by sport
^^^^^^^^^^^^^^^^^^^^^^^^^^

Pass ``sport=`` to restrict what comes back — useful when you only care
about one sport or want to cut payload size:

.. code-block:: python

   # Just pickleball
   member = await client.members.get("vair_mem_xxx", sport="pickleball")

   # Multiple sports
   member = await client.members.get(
       "vair_mem_xxx",
       sport=["pickleball", "padel"],
   )

Searching Players
-----------------

``client.members.search()`` is an **auto-paginating async iterator** —
it yields members one at a time, fetching pages from the server lazily
as you iterate. Memory usage stays bounded regardless of how many
results match.

.. code-block:: python

   async for member in client.members.search(
       name="Mike",                  # Partial match on first or last name
       city="Austin",
       state="TX",
       country="US",
       zip="78701",
       rating_min=3.5,
       rating_max=4.5,
       gender="MALE",
       vairified_only=True,
       age_min=30,
       age_max=40,
       sort_by="rating",
       sort_order="desc",
       page_size=50,                 # Server batch size (max 100)
   ):
       print(member.name, member.rating_for("pickleball"))

Capping results
^^^^^^^^^^^^^^^

Pass ``max_results=N`` to stop after N total, or ``break`` out of the
loop yourself:

.. code-block:: python

   top_10 = []
   async for m in client.members.search(state="TX", max_results=10):
       top_10.append(m)

Finding by name
^^^^^^^^^^^^^^^

For the common "look up one player by name" case:

.. code-block:: python

   mike = await client.members.find("Mike Barker")
   if mike:
       print(mike.rating_for("pickleball"))

This is equivalent to the first hit of a ``search(name=...)`` — the SDK
stops after the first page with ``max_results=1``.

Submitting Matches
------------------

The 0.2.0 match API is n-team × n-game. Every match — singles, doubles,
3-way round robin, best-of-N — uses the same shape. Submissions go
through a ``MatchBatch`` that carries shared defaults for every match
in the batch.

Required batch-level fields
^^^^^^^^^^^^^^^^^^^^^^^^^^^

Three fields are always required on the batch:

- ``sport`` — the sport code (e.g. ``"pickleball"``). Tells the rater
  which rating pool to apply.
- ``win_score`` — the score a team reaches to win a normal game
  (e.g. ``11`` for standard pickleball, ``15`` for rally-scored games).
- ``win_by`` — the margin required to close out a game (usually ``2``).

Everything else is optional and inherited by every match in the batch
unless the match sets its own override.

Doubles example
^^^^^^^^^^^^^^^

.. code-block:: python

   from vairified import MatchBatch, Match, Game

   batch = MatchBatch(
       sport="pickleball",
       win_score=11,
       win_by=2,
       bracket="4.0 Doubles",
       event="Weekly League",
       match_date="2026-04-11T14:00:00Z",
       location="Austin Club",
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

Singles and round-robin
^^^^^^^^^^^^^^^^^^^^^^^

The team shape extends naturally — one player per team for singles, any
number of teams for round-robin:

.. code-block:: python

   # Singles
   Match(
       identifier="singles-1",
       teams=[["vair_mem_a"], ["vair_mem_b"]],
       games=[Game(scores=[11, 9]), Game(scores=[11, 7])],
   )

   # 3-way round-robin, best of 5, rally scoring to 15
   Match(
       identifier="rr-1",
       teams=[["a"], ["b"], ["c"]],
       games=[
           Game(scores=[15, 10, 8]),
           Game(scores=[12, 15, 9]),
           Game(scores=[15, 11, 13]),
           Game(scores=[14, 15, 10]),
           Game(scores=[15, 12, 11]),
       ],
   )

Per-match and per-game overrides
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Any match can override any batch-level default:

.. code-block:: python

   batch = MatchBatch(
       sport="pickleball",
       win_score=11,
       win_by=2,
       event="Weekly League",
       matches=[
           Match(
               identifier="regular",
               teams=[["a", "b"], ["c", "d"]],
               games=[Game(scores=[11, 9]), Game(scores=[11, 7])],
           ),
           Match(
               identifier="championship",
               bracket="Gold Medal Match",
               win_score=15,                 # Override: played to 15
               teams=[["a", "b"], ["c", "d"]],
               games=[Game(scores=[15, 12])],
           ),
       ],
   )

Individual games can also override ``win_score`` and ``win_by`` for
things like deciding games in a best-of-3.

Batch result
^^^^^^^^^^^^

.. code-block:: python

   result = await client.matches.submit(batch)

   result.success       # bool — every match accepted?
   result.ok            # bool — success AND no errors
   result.num_matches   # Matches processed
   result.num_games     # Games recorded
   result.dry_run       # True if this was a validation-only run
   result.is_dry_run    # Same as above (property)
   result.message       # Human-readable summary
   result.errors        # Optional list of per-match errors

Dry-run mode
^^^^^^^^^^^^

Set ``dry_run=True`` on the batch to validate without persisting. No
special scope needed — any key with ``key:match:submit`` can dry-run:

.. code-block:: python

   batch = MatchBatch(
       sport="pickleball",
       win_score=11,
       win_by=2,
       dry_run=True,
       matches=[...],
   )
   result = await client.matches.submit(batch)
   if result.is_dry_run and result.ok:
       print(f"Validation passed: {result.num_games} games would be created")

Rating Updates
--------------

Poll for rating change notifications for players who have subscribed
via the ``user:webhook:subscribe`` OAuth scope:

.. code-block:: python

   updates = await client.members.rating_updates()

   for update in updates:
       arrow = "↑" if update.improved else "↓"
       print(
           f"{update.display_name} {arrow} "
           f"{update.previous_rating:.3f} → {update.new_rating:.3f} "
           f"({update.delta:+.3f})"
       )

Properties on :class:`~vairified.models.RatingUpdate`:

.. code-block:: python

   update.member_id
   update.display_name
   update.sport
   update.previous_rating
   update.new_rating
   update.changed_at
   update.delta          # new - previous (property, None if either missing)
   update.improved       # bool (property)

Webhook testing
^^^^^^^^^^^^^^^

Send a test payload to your webhook endpoint:

.. code-block:: python

   result = await client.matches.test_webhook("https://your-service.com/webhook")

OAuth Connect Flow
------------------

The Partner API uses OAuth to request player consent before accessing
their data. Players must explicitly approve your application before you
can read their rating or submit matches on their behalf.

All OAuth operations live on the ``client.oauth`` sub-resource.

Step 1 — Start authorization
^^^^^^^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   import secrets
   from vairified import Vairified

   async with Vairified(api_key="vair_pk_xxx") as client:
       state = secrets.token_urlsafe(32)   # CSRF token
       auth = await client.oauth.authorize(
           redirect_uri="https://your-app.com/callback",
           scopes=["user:profile:read", "user:rating:read", "user:match:submit"],
           state=state,
       )

       # Persist `state` for verification, then redirect the user to
       # auth.authorization_url.

``OAuthScope`` is a ``Literal`` type alias listing every valid scope
string, so your editor and type checker catch typos:

.. code-block:: python

   from vairified import OAuthScope

   scopes: list[OAuthScope] = [
       "user:profile:read",
       "user:rating:read",
       "user:match:submit",
   ]

Available scopes
""""""""""""""""

============================  ==============================================
Scope                         Description
============================  ==============================================
``user:profile:read``         Name, location, verification status (required)
``user:profile:email``        Email address
``user:rating:read``          Current rating and rating splits
``user:rating:history``       Complete rating history
``user:match:submit``         Submit matches on player's behalf
``user:webhook:subscribe``    Receive rating change notifications
============================  ==============================================

Step 2 — Exchange the code
^^^^^^^^^^^^^^^^^^^^^^^^^^

After the user approves, they're redirected back with a ``code`` and
``state``. Verify ``state`` and exchange the code:

.. code-block:: python

   # In your /callback route
   if request.query_params["state"] != stored_state:
       raise ValueError("State mismatch — possible CSRF")

   tokens = await client.oauth.exchange_token(
       code=request.query_params["code"],
       redirect_uri="https://your-app.com/callback",
   )

   # Store these securely
   tokens.access_token
   tokens.refresh_token
   tokens.expires_in
   tokens.scope          # list[str] of granted scopes
   tokens.player_id      # Connected player's external ID

   member = await client.members.get(tokens.player_id)

Step 3 — Refresh tokens
^^^^^^^^^^^^^^^^^^^^^^^

Access tokens expire. Use the refresh token to get a new one:

.. code-block:: python

   from vairified import OAuthError

   try:
       new_tokens = await client.oauth.refresh(stored_refresh_token)
   except OAuthError as e:
       if e.error_code == "invalid_grant":
           # Refresh token revoked — user must re-authorize
           ...

Step 4 — Revoke the connection
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Disconnect a player from your application:

.. code-block:: python

   await client.oauth.revoke("vair_mem_xxx")

Discovering scopes at runtime
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

The server returns the authoritative scope list:

.. code-block:: python

   available = await client.oauth.available_scopes()
   for scope in available:
       print(scope["name"], "—", scope["description"])

Leaderboards
------------

Read-only leaderboard queries live on ``client.leaderboard``:

.. code-block:: python

   # Global leaderboard
   lb = await client.leaderboard.list(limit=50)

   # Filtered
   tx_singles = await client.leaderboard.list(
       category="singles",
       scope="state",
       state="TX",
       verified_only=True,
       limit=50,
   )

   # A specific player's rank + nearby players
   rank = await client.leaderboard.rank(
       "vair_mem_xxx",
       category="doubles",
       age_bracket="open",
       scope="global",
       context_size=5,
   )
   print(f"#{rank['rank']} (top {rank['percentile']:.1f}%)")

   # Discover valid category / bracket / scope values
   categories = await client.leaderboard.categories()

API Usage Statistics
--------------------

Check rate-limit and request-count stats for your API key:

.. code-block:: python

   usage = await client.usage()
   print(usage)
   # {'rateLimit': ..., 'requestsToday': ..., 'quotaUsed': ...}

Working with Models
-------------------

All response models are frozen ``pydantic`` v2 ``BaseModel`` instances.
This has a few practical implications:

**Immutable** — attempts to mutate a field raise at runtime:

.. code-block:: python

   member = await client.members.get("vair_mem_xxx")
   member.first_name = "Changed"     # ValidationError

**Forward compatible** — unknown fields from the server are preserved,
so you can upgrade the API without upgrading the SDK.

**Aliased** — you write snake_case in Python; the wire format stays
camelCase:

.. code-block:: python

   batch = MatchBatch(
       sport="pickleball",
       win_score=11,
       win_by=2,
       match_date="2026-04-11T14:00:00Z",
       matches=[...],
   )

   data = batch.model_dump(by_alias=True, exclude_none=True)
   assert data["winScore"] == 11
   assert data["matchDate"] == "2026-04-11T14:00:00Z"

**REPL-friendly** — every model has a compact ``__repr__``:

.. code-block:: python

   >>> member
   <Member #4873327 'Mike B.' rating=3.915 VO>
   >>> update
   <RatingUpdate #4873327 'Mike B.' 3.800 ↑ 3.915>
   >>> batch
   <MatchBatch sport='pickleball' matches=1 games=2>

Error Handling
--------------

The SDK maps HTTP status codes to typed exceptions:

========  ========================  ================================
Status    Exception                 Meaning
========  ========================  ================================
400       ``ValidationError``       Bad request, invalid input
401       ``AuthenticationError``   Invalid or missing API key
404       ``NotFoundError``         Resource not found
429       ``RateLimitError``        Rate limit exceeded
5xx       ``VairifiedError``        Server error (generic)
—         ``OAuthError``            OAuth-specific failure
========  ========================  ================================

All typed exceptions inherit from :class:`~vairified.errors.VairifiedError`,
so a single ``except VairifiedError`` catches everything.

.. code-block:: python

   from vairified import (
       VairifiedError,
       RateLimitError,
       AuthenticationError,
       NotFoundError,
       ValidationError,
       OAuthError,
   )

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
