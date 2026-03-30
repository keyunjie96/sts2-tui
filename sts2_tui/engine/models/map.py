"""Map data models."""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel, Field


class MapNodeType(str, Enum):
    MONSTER = "monster"
    ELITE = "elite"
    REST = "rest"
    SHOP = "shop"
    EVENT = "event"
    BOSS = "boss"
    TREASURE = "treasure"


class MapNode(BaseModel):
    """A single node on the map."""

    id: int = 0
    type: MapNodeType = MapNodeType.MONSTER
    x: int = 0
    y: int = 0
    connections: list[int] = Field(default_factory=list)


class GameMap(BaseModel):
    """The full game map."""

    nodes: list[MapNode] = Field(default_factory=list)
