"""Creature (Player / Monster) data models."""

from __future__ import annotations

from pydantic import BaseModel, Field

from sts2_tui.engine.models.cards import Card
from sts2_tui.engine.models.potions import Potion
from sts2_tui.engine.models.powers import Power
from sts2_tui.engine.models.relics import Relic


class MonsterIntent(BaseModel):
    """Summarised intent for one turn."""

    id: str = "unknown"
    name: str = "Unknown"
    damage: int | None = None
    hits: int = 1
    block: int | None = None
    is_buff: bool = False
    is_debuff: bool = False
    is_unknown: bool = False


class Monster(BaseModel):
    """An enemy monster in combat."""

    id: str = "0"
    name: str = "?"
    max_hp: int = 0
    current_hp: int = 0
    block: int = 0
    powers: list[Power] = Field(default_factory=list)
    is_dead: bool = False
    intent: MonsterIntent | None = None


class Player(BaseModel):
    """The player character."""

    id: str = "player"
    name: str = "?"
    character: str = "ironclad"
    max_hp: int = 80
    current_hp: int = 80
    block: int = 0
    gold: int = 0
    energy: int = 0
    max_energy: int = 3
    deck: list[Card] = Field(default_factory=list)
    relics: list[Relic] = Field(default_factory=list)
    potions: list[Potion | None] = Field(default_factory=list)
    powers: list[Power] = Field(default_factory=list)
