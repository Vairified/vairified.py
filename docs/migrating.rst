Migrating from 0.1.x
====================

Version 0.2.0 is a breaking rewrite of the SDK surface to match the
multi-sport Partner API v1. This guide walks through the changes and
shows how to port existing code.

See the `CHANGELOG
<https://github.com/Vairified/vairified.py/blob/main/CHANGELOG.md>`_
for the full release notes.

Upgrading from 0.8.x? See `Migrating from 0.8.x to 0.9.0`_ at the end.

At a glance
-----------

===================================================  ============================================================
0.1.x                                                0.2.0
===================================================  ============================================================
``client.get_member(id)``                            ``client.members.get(id)``
``client.search(...)`` returning ``SearchResults``   ``async for m in client.members.search(...)``
``client.find_player(name)``                         ``client.members.find(name)``
``client.submit_match(match)``                       ``client.matches.submit(batch)``
``client.submit_matches([m1, m2])``                  ``client.matches.submit(batch)`` (put both in ``batch.matches``)
``client.get_rating_updates()``                      ``client.members.rating_updates()``
``client.start_oauth(...)``                          ``client.oauth.authorize(...)``
``client.exchange_token(...)``                       ``client.oauth.exchange_token(...)``
``client.refresh_access_token(...)``                 ``client.oauth.refresh(...)``
``client.revoke_connection(...)``                    ``client.oauth.revoke(...)``
``client.get_leaderboard(...)``                      ``client.leaderboard.list(...)``
``client.get_player_rank(...)``                      ``client.leaderboard.rank(...)``
``client.get_leaderboard_categories()``              ``client.leaderboard.categories()``
``client.get_usage()``                               ``client.usage()``
``member.rating`` (single sport)                     ``member.rating_for("pickleball")``
``member.rating_splits.gender``                      ``member.sport["pickleball"]["gender-open"].rating``
``member.is_vairified``                              ``member.status.is_vairified``
``Player.from_dict(...)``                            ``Member.model_validate(...)``
===================================================  ============================================================

Sub-resources
-------------

All operations now live on sub-resources that mirror the REST path. This
replaces the flat ``client.xxx`` methods:

.. code-block:: python

   # Before
   member = await client.get_member("4873327")
   results = await client.search(city="Austin")
   result = await client.submit_match(match)

   # After
   member = await client.members.get("4873327")
   async for member in client.members.search(city="Austin"):
       ...
   result = await client.matches.submit(batch)

Multi-sport ratings
-------------------

The biggest conceptual change. In 0.1.x, every ``Member`` had a single
``rating`` and a flat ``rating_splits`` object. In 0.2.0, rating data
lives under ``member.sport`` keyed by sport code, so the same SDK can
represent a player's pickleball *and* padel ratings in one call:

.. code-block:: python

   # Before
   member.rating                        # 3.915
   member.rating_splits.gender          # 3.880
   member.rating_splits.singles         # 3.710
   member.is_vairified                  # True

   # After
   member.rating_for("pickleball")      # 3.915
   member.sport["pickleball"]["gender-open"].rating   # 3.880
   member.sport["pickleball"]["singles-open"].rating  # 3.710
   member.status.is_vairified           # True

``SportRating`` is dict-like, so you can also iterate or check membership:

.. code-block:: python

   pb = member.sport["pickleball"]
   print(len(pb), "splits")              # 3 splits
   if "singles-open" in pb:
       print(pb["singles-open"].rating)
   for key, split in pb:
       print(key, split.rating, split.abbr)

Fetch ratings for just the sports you care about with the ``sport``
filter:

.. code-block:: python

   # All sports this player has ratings in
   member = await client.members.get("4873327")

   # Just pickleball
   member = await client.members.get("4873327", sport="pickleball")

   # Multiple sports
   member = await client.members.get(
       "4873327",
       sport=["pickleball", "padel"],
   )

Auto-paginating search
----------------------

In 0.1.x, ``client.search()`` returned a ``SearchResults`` object with
``.next_page()``. In 0.2.0, ``client.members.search()`` is an async
iterator that fetches pages lazily as you iterate:

.. code-block:: python

   # Before
   results = await client.search(city="Austin", limit=20)
   while results.has_more:
       for player in results:
           print(player.name)
       results = await results.next_page()

   # After
   async for member in client.members.search(city="Austin"):
       print(member.name)

   # Cap the total
   async for member in client.members.search(name="Smith", max_results=50):
       ...

