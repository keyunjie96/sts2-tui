"""Potion data models."""

from __future__ import annotations

from pydantic import BaseModel


class Potion(BaseModel):
    """A potion in the player's belt."""

    id: str = "unknown"
    name: str = "?"
    description: str = ""
