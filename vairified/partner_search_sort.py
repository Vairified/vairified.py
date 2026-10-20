"""
The ``sortField`` whitelist of ``GET /partner/search``.

Mirrors ``src/models/partner-search-sort.ts`` in the TypeScript SDK. The values
are the wire values in both SDKs (``"lastName"``, not ``"last_name"``), so an
argument means the same thing whichever SDK sent it.
"""

from __future__ import annotations

from typing import Literal

__all__ = ["PARTNER_SEARCH_SORT_FIELDS", "PartnerSearchSortField"]

PartnerSearchSortField = Literal[
    "lastName", "firstName", "memberId", "city", "state", "country"
]
"""A field ``members.search(sort_by=...)`` can sort by -- every one a column the
search results already show. There is no rating sort: ratings are per sport and
category, so there is no single value to order by."""

PARTNER_SEARCH_SORT_FIELDS: tuple[PartnerSearchSortField, ...] = (
    "lastName",
    "firstName",
    "memberId",
    "city",
    "state",
    "country",
)
"""Every value :data:`PartnerSearchSortField` allows, in the API's order."""
