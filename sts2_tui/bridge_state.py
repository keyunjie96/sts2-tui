"""State adapter — converts sts2-cli JSON responses into Pydantic models.

The sts2-cli engine returns rich JSON dicts describing the game state.
This module maps those into the existing :mod:`sts2_tui.engine.models`
Pydantic classes so the Textual TUI can keep using the same data models
regardless of whether the data comes from the Python engine or the real
.NET engine.

Typical usage::

    from sts2_tui.bridge_state import parse_combat_state, parse_map

    state = await bridge.play_card(0, target=0)
    if state.get("decision") == "combat_play":
        combat = parse_combat_state(state)
"""

from __future__ import annotations

import re
from typing import Any

from sts2_tui.engine.models.cards import (
    Card,
    CardKeyword,
    CardRarity,
    CardType,
    TargetType,
)
from sts2_tui.engine.models.combat import CardPile, CombatState, TurnPhase
from sts2_tui.engine.models.creatures import Monster, MonsterIntent, Player
from sts2_tui.engine.models.map import GameMap, MapNode, MapNodeType
from sts2_tui.engine.models.potions import Potion
from sts2_tui.engine.models.powers import Power, PowerType
from sts2_tui.engine.models.relics import Relic, RelicRarity
from sts2_tui.engine.models.run import RunState

# ---------------------------------------------------------------------------
# Name helpers
# ---------------------------------------------------------------------------

def _name_str(name_obj: Any) -> str:
    """Normalise a name that may be a bilingual dict or plain string."""
    if name_obj is None:
        return "?"
    if isinstance(name_obj, dict):
        return name_obj.get("en") or name_obj.get("zh") or str(name_obj)
    return str(name_obj)


def _lower_or(value: Any, default: str = "") -> str:
    """Lowercase a value, handling bilingual dicts and None gracefully."""
    if value is None:
        return default.lower()
    if isinstance(value, dict):
        # Bilingual dict like {"en": "Ironclad", "zh": "铁甲战士"}
        value = _name_str(value)
    return str(value).lower() if value else default.lower()


# ---------------------------------------------------------------------------
# Card parsing
# ---------------------------------------------------------------------------

_CARD_TYPE_MAP: dict[str, CardType] = {
    "attack": CardType.ATTACK,
    "skill": CardType.SKILL,
    "power": CardType.POWER,
    "status": CardType.STATUS,
    "curse": CardType.CURSE,
}

_TARGET_TYPE_MAP: dict[str, TargetType] = {
    "anyenemy": TargetType.SINGLE_ENEMY,
    "self": TargetType.SELF,
    "allenemy": TargetType.ALL_ENEMIES,
    "allenemies": TargetType.ALL_ENEMIES,
    "none": TargetType.NONE,
}

_CARD_RARITY_MAP: dict[str, CardRarity] = {
    "basic": CardRarity.BASIC,
    "common": CardRarity.COMMON,
    "uncommon": CardRarity.UNCOMMON,
    "rare": CardRarity.RARE,
    "special": CardRarity.SPECIAL,
}

_KEYWORD_MAP: dict[str, CardKeyword] = {
    "exhaust": CardKeyword.EXHAUST,
    "ethereal": CardKeyword.ETHEREAL,
    "retain": CardKeyword.RETAIN,
    "innate": CardKeyword.INNATE,
    "unplayable": CardKeyword.UNPLAYABLE,
    "sly": CardKeyword.SLY,
}


def _resolve_description(raw_desc: Any, stats: dict[str, Any] | None = None) -> str:
    """Strip BBCode and resolve SmartFormat template variables."""
    if raw_desc is None:
        return ""
    text = _name_str(raw_desc) if isinstance(raw_desc, dict) else str(raw_desc)
    # Strip BBCode tags like [b], [/b], [color=...], etc.
    text = re.sub(r"\[/?[^\]]+\]", "", text)
    # Resolve simple {VarName:...} templates with stats values.
    if stats:
        lower_stats = {k.lower(): v for k, v in stats.items()}

        def _replace(m: re.Match[str]) -> str:
            full = m.group(1)
            var = full.split(":")[0].lower()
            val = lower_stats.get(var)
            if val is not None:
                return str(val)
            return m.group(0)

        text = re.sub(r"\{([^{}]+)\}", _replace, text)
    return text.strip()


