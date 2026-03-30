"""Game controller -- bridges the TUI to sts2-cli via EngineBridge.

The controller is now a thin pass-through: all game logic lives in sts2-cli.
It forwards TUI inputs to the bridge and stores the latest raw state dict.
Error responses from the bridge are caught and returned as dict with
``type: "error"`` so screens can show them without crashing.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from sts2_tui.bridge import BridgeError, EngineBridge

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers for extracting display-friendly data from raw sts2-cli responses
# ---------------------------------------------------------------------------


def _name_str(name_obj: Any) -> str:
    """Convert a name object (possibly bilingual dict) to a plain string.

    When the engine sends bilingual dicts like ``{"en": "Strike", "zh": "打击"}``,
    this returns the value for the current language setting, falling back to
    English then Chinese.

    Also handles raw localization keys like ``"KAISER_CRAB.name"`` by stripping
    the ``.name`` suffix and converting ``UPPER_SNAKE`` to title case.
    """
    if name_obj is None:
        return "?"
    if isinstance(name_obj, dict):
        from sts2_tui.tui.i18n import get_language
        lang = get_language()
        return name_obj.get(lang) or name_obj.get("en") or name_obj.get("zh") or str(name_obj)
    s = str(name_obj)
    # Detect unresolved localization keys like "KAISER_CRAB.name"
    if s.endswith(".name") and s[0].isupper():
        key = s[: -len(".name")]
        # Convert UPPER_SNAKE_CASE to Title Case (e.g. "KAISER_CRAB" -> "Kaiser Crab")
        return key.replace("_", " ").title()
    return s


_STAT_KEY_LABELS: dict[str, str] = {
    "damage": "Damage",
    "block": "Block",
    "hploss": "HP Loss",
    "maxhp": "Max HP",
    "energy": "Energy",
    "cards": "Cards",
    "heal": "Heal",
    "magic": "Magic",
    "strength": "Strength",
    "dexterity": "Dexterity",
    "parry": "Block",
    "strengthloss": "Strength Loss",
}


def humanize_stat_key(key: str) -> str:
    """Convert an engine stat key like 'juggernautpower' into a human-readable label.

    Known patterns:
    - Keys ending in 'power' (e.g., 'vulnerablepower', 'juggernautpower')
      are power/buff names -- strip the suffix and title-case.
    - Keys like 'hploss' -> 'HP Loss', 'maxhp' -> 'Max HP'.
    - Otherwise, split on underscores and title-case.
    """
    lower = key.lower()
    known = _STAT_KEY_LABELS.get(lower)
    if known:
        return known
    # Strip 'power' suffix for buff/debuff stat keys
    if lower.endswith("power") and len(lower) > 5:
        base = lower[:-5]
        return base.title()
    return key.replace("_", " ").title()


def resolve_card_description(description: str, stats: dict[str, Any] | None) -> str:
    """Resolve template variables in a card description using the stats dict.

    sts2-cli sends descriptions with SmartFormat templates like
    ``{Damage:diff()}``, ``{Block:diff()}``, ``{VulnerablePower:diff()}``.
    The ``stats`` dict contains the actual values with lowercase keys
    (e.g. ``damage``, ``block``, ``vulnerablepower``).

    This function replaces each ``{VarName:...}`` placeholder with the
    corresponding value from stats (matched case-insensitively), and strips
    any BBCode markup tags like ``[b]``, ``[/b]``, ``[color=...]``, etc.

    Special templates handled:
    - ``{energyPrefix:energyIcons(N)}`` -> ``[N]`` (energy cost icons)
    - ``{IfUpgraded:show:A|B}`` -> ``B`` (cards are not upgraded by default)
    - ``{Var:plural:singular|plural}`` -> singular/plural based on stat value
    - ``{Stars:starIcons()}`` -> ``N Stars``
    - ``{InCombat:...|...}`` -> stripped (out-of-combat context)
    """
    if not description:
        return ""
    text = description
    # Strip BBCode tags (e.g. [b], [/b], [color=#ff0000]) but preserve
    # energy icons like [2], [3] (pure numeric content in brackets)
    text = re.sub(r"\[/?[a-zA-Z][^\]]*\]", "", text)
    # Remove {InCombat:...|} blocks (may span newlines and contain nested {})
    text = re.sub(r"\{InCombat:.*?\|\}", "", text, flags=re.DOTALL)
    # Remove {IsTargeting:...|} blocks (conditional targeting display)
    text = re.sub(r"\{IsTargeting:.*?\|\}", "", text, flags=re.DOTALL)
    # Handle {IsMultiplayer:true_text|false_text} conditional (always single-player in CLI)
    text = re.sub(r"\{IsMultiplayer:([^|]*)\|([^}]*)\}", r"\2", text)
    # Replace {energyPrefix:energyIcons(N)} -- this is an energy icon/prefix.
    # When N==1 it's just the energy symbol (e.g., "Costs 1 less [E]"),
    # when N>1 it shows N energy (e.g., "Gain [3]").
    from sts2_tui.tui.i18n import get_label
    _energy_label = get_label("energy")  # "Energy" or "能量"

    def _energy_prefix_replace(m: re.Match[str]) -> str:
        n = int(m.group(1))
        return _energy_label if n <= 1 else f"{n} {_energy_label}"
    text = re.sub(r"\{energyPrefix:energyIcons\((\d+)\)\}", _energy_prefix_replace, text)
    # Replace {IfUpgraded:show:A|B} with B (default non-upgraded value)
    # A can be empty (e.g., {IfUpgraded:show:| at random} → " at random")
    text = re.sub(r"\{IfUpgraded:show:([^|]*)\|([^}]*)\}", r"\2", text)
    # Replace {IfUpgraded:show:A} (without pipe) with empty (not upgraded)
    text = re.sub(r"\{IfUpgraded:show:[^}]*\}", "", text)

    # Resolve {VarName:...} templates using stats values
    lower_stats = {k.lower(): v for k, v in stats.items()} if stats else {}

    # Known icon/variable substitutions that aren't in stats
    _ICON_VARS: dict[str, str] = {
        "singlestaricon": "\u2605",   # filled star
        "emptystaricon": "\u2606",    # empty star
        "energyicon": "[E]",
    }

    def _replace(m: re.Match[str]) -> str:
        full = m.group(1)
        parts = full.split(":")
        var = parts[0].lower()

        # Self-reference {:diff()}, {:fmt()} -- leave untouched for the
        # nested-brace pass which resolves these using the parent variable.
        if not var and len(parts) >= 2:
            return m.group(0)

        val = lower_stats.get(var)

        # Handle conditional pattern: {Var:cond:>0?text|} or {Var:cond:>N?text|}
        # SmartFormat syntax: if Var matches the condition, show the true branch;
        # otherwise show the false branch (after the pipe).
        if len(parts) >= 3 and parts[1] == "cond":
            cond_str = ":".join(parts[2:])  # rejoin in case text contains colons
            # Parse condition like ">0?text|fallback" or ">0? text|"
            cond_match = re.match(r"([><=!]+)(\d+)\?(.*)$", cond_str, re.DOTALL)
            if cond_match:
                op = cond_match.group(1)
                threshold = int(cond_match.group(2))
                branches = cond_match.group(3)
                # Split on last unescaped pipe for true|false branches
                pipe_idx = branches.rfind("|")
                if pipe_idx >= 0:
                    true_branch = branches[:pipe_idx]
                    false_branch = branches[pipe_idx + 1:]
                else:
                    true_branch = branches
                    false_branch = ""
                if val is not None:
                    try:
                        num_val = int(val)
                    except (ValueError, TypeError):
                        num_val = 0
                    satisfied = False
                    if op == ">":
                        satisfied = num_val > threshold
                    elif op == ">=":
                        satisfied = num_val >= threshold
                    elif op == "<":
                        satisfied = num_val < threshold
                    elif op == "<=":
                        satisfied = num_val <= threshold
                    elif op == "==" or op == "=":
                        satisfied = num_val == threshold
                    elif op == "!=":
                        satisfied = num_val != threshold
                    return true_branch if satisfied else false_branch
                # Value unknown -- default to false branch (conservative)
                return false_branch

        # Handle plural pattern: {Var:plural:singular|plural}
        if len(parts) >= 3 and parts[1] == "plural":
            plural_parts = parts[2].split("|")
            if val is not None and len(plural_parts) == 2:
                word = plural_parts[0] if val == 1 else plural_parts[1]
                return word
            return parts[2].split("|")[-1] if "|" in parts[2] else parts[2]

        # Handle starIcons() formatter -- show "N Star(s)" / "N 星辰"
        if len(parts) >= 2 and "staricons" in parts[1].lower():
            _stars_label = get_label("stars")  # "Stars" or "星辰"
            if val is not None:
                return f"{val} {_stars_label}"
            return _stars_label  # fallback when value is unknown

        # Handle energyIcons() formatter -- show "N Energy" / "N 能量"
        if len(parts) >= 2 and "energyicons" in parts[1].lower():
            if val is not None:
                return f"{val} {_energy_label}"
            return _energy_label  # fallback when value is unknown

        # Standard resolution: look up var in stats
        if val is not None:
            # When a var resolves to 0 and looks like an entity reference
            # (e.g., {Relic}, {BirdCard}, {SnakeEnchantment}), the engine is
            # sending an ID rather than a name.  Show a readable fallback
            # like "a Relic" instead of the literal "0".
            if val == 0 and len(parts) == 1:
                # Heuristic: var names ending in Card/Relic/Enchantment/Potion
                # are entity references, not numeric stats.
                _ENTITY_SUFFIXES = ("card", "relic", "enchantment", "potion", "curse", "summon")
                if any(var.endswith(s) for s in _ENTITY_SUFFIXES):
                    # Split camelCase into words: "BirdCard" -> "Bird Card"
                    label = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", parts[0])
                    # Localize common entity type names for Chinese mode
                    from sts2_tui.tui.i18n import get_language
                    if get_language() == "zh":
                        _ZH_ENTITY_LABELS: dict[str, str] = {
                            "Curse": "\u8bc5\u5492",        # 诅咒
                            "Enchantment": "\u9644\u9b54",  # 附魔
                            "Relic": "\u9057\u7269",        # 遗物
                            "Potion": "\u836f\u6c34",       # 药水
                            "Card": "\u5361\u724c",         # 卡牌
                        }
                        label = _ZH_ENTITY_LABELS.get(label, label)
                    return label
            return str(val)

        # Check known icon variables (e.g., {singleStarIcon})
        icon = _ICON_VARS.get(var)
        if icon is not None:
            return icon

        # For unresolved templates with formatters like {Var:diff()},
        # show "X" instead of the var name to avoid duplication like
        # "Deal Damage damage" or "Gain Block Block"
        if len(parts) >= 2:
            return "X"

        return "X"  # unresolved simple {Var} also becomes X

    # Apply resolution in multiple passes to handle nested templates.
    # Inner templates resolve first, then outer ones.
    for _ in range(3):  # max 3 passes for deeply nested templates
        new_text = re.sub(r"\{([^{}]+)\}", _replace, text)
        if new_text == text:
            break
        text = new_text

    # Handle nested-brace patterns that couldn't be resolved above,
    # e.g. {Var:plural:word|{:fmt()}} -- match one level of nesting.
    def _replace_nested(m: re.Match[str]) -> str:
        full = m.group(1)
        colon_idx = full.find(":")
        if colon_idx < 0:
            var = full.lower().replace("{", "").replace("}", "")
            val = lower_stats.get(var)
            if val is not None:
                return str(val)
            icon = _ICON_VARS.get(var)
            return icon if icon is not None else ""
        var = full[:colon_idx].lower()
        rest = full[colon_idx + 1:]
        val = lower_stats.get(var)

        def _resolve_self_refs(text_part: str, parent_val: Any) -> str:
            """Replace {:diff()}, {:fmt()}, and {} self-references with the parent value.

            In SmartFormat, ``{:diff()}`` inside a plural pattern refers
            back to the parent variable's value.  E.g.
            ``{LightningRodPower:plural:turn|{:diff()} turns}`` with
            value 2 should produce ``2 turns``.

            Bare ``{}`` is also a SmartFormat self-reference (e.g.
            ``{ClarityPower:plural:turn|{} turns}`` with value 3
            should produce ``3 turns``).
            """
            if parent_val is not None:
                # Replace {:formatter()} patterns
                text_part = re.sub(r"\{:\w+\(\)\}", str(parent_val), text_part)
                # Replace bare {} self-references
                text_part = text_part.replace("{}", str(parent_val))
            # Strip any remaining unresolvable inner templates
            return re.sub(r"\{[^}]*\}", "", text_part)

        if rest.startswith("plural:"):
            plural_content = rest[len("plural:"):]
            pipe_idx = plural_content.find("|")
            if pipe_idx >= 0:
                singular = _resolve_self_refs(plural_content[:pipe_idx], val)
                plural_word = _resolve_self_refs(plural_content[pipe_idx + 1:], val)
                if val is not None:
                    return singular if val == 1 else (plural_word or singular)
                return plural_word or singular
        if val is not None:
            return str(val)
        return ""  # strip unresolvable nested templates

    text = re.sub(r"\{([^{}]*\{[^{}]*\}[^{}]*)\}", _replace_nested, text)
    # Collapse excess whitespace, multiple spaces, and blank lines
    text = re.sub(r"  +", " ", text)
    text = re.sub(r"\n\s*\n", "\n", text)
    return text.strip()


def calculate_display_damage(base_damage: int, player: dict, target: dict | None) -> int:
    """Calculate the displayed damage for a card against a specific target.

    This is for DISPLAY ONLY -- the engine does the real calculation.
    Accounts for:
    - Player Strength buff -> +damage
    - Player Weak debuff -> damage * 0.75
    - Target Vulnerable debuff -> damage * 1.5
    """
    damage = base_damage

    # Add player Strength
    for p in player.get("powers", []):
        if p.get("name", "").lower() == "strength":
            damage += p.get("amount", 0)

    # Player Weak reduces damage by 25%
    for p in player.get("powers", []):
        if p.get("name", "").lower() == "weak":
            damage = int(damage * 0.75)

    # Target Vulnerable increases damage by 50%
    if target:
        for p in target.get("powers", []):
            if p.get("name", "").lower() == "vulnerable":
                damage = int(damage * 1.5)

    return max(0, damage)


def calculate_display_block(base_block: int, player: dict) -> int:
    """Calculate the displayed block for a card accounting for player buffs/debuffs.

    This is for DISPLAY ONLY -- the engine does the real calculation.
    Accounts for:
    - Player Dexterity buff -> +block
    - Player Frail debuff -> block * 0.75
    """
    block = base_block

    # Add player Dexterity
    for p in player.get("powers", []):
        if p.get("name", "").lower() == "dexterity":
            block += p.get("amount", 0)

    # Player Frail reduces block by 25%
    for p in player.get("powers", []):
        if p.get("name", "").lower() == "frail":
            block = int(block * 0.75)

    return max(0, block)


def extract_enemies(state: dict) -> list[dict]:
    """Normalise enemy data from a combat_play response."""
    result = []
    for e in state.get("enemies", []):
        powers = []
        for pw in e.get("powers") or []:
            powers.append({
                "name": pw.get("name", ""),
                "amount": pw.get("amount", 0),
                "description": pw.get("description", ""),
            })
        # Parse intents -- collect ALL intent parts for multi-intent enemies
        intents_raw = e.get("intents") or []
        intent_parts: list[str] = []
        intent_damage: int | None = None
        intent_hits: int | None = None
        is_defend = False
        is_buff = False
        is_debuff = False
        is_debuff_strong = False
        is_status_card = False
        is_heal = False
        is_stun = False
        is_summon = False
        is_sleep = False
        for it in intents_raw:
            itype = it.get("type", "")
            dmg = it.get("damage")
            hits = it.get("hits")
            if itype == "Attack":
                intent_damage = dmg
                intent_hits = hits
                if dmg is not None:
                    if hits and hits > 1:
                        # Engine sends total damage — show per-hit × hits
                        per_hit = dmg // hits
                        part = f"Attack {per_hit}x{hits}"
                    else:
                        part = f"Attack {dmg}"
                else:
                    part = "Attack"
                intent_parts.append(part)
            elif itype == "Defend":
                is_defend = True
                intent_parts.append("Defend")
            elif itype == "Buff":
                is_buff = True
                intent_parts.append("Buff")
            elif itype == "Debuff":
                is_debuff = True
                intent_parts.append("Debuff")
            elif itype == "DebuffStrong":
                is_debuff = True
                is_debuff_strong = True
                intent_parts.append("Strong Debuff")
            elif itype == "StatusCard":
                is_status_card = True
                intent_parts.append("Status Card")
            elif itype == "Heal":
                is_heal = True
                intent_parts.append("Heal")
            elif itype == "Stun":
                is_stun = True
                intent_parts.append("Stun")
            elif itype == "Summon":
                is_summon = True
                intent_parts.append("Summon")
            elif itype == "Sleep":
                is_sleep = True
                intent_parts.append("\U0001f4a4 Zzz")
            elif itype:
                intent_parts.append(itype)
        intent_summary = " + ".join(intent_parts) if intent_parts else ""

        hp_val = e.get("hp") or 0
        result.append({
            "index": e.get("index", 0),
            "name": _name_str(e.get("name")),
            "hp": hp_val,
            "max_hp": e.get("max_hp") or 0,
            "block": e.get("block") or 0,
            "intent_summary": intent_summary,
            "intent_damage": intent_damage,
            "intent_hits": intent_hits,
            "is_defend": is_defend,
            "is_buff": is_buff,
            "is_debuff": is_debuff,
            "is_debuff_strong": is_debuff_strong,
            "is_status_card": is_status_card,
            "is_heal": is_heal,
            "is_stun": is_stun,
            "is_summon": is_summon,
            "is_sleep": is_sleep,
            "powers": powers,
            "is_dead": hp_val <= 0,
        })
    return result


def _merge_known_relic_vars(relic: dict, engine_vars: dict) -> dict:
    """Merge well-known default vars into engine vars for relic description resolution.

    Some relics (e.g. Bone Tea, Ember Tea) have template variables like
    {Combats} in their description but the engine may not always send
    the vars dict (game_data also lacks them).  This merges known
    defaults for keys not already present in the engine vars.
    """
    from sts2_tui.tui.screens.shop import _KNOWN_RELIC_VARS
    relic_id = relic.get("id", "")
    name = _name_str(relic.get("name"))
    # Look up by id first (language-independent), then by display name
    known: dict = {}
    if relic_id:
        known = _KNOWN_RELIC_VARS.get(relic_id.lower().replace("_", " "), {})
    if not known:
        known = _KNOWN_RELIC_VARS.get(name.lower(), {})
    if not known:
        return engine_vars
    # Merge: only add keys not already present (case-insensitive check)
    lower_engine = {k.lower() for k in engine_vars}
    merged = dict(engine_vars)
    for k, v in known.items():
        if k.lower() not in lower_engine:
            merged[k] = v
    return merged


def extract_player(state: dict) -> dict:
    """Normalise player data from a response."""
    p = state.get("player", {})
    powers = []
    for pw in state.get("player_powers") or []:
        powers.append({
            "name": pw.get("name", ""),
            "amount": pw.get("amount", 0),
            "description": pw.get("description", ""),
        })
    potions = []
    for pot in p.get("potions") or []:
        raw_desc = pot.get("description", "")
        pot_vars = pot.get("vars") or {}
        resolved_desc = resolve_card_description(raw_desc, pot_vars)
        potions.append({
            "index": pot.get("index", 0),
            "name": _name_str(pot.get("name")),
            "description": resolved_desc,
            "target_type": pot.get("target_type", ""),
        })
    relics = []
    for r in p.get("relics") or []:
        raw_desc = r.get("description", "")
        relic_vars = r.get("vars") or {}
        # Merge well-known default vars for relics whose engine response
        # has empty/missing vars (e.g. Bone Tea's {Combats} template).
        relic_vars = _merge_known_relic_vars(r, relic_vars)
        resolved_desc = resolve_card_description(raw_desc, relic_vars)
        relics.append({
            "id": r.get("id", ""),
            "name": _name_str(r.get("name")),
            "description": resolved_desc,
            "counter": r.get("counter", -1),
        })
    # Orbs (Defect character): may be in player dict or top-level state
    orbs = []
    orbs_raw = p.get("orbs") or state.get("orbs") or []
    for orb in orbs_raw:
        # Engine sends "passive" and "evoke"; fall back to "passive_amount"/"evoke_amount"
        passive = orb.get("passive")
        if passive is None:
            passive = orb.get("passive_amount", 0)
        evoke = orb.get("evoke")
        if evoke is None:
            evoke = orb.get("evoke_amount", 0)
        orbs.append({
            "type": orb.get("type", "Empty"),
            "passive_amount": passive,
            "evoke_amount": evoke,
        })
    orb_slots = p.get("orb_slots") or state.get("orb_slots") or len(orbs)

    # Necrobinder companion (Osty)
    osty_raw = state.get("osty")
    osty: dict | None = None
    if osty_raw and isinstance(osty_raw, dict):
        osty = {
            "name": osty_raw.get("name", "Osty"),
            "hp": osty_raw.get("hp", 0),
            "max_hp": osty_raw.get("max_hp", 0),
            "block": osty_raw.get("block", 0),
            "alive": osty_raw.get("alive", False),
        }

    # Regent star resource
    stars: int | None = state.get("stars")

    return {
        "name": _name_str(p.get("name")),
        "hp": p.get("hp") or 0,
        "max_hp": p.get("max_hp") or 0,
        "block": p.get("block") or 0,
        "energy": state.get("energy") or 0,
        "max_energy": state.get("max_energy") or 0,
        "gold": p.get("gold") or 0,
        "powers": powers,
        "potions": potions,
        "relics": relics,
        "deck_size": p.get("deck_size") or 0,
        "orbs": orbs,
        "orb_slots": orb_slots,
        "osty": osty,
        "stars": stars,
    }


def extract_pile_counts(state: dict) -> dict:
    """Extract draw, discard, and exhaust pile counts from a combat state.

    The engine now sends ``exhaust_pile_count`` directly.  We use it when
    available and fall back to the old approximation (deck_size - draw -
    discard - hand) for older engine versions that omit it.
    """
    draw = state.get("draw_pile_count", 0)
    discard = state.get("discard_pile_count", 0)
    # Prefer real exhaust count from engine; fall back to approximation
    exhaust = state.get("exhaust_pile_count")
    if exhaust is None:
        hand_count = len(state.get("hand", []))
        deck_size = state.get("player", {}).get("deck_size", 0)
        exhaust = max(0, deck_size - draw - discard - hand_count)
    return {
        "draw": draw,
        "discard": discard,
        "exhaust": exhaust,
    }


def extract_pile_contents(state: dict) -> dict:
    """Extract draw, discard, and exhaust pile card lists from a combat state.

    The engine sends ``draw_pile``, ``discard_pile``, and ``exhaust_pile`` as
    lists of ``{id, name}`` dicts.  Returns a dict with three lists of card
    name strings.  Falls back to empty lists when fields are absent (old engine).
    """
    def _card_names(pile_key: str) -> list[str]:
        pile = state.get(pile_key)
        if not pile or not isinstance(pile, list):
            return []
        return [_name_str(c.get("name")) for c in pile if isinstance(c, dict)]

    return {
        "draw": _card_names("draw_pile"),
        "discard": _card_names("discard_pile"),
        "exhaust": _card_names("exhaust_pile"),
    }


def _detect_x_cost(cost: int, description: str) -> bool:
    """Detect X-cost cards using the **raw** (pre-resolution) description.

    The engine sends cost=0 for both 0-cost and X-cost cards.
    Real X-cost cards have a literal "X" in their raw template description
    (e.g., "X times", "X Lightning", "X+1", "{IfUpgraded:show:X+1|X}").

    Cards like Spite whose description contains ``{Repeat:diff()}`` are NOT
    X-cost -- the "X" only appears after template resolution when the stat
    is missing.  By checking the raw description we avoid this false positive.
    """
    if cost != 0:
        return False
    # Check for literal X as a word boundary in the raw description.
    # This catches "X times", "X Lightning", "X Strength", "X+1", etc.
    # but NOT template variables like "{Repeat:diff()}" which only
    # resolve to "X" after template processing.
    return bool(re.search(r'\bX\b', description))


def extract_hand(state: dict) -> list[dict]:
    """Normalise hand card data from a combat_play response."""
    result = []
    for card in state.get("hand", []):
        stats = card.get("stats", {}) or {}
        # Enrich stats from game_data: either fill in completely when empty,
        # or merge missing keys when engine stats are incomplete (e.g. Dominate
        # sends strengthpervulnerable but not vulnerablepower).
        enriched = _enrich_card_stats(card)
        if not stats:
            stats = enriched
        elif enriched:
            for k, v in enriched.items():
                if k not in stats:
                    stats[k] = v
        raw_desc = card.get("description", "")
        resolved_desc = resolve_card_description(raw_desc, stats)
        cost = card.get("cost", 0)
        # Detect X-cost cards using the RAW description (before template resolution)
        # to avoid false positives from unresolved stat variables that become "X".
        if _detect_x_cost(cost, raw_desc):
            cost = -1  # -1 is our sentinel for X-cost
        # Process after_upgrade data if present
        after_upgrade_raw = card.get("after_upgrade")
        after_upgrade = None
        if after_upgrade_raw:
            up_stats = after_upgrade_raw.get("stats") or {}
            up_desc_raw = after_upgrade_raw.get("description", "")
            up_desc = resolve_card_description(up_desc_raw, up_stats)
            up_cost = after_upgrade_raw.get("cost", cost)
            after_upgrade = {
                "cost": up_cost,
                "stats": up_stats,
                "description": up_desc,
                "added_keywords": after_upgrade_raw.get("added_keywords") or [],
                "removed_keywords": after_upgrade_raw.get("removed_keywords") or [],
            }

        result.append({
            "index": card.get("index", 0),
            "name": _name_str(card.get("name")),
            "cost": cost,
            "star_cost": card.get("star_cost"),  # Regent: some cards cost stars
            "type": card.get("type", ""),
            "can_play": card.get("can_play", False),
            "target_type": card.get("target_type", ""),
            "damage": stats.get("damage"),
            "block": stats.get("block"),
            "stats": stats,
            "description": resolved_desc,
            "keywords": card.get("keywords") or [],
            "effective_damage": card.get("effective_damage"),
            "enchantment": card.get("enchantment"),
            "enchantment_amount": card.get("enchantment_amount"),
            "affliction": card.get("affliction"),
            "affliction_amount": card.get("affliction_amount"),
            "upgraded": card.get("upgraded", False),
            "rarity": card.get("rarity", ""),
            "after_upgrade": after_upgrade,
        })
    return result


def _enrich_card_stats(card: dict) -> dict:
    """Try to fill in missing stats from game_data/cards.json.

    When the engine sends ``stats: null`` for reward or shop cards,
    this function looks up the card by name in the local card database
    and returns an expanded stats dict suitable for template resolution.
    Returns empty dict if no data is found.

    Handles basic cards like "Strike" / "Defend" which are stored in
    game_data as "Strike Ironclad", "Strike Silent", etc. by trying
    all character suffixes if the exact name is not found.
    """
    try:
        from sts2_tui.tui.screens.shop import _load_card_data, _expand_vars, _normalize_name
        name = _name_str(card.get("name"))
        card_db = _load_card_data()
        normalized = _normalize_name(name)
        data = card_db.get(normalized)
        # Fallback: try character-specific names for basic cards
        if not data and normalized in ("strike", "defend"):
            _CHAR_SUFFIXES = ["ironclad", "silent", "defect", "necrobinder", "regent"]
            for suffix in _CHAR_SUFFIXES:
                data = card_db.get(f"{normalized} {suffix}")
                if data:
                    break
        if data:
            raw_vars = data.get("vars") or {}
            if raw_vars:
                return _expand_vars(raw_vars)
    except Exception:
        pass
    return {}


def extract_reward_cards(state: dict) -> list[dict]:
    """Normalise card reward data with resolved descriptions and X-cost detection."""
    result = []
    for card in state.get("cards", []):
        stats = card.get("stats", {}) or {}
        # Enrich stats from game_data: either fill in completely when empty,
        # or merge missing keys when engine stats are incomplete (e.g. Dominate
        # sends strengthpervulnerable but not vulnerablepower).
        enriched = _enrich_card_stats(card)
        if not stats:
            stats = enriched
        elif enriched:
            for k, v in enriched.items():
                if k not in stats:
                    stats[k] = v
        raw_desc = card.get("description", "")
        resolved_desc = resolve_card_description(raw_desc, stats)
        cost = card.get("cost", 0)
        # Use raw description for X-cost detection to avoid false positives
        if _detect_x_cost(cost, raw_desc):
            cost = -1
        # Process after_upgrade data if present
        after_upgrade_raw = card.get("after_upgrade")
        after_upgrade = None
        if after_upgrade_raw:
            up_stats = after_upgrade_raw.get("stats") or {}
            up_desc_raw = after_upgrade_raw.get("description", "")
            up_desc = resolve_card_description(up_desc_raw, up_stats)
            up_cost = after_upgrade_raw.get("cost", cost)
            after_upgrade = {
                "cost": up_cost,
                "stats": up_stats,
                "description": up_desc,
                "added_keywords": after_upgrade_raw.get("added_keywords") or [],
                "removed_keywords": after_upgrade_raw.get("removed_keywords") or [],
            }

        result.append({
            "index": card.get("index", 0),
            "name": _name_str(card.get("name")),
            "cost": cost,
            "star_cost": card.get("star_cost"),  # Regent: some cards cost stars
            "type": card.get("type", ""),
            "rarity": card.get("rarity", ""),
            "stats": stats,
            "description": resolved_desc,
            "keywords": card.get("keywords") or [],
            "upgraded": card.get("upgraded", False),
            "after_upgrade": after_upgrade,
        })
    return result


def _error_dict(message: str) -> dict:
    """Build an error response dict matching the engine's error format."""
    return {"type": "error", "message": message}


