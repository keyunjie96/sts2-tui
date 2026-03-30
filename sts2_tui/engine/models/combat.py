"""Combat state data models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field

from sts2_tui.engine.models.cards import Card
from sts2_tui.engine.models.creatures import Monster, Player


class TurnPhase(str, Enum):
    PLAYER_TURN = "player_turn"
    ENEMY_TURN = "enemy_turn"
    BETWEEN_TURNS = "between_turns"


class CardPile(BaseModel):
    """A pile of cards (hand, draw pile, discard, exhaust)."""

    cards: list[Card] = Field(default_factory=list)

    def __len__(self) -> int:
        return len(self.cards)

    def __iter__(self):
        return iter(self.cards)

    def __getitem__(self, idx):
        return self.cards[idx]


class CombatState(BaseModel):
    """Full combat state snapshot."""

    player: Player
    monsters: list[Monster] = Field(default_factory=list)
    hand: CardPile = Field(default_factory=CardPile)
    draw_pile: CardPile = Field(default_factory=CardPile)
    discard_pile: CardPile = Field(default_factory=CardPile)
    exhaust_pile: CardPile = Field(default_factory=CardPile)
    turn: int = 0
    phase: TurnPhase = TurnPhase.PLAYER_TURN
