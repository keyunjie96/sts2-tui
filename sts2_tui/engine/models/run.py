"""Run state data models."""

from __future__ import annotations

from pydantic import BaseModel

from sts2_tui.engine.models.creatures import Player


class RunState(BaseModel):
    """Top-level run state."""

    player: Player
    act: int = 1
    floor: int = 0
