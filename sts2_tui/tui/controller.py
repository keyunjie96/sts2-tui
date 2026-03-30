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

    The CLI now resolves localization keys (power names, monster names, etc.)
    with fallback to HumanizeId, so the TUI no longer needs to strip
    ``.name``/``.title`` suffixes or convert UPPER_SNAKE_CASE.
    """
    if name_obj is None:
        return "?"
    if isinstance(name_obj, dict):
        from sts2_tui.tui.i18n import get_language
        lang = get_language()
        return name_obj.get(lang) or name_obj.get("en") or name_obj.get("zh") or str(name_obj)
    return str(name_obj)


def _resolve_inline_loc_keys(text: str) -> str:
    """Resolve literal localization keys embedded in text (e.g. ``CLUMSY.title``).

    The engine sometimes emits event descriptions with raw localization keys
    like ``Add CLUMSY.title to your Deck`` instead of ``Add Clumsy to your Deck``.
    This function detects ``UPPER_SNAKE_CASE.title`` / ``.name`` / ``.description``
    patterns and converts them to readable title-case text, stripping the suffix
    and any ``_POWER``/``_RELIC``/``_POTION`` type markers.
    """
    def _replace_key(m: re.Match[str]) -> str:
        raw = m.group(1)  # e.g. "CLUMSY", "BYRDONIS_EGG", "SHARP"
        # Strip known type suffixes
        for suffix in ("_POWER", "_RELIC", "_POTION", "_CARD"):
            if raw.endswith(suffix):
                raw = raw[: -len(suffix)]
                break
        # Convert UPPER_SNAKE_CASE to Title Case
        return " ".join(w.capitalize() for w in raw.split("_"))

    return re.sub(r"\b([A-Z][A-Z0-9_]+)\.(?:title|name|description|titleObject)\b", _replace_key, text)


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


def resolve_card_description(description: str, stats: dict[str, Any] | None,
                             *, in_combat: bool = False) -> str:
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
    - ``{InCombat:true|false}`` -> true branch when *in_combat*, false branch otherwise
    """
    if not description:
        return ""
    text = description
    # Strip BBCode tags (e.g. [b], [/b], [color=#ff0000]) but preserve
    # energy icons like [2], [3] (pure numeric content in brackets)
    text = re.sub(r"\[/?[a-zA-Z][^\]]*\]", "", text)
    # Handle {InCombat:true_branch|false_branch} blocks.
    # In combat, show the true_branch; out of combat, show the false_branch.
    def _incombat_replace(m: re.Match[str]) -> str:
        content = m.group(1)
        pipe_idx = content.rfind("|")
        if pipe_idx >= 0:
            true_branch = content[:pipe_idx]
            false_branch = content[pipe_idx + 1:]
        else:
            true_branch = content
            false_branch = ""
        return true_branch if in_combat else false_branch
    text = re.sub(r"\{InCombat:(.*?)\}", _incombat_replace, text, flags=re.DOTALL)
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
        label = _energy_label if n <= 1 else f"{n} {_energy_label}"
        # Insert space when the template immediately follows a digit (e.g. "0{...}" -> "0 Energy")
        start = m.start()
        if start > 0 and text[start - 1].isdigit():
            return " " + label
        return label
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

    # --- Post-resolution cleanup for engine partial-resolution artifacts ---
    # The engine's SmartFormat resolver sometimes partially resolves templates,
    # leaving orphan closing braces, pipe branches, and concatenated values.
    # These patterns cannot be fixed by the template resolver above because the
    # opening '{' has already been consumed by the engine.

    # Strip residual plural/cond fragments like ".times)|}" or "Exhausted.times)|}"
    text = re.sub(r"\.\w*\)\|?\}", ".", text)

    # Strip orphan "{ word}" patterns (opening brace with space, e.g. "{ cards}")
    text = re.sub(r"\{\s+\w+\}", "", text)

    # Strip orphan "|branch}" patterns: "Attacks are|Attack is}" -> "Attacks are"
    # Keep the text before the pipe, discard the pipe-branch and orphan brace.
    text = re.sub(r"\|[^|}]*\}", "", text)

    # Strip orphan " word}" where a space-delimited word ends with "}" and
    # there is no matching "{" earlier.  Only strip if no "{" exists earlier
    # on the same line (to avoid stripping legitimate template content).
    def _strip_orphan_word_brace(m: re.Match[str]) -> str:
        line_start = text.rfind("\n", 0, m.start())
        preceding = text[line_start + 1:m.start()] if line_start >= 0 else text[:m.start()]
        if "{" not in preceding:
            return " "  # replace "word}" with space
        return m.group(0)
    text = re.sub(r"(?<=\s)\w+\}", _strip_orphan_word_brace, text)

    # Strip orphan bare "}" that follow a word char with no matching "{"
    # Check that no "{" exists on the same line before this "}"
    def _strip_orphan_brace(m: re.Match[str]) -> str:
        line_start = text.rfind("\n", 0, m.start())
        preceding = text[line_start + 1:m.start()] if line_start >= 0 else text[:m.start()]
        if "{" not in preceding:
            return m.group(1)  # keep the preceding char, drop the "}"
        return m.group(0)
    text = re.sub(r"(\w)\}", _strip_orphan_brace, text)

    # Strip orphan "}" preceded by a space: "times }that" -> "times that"
    text = re.sub(r"\s+\}", " ", text)

    # Fix engine double-resolution: "N word(s) N" where the second N
    # replaced a plural template. Common patterns:
    # "draw 2 additional 2." -> "draw 2 additional."
    # "defeating 5 5." -> "defeating 5."
    # "gain 1 1 Energy" -> "gain 1 Energy"
    #
    # Two cases:
    # 1) Adjacent duplicate numbers (0 intervening words): always collapse.
    # 2) 1-2 intervening words: only collapse when the second number is
    #    followed by punctuation or end-of-string, meaning the number
    #    replaced a plural word (e.g., "2 additional 2." but NOT
    #    "1 Strength and 1 Dexterity").
    # Case 1: adjacent duplicates ("5 5.", "1 1 Energy")
    text = re.sub(r"\b(\d+) \1\b(?=[^0-9])", r"\1", text)
    # Case 2: 1-2 words between, second number before punctuation/EOL
    # The lookahead ensures the second number is followed by punctuation
    # (possibly after whitespace) or end-of-string — NOT by another word
    # like "Dexterity". This avoids false positives on legitimate repeated
    # stat values like "lose 1 Strength and 1 Dexterity".
    def _dedup_numbers(m: re.Match[str]) -> str:
        return m.group(1) + m.group(3)
    text = re.sub(
        r"(\b(\d+))(\s+(?:\w+\s+){1,2})\2\b(?=\s*[.,;:]|\s*$)",
        _dedup_numbers,
        text,
    )

    # Fix "0 N Energy" pattern where engine concatenated cost (0) with
    # energyPrefix resolution (N Energy): "costs 0 1 Energy" -> "costs 0 Energy"
    text = re.sub(r"\b0 \d+ Energy\b", "0 Energy", text)

    # Fix "0N Energy" pattern without space: "01 Energy" -> "0 Energy"
    text = re.sub(r"\b0(\d+) Energy\b", "0 Energy", text)

    # Fix concatenated "letter0digit" patterns from engine joining resolved values
    # without space: "damage01" -> "damage 1", "a\n01" -> "a\n1"
    text = re.sub(r"([a-zA-Z])0(\d)", r"\1 \2", text)
    # Also at line start: "\n01" -> "\n1"
    text = re.sub(r"(\n)0(\d)", r"\1\2", text)

    # Fix trailing "N" stray digit after "damage" from engine concat:
    # "Deal 13 damage0." -> "Deal 13 damage."
    text = re.sub(r"(damage)\d+([.\s])", r"\1\2", text)

    # Fix missing space in engine localization templates (e.g. "damagefor" -> "damage for")
    text = re.sub(r"damage(for)", r"damage \1", text)

    # Strip stray "for the next -1 turns" patterns (negative turn counts are invalid)
    text = re.sub(r"(?:for )?(?:the next )?-\d+ turns?\.?", "", text)

    # Collapse excess whitespace, multiple spaces, and blank lines
    text = re.sub(r"  +", " ", text)
    text = re.sub(r"\n\s*\n", "\n", text)
    # Fix space before punctuation left by template removal
    text = re.sub(r"\s+([.,;:])", r"\1", text)
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