Matches: n-team × n-game
------------------------

``Match`` has been restructured to natively support any match shape —
singles, doubles, 3-way round robin, best-of-N, etc. — through a single
schema. Submit matches as a ``MatchBatch`` that carries shared defaults
for every match in the batch:

.. code-block:: python

   # Before
   from datetime import datetime
   match = Match(
       event="Weekly League",
       bracket="4.0 Doubles",
       date=datetime.now(),
       team1=("p1", "p2"),
       team2=("p3", "p4"),
       scores=[(11, 9), (11, 7)],
   )
   result = await client.submit_match(match)

   # After
   from vairified import MatchBatch, Match, Game
   batch = MatchBatch(
       sport="pickleball",                 # NEW: sport code is required
       win_score=11,                        # NEW: so the rater can interpret scores
       win_by=2,
       bracket="4.0 Doubles",
       event="Weekly League",
       match_date="2026-04-11T14:00:00Z",
       matches=[
           Match(
               identifier="m1",
               teams=[["p1", "p2"], ["p3", "p4"]],
               games=[Game(scores=[11, 9]), Game(scores=[11, 7])],
           ),
       ],
   )
   result = await client.matches.submit(batch)

Singles becomes ``teams=[["p1"], ["p2"]]``. A 3-way round robin becomes
``teams=[["p1"], ["p2"], ["p3"]]``. Each ``Game`` scores one entry per
team in the same order.

OAuth
-----

The OAuth methods moved to the ``client.oauth`` sub-resource:

.. code-block:: python

   # Before
   auth = await client.start_oauth(redirect_uri=..., scopes=[...])
   tokens = await client.exchange_token(code=..., redirect_uri=...)
   new_tokens = await client.refresh_access_token(refresh_token)
   await client.revoke_connection(player_id)

   # After
   auth = await client.oauth.authorize(redirect_uri=..., scopes=[...])
   tokens = await client.oauth.exchange_token(code=..., redirect_uri=...)
   new_tokens = await client.oauth.refresh(refresh_token)
   await client.oauth.revoke(player_id)

Scope strings are the same. ``OAuthScope`` is now a ``Literal`` type
alias, so editors and type checkers will flag typos in scope lists at
authoring time.

Immutable pydantic models
-------------------------

Response models (``Member``, ``SportRating``, ``RatingUpdate``, etc.)
are now frozen ``pydantic`` v2 ``BaseModel`` instances. This means:

- They're immutable — attempts to assign attributes raise ``ValidationError``.
- They tolerate unknown fields so the SDK stays forward-compatible with
  API additions.
- They accept both ``snake_case`` (Python) and ``camelCase`` (wire) field
  names via aliases.
- ``Player.from_dict(data)`` is replaced by ``Member.model_validate(data)``.

Request models (``Match``, ``MatchBatch``, ``Game``) use
``extra="forbid"`` so typos in keyword arguments fail loudly at
construction time instead of silently dropping data.

Status flags
------------

The top-level ``is_*`` booleans on ``Member`` are now grouped under
``member.status``:

.. code-block:: python

   # Before
   member.is_vairified
   member.is_wheelchair
   member.is_ambassador

   # After
   member.status.is_vairified
   member.status.is_wheelchair
   member.status.is_ambassador
   member.status.is_rater
   member.status.is_connected

Environment presets
-------------------

Use ``env=`` instead of writing the full base URL by hand:

.. code-block:: python

   # Before
   client = Vairified(
       api_key="vair_pk_xxx",
       base_url="https://api-staging.vairified.com/api/v1",
   )

   # After
   client = Vairified(api_key="vair_pk_xxx", env="staging")

Supported values: ``"production"`` (default), ``"staging"``, ``"local"``.
Reads ``VAIRIFIED_ENV`` from the environment when not supplied.

Migrating from 0.8.x to 0.9.0
=============================

0.9.0 removes and renames nothing in the SDK. Three SDK changes can affect
existing code (the first sections below), and two API behaviour changes need a
look even though code runs unchanged: ``Rv`` is now ``R``, and the leaderboard's
``verified_only`` default.

``sort_by`` only accepts the sortable fields
--------------------------------------------

