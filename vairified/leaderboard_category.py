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
    verified in the sport. The last four are **recreational** tracks. Members
    are plain strings, so either the member or its value can be passed::

        await client.leaderboard.list(category=LeaderboardCategory.RECREATIONAL_GENDER)
        await client.leaderboard.list(category="recreational_gender")
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
    """The recreational chain (RO, or Rv for a player verified in the sport)."""
    RECREATIONAL_GENDER = "recreational_gender"
    """Recreational same-gender doubles (RG)."""
    RECREATIONAL_MIXED = "recreational_mixed"
    """Recreational mixed doubles (RM)."""
    RECREATIONAL_SINGLES = "recreational_singles"
    """Recreational singles (RS)."""


LeaderboardCategoryLabel = Literal[
    "VO", "VG", "VM", "VS", "S", "RO", "Rv", "R", "RG", "RM", "RS"
]
"""A label the API maps to a :class:`LeaderboardCategory`, case-insensitively.
``S`` (verified singles) and ``R`` / ``Rv`` (the recreational chain) are the
legacy partner abbreviations and keep resolving."""

LEADERBOARD_CATEGORY_LABELS: tuple[LeaderboardCategoryLabel, ...] = (
    "VO",
    "VG",
    "VM",
    "VS",
    "S",
    "RO",
    "Rv",
    "R",
    "RG",
    "RM",
    "RS",
)
"""Every label the API accepts in place of a category code."""


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
    """The label the web app shows for this track (``"VO"``, ``"RO"``, ``"RG"``)."""
    verified_only: bool = Field(alias="verifiedOnly")
    """``True`` for the verified tracks: their board lists only players verified
    in the sport."""
    verified_label: str | None = Field(default=None, alias="verifiedLabel")
    """The recreational chain's label for a player verified in the sport
    (``"Rv"``); ``None`` on every other track."""

    def __repr__(self) -> str:  # pragma: no cover - REPL affordance
        return f"<LeaderboardCategoryInfo {self.code} ({self.label})>"
