"""
Leaderboard rating tracks -- the ``category`` codes, the labels the API also
accepts, and :class:`LeaderboardCategoryInfo` (one entry of
``GET /leaderboard/categories``).

A separate module from :mod:`vairified.models`, which is already past this
project's file-size budget; the TypeScript SDK keeps the same split
(``src/models/leaderboard-category.ts``).
"""

from __future__ import annotations

from enum import StrEnum
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

__all__ = [
    "LEADERBOARD_CATEGORY_LABELS",
    "LeaderboardCategory",
    "LeaderboardCategoryInfo",
    "LeaderboardCategoryLabel",
]


class LeaderboardCategory(StrEnum):
    """
    A leaderboard ``category`` code, in the order the API lists them.

    The first four are **verified** tracks -- their boards list only players
    verified in the sport. The last two are **recreational** tracks -- their
    boards rank every player, verified in the sport or not. Members are plain
    strings, so either the member or its value can be passed::

        await client.leaderboard.list(category=LeaderboardCategory.RECREATIONAL_SINGLES)
        await client.leaderboard.list(category="recreational_singles")
    """

    OVERALL = "overall"
    """Verified doubles, every gender mix (VO)."""
    GENDER = "gender"
    """Verified same-gender doubles (VG)."""
    SINGLES = "singles"
    """Verified singles (VS; legacy partner abbreviation ``S``)."""
    MIXED = "mixed"
    """Verified mixed doubles (VM)."""
    RECREATIONAL = "recreational"
    """The recreational doubles chain (R, for every player)."""
    RECREATIONAL_SINGLES = "recreational_singles"
    """Recreational singles (RS)."""


LeaderboardCategoryLabel = Literal["VO", "VG", "VM", "VS", "R", "RS"]
"""A label the API maps to a :class:`LeaderboardCategory`, case-insensitively --
the labels the web app shows, one per track. The API still resolves the legacy
``S`` (verified singles) and ``RO`` / ``Rv`` (the recreational chain, now
``R``); they are left out here so new code uses the current labels."""

LEADERBOARD_CATEGORY_LABELS: tuple[LeaderboardCategoryLabel, ...] = (
    "VO",
    "VG",
    "VM",
    "VS",
    "R",
    "RS",
)
"""Every track label the API accepts in place of a category code."""


class LeaderboardCategoryInfo(BaseModel):
    """
    One leaderboard track, as listed by
    :meth:`vairified.LeaderboardResource.category_list`.
    """

    model_config = ConfigDict(frozen=True, populate_by_name=True, extra="allow")

    code: str
    """The ``category`` code to pass to ``list()`` / ``rank()``. A plain ``str``
    rather than :class:`LeaderboardCategory`, so a track the API adds later
    parses."""
    name: str
    """Display name (``"Doubles"``, ``"Singles"``, ``"Recreational"``, ...)."""
    label: str
    """The label every surface shows for this track (``"VO"``, ``"VS"``, ``"R"``,
    ``"RS"``)."""
    verified_only: bool = Field(alias="verifiedOnly")
    """``True`` for the verified tracks: their board lists only players verified
    in the sport. ``False`` for ``R`` / ``RS``, whose boards rank every player."""

    def __repr__(self) -> str:  # pragma: no cover - REPL affordance
        return f"<LeaderboardCategoryInfo {self.code} ({self.label})>"