``members.search(sort_by=...)`` and ``SearchFilters.sort_field`` are typed
``PartnerSearchSortField``, a ``Literal["lastName", "firstName", "memberId",
"city", "state", "country"]``. The API now refuses any other value with a 400;
``"rating"`` never worked and always failed with a 500. The narrowing is for type
checkers only. A plain ``str`` still runs, but mypy / pyright flag it. Check the
value against the exported tuple:

.. code-block:: python

   from vairified import PARTNER_SEARCH_SORT_FIELDS

   sort_by = raw if raw in PARTNER_SEARCH_SORT_FIELDS else None
   async for m in client.members.search(sort_by=sort_by):
       ...

A value outside the list is still sent, as in the TypeScript SDK, and the API's
400 surfaces as :class:`vairified.ValidationError`.

An unset ``sort_order`` now means ascending
-------------------------------------------

``sort_order`` defaulted to ``"desc"``, so every search was sent with
``sortDirection=desc``. It now defaults to ``None`` and is sent only when set,
which gives the API's default order, ascending by last name. This matches the
TypeScript SDK. To keep the old order:

.. code-block:: python

   client.members.search(city="Austin", sort_order="desc")

``sort_order`` and ``SearchFilters.sort_direction`` are also typed
``Literal["asc", "desc"]``.

``Rv`` is now ``R``
-------------------

The recreational doubles chain is ``R`` for every player, in ``abbr`` and
``label`` alike. A player verified in the sport used to get ``Rv`` (and the
label ``RO``); neither is sent any more. The labels the API sends are ``VO``,
``VG``, ``VM``, ``VS``, ``R`` and ``RS`` (plus a bracket suffix such as
``RS40+``).

.. code-block:: python

   # Before -- inferred "verified" from the recreational abbreviation
   verified = pb.abbr == "Rv"     # never True now
   # After -- the per-sport flag (a verified VO / VG / VM / VS rating there)
   verified = pb.is_vairified

Also replace ``by_label("Rv")`` / ``by_label("RO")`` with ``by_label("R")``. As
a leaderboard ``category``, ``"Rv"`` and ``"RO"`` still resolve to
``recreational``, but ``LEADERBOARD_CATEGORY_LABELS`` lists ``"R"`` only.

Leaderboard ``verified_only`` no longer defaults to "unverified only"
---------------------------------------------------------------------

``verified_only`` on ``leaderboard.list()`` is an optional narrowing filter. Its
default is now ``None`` (was ``False``), and it is sent only when you set it.

==================  =========================  ========================
``verified_only``   Before 0.9.0               Now
==================  =========================  ========================
unset / ``None``    unverified players only    no filter -- everyone
``False``           unverified players only    no filter -- everyone
``True``            verified players only      VAIRified players only
==================  =========================  ========================

Verified boards (``overall``, ``gender``, ``mixed``, ``singles``) list only
verified players whatever it says; the recreational boards (``R``, ``RS``) rank
everyone unless you pass ``True``. There is no longer a way to list *only*
unverified players; if you relied on that, filter the page yourself.

.. code-block:: python

   await client.leaderboard.list(category="R")                      # everyone
   await client.leaderboard.list(category="R", verified_only=True)  # VAIRified only

Six leaderboard tracks
----------------------

``LeaderboardCategory`` (new) is ``OVERALL``, ``GENDER``, ``SINGLES``,
``MIXED``, ``RECREATIONAL``, ``RECREATIONAL_SINGLES``. The engine's recreational
same-gender and mixed tracks are internal: the API refuses them as a
``category`` (``ValidationError``) and never sends their splits, so don't look
for ``recreational_gender-*`` / ``recreational_mixed-*`` keys.

Behaviour to expect from the API
--------------------------------

Nothing to change in code, but don't rely on the old behaviour:

- **Verified-track splits** (``overall-*``, ``gender-*``, ``mixed-*``,
  ``singles-*``) are absent for a player not verified in that sport. The
  primary rating falls back to the recreational chain (``R``). Use
  ``key in sport_rating`` before you index.
- **On the leaderboard**, ``list()`` and ``categories()`` now check the API
  key the SDK sends. An invalid key raises ``AuthenticationError``, a key
  without ``leaderboard:read`` raises ``PermissionDeniedError``.
- **Deprecated leaderboard options** ``club_id`` (on ``list`` and ``rank``) and
  ``city`` (on ``rank``) are no longer sent and raise a ``DeprecationWarning``.
  Remove them.
- **Rating splits** were already immutable in Python (frozen pydantic models),
  so the TypeScript SDK's frozen-split change has no Python counterpart.
