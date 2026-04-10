Quick Start
===========

This guide gets you up and running with the Vairified Python SDK in a
few minutes.

Installation
------------

.. code-block:: bash

   pip install vairified

Or with `uv <https://docs.astral.sh/uv>`_:

.. code-block:: bash

   uv add vairified

Configuration
-------------

You'll need a Partner API key from Vairified. Pass it directly or set it
in the environment:

.. code-block:: bash

   export VAIRIFIED_API_KEY="vair_pk_xxx"
   export VAIRIFIED_ENV="production"   # optional; default: production

Supported environments: ``production``, ``staging``, ``local``.

Hello, member
-------------

The SDK uses an async context manager. Opening it creates the underlying
``httpx.AsyncClient``; closing it releases the connection pool.

.. code-block:: python

   import asyncio
   from vairified import Vairified

   async def main() -> None:
       async with Vairified(api_key="vair_pk_xxx") as client:
           member = await client.members.get("vair_mem_xxx")
           print(member.name, "rated", member.rating_for("pickleball"))

   asyncio.run(main())

Sub-resources
-------------

Every operation lives on a sub-resource that mirrors the REST path:

- ``client.members`` — ``get``, ``search``, ``find``, ``rating_updates``
- ``client.matches`` — ``submit``, ``test_webhook``
- ``client.oauth`` — ``authorize``, ``exchange_token``, ``refresh``, ``revoke``
- ``client.leaderboard`` — ``list``, ``rank``, ``categories``
- ``client.usage()`` — rate-limit and request-count stats

Get a member
^^^^^^^^^^^^

.. code-block:: python

   member = await client.members.get("vair_mem_xxx")

   print(member.name)                        # Full name
   print(member.display_name)                # "Mike B."
   print(member.rating_for("pickleball"))    # 3.915
   print(member.status.is_vairified)         # True

   # Dict-like access to rating splits
   pb = member.sport["pickleball"]
   print(pb.rating, pb.abbr)                 # 3.915 VO
   print(pb["overall-open"].rating)          # 3.915

Search players
^^^^^^^^^^^^^^

``search()`` is an async iterator that fetches pages lazily — iterate
directly, ``break`` early, or cap with ``max_results``:

.. code-block:: python

   async for member in client.members.search(
       city="Austin",
       state="TX",
       rating_min=3.5,
       rating_max=4.5,
       vairified_only=True,
   ):
       print(member.name, member.rating_for("pickleball"))

   # First 20 hits across all pages
   top_20 = []
   async for m in client.members.search(name="Smith", max_results=20):
       top_20.append(m)

Submit matches
^^^^^^^^^^^^^^

Matches are submitted as a ``MatchBatch``. Batch-level fields apply as
defaults to every match unless overridden. The n-team × n-game shape
supports singles, doubles, round-robin, and best-of-N through a single
schema.

.. code-block:: python

   from vairified import MatchBatch, Match, Game

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
       print(f"Submitted {result.num_games} games in {result.num_matches} matches")

Environment selection
---------------------

.. code-block:: python

   # Default — production
   client = Vairified(api_key="vair_pk_xxx")

   # Staging
   client = Vairified(api_key="vair_pk_xxx", env="staging")

   # Local development
   client = Vairified(api_key="vair_pk_xxx", env="local")

   # Explicit base URL (overrides env)
   client = Vairified(
       api_key="vair_pk_xxx",
       base_url="http://localhost:3001/api/v1",
   )

OAuth connect flow
------------------

Connect players to your application with OAuth:

.. code-block:: python

   import secrets
   from vairified import Vairified

   async with Vairified(api_key="vair_pk_xxx") as client:
       # Step 1 — start authorization
       state = secrets.token_urlsafe(32)
       auth = await client.oauth.authorize(
           redirect_uri="https://your-app.com/callback",
           scopes=["profile:read", "rating:read"],
           state=state,
       )
       # Redirect the user to auth.authorization_url

       # Step 2 — exchange the code from the callback
       tokens = await client.oauth.exchange_token(
           code="code-from-callback",
           redirect_uri="https://your-app.com/callback",
       )

       # Step 3 — access the connected player
       member = await client.members.get(tokens.player_id)

See :doc:`guide` for refresh, revoke, and scope details.

Error handling
--------------

The SDK provides typed exceptions you can catch individually:

.. code-block:: python

   from vairified import (
       Vairified,
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
       print(f"Rate limited; retry after {e.retry_after} seconds")
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