def parse_card(data: dict[str, Any]) -> Card:
    """Convert a single card JSON dict to a :class:`Card` model."""
    card_id = data.get("id", "unknown")
    stats = data.get("stats") or {}
    keywords_raw = data.get("keywords") or []
    keywords: set[CardKeyword] = set()
    for kw in keywords_raw:
        mapped = _KEYWORD_MAP.get(kw.lower())
        if mapped:
            keywords.add(mapped)

    rarity_str = _lower_or(data.get("rarity"), "basic")
    card_type_str = _lower_or(data.get("type"), "attack")
    target_str = _lower_or(data.get("target_type"), "none")

    # Extract character from card ID, e.g. "CARD.STRIKE_IRONCLAD" -> "ironclad"
    character = "neutral"
    parts = card_id.split(".")
    if len(parts) > 1:
        name_part = parts[-1]
        for char in ("ironclad", "silent", "defect", "regent", "necrobinder"):
            if char.upper() in name_part.upper():
                character = char
                break

    return Card(
        id=card_id,
        name=_name_str(data.get("name")),
        type=_CARD_TYPE_MAP.get(card_type_str, CardType.ATTACK),
        rarity=_CARD_RARITY_MAP.get(rarity_str, CardRarity.BASIC),
        character=character,
        energy_cost=data.get("cost", 0) if data.get("cost") is not None else 0,
        star_cost=data.get("star_cost", 0) or 0,
        target_type=_TARGET_TYPE_MAP.get(target_str, TargetType.NONE),
        description=_resolve_description(data.get("description"), stats),
        keywords=keywords,
        upgrade_level=1 if data.get("upgraded") else 0,
        base_damage=stats.get("damage"),
        base_block=stats.get("block"),
        base_magic_number=stats.get("magic") or stats.get("magicnumber"),
        vars={k: v for k, v in stats.items() if isinstance(v, (int, float))},
    )


def parse_hand(data: list[dict[str, Any]]) -> list[Card]:
    """Convert a list of hand card dicts to :class:`Card` models."""
    return [parse_card(c) for c in data]


# ---------------------------------------------------------------------------
# Power parsing
# ---------------------------------------------------------------------------

def parse_power(data: dict[str, Any]) -> Power:
    """Convert a power JSON dict to a :class:`Power` model."""
    amount = data.get("amount", 0)
    if amount is None:
        amount = 0
    # Negative amounts typically indicate debuffs.
    ptype = PowerType.DEBUFF if (isinstance(amount, (int, float)) and amount < 0) else PowerType.BUFF
    return Power(
        id=_lower_or(data.get("id") or data.get("name"), "unknown"),
        name=_name_str(data.get("name")),
        type=ptype,
        amount=int(amount),
    )


def parse_powers(data: list[dict[str, Any]] | None) -> list[Power]:
    """Convert a list of power dicts.  Accepts ``None``."""
    if not data:
        return []
    return [parse_power(p) for p in data]


# ---------------------------------------------------------------------------
# Relic parsing
# ---------------------------------------------------------------------------

def parse_relic(data: dict[str, Any]) -> Relic:
    """Convert a relic JSON dict to a :class:`Relic` model."""
    return Relic(
        id=_lower_or(data.get("id") or data.get("name"), "unknown"),
        name=_name_str(data.get("name")),
        description=_resolve_description(
            data.get("description"), data.get("vars")
        ),
        rarity=RelicRarity.COMMON,  # engine doesn't always send rarity
        counter=data.get("counter", -1) if data.get("counter") is not None else -1,
    )


# ---------------------------------------------------------------------------
# Potion parsing
# ---------------------------------------------------------------------------

def parse_potion(data: dict[str, Any]) -> Potion:
    """Convert a potion JSON dict to a :class:`Potion` model."""
    return Potion(
        id=_lower_or(data.get("id") or data.get("name"), "unknown"),
        name=_name_str(data.get("name")),
        description=_resolve_description(
            data.get("description"), data.get("vars")
        ),
    )


# ---------------------------------------------------------------------------
# Monster / intent parsing
# ---------------------------------------------------------------------------

