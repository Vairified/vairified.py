User Guide
==========

This guide covers the SDK features in detail.

Working with Members
--------------------

Members are players with full profile access. When you fetch a member, you
automatically subscribe to their rating updates.

.. code-block:: python

   member = await client.get_member("clerk_user_123")

   # Access properties
   print(member.name)          # "John Smith"
   print(member.rating)        # 4.25
   print(member.is_vairified)  # True

   # Refresh data from API
   await member.refresh()

Rating Splits
^^^^^^^^^^^^^

Ratings are broken down by category:

.. code-block:: python

   splits = member.rating_splits

   # Convenience properties
   splits.open           # Open division rating
   splits.gender         # Same-gender doubles
   splits.mixed          # Mixed doubles
   splits.recreational   # Recreational
   splits.singles        # Singles
   splits.best           # Best available rating

   # Age brackets
   splits.get("50_and_up")
   splits.get("60_and_up")

Searching Players
-----------------

The search endpoint supports extensive filtering:

.. code-block:: python

   results = await client.search(
       name="John",              # Partial name match
       city="Austin",
       state="TX",
       country="US",
       zip_code="78701",
       rating_min=3.5,
       rating_max=4.5,
       gender="MALE",
       vairified_only=True,
       age=35,                   # Exact age
       # Or age range:
       # age_min=30,
       # age_max=40,
       sort_by="rating",
       sort_order="desc",
       limit=20,
   )

Pagination
^^^^^^^^^^

Search results support pagination:

.. code-block:: python

   results = await client.search(city="Austin", limit=20)

   print(f"Page {results.page} of {results.pages}")
   print(f"Total: {results.total} players")

   # Iterate current page
   for player in results:
       print(player.name)

   # Get next page
   if results.has_more:
       next_results = await results.next_page()

Find Player Helper
^^^^^^^^^^^^^^^^^^

For simple name lookups:

.. code-block:: python

   player = await client.find_player("John Smith")
   if player:
       print(f"Found: {player.name} ({player.rating})")

Submitting Matches
------------------

Match Structure
^^^^^^^^^^^^^^^

Matches require event information, teams, and scores:

.. code-block:: python

   from datetime import datetime
   from vairified import Match

   # Doubles match
   match = Match(
       event="Weekly League",           # Required
       bracket="4.0 Doubles",            # Required
       date=datetime.now(),              # Required
       team1=("player1", "player2"),     # Player IDs
       team2=("player3", "player4"),
       scores=[(11, 9), (11, 7)],        # (team1_score, team2_score) per game
       location="Austin Club",           # Optional
       match_type="SIDEOUT",             # Default: "SIDEOUT"
       source="PARTNER",                 # Default: "PARTNER"
   )

   # Singles match
   singles = Match(
       event="Club Singles",
       bracket="Open Singles",
       date=datetime.now(),
       team1=("player1",),               # Single player tuple
       team2=("player2",),
       scores=[(11, 8), (9, 11), (11, 6)],
   )

Match Properties
^^^^^^^^^^^^^^^^

.. code-block:: python

   match.format         # "DOUBLES" or "SINGLES"
   match.winner         # 1, 2, or 0 (tie)
   match.score_summary  # "11-9, 11-7"
   match.identifier     # Auto-generated unique ID

Submitting
^^^^^^^^^^

Submit single or batch:

.. code-block:: python

   # Single match
   result = await client.submit_match(match)

   # Batch submission
   result = await client.submit_matches([match1, match2, match3])

   # Check result
   if result:
       print(f"Success: {result.num_games} games recorded")
   else:
       print(f"Errors: {result.errors}")

Match Result
^^^^^^^^^^^^

The ``MatchResult`` object contains:

.. code-block:: python

   result.success       # True/False
   result.num_matches   # Matches processed
   result.num_games     # Games recorded
   result.dry_run       # True if validation only
   result.message       # Human-readable message
   result.errors        # List of errors

   # Truthiness check
   if result:  # True if success and no errors
       print("OK!")

Dry-Run Mode
------------

API keys with the ``dry-run`` scope validate without persisting data:

