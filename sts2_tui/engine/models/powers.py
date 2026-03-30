"""Power data models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class PowerType(str, Enum):
    BUFF = "buff"
    DEBUFF = "debuff"


class Power(BaseModel):
    """A power (buff/debuff) applied to a creature."""

    id: str = "unknown"
    name: str = "?"
    type: PowerType = PowerType.BUFF
    amount: int = 0