# ---------------------------------------------------------------------------
# Controller
# ---------------------------------------------------------------------------


class GameController:
    """Bridges TUI events to sts2-cli via EngineBridge.

    Every public method returns the raw dict response from sts2-cli.
    BridgeErrors are caught and returned as ``{"type": "error", ...}``
    dicts so screens can display them without crashing.
    """

    def __init__(self, bridge: EngineBridge) -> None:
        self.bridge = bridge
        self.current_state: dict = {}
        self.player_deck: list[dict] = []

    def _update_deck(self, state: dict) -> None:
        """Extract and cache the player's deck from the latest state."""
        deck = state.get("player", {}).get("deck")
        if deck is not None:
            self.player_deck = deck

    async def _call(self, coro) -> dict:
        """Wrap a bridge coroutine: store state, update deck, catch errors."""
        try:
            state = await coro
            self.current_state = state
            self._update_deck(state)
            return state
        except BridgeError as e:
            return _error_dict(str(e))

    async def start_run(self, character: str, seed: str | None = None, *, lang: str = "en", god_mode: bool = False) -> dict:
        """Start a new game run. Returns the first decision state (usually Neow event)."""
        return await self._call(self.bridge.start_run(character, seed, lang=lang, god_mode=god_mode))

    async def play_card(self, card_index: int, target_index: int | None = None) -> dict:
        """Play a card from the hand by its index."""
        return await self._call(self.bridge.play_card(card_index, target_index))

    async def end_turn(self) -> dict:
        """End the player turn. Returns state after enemy actions + new draw."""
        return await self._call(self.bridge.end_turn())

    async def choose(self, index: int) -> dict:
        """Make a choice (event option, rest option, etc.)."""
        return await self._call(self.bridge.choose(index))

    async def select_map_node(self, col: int, row: int) -> dict:
        """Select a map node by column and row."""
        return await self._call(self.bridge.select_map_node(col, row))

    async def select_card_reward(self, card_index: int) -> dict:
        """Pick a card from the reward screen."""
        return await self._call(self.bridge.select_card_reward(card_index))

    async def skip_card_reward(self) -> dict:
        """Skip the card reward."""
        return await self._call(self.bridge.skip_card_reward())

    async def use_potion(self, index: int, target_index: int | None = None) -> dict:
        """Use a potion from the potion belt."""
        return await self._call(self.bridge.use_potion(index, target_index))

    async def discard_potion(self, index: int) -> dict:
        """Discard a potion from the potion belt to free the slot."""
        return await self._call(
            self.bridge.send(
                {"cmd": "action", "action": "discard_potion", "args": {"potion_index": index}}
            )
        )

    async def proceed(self) -> dict:
        """Send a generic proceed action."""
        return await self._call(self.bridge.proceed())

    async def leave_room(self) -> dict:
        """Leave the current room."""
        return await self._call(self.bridge.leave_room())

    async def select_bundle(self, index: int) -> dict:
        """Select a bundle (Neow's Scroll Boxes, etc.)."""
        return await self._call(self.bridge.select_bundle(index))

    async def select_cards(self, indices: str) -> dict:
        """Select cards by comma-separated indices."""
        return await self._call(self.bridge.select_cards(indices))

    async def skip_select(self) -> dict:
        """Skip a card selection."""
        return await self._call(self.bridge.skip_select())

    async def get_map(self) -> dict:
        """Fetch full map data from the engine."""
        try:
            return await self.bridge.get_map()
        except BridgeError as e:
            return _error_dict(str(e))

    async def get_state(self) -> dict:
        """Fetch the current state from the engine."""
        return await self._call(self.bridge.get_state())

    async def quit(self) -> None:
        """Shut down the engine process."""
        await self.bridge.quit()