def _parse_intent(intents_raw: list[dict[str, Any]] | None) -> MonsterIntent | None:
    """Summarise the intents list into a single :class:`MonsterIntent`."""
    if not intents_raw:
        return None

    # Combine all intents into a summary.
    damage: int | None = None
    hits: int = 1
    block: int | None = None
    is_buff = False
    is_debuff = False
    is_unknown = False
    intent_name_parts: list[str] = []

    for it in intents_raw:
        itype = it.get("type", "")
        if itype == "Attack":
            dmg = it.get("damage")
            if dmg is not None:
                damage = (damage or 0) + dmg if damage else dmg
            h = it.get("hits")
            if h and h > 1:
                hits = h
            intent_name_parts.append("Attack")
        elif itype == "Defend":
            blk_val = it.get("block")
            if blk_val is not None:
                block = (block or 0) + blk_val
            intent_name_parts.append("Defend")
        elif itype in ("Buff", "Heal"):
            is_buff = True
            intent_name_parts.append(itype)
        elif itype in ("Debuff", "DebuffStrong", "CardDebuff", "StatusCard"):
            is_debuff = True
            intent_name_parts.append(itype)
        elif itype == "Sleep":
            intent_name_parts.append("Sleep")
        elif itype == "Escape":
            intent_name_parts.append("Escape")
        elif itype == "Hidden":
            is_unknown = True
            intent_name_parts.append("Unknown")
        elif itype:
            intent_name_parts.append(itype)

    return MonsterIntent(
        id="+".join(intent_name_parts) or "unknown",
        name=" + ".join(intent_name_parts) or "Unknown",
        damage=damage,
        hits=hits,
        block=block,
        is_buff=is_buff,
        is_debuff=is_debuff,
        is_unknown=is_unknown,
    )


def parse_monster(data: dict[str, Any]) -> Monster:
    """Convert a single enemy dict to a :class:`Monster` model."""
    return Monster(
        id=str(data.get("index", 0)),
        name=_name_str(data.get("name")),
        max_hp=data.get("max_hp", 0),
        current_hp=data.get("hp", 0),
        block=data.get("block", 0),
        powers=parse_powers(data.get("powers")),
        is_dead=data.get("hp", 0) <= 0,
        intent=_parse_intent(data.get("intents")),
    )


def parse_monsters(data: list[dict[str, Any]]) -> list[Monster]:
    """Convert a list of enemy dicts to :class:`Monster` models."""
    return [parse_monster(e) for e in data]


# ---------------------------------------------------------------------------
# Player parsing
# ---------------------------------------------------------------------------

def parse_player(data: dict[str, Any], state: dict[str, Any] | None = None) -> Player:
    """Convert the ``player`` dict (and optional top-level state) to :class:`Player`.

    *state* is the full response dict so we can pull ``energy``, ``player_powers``,
    etc. which live outside the ``player`` sub-dict.
    """
    if state is None:
        state = {}

    relics_raw = data.get("relics") or []
    potions_raw = data.get("potions") or []
    deck_raw = data.get("deck") or []

    potions: list[Potion | None] = []
    for p in potions_raw:
        if p:
            potions.append(parse_potion(p))
        else:
            potions.append(None)

    player_powers = parse_powers(state.get("player_powers"))

    return Player(
        id="player",
        name=_name_str(data.get("name")),
        character=_lower_or(data.get("name"), "ironclad"),
        max_hp=data.get("max_hp", 80),
        current_hp=data.get("hp", 80),
        block=data.get("block", 0),
        gold=data.get("gold", 0),
        energy=state.get("energy", 0),
        max_energy=state.get("max_energy", 3),
        deck=[parse_card(c) for c in deck_raw],
        relics=[parse_relic(r) for r in relics_raw],
        potions=potions,
        powers=player_powers,
    )


# ---------------------------------------------------------------------------
# Combat state
# ---------------------------------------------------------------------------

def parse_combat_state(response: dict[str, Any]) -> CombatState:
    """Convert a ``combat_play`` decision response to :class:`CombatState`.

    The response must have ``decision == "combat_play"``.
    """
    player_data = response.get("player", {})
    player = parse_player(player_data, response)

    monsters = parse_monsters(response.get("enemies") or [])
    hand = parse_hand(response.get("hand") or [])

    return CombatState(
        player=player,
        monsters=monsters,
        hand=CardPile(cards=hand),
        draw_pile=CardPile(cards=[]),  # only counts available
        discard_pile=CardPile(cards=[]),
        exhaust_pile=CardPile(cards=[]),
        turn=response.get("round", 0),
        phase=TurnPhase.PLAYER_TURN,
        # Stash the pile counts so consumers can display them.
    )


