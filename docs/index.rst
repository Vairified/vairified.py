Vairified Python SDK
====================

Official Python SDK for the Vairified Partner API. Async-first,
``pydantic`` v2 models, and a sub-resource layout that mirrors the REST
surface — built for multi-sport player ratings, search, and bulk match
submission.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   quickstart
   guide
   api
   migrating

Installation
------------

.. code-block:: bash

   pip install vairified

Or with `uv <https://docs.astral.sh/uv>`_:

.. code-block:: bash

   uv add vairified

Quick Example
-------------

.. code-block:: python

   import asyncio
   from vairified import Vairified

   async def main() -> None:
       async with Vairified(api_key="vair_pk_xxx") as client:
           member = await client.members.get("vair_mem_xxx")
           print(member.name, "rated", member.rating_for("pickleball"))

           async for m in client.members.search(city="Austin", max_results=5):
               print(m.name, m.rating_for("pickleball"))

   asyncio.run(main())

Features
--------

- **Async-first** — built on ``httpx`` with a clean ``async with`` lifecycle
- **Multi-sport** — rating data keyed by sport code, dict-like access to splits
- **Auto-paginating search** — iterate through thousands of results lazily
- **n-team × n-game matches** — singles, doubles, round-robin, best-of-N in one shape
- **Immutable pydantic v2 models** — frozen, forward-compatible, REPL-friendly
- **Type-safe OAuth** — ``OAuthScope`` literal catches typos at authoring time
- **Typed exceptions** — map HTTP status codes to dedicated error classes

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
