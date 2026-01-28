Quick Start
===========

This guide will get you up and running with the Vairified Python SDK in minutes.

Installation
------------

Install from PyPI using pip:

.. code-block:: bash

   pip install vairified

Or with UV (recommended):

.. code-block:: bash

   uv add vairified

Configuration
-------------

You'll need a Partner API key from Vairified. You can pass it directly or use
environment variables:

.. code-block:: bash

   export VAIRIFIED_API_KEY="vair_pk_xxx"
   export VAIRIFIED_ENV="next"  # Optional: production, next, staging, local

Basic Usage
-----------

The SDK uses an async context manager pattern:

.. code-block:: python

   import asyncio
   from vairified import Vairified

   async def main():
       async with Vairified(api_key="vair_pk_xxx") as client:
           # Your code here
           pass

   asyncio.run(main())

Get a Member
^^^^^^^^^^^^

Fetch a member by their Clerk user ID, member ID, or UUID:

.. code-block:: python

   member = await client.get_member("clerk_user_123")
   print(f"{member.name}: {member.rating}")
   print(f"Verified: {member.is_vairified}")

Search Players
^^^^^^^^^^^^^^

Search with various filters:

.. code-block:: python

   results = await client.search(
       city="Austin",
       state="TX",
       rating_min=3.5,
       rating_max=4.5,
       vairified_only=True,
   )

   for player in results:
       print(f"{player.name}: {player.rating}")

   # Pagination
   if results.has_more:
       next_page = await results.next_page()

Submit Matches
^^^^^^^^^^^^^^

Submit match results:

.. code-block:: python

   from datetime import datetime
   from vairified import Match

   # Doubles match
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

Environment Selection
---------------------

The SDK defaults to the production environment:

.. code-block:: python

   # Default (production)
   client = Vairified(api_key="vair_pk_xxx")

   # Staging for testing
   client = Vairified(api_key="vair_pk_xxx", env="staging")

   # Local development
   client = Vairified(api_key="vair_pk_xxx", env="local")

Available environments:

==============  ================================
Environment     Description
==============  ================================
``production``  Live API (default)
``staging``     Testing environment
``local``       Local development
==============  ================================

OAuth Connect Flow
------------------

Connect players to your application using OAuth:

.. code-block:: python

   import secrets
   from vairified import Vairified

   async with Vairified(api_key="vair_pk_xxx") as client:
       # Step 1: Start OAuth flow
       state = secrets.token_urlsafe(32)  # CSRF protection
       auth = await client.start_oauth(
           redirect_uri="https://your-app.com/callback",
           scopes=["profile:read", "rating:read"],
           state=state,
       )
       # Redirect user to auth.authorization_url

After the user approves, exchange the code for tokens:

.. code-block:: python

   # Step 2: Exchange code for tokens
   tokens = await client.exchange_token(code, redirect_uri)

   # Store tokens securely
   player_id = tokens.player_id
   access_token = tokens.access_token

   # Step 3: Access connected player
   member = await client.get_member(player_id)

Error Handling
--------------

The SDK provides typed exceptions:

.. code-block:: python

   from vairified import (
       VairifiedError,
       RateLimitError,
       AuthenticationError,
       NotFoundError,
       OAuthError,
   )

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
       print(f"API error: {e.message}")