# Known power template variables from game_data/powers.json.
# Maps lowercase power name -> dict of template vars.
# Used when the engine partially resolves power descriptions but leaves
# template vars like {DamageDecrease} or {DamageIncrease} unresolved.
_KNOWN_POWER_VARS: dict[str, dict[str, Any]] = {
    "flutter": {"damagedecrease": 50},
    "shrink": {"damagedecrease": 30},
    "vulnerable": {"damageincrease": 50},
    "weak": {"damagedecrease": 25},
}


def _power_resolve_stats(power_name: str, amount: int) -> dict[str, Any]:
    """Build the stats dict for resolving a power description template.

    Includes the power's amount plus any known extra vars from game_data.
    """
    stats: dict[str, Any] = {"amount": amount}
    known = _KNOWN_POWER_VARS.get(power_name.lower(), {})
    stats.update(known)
    return stats


def _resolve_applier_name(text: str, *, owner: str, applier: str,
                          use_false_branch: bool = False) -> str:
    """Resolve {ApplierName.StringValue:cond:trueText|falseText} patterns.

    These patterns reference the creature that applied a power. The true
    branch typically says "While {applier} is alive, your..." and the
    false branch says "{OwnerName}'s...".

    Because the false branch contains nested ``{OwnerName}``, a simple
    regex cannot match the balanced outer braces.  This function finds
    the pattern manually with brace counting.

    Args:
        text: The description text to process.
        owner: Name to substitute for {OwnerName} inside the result.
        applier: Name to substitute for {} self-references in the true branch.
        use_false_branch: If True, use the false branch (for enemy context).
    """
    marker = "{ApplierName."
    idx = text.find(marker)
    if idx < 0:
        return text

    # Find balanced closing brace
    depth = 0
    end = -1
    for i in range(idx, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return text  # unbalanced -- leave as-is

    block = text[idx + 1:end]  # everything inside the outer { }
    # Find the pipe separating true|false branches
    # Skip nested braces when looking for the pipe
    pipe_depth = 0
    pipe_idx = -1
    cond_start = block.find(":cond:")
    if cond_start < 0:
        return text
    search_start = cond_start + len(":cond:")
    for i in range(search_start, len(block)):
        if block[i] == "{":
            pipe_depth += 1
        elif block[i] == "}":
            pipe_depth -= 1
        elif block[i] == "|" and pipe_depth == 0:
            pipe_idx = i
            break
    if pipe_idx < 0:
        return text

    true_branch = block[search_start:pipe_idx]
    false_branch = block[pipe_idx + 1:]

    if use_false_branch:
        result = false_branch
        # Substitute {OwnerName} in the false branch (may already be resolved)
        result = result.replace("{OwnerName}", owner)
    else:
        result = true_branch
        # Substitute {} self-references with the applier name
        result = result.replace("{}", applier)

    return text[:idx] + result + text[end + 1:]


def extract_enemies(state: dict) -> list[dict]:
    """Normalise enemy data from a combat_play response."""
    result = []
    for e in state.get("enemies", []):
        enemy_name = _name_str(e.get("name"))
        powers = []
        for pw in e.get("powers") or []:
            # CLI resolves most power descriptions, but some still contain
            # unresolved templates (e.g. {energyPrefix:energyIcons(1)},
            # {DamageDecrease}, {OwnerName}).
            # Run through resolve_card_description as a fallback.
            pw_name = _name_str(pw.get("name", ""))
            pw_amount = pw.get("amount", 0)
            raw_desc = pw.get("description", "")
            # Substitute {OwnerName} with the enemy's name before template resolution
            raw_desc = re.sub(r"\{OwnerName\}", enemy_name, raw_desc)
            # Substitute {ApplierName.StringValue:cond:trueText|falseText} pattern.
            # For enemy powers: use the false branch which has {OwnerName}'s
            # (already substituted with enemy name above).
            raw_desc = _resolve_applier_name(raw_desc, owner=enemy_name, applier="enemy", use_false_branch=True)
            stats = _power_resolve_stats(pw_name, pw_amount)
            resolved_desc = resolve_card_description(raw_desc, stats)
            # Fix Vulnerable missing percentage from engine partial resolution
            if pw_name == "Vulnerable" and "Receive % more" in resolved_desc:
                resolved_desc = resolved_desc.replace("Receive % more", "Receive 50% more")
            powers.append({
                "name": pw_name,
                "amount": pw_amount,
                "description": resolved_desc,
                "type": pw.get("type"),
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
        is_card_debuff = False
        is_escape = False
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
            elif itype == "CardDebuff":
                is_card_debuff = True
                intent_parts.append("Card Debuff")
            elif itype == "Sleep":
                is_sleep = True
                intent_parts.append("\U0001f4a4 Zzz")
            elif itype == "Escape":
                is_escape = True
                intent_parts.append("\U0001f3c3 Escape")
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
            "is_card_debuff": is_card_debuff,
            "is_escape": is_escape,
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
        # CLI resolves most power descriptions, but some still contain
        # unresolved templates (e.g. {energyPrefix:energyIcons(1)},
        # {DamageDecrease}, {ApplierName...}).
        # Run through resolve_card_description as a fallback.
        resolved_name = _name_str(pw.get("name", ""))
        pw_amount = pw.get("amount", 0)
        raw_desc = pw.get("description", "")
        # Substitute {ApplierName.StringValue:cond:trueText|falseText} pattern.
        # For player powers: use the true branch (applier-alive context).
        # The false branch may contain nested {OwnerName} so we use a function
        # to find the balanced closing brace.
        raw_desc = _resolve_applier_name(raw_desc, owner="you", applier="the enemy")
        # Substitute remaining {OwnerName} with "your"/"you" for player context
        raw_desc = re.sub(r"\{OwnerName\}'s", "your", raw_desc)
        raw_desc = re.sub(r"\{OwnerName\}", "you", raw_desc)
        stats = _power_resolve_stats(resolved_name, pw_amount)
        resolved_desc = resolve_card_description(raw_desc, stats)
        # Clarify Doom description context when on the player
        if resolved_name == "Doom" and "it dies" in resolved_desc:
            resolved_desc = resolved_desc.replace("it dies", "you die")
            resolved_desc = resolved_desc.replace("it has", "you have")
        # Clarify Shrink description context when on the player
        if resolved_name == "Shrink" and "This creature's Attacks" in resolved_desc:
            resolved_desc = resolved_desc.replace("This creature's Attacks", "Your Attacks")
        # Fix Vulnerable missing percentage from engine partial resolution
        if resolved_name == "Vulnerable" and "Receive % more" in resolved_desc:
            resolved_desc = resolved_desc.replace("Receive % more", "Receive 50% more")
        powers.append({
            "name": resolved_name,
            "amount": pw_amount,
            "description": resolved_desc,
            "type": pw.get("type"),
        })
    potions = []
    for pot in p.get("potions") or []:
        raw_desc = pot.get("description", "")
        pot_vars = pot.get("vars") or {}
        if pot_vars:
            resolved_desc = resolve_card_description(raw_desc, pot_vars)
        else:
            # When engine sends vars=None, use shop enrichment path which
            # looks up game_data and known extra vars for template resolution.
            from sts2_tui.tui.screens.shop import _enrich_potion_description
            resolved_desc = _enrich_potion_description(pot)
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
        # Hand cards are always in combat context
        resolved_desc = resolve_card_description(raw_desc, stats, in_combat=True)
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
            up_desc = resolve_card_description(up_desc_raw, up_stats, in_combat=True)
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
            "damage": stats.get("damage") if stats.get("damage") is not None else (stats.get("ostydamage") if stats.get("ostydamage") is not None else stats.get("calculateddamage")),
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
