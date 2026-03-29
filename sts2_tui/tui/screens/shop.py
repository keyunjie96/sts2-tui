"""Shop screen -- buy cards, relics, potions, or remove a card.

Driven by raw dict state from sts2-cli (decision == "shop").
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static
from textual.reactive import reactive
from rich.text import Text

from sts2_tui.tui.controller import GameController, _name_str
from sts2_tui.tui.i18n import L
from sts2_tui.tui.shared import CARD_TYPE_COLORS, RARITY_COLORS, build_status_footer, build_upgrade_preview, hp_color

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Card data lookup -- fills in stats and rarity the engine omits for shop cards
# ---------------------------------------------------------------------------

_CARD_DATA_BY_NAME: dict[str, dict] | None = None
_RELIC_DATA_BY_NAME: dict[str, dict] | None = None
_POTION_DATA_BY_NAME: dict[str, dict] | None = None

# ---------------------------------------------------------------------------
# Chinese-name -> ID reverse lookup (loaded from sts2-cli localization files)
# ---------------------------------------------------------------------------

_ZH_CARD_NAME_TO_ID: dict[str, str] | None = None
_ZH_RELIC_NAME_TO_ID: dict[str, str] | None = None
_ZH_POTION_NAME_TO_ID: dict[str, str] | None = None


def _find_sts2_cli_dir() -> Path | None:
    """Locate sts2-cli project root for localization files."""
    import os
    env = os.environ.get("STS2_CLI_PATH")
    if env:
        p = Path(env)
        if p.is_dir():
            return p
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent.parent / "sts2-cli",
        Path.home() / "Documents" / "Projects" / "sts2-cli",
        Path("/tmp/sts2-cli"),
    ]
    for c in candidates:
        if c.is_dir():
            return c
    return None


def _load_zh_name_map(kind: str) -> dict[str, str]:
    """Load a Chinese-name -> id mapping from sts2-cli localization_zhs/{kind}.json.

    The localization files have entries like ``"SPITE.title": "怨恨"`` which
    lets us map Chinese display names back to the English id used in game_data.
    """
    sts2_dir = _find_sts2_cli_dir()
    if not sts2_dir:
        return {}
    loc_file = sts2_dir / "localization_zhs" / f"{kind}.json"
    if not loc_file.is_file():
        return {}
    try:
        with open(loc_file, encoding="utf-8") as f:
            data = json.load(f)
        mapping: dict[str, str] = {}
        for key, val in data.items():
            if key.endswith(".title") and isinstance(val, str):
                item_id = key[:-6].lower()  # "SPITE.title" -> "spite"
                mapping[val] = item_id
        log.debug("Loaded %d zh->id mappings for %s", len(mapping), kind)
        return mapping
    except Exception:
        log.warning("Failed to load zh localization for %s", kind, exc_info=True)
        return {}


def _zh_card_to_id(zh_name: str) -> str:
    """Map a Chinese card name to the game_data id."""
    global _ZH_CARD_NAME_TO_ID
    if _ZH_CARD_NAME_TO_ID is None:
        _ZH_CARD_NAME_TO_ID = _load_zh_name_map("cards")
    return _ZH_CARD_NAME_TO_ID.get(zh_name, "")


def _zh_relic_to_id(zh_name: str) -> str:
    """Map a Chinese relic name to the game_data id."""
    global _ZH_RELIC_NAME_TO_ID
    if _ZH_RELIC_NAME_TO_ID is None:
        _ZH_RELIC_NAME_TO_ID = _load_zh_name_map("relics")
    return _ZH_RELIC_NAME_TO_ID.get(zh_name, "")


def _zh_potion_to_id(zh_name: str) -> str:
    """Map a Chinese potion name to the game_data id."""
    global _ZH_POTION_NAME_TO_ID
    if _ZH_POTION_NAME_TO_ID is None:
        _ZH_POTION_NAME_TO_ID = _load_zh_name_map("potions")
    return _ZH_POTION_NAME_TO_ID.get(zh_name, "")


def _normalize_name(name: str) -> str:
    """Normalize item names for case-insensitive, punctuation-insensitive lookup.

    The engine may send names with apostrophes (e.g. "Mazaleth's Gift")
    while game_data stores them without (e.g. "Mazaleths Gift").
    This strips apostrophes and lowercases so both forms match.
    """
    return name.lower().replace("'", "").replace("\u2019", "")


def _load_relic_data() -> dict[str, dict]:
    """Load game_data/relics.json once and build a name->data lookup."""
    global _RELIC_DATA_BY_NAME
    if _RELIC_DATA_BY_NAME is not None:
        return _RELIC_DATA_BY_NAME

    _RELIC_DATA_BY_NAME = {}
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent.parent / "game_data" / "relics.json",
        Path.cwd() / "game_data" / "relics.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                with open(path) as f:
                    relics = json.load(f)
                for relic in relics:
                    name = relic.get("name", "")
                    if isinstance(name, dict):
                        name = name.get("en", "")
                    if name:
                        _RELIC_DATA_BY_NAME[_normalize_name(name)] = relic
                    relic_id = relic.get("id", "")
                    if relic_id:
                        _RELIC_DATA_BY_NAME[_normalize_name(relic_id)] = relic
                log.debug("Loaded %d relics from %s", len(_RELIC_DATA_BY_NAME), path)
            except Exception:
                log.warning("Failed to load relic data from %s", path, exc_info=True)
            break

    return _RELIC_DATA_BY_NAME


# Well-known relic vars not in game_data (engine defaults).
# These are stable STS2 values for relics whose game_data lacks vars.
_KNOWN_RELIC_VARS: dict[str, dict[str, int]] = {
    "lantern": {"energy": 1},
    "lucky fysh": {"gold": 10},
    "lee's waffle": {"maxhp": 7},
    "pen nib": {"damage": 2},
    "bag of marbles": {"vulnerablepower": 1, "vulnerable": 1},
    "data disk": {"focuspower": 1, "focus": 1},
    "vajra": {"strength": 1, "strengthpower": 1},
    "bag of preparation": {"cards": 2},
    # Relics whose game_data has vars=null but engine templates need values
    "pear": {"maxhp": 10},
    "dragon fruit": {"maxhp": 7},
    "bowler hat": {"goldincrease": 25},
    "bread": {"gainenergy": 1, "loseenergy": 1},
    "anchor": {"block": 10},
    "odd mushroom": {"strengthpower": 1, "strength": 1},
    "horn cleat": {"block": 14},
    "black star": {"relics": 1},
    "ceramic fish": {"gold": 9},
    "dream catcher": {"cards": 1},
    "frozen eye": {"cards": 0},
    "juzu bracelet": {"maxhp": 5},
    "question card": {"cards": 1},
    "red skull": {"strengthpower": 3, "strength": 3},
    "runic dome": {"energy": 1},
    "thread and needle": {"platedarmor": 4, "plated_armor": 4},
    "tiny house": {"maxhp": 6, "gold": 50, "cards": 1},
    "amethyst aubergine": {"gold": 25},
    "candelabra": {"energy": 1},
    # Entity-reference relics: use 0 so the entity fallback in
    # resolve_card_description shows the readable name.
    "royal stamp": {"cards": 1, "enchantment": 0},
    # Relics with {Repeat} template vars not in game_data
    "runic capacitor": {"repeat": 2},
    "wongos mystery ticket": {"repeat": 2, "remaining": 1},
    "strawberry": {"maxhp": 7},
    "galactic dust": {"stars": 3, "block": 10},
    # Tea Master event relics — {Combats} is a countdown DynamicVar.
    # game_data has no vars entry; the engine sets it at runtime (typically 3).
    "bone tea": {"combats": 3},
    "ember tea": {"combats": 3, "strengthpower": 2, "strength": 2},
    "red vine tea": {"combats": 3, "cards": 1},
}

# Well-known card vars not in game_data (engine runtime defaults).
# The engine's {Repeat} template variable is a runtime computation that
# isn't stored in game_data.  These provide the base (non-upgraded) values.
_KNOWN_CARD_EXTRA_VARS: dict[str, dict[str, int]] = {
    "spite": {"repeat": 1},
    "bouncing flask": {"repeat": 3},
    "capacitor": {"repeat": 2},
    "celestial might": {"repeat": 2},
    "chaos": {"repeat": 1},
    "consuming shadow": {"repeat": 2},
    "deaths door": {"repeat": 1},
    "decisions decisions": {"repeat": 1},
    "exterminate": {"repeat": 2},
    "gunk up": {"repeat": 1},
    "ice lance": {"repeat": 1},
    "modded": {"repeat": 1},
    "outbreak": {"repeat": 1},
    "peck": {"repeat": 3},
    "quadcast": {"repeat": 4},
    "refract": {"repeat": 1},
    "ricochet": {"repeat": 3},
    "seven stars": {"repeat": 7},
    "sovereign blade": {"repeat": 1},
    "sword boomerang": {"repeat": 3},
    # Necrobinder Summon cards -- {Summon} is Osty's summoned HP (base 6)
    "afterlife": {"summon": 6},
    "bodyguard": {"summon": 6},
    "cleanse": {"summon": 6},
    "dirge": {"summon": 6},
    "invoke": {"summon": 6},
    "legion of bone": {"summon": 6},
    "necro mastery": {"summon": 6},
    "pull aggro": {"summon": 6},
    "reanimate": {"summon": 6},
    "spur": {"summon": 6},
}

# Well-known potion vars not in game_data.
_KNOWN_POTION_EXTRA_VARS: dict[str, dict[str, int]] = {
    "beetle juice": {"repeat": 2, "damagedecrease": 25},
    "bone brew": {"summon": 6},
    "clarity extract": {"cards": 1, "clarity": 3},
    "distilled chaos": {"repeat": 3},
    "potion of capacity": {"repeat": 2},
    "stable serum": {"repeat": 1},
}


def _enrich_relic_description(relic: dict) -> str:
    """Resolve template variables in a shop relic description using game data.

    Returns the cleaned description with actual numbers.
    Tries multiple sources: game_data vars, engine-sent vars, well-known defaults.
    """
    desc = relic.get("description", "")
    if not desc:
        return ""
    name = _name_str(relic.get("name"))
    # Try id-based lookup first (language-independent)
    relic_id = relic.get("id", "")
    data = None
    if relic_id:
        data = _load_relic_data().get(_normalize_name(relic_id))
    if not data:
        data = _load_relic_data().get(_normalize_name(name))
    if not data:
        # Chinese mode: reverse lookup zh name -> id
        zh_id = _zh_relic_to_id(name)
        if zh_id:
            data = _load_relic_data().get(_normalize_name(zh_id))
            if not relic_id:
                relic_id = zh_id  # Use for _KNOWN_RELIC_VARS lookup below
    raw_vars: dict = {}
    if data:
        raw_vars = dict(data.get("vars") or {})
    # Merge engine-sent vars (some shop relics include vars inline)
    engine_vars = relic.get("vars") or {}
    for k, v in engine_vars.items():
        if k not in raw_vars:
            raw_vars[k] = v
    # Merge well-known defaults for vars not already covered.
    # Try relic_id (underscores -> spaces) first, then the display name.
    # In Chinese mode the display name is Chinese, so the id-based form
    # is essential for finding the English lookup key.
    known: dict = {}
    if relic_id:
        known = _KNOWN_RELIC_VARS.get(relic_id.lower().replace("_", " "), {})
    if not known:
        known = _KNOWN_RELIC_VARS.get(_normalize_name(name), {})
    if not known and data:
        # If game_data record has an English name, try that too
        en_name = data.get("name", "")
        if isinstance(en_name, dict):
            en_name = en_name.get("en", "")
        if en_name:
            known = _KNOWN_RELIC_VARS.get(_normalize_name(en_name), {})
    for k, v in known.items():
        if k not in raw_vars:
            raw_vars[k] = v
    stats = _expand_vars(raw_vars) if raw_vars else None
    return _clean_description(desc, stats)


def _load_potion_data() -> dict[str, dict]:
    """Load game_data/potions.json once and build a name->data lookup."""
    global _POTION_DATA_BY_NAME
    if _POTION_DATA_BY_NAME is not None:
        return _POTION_DATA_BY_NAME

    _POTION_DATA_BY_NAME = {}
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent.parent / "game_data" / "potions.json",
        Path.cwd() / "game_data" / "potions.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                with open(path) as f:
                    potions = json.load(f)
                for potion in potions:
                    name = potion.get("name", "")
                    if isinstance(name, dict):
                        name = name.get("en", "")
                    if name:
                        _POTION_DATA_BY_NAME[_normalize_name(name)] = potion
                    potion_id = potion.get("id", "")
                    if potion_id:
                        _POTION_DATA_BY_NAME[_normalize_name(potion_id)] = potion
                log.debug("Loaded %d potions from %s", len(_POTION_DATA_BY_NAME), path)
            except Exception:
                log.warning("Failed to load potion data from %s", path, exc_info=True)
            break

    return _POTION_DATA_BY_NAME


def _enrich_potion_description(potion: dict) -> str:
    """Resolve template variables in a shop potion description using game data."""
    desc = potion.get("description", "")
    if not desc:
        return ""
    name = _name_str(potion.get("name"))
    # Try id-based lookup first (language-independent)
    potion_id = potion.get("id", "")
    data = None
    if potion_id:
        data = _load_potion_data().get(_normalize_name(potion_id))
    if not data:
        data = _load_potion_data().get(_normalize_name(name))
    if not data:
        # Chinese mode: reverse lookup zh name -> id
        zh_id = _zh_potion_to_id(name)
        if zh_id:
            data = _load_potion_data().get(_normalize_name(zh_id))
    raw_vars: dict = {}
    if data:
        raw_vars = dict(data.get("vars") or {})
    # Merge well-known extra vars (e.g. Repeat) not in game_data.
    en_name = data.get("name", "") if data else ""
    data_id = data.get("id", "") if data else ""
    # Also try the zh reverse-lookup id if we resolved one
    if not data_id and not potion_id:
        data_id = _zh_potion_to_id(name)
    extra: dict = {}
    lookup_id = data_id or potion_id
    if lookup_id:
        extra = _KNOWN_POTION_EXTRA_VARS.get(lookup_id.lower().replace("_", " "), {})
    if not extra and en_name:
        extra = _KNOWN_POTION_EXTRA_VARS.get(_normalize_name(en_name), {})
    # Fallback: try the display name directly (handles cases where game_data
    # uses a different name than the engine, e.g. "Clarity" vs "Clarity Extract").
    if not extra and name:
        extra = _KNOWN_POTION_EXTRA_VARS.get(_normalize_name(name), {})
    for k, v in extra.items():
        if k not in raw_vars:
            raw_vars[k] = v
    stats: dict[str, int | float] | None = None
    if raw_vars:
        stats = _expand_vars(raw_vars)
    return _clean_description(desc, stats)


def _load_card_data() -> dict[str, dict]:
    """Load game_data/cards.json once and build a name->data lookup.

    The lookup is case-insensitive because the engine sometimes sends
    slightly different casing than the game data (e.g. "Expect a Fight"
    vs "Expect A Fight").
    """
    global _CARD_DATA_BY_NAME
    if _CARD_DATA_BY_NAME is not None:
        return _CARD_DATA_BY_NAME

    _CARD_DATA_BY_NAME = {}
    # Search for cards.json relative to the project root
    candidates = [
        Path(__file__).resolve().parent.parent.parent.parent.parent / "game_data" / "cards.json",
        Path.cwd() / "game_data" / "cards.json",
    ]
    for path in candidates:
        if path.is_file():
            try:
                with open(path) as f:
                    cards = json.load(f)
                for card in cards:
                    name = card.get("name", "")
                    if isinstance(name, dict):
                        name = name.get("en", "")
                    if name:
                        # Store under normalized key for punctuation-insensitive lookup
                        _CARD_DATA_BY_NAME[_normalize_name(name)] = card
                    # Also index by id for language-independent lookup
                    card_id = card.get("id", "")
                    if card_id:
                        _CARD_DATA_BY_NAME[_normalize_name(card_id)] = card
                log.debug("Loaded %d cards from %s", len(_CARD_DATA_BY_NAME), path)
            except Exception:
                log.warning("Failed to load card data from %s", path, exc_info=True)
            break

    return _CARD_DATA_BY_NAME


def _expand_vars(raw_vars: dict[str, int | float]) -> dict[str, int | float]:
    """Expand game-data vars into all key forms the engine templates might use.

    Game data uses snake_case (``phantom_blades``, ``potion_slots``) while
    engine templates use PascalCase without underscores (``PhantomBladesPower``,
    ``PotionSlots``).  The ``resolve_card_description`` function does
    case-insensitive lookup, so we just need to generate the right key
    *shapes*: original, without underscores, with ``power`` suffix, and
    the combination of both.
    """
    expanded: dict[str, int | float] = {}
    for k, v in raw_vars.items():
        lower = k.lower()
        no_underscore = lower.replace("_", "")
        expanded[lower] = v
        expanded[no_underscore] = v
        if not lower.endswith("power"):
            expanded[lower + "power"] = v
            expanded[no_underscore + "power"] = v
    return expanded


def _enrich_shop_card(card: dict) -> tuple[dict | None, str]:
    """Look up a shop card's base stats and rarity from game data.

    Returns (stats_dict_or_None, rarity_string).

    The engine's description templates use keys like ``PlatingPower``,
    ``VulnerablePower`` (case-insensitive) while ``game_data/cards.json``
    stores the shorter forms ``plating``, ``vulnerable``.  We generate
    all plausible forms so ``resolve_card_description`` can match.
    """
    name = _name_str(card.get("name"))
    # Try id-based lookup first (language-independent), then name,
    # then Chinese reverse lookup if the name is non-ASCII (Chinese mode).
    card_id = card.get("id", "")
    data = None
    if card_id:
        # Engine sends ids like "CARD.STRIKE_IRONCLAD" — normalize to "strike_ironclad"
        clean_id = card_id.replace("CARD.", "").lower()
        data = _load_card_data().get(_normalize_name(clean_id))
    if not data:
        data = _load_card_data().get(_normalize_name(name))
    if not data:
        # Chinese mode: engine sends Chinese name with no id.
        # Use localization reverse lookup to find the game_data id.
        zh_id = _zh_card_to_id(name)
        if zh_id:
            data = _load_card_data().get(_normalize_name(zh_id))
    if not data:
        return None, ""
    raw_vars = dict(data.get("vars") or {})
    rarity_raw = data.get("rarity", "")
    rarity = rarity_raw.title() if rarity_raw else ""
    # Merge well-known extra vars (e.g. Repeat) not in game_data.
    # Lookup by id (underscores -> spaces), then by English name from game_data.
    en_name = data.get("name", "")
    data_id = data.get("id", "")
    extra: dict = {}
    if data_id:
        extra = _KNOWN_CARD_EXTRA_VARS.get(data_id.lower().replace("_", " "), {})
    if not extra and en_name:
        extra = _KNOWN_CARD_EXTRA_VARS.get(_normalize_name(en_name), {})
    for k, v in extra.items():
        if k not in raw_vars:
            raw_vars[k] = v
    if not raw_vars:
        return None, rarity
    return _expand_vars(raw_vars), rarity


# ---------------------------------------------------------------------------
# Message posted when the shop screen is done
# ---------------------------------------------------------------------------


class ShopDoneMessage(Message):
    """Posted when the shop screen is dismissed."""

    def __init__(self, next_state: dict) -> None:
        super().__init__()
        self.next_state = next_state


# ---------------------------------------------------------------------------
# Type colors
# ---------------------------------------------------------------------------

_CARD_TYPE_COLORS = CARD_TYPE_COLORS


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _clean_description(desc: str, stats: dict | None = None) -> str:
    """Clean a description for shop display.

    If stats are available, resolve templates using them (same as combat).
    Otherwise, strip template variables to show readable names.
    """
    if not desc:
        return ""
    # First try resolving with stats (uses the same logic as combat cards)
    from sts2_tui.tui.controller import resolve_card_description
    cleaned = resolve_card_description(desc, stats)
    # Map known variable names to readable display values
    # All unresolved vars become "X" — the actual number isn't available
    # without stats, and using the var name creates duplication like
    # "Gain Strength Strength"

    # Any remaining {Var:formatter()} patterns -> "X"
    cleaned = re.sub(r"\{(\w+):[^}]+\}", "X", cleaned)
    # Any remaining {Var} simple patterns -> "X"
    cleaned = re.sub(r"\{(\w+)\}", "X", cleaned)
    # Remove leftover brackets from resolved vars (e.g., "[2]" energy becomes "2")
    cleaned = re.sub(r"\[(\d+)\]", r"\1", cleaned)
    # Replace newlines with spaces for single-line display
    cleaned = cleaned.replace("\n", " ")
    # Collapse whitespace
    cleaned = re.sub(r"  +", " ", cleaned)
    return cleaned.strip()


# ---------------------------------------------------------------------------
# Shop item -- a unified representation for all purchasable things
# ---------------------------------------------------------------------------


_RARITY_COLORS = RARITY_COLORS


class _ShopItem:
    """A normalized shop item (card, relic, potion, or card removal)."""

    __slots__ = (
        "kind",          # "card", "relic", "potion", "remove"
        "index",         # engine index for the buy command
        "name",
        "description",
        "cost",          # price in gold
        "card_type",     # only for cards: "Attack", "Skill", "Power", etc.
        "card_cost",     # only for cards: energy cost
        "card_rarity",   # only for cards: "Common", "Uncommon", "Rare"
        "on_sale",       # only for cards: discount flag
        "is_stocked",    # whether the item is still available
        "after_upgrade", # only for cards: upgrade preview data
        "keywords",      # only for cards: keyword tags (Exhaust, Ethereal, etc.)
        "card_stats",    # only for cards: resolved stats dict for upgrade preview
    )

    def __init__(
        self,
        kind: str,
        index: int,
        name: str,
        description: str,
        cost: int,
        *,
        card_type: str = "",
        card_cost: int | str = "",
        card_rarity: str = "",
        on_sale: bool = False,
        is_stocked: bool = True,
        after_upgrade: dict | None = None,
        keywords: list | None = None,
        card_stats: dict | None = None,
    ) -> None:
        self.kind = kind
        self.index = index
        self.name = name
        self.description = description
        self.cost = cost
        self.card_type = card_type
        self.card_cost = card_cost
        self.card_rarity = card_rarity
        self.on_sale = on_sale
        self.is_stocked = is_stocked
        self.after_upgrade = after_upgrade
        self.keywords = keywords or []
        self.card_stats = card_stats or {}


def _build_shop_items(state: dict) -> list[_ShopItem]:
    """Parse the shop state into a flat list of purchasable items."""
    items: list[_ShopItem] = []

    # Cards
    for card in state.get("cards", []):
        if not card.get("is_stocked", False):
            continue
        # The engine often sends stats=None for shop cards.  Look up
        # base stats and rarity from our game_data card database so the
        # player sees actual numbers (e.g. "Deal 9 damage") instead of "X".
        engine_stats = card.get("stats")
        engine_rarity = card.get("rarity") or ""
        if engine_stats is None or not engine_rarity:
            lookup_stats, lookup_rarity = _enrich_shop_card(card)
            if engine_stats is None and lookup_stats:
                engine_stats = lookup_stats
            if not engine_rarity and lookup_rarity:
                engine_rarity = lookup_rarity
        # Also try engine-sent vars on the card itself (some shop cards include vars)
        if engine_stats is None:
            card_vars = card.get("vars")
            if card_vars:
                engine_stats = _expand_vars(card_vars)
        # If some template vars are still unresolved after game_data lookup,
        # try the engine's after_upgrade.stats as a fallback.  The upgraded
        # values are slightly higher than base, but approximate numbers are
        # better than "X" for decision-making.
        after_upgrade = card.get("after_upgrade")
        if after_upgrade:
            up_stats = after_upgrade.get("stats") or {}
            if up_stats:
                expanded_up = _expand_vars(up_stats)
                if engine_stats is None:
                    engine_stats = expanded_up
                else:
                    for k, v in expanded_up.items():
                        if k not in engine_stats:
                            engine_stats[k] = v
        # Build after_upgrade preview data if available
        shop_after_upgrade = None
        if after_upgrade:
            up_stats = after_upgrade.get("stats") or {}
            up_desc_raw = after_upgrade.get("description", "")
            up_cost = after_upgrade.get("cost", card.get("card_cost", "?"))
            shop_after_upgrade = {
                "cost": up_cost,
                "stats": _expand_vars(up_stats) if up_stats else {},
                "description": up_desc_raw,
                "added_keywords": after_upgrade.get("added_keywords") or [],
                "removed_keywords": after_upgrade.get("removed_keywords") or [],
            }
        items.append(_ShopItem(
            kind="card",
            index=card.get("index", 0),
            name=_name_str(card.get("name")),
            description=_clean_description(card.get("description", ""), engine_stats),
            cost=card.get("cost", 0),
            card_type=card.get("type", ""),
            card_cost=card.get("card_cost", "?"),
            card_rarity=engine_rarity,
            on_sale=card.get("on_sale", False),
            is_stocked=True,
            after_upgrade=shop_after_upgrade,
            keywords=card.get("keywords") or [],
            card_stats=engine_stats or {},
        ))

    # Relics
    for relic in state.get("relics", []):
        if not relic.get("is_stocked", False):
            continue
        items.append(_ShopItem(
            kind="relic",
            index=relic.get("index", 0),
            name=_name_str(relic.get("name")),
            description=_enrich_relic_description(relic),
            cost=relic.get("cost", 0),
        ))

    # Potions
    for potion in state.get("potions", []):
        if not potion.get("is_stocked", False):
            continue
        items.append(_ShopItem(
            kind="potion",
            index=potion.get("index", 0),
            name=_name_str(potion.get("name")),
            description=_enrich_potion_description(potion),
            cost=potion.get("cost", 0),
        ))

    # Card removal
    removal_cost = state.get("card_removal_cost")
    removal_available = state.get("card_removal_available", True)
    if removal_cost is not None and removal_available:
        items.append(_ShopItem(
            kind="remove",
            index=-1,
            name=L("remove_card"),
            description=L("remove_card_desc"),
            cost=removal_cost,
        ))

    return items


# ---------------------------------------------------------------------------
# ShopScreen
# ---------------------------------------------------------------------------


class ShopScreen(Screen):
    """Shop screen -- browse and buy cards, relics, potions, or remove a card."""

    BINDINGS = [
        Binding("1", "select_item(0)", "Item 1", show=False),
        Binding("2", "select_item(1)", "Item 2", show=False),
        Binding("3", "select_item(2)", "Item 3", show=False),
        Binding("4", "select_item(3)", "Item 4", show=False),
        Binding("5", "select_item(4)", "Item 5", show=False),
        Binding("6", "select_item(5)", "Item 6", show=False),
        Binding("7", "select_item(6)", "Item 7", show=False),
        Binding("8", "select_item(7)", "Item 8", show=False),
        Binding("9", "select_item(8)", "Item 9", show=False),
        Binding("0", "select_item(9)", "Item 10", show=False),
        Binding("a", "select_item(10)", "Item 11", show=False),
        Binding("b", "select_item(11)", "Item 12", show=False),
        Binding("c", "select_item(12)", "Item 13", show=False),
        Binding("g", "select_item(13)", "Item 14", show=False),
        Binding("h", "select_item(14)", "Item 15", show=False),
        Binding("f", "select_item(15)", "Item 16", show=False),
        Binding("enter", "buy", "Buy"),
        Binding("l", "leave", "Leave Shop"),
        Binding("escape", "leave", "Leave Shop"),
    ]

    selected: reactive[int] = reactive(-1, init=False)

    def __init__(self, state: dict, *, controller: GameController) -> None:
        super().__init__()
        self.state = state
        self.controller = controller
        self.items: list[_ShopItem] = _build_shop_items(state)
        self._gold: int = state.get("player", {}).get("gold") or 0
        self._is_composed = False
        self._busy = False
        self._refreshing = False

    # ------------------------------------------------------------------
    # Key label helpers -- items can go past 9, so we use 1-9, 0, a-f
    # ------------------------------------------------------------------

    # Keys for indices 10..15: a, b, c, g, h, f
    # (d and e are avoided -- they conflict with deck viewer / end turn)
    _EXTENDED_KEYS = {10: "a", 11: "b", 12: "c", 13: "g", 14: "h", 15: "f"}

    @staticmethod
    def _key_label(index: int) -> str:
        """Return the key label for a given flat index."""
        if index < 9:
            return str(index + 1)
        if index == 9:
            return "0"
        return ShopScreen._EXTENDED_KEYS.get(index, "?")

    # ------------------------------------------------------------------
    # Compose
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Vertical(id="shop-screen"):
            yield Static(self._title_text(), id="shop-title")
            with VerticalScroll(id="shop-viewport"):
                yield Static(self._shop_body(), id="shop-body")
            yield Static(self._footer_text(), id="shop-footer")

    def on_mount(self) -> None:
        self._is_composed = True

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------

    def _title_text(self) -> Text:
        t = Text(justify="center")
        t.append(f"  {L('shop')}  ", style="bold white on dark_blue")
        # Player info
        player = self.state.get("player", {})
        hp = player.get("hp") or 0
        max_hp = player.get("max_hp") or 0
        color = hp_color(hp, max_hp)
        t.append(f"\n \u2764 {hp}/{max_hp}", style=f"bold {color}")
        t.append(f"  |  \u25c9 {self._gold}", style="bold yellow")
        return t

    def _shop_body(self) -> Text:
        t = Text()
        flat_idx = 0

        # --- Cards section ---
        cards = [item for item in self.items if item.kind == "card"]
        if cards:
            t.append(f"\n  \u2660 {L('cards_for_sale')}\n", style="bold white underline")
            for item in cards:
                self._render_card_line(t, item, flat_idx)
                flat_idx += 1
            t.append("\n")

        # --- Relics section ---
        relics = [item for item in self.items if item.kind == "relic"]
        if relics:
            t.append(f"  \u2b50 {L('shop_relics')}\n", style="bold cyan underline")
            for item in relics:
                self._render_item_line(t, item, flat_idx)
                flat_idx += 1
            t.append("\n")

        # --- Potions section ---
        potions = [item for item in self.items if item.kind == "potion"]
        if potions:
            t.append(f"  \u2697 {L('shop_potions')}\n", style="bold cyan underline")
            for item in potions:
                self._render_item_line(t, item, flat_idx)
                flat_idx += 1
            t.append("\n")

        # --- Services section (card removal) ---
        services = [item for item in self.items if item.kind == "remove"]
        if services:
            t.append(f"  \u2702 {L('services')}\n", style="bold white underline")
            for item in services:
                self._render_item_line(t, item, flat_idx)
                flat_idx += 1
            t.append("\n")

        if not self.items:
            t.append(f"\n  {L('shop_empty')}\n", style="dim")

        return t

    def _render_card_line(self, t: Text, item: _ShopItem, flat_idx: int) -> None:
        """Render a single card line in the shop body."""
        affordable = item.cost <= self._gold
        is_selected = flat_idx == self.selected

        # Selection marker
        marker = " >>>" if is_selected else "    "
        key = self._key_label(flat_idx)

        t.append(f"{marker} ", style="bold yellow" if is_selected else "dim")
        t.append(f"[{key}] ", style="bold yellow" if affordable else "dim yellow")
        # Card name with type color
        name_color = _CARD_TYPE_COLORS.get(item.card_type, "white")
        t.append(f"{item.name}", style=f"bold {name_color}" if affordable else f"dim {name_color}")
        # Energy cost, card type, and rarity
        t.append(f"  ({item.card_cost})", style="bold yellow" if affordable else "dim yellow")
        t.append(f"  {item.card_type}", style="dim")
        if item.card_rarity:
            rarity_label, rarity_color = _RARITY_COLORS.get(
                item.card_rarity, (item.card_rarity, "dim")
            )
            t.append(f"  {rarity_label}", style=f"bold {rarity_color}" if affordable else f"dim {rarity_color}")
        # Price
        price_color = "green" if affordable else "red"
        t.append(f"  {item.cost}g", style=f"bold {price_color}" if affordable else f"dim {price_color}")
        # Sale badge
        if item.on_sale:
            t.append(f"  {L('sale')}", style="bold yellow")
        # Keyword tags (Exhaust, Ethereal, etc.)
        _KW_ICONS: dict[str, str] = {
            "Exhaust": "\u2716",
            "Ethereal": "\u2728",
            "Innate": "\u2605",
            "Retain": "\u21ba",
            "Sly": "\u2694",
        }
        for kw in (item.keywords or []):
            if isinstance(kw, str):
                icon = _KW_ICONS.get(kw.title(), "")
                if icon:
                    t.append(f" {icon}{kw}", style="dim magenta")
                else:
                    t.append(f" [{kw}]", style="dim magenta")
        t.append("\n")
        # Description on next line
        if item.description:
            desc_indent = "          "
            t.append(f"{desc_indent}{item.description}\n", style="dim" if affordable else "dim strike")
        # Upgrade preview
        if item.after_upgrade:
            card_dict = {"cost": item.card_cost, "stats": item.card_stats, "description": item.description}
            upgrade_str = build_upgrade_preview(card_dict, item.after_upgrade)
            if upgrade_str:
                desc_indent = "          "
                t.append(f"{desc_indent}Upgrade: {upgrade_str}\n", style="dim cyan")

    def _render_item_line(self, t: Text, item: _ShopItem, flat_idx: int) -> None:
        """Render a relic, potion, or service line."""
        affordable = item.cost <= self._gold
        is_selected = flat_idx == self.selected

        marker = " >>>" if is_selected else "    "
        key = self._key_label(flat_idx)

        t.append(f"{marker} ", style="bold yellow" if is_selected else "dim")
        t.append(f"[{key}] ", style="bold yellow" if affordable else "dim yellow")
        t.append(f"{item.name}", style="bold white" if affordable else "dim white")
        # Price
        price_color = "green" if affordable else "red"
        t.append(f"  {item.cost}g", style=f"bold {price_color}" if affordable else f"dim {price_color}")
        t.append("\n")
        # Description
        if item.description:
            desc_indent = "          "
            t.append(f"{desc_indent}{item.description}\n", style="dim")

    def _footer_text(self) -> Text:
        bindings = Text()
        n = len(self.items)
        if n > 0:
            last_key = self._key_label(min(n - 1, 15))
            first_key = "1"
            bindings.append(f"[{first_key}-{last_key}]", style="bold yellow")
            bindings.append(f" {L('select')}  ", style="dim")
            bindings.append("[Enter]", style="bold yellow")
            bindings.append(f" {L('buy')}  ", style="dim")
        bindings.append("[L/Esc]", style="bold yellow")
        bindings.append(f" {L('leave_shop')}", style="dim")
        return build_status_footer(bindings, self.state)

    # ------------------------------------------------------------------
    # Refresh display after state changes
    # ------------------------------------------------------------------

    async def _refresh_display(self) -> None:
        if not self._is_composed or self._refreshing:
            return
        self._refreshing = True
        try:
            for old in self.query("#shop-screen"):
                await old.remove()
            await self.mount(
                Vertical(
                    Static(self._title_text(), id="shop-title"),
                    VerticalScroll(
                        Static(self._shop_body(), id="shop-body"),
                        id="shop-viewport",
                    ),
                    Static(self._footer_text(), id="shop-footer"),
                    id="shop-screen",
                )
            )
        finally:
            self._refreshing = False

    async def watch_selected(self, value: int) -> None:
        await self._refresh_display()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_select_item(self, index: int) -> None:
        if 0 <= index < len(self.items):
            item = self.items[index]
            if item.cost > self._gold:
                self.notify(L("not_enough_gold").format(item.cost, self._gold), severity="warning")
                return
            self.selected = index

    async def action_buy(self) -> None:
        """Buy the currently selected item."""
        if self._busy:
            return
        if self.selected < 0:
            self.notify(L("select_item_first"), severity="warning")
            return

        item = self.items[self.selected]
        if item.cost > self._gold:
            self.notify(L("not_enough_gold").format(item.cost, self._gold), severity="warning")
            return

        self._busy = True
        try:
            state = await self._buy_item(item)

            if state.get("type") == "error":
                self.notify(state.get("message", "Purchase failed."), severity="error")
                self._busy = False
                return


            # If the response is still a shop decision, re-render with updated state
            if state.get("decision") == "shop":
                self.state = state
                self.items = _build_shop_items(state)
                self._gold = state.get("player", {}).get("gold") or 0
                self.selected = -1  # triggers watch_selected -> refresh
                self._busy = False
            else:
                # Shop was exited (e.g., card removal triggers card_select)
                self.app.post_message(ShopDoneMessage(state))
                self.app.pop_screen()
                self._busy = False
        except Exception:
            self._busy = False
            raise

    async def _buy_item(self, item: _ShopItem) -> dict:
        """Send the appropriate buy command to the engine."""
        bridge = self.controller.bridge
        try:
            if item.kind == "card":
                return await bridge.send(
                    {"cmd": "action", "action": "buy_card", "args": {"card_index": item.index}}
                )
            elif item.kind == "relic":
                return await bridge.send(
                    {"cmd": "action", "action": "buy_relic", "args": {"relic_index": item.index}}
                )
            elif item.kind == "potion":
                return await bridge.send(
                    {"cmd": "action", "action": "buy_potion", "args": {"potion_index": item.index}}
                )
            elif item.kind == "remove":
                return await bridge.send(
                    {"cmd": "action", "action": "remove_card"}
                )
            else:
                return {"type": "error", "message": f"Unknown item kind: {item.kind}"}
        except Exception as e:
            return {"type": "error", "message": str(e)}

    async def action_leave(self) -> None:
        """Leave the shop."""
        if self._busy:
            return
        self._busy = True
        try:
            state = await self.controller.leave_room()

            if state.get("type") == "error":
                # Fallback: try proceed
                state = await self.controller.proceed()

            self.app.post_message(ShopDoneMessage(state))
            self.app.pop_screen()
        finally:
            self._busy = False
