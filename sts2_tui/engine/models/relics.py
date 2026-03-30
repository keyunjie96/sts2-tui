"""Relic data models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class RelicRarity(str, Enum):
    STARTER = "starter"
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    BOSS = "boss"
    SPECIAL = "special"
    SHOP = "shop"
    EVENT = "event"


class Relic(BaseModel):
    """A relic the player possesses."""

    id: str = "unknown"
    name: str = "?"
    description: str = ""
    rarity: RelicRarity = RelicRarity.COMMON
    counter: int = -1
