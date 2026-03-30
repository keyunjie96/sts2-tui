"""Card data models."""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class CardType(str, Enum):
    ATTACK = "attack"
    SKILL = "skill"
    POWER = "power"
    STATUS = "status"
    CURSE = "curse"


class TargetType(str, Enum):
    SINGLE_ENEMY = "single_enemy"
    ALL_ENEMIES = "all_enemies"
    SELF = "self"
    NONE = "none"


class CardRarity(str, Enum):
    BASIC = "basic"
    COMMON = "common"
    UNCOMMON = "uncommon"
    RARE = "rare"
    SPECIAL = "special"


class CardKeyword(str, Enum):
    EXHAUST = "exhaust"
    ETHEREAL = "ethereal"
    RETAIN = "retain"
    INNATE = "innate"
    UNPLAYABLE = "unplayable"
    SLY = "sly"


class Card(BaseModel):
    """A single card in the game."""

    id: str = "unknown"
    name: str = "?"
    type: CardType = CardType.ATTACK
    rarity: CardRarity = CardRarity.BASIC
    character: str = "neutral"
    energy_cost: int = 0
    star_cost: int = 0
    target_type: TargetType = TargetType.NONE
    description: str = ""
    keywords: set[CardKeyword] = Field(default_factory=set)
    upgrade_level: int = 0
    base_damage: int | None = None
    base_block: int | None = None
    base_magic_number: int | None = None
    vars: dict[str, Any] = Field(default_factory=dict)

    @property
    def is_upgraded(self) -> bool:
        return self.upgrade_level > 0
