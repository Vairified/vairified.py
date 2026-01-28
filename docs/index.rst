Vairified Python SDK
====================

Official Python SDK for the Vairified Partner API. Async-first, object-oriented
design for easy integration with player ratings, search, and match submission.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   quickstart
   guide
   api

Installation
------------

Install from PyPI:

.. code-block:: bash

   pip install vairified

Or with UV:

.. code-block:: bash

   uv add vairified

Quick Example
-------------

.. code-block:: python

   import asyncio
   from vairified import Vairified

   async def main():
       async with Vairified(api_key="vair_pk_xxx") as client:
           member = await client.get_member("user_123")
           print(f"{member.name}: {member.rating}")

   asyncio.run(main())

Features
--------

- **Async-first**: Built on ``httpx`` for modern async/await patterns
- **Object-oriented**: Rich models with methods (``member.refresh()``, ``results.next_page()``)
- **Type-safe**: Full type hints for IDE autocompletion
- **OAuth support**: Full OAuth flow for player consent and token management
- **Environment support**: Switch between production, staging, and local environments
- **Dry-run mode**: Test integrations without affecting production data

Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