.. code-block:: python

   result = await client.submit_matches([match1, match2])

   if result.dry_run:
       print("Dry-run mode - no data saved")
       print(f"Would create: {result.num_games} games")
       print(result.message)

Request a dry-run API key from your Vairified partner contact.

Rating Updates
--------------

Poll for rating changes on subscribed members:

.. code-block:: python

   # Subscribe by fetching members
   await client.get_member("user_1")
   await client.get_member("user_2")

   # Later, check for updates
   updates = await client.get_rating_updates()

   for update in updates:
       print(f"{update.member_id}: {update.previous_rating:.2f} → {update.new_rating:.2f}")

       if update.improved:
           member = await update.get_member()
           print(f"{member.name} improved!")

Webhook Testing
---------------

Test your webhook endpoint:

.. code-block:: python

   result = await client.test_webhook("https://your-service.com/webhook")

Advanced Configuration
----------------------

Custom Base URL
^^^^^^^^^^^^^^^

.. code-block:: python

   client = Vairified(
       api_key="vair_pk_xxx",
       base_url="https://custom-api.example.com/api/v1",
       timeout=60.0,
   )

Without Context Manager
^^^^^^^^^^^^^^^^^^^^^^^

If you need manual lifecycle control:

.. code-block:: python

   client = Vairified(api_key="vair_pk_xxx")

   try:
       member = await client.get_member("user_123")
   finally:
       await client.close()

OAuth Connect Flow
------------------

The Partner API uses OAuth to request player consent before accessing their data.
Players must explicitly approve your application before you can access their profile.

Starting Authorization
^^^^^^^^^^^^^^^^^^^^^^

.. code-block:: python

   import secrets
   from vairified import Vairified

   async with Vairified(api_key="vair_pk_xxx") as client:
       # Generate CSRF state token
       state = secrets.token_urlsafe(32)

       # Start OAuth flow
       auth = await client.start_oauth(
           redirect_uri="https://your-app.com/callback",
           scopes=["profile:read", "rating:read", "match:submit"],
           state=state,
       )

       # Store state for verification, then redirect user
       # to auth.authorization_url

Available OAuth Scopes
^^^^^^^^^^^^^^^^^^^^^^

===================  =============================================
Scope                Description
===================  =============================================
``profile:read``     Name, location, verification status (required)
``profile:email``    Email address
``rating:read``      Current rating and rating splits
``rating:history``   Complete rating history
``match:submit``     Submit matches on player's behalf
``webhook:subscribe`` Receive rating change notifications
===================  =============================================

Exchanging Tokens
^^^^^^^^^^^^^^^^^

After the user approves, they're redirected to your callback URL with a code:

.. code-block:: python

   # Handle callback: https://your-app.com/callback?code=xxx&state=yyy

   # Verify state matches what you stored
   if request.query_params["state"] != stored_state:
       raise ValueError("Invalid state - possible CSRF attack")

   # Exchange code for tokens
   tokens = await client.exchange_token(
       code=request.query_params["code"],
       redirect_uri="https://your-app.com/callback",
   )

   # Store tokens securely
   player_id = tokens.player_id
   access_token = tokens.access_token
   refresh_token = tokens.refresh_token

   # Now access the player's data
   member = await client.get_member(player_id)

Refreshing Tokens
^^^^^^^^^^^^^^^^^

Access tokens expire. Use the refresh token to get a new one:

.. code-block:: python

   from vairified import OAuthError

   try:
       new_tokens = await client.refresh_access_token(stored_refresh_token)
       # Update stored tokens
   except OAuthError as e:
       if e.error_code == "invalid_grant":
           # Refresh token revoked - user needs to re-authorize
           pass

Revoking Connections
^^^^^^^^^^^^^^^^^^^^

Disconnect a player from your application:

.. code-block:: python

   await client.revoke_connection("vair_mem_xxx")
   # Player is now disconnected

API Usage Statistics
^^^^^^^^^^^^^^^^^^^^

Check your API usage:

.. code-block:: python

   usage = await client.get_usage()
   print(f"Requests today: {usage['requestsToday']}")
   print(f"Rate limit: {usage['rateLimit']}/hour")