# ---------------------------------------------------------------------------
# Map parsing
# ---------------------------------------------------------------------------

_NODE_TYPE_MAP: dict[str, MapNodeType] = {
    "monster": MapNodeType.MONSTER,
    "elite": MapNodeType.ELITE,
    "restsite": MapNodeType.REST,
    "rest": MapNodeType.REST,
    "shop": MapNodeType.SHOP,
    "event": MapNodeType.EVENT,
    "boss": MapNodeType.BOSS,
    "treasure": MapNodeType.TREASURE,
    "unknown": MapNodeType.EVENT,
}


def parse_map_choices(response: dict[str, Any]) -> GameMap:
    """Convert a ``map_select`` decision to a :class:`GameMap`.

    Note: the sts2-cli ``map_select`` only sends the *available choices*,
    not the full map.  Use ``get_map`` for the full map.
    """
    choices = response.get("choices") or []
    nodes: list[MapNode] = []
    for i, ch in enumerate(choices):
        ntype_str = _lower_or(ch.get("type"), "monster")
        nodes.append(
            MapNode(
                id=i,
                type=_NODE_TYPE_MAP.get(ntype_str, MapNodeType.MONSTER),
                x=ch.get("col", 0),
                y=ch.get("row", 0),
            )
        )
    return GameMap(nodes=nodes)


def parse_full_map(response: dict[str, Any]) -> GameMap:
    """Convert a ``get_map`` response to a :class:`GameMap`."""
    nodes_raw = response.get("nodes") or response.get("map") or []
    nodes: list[MapNode] = []
    for i, nd in enumerate(nodes_raw):
        ntype_str = _lower_or(nd.get("type"), "monster")
        connections = nd.get("connections") or nd.get("children") or []
        nodes.append(
            MapNode(
                id=nd.get("id", i),
                type=_NODE_TYPE_MAP.get(ntype_str, MapNodeType.MONSTER),
                x=nd.get("col", nd.get("x", 0)),
                y=nd.get("row", nd.get("y", 0)),
                connections=connections,
            )
        )
    return GameMap(nodes=nodes)


# ---------------------------------------------------------------------------
# Run state
# ---------------------------------------------------------------------------

def parse_run_state(response: dict[str, Any]) -> RunState:
    """Build a :class:`RunState` from any decision response.

    Pulls ``act``, ``floor``, and ``player`` from the response or its
    ``context`` sub-dict.
    """
    ctx = response.get("context") or {}
    player_data = response.get("player") or {}
    player = parse_player(player_data, response)

    return RunState(
        player=player,
        act=ctx.get("act") or response.get("act", 1),
        floor=ctx.get("floor") or response.get("floor", 0),
    )


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

def parse_response(response: dict[str, Any]) -> dict[str, Any]:
    """Parse any sts2-cli response into a dict of typed model objects.

    Returns a dict with at least ``"decision"`` and ``"raw"`` keys.
    Depending on the decision type, additional keys may be present:

    - ``"combat"``: :class:`CombatState` (for ``combat_play``)
    - ``"player"``: :class:`Player`
    - ``"map"``: :class:`GameMap` (for ``map_select``)
    - ``"run"``: :class:`RunState`
    - ``"options"``: list of option dicts (for events / rest)
    - ``"cards"``: list of :class:`Card` (for card rewards)
    """
    decision = response.get("decision", "")
    result: dict[str, Any] = {
        "decision": decision,
        "raw": response,
    }

    # Always parse run-level info if player data present.
    if "player" in response:
        result["run"] = parse_run_state(response)
        result["player"] = result["run"].player

    if decision == "combat_play":
        result["combat"] = parse_combat_state(response)

    elif decision == "map_select":
        result["map"] = parse_map_choices(response)

    elif decision in ("event_choice", "rest_site"):
        result["options"] = response.get("options") or []

    elif decision in ("card_reward", "card_select"):
        result["cards"] = [parse_card(c) for c in (response.get("cards") or [])]

    elif decision == "game_over":
        result["victory"] = response.get("victory", False)

    return result
