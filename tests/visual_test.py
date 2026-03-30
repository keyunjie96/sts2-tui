"""Visual screenshot tests for every TUI screen type.

Loads real game states from ground truth data, renders each screen
headlessly via Textual's async test runner, and saves SVG screenshots
to tests/screenshots/ for visual review in any browser.

Usage::

    python3 -m tests.visual_test          # capture all screens
    python3 -m tests.visual_test --open   # capture + open in browser

Requires no running sts2-cli instance -- everything uses recorded data.
"""

from __future__ import annotations

import asyncio
import json
import sys
import webbrowser
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

from textual.app import App

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = Path(__file__).resolve().parent.parent
GROUND_TRUTH_DIR = Path(__file__).resolve().parent / "ground_truth_data"
SCREENSHOT_DIR = Path(__file__).resolve().parent / "screenshots"
CSS_PATH = PROJECT_ROOT / "src" / "sts2_tui" / "tui" / "sls.tcss"

SCREENSHOT_DIR.mkdir(parents=True, exist_ok=True)


# ---------------------------------------------------------------------------
# Load ground truth data
# ---------------------------------------------------------------------------

def _load_raw(seed: int = 1) -> list[dict]:
    """Load all raw sts2-cli responses from a seed file."""
    path = GROUND_TRUTH_DIR / f"seed_{seed}_raw.json"
    if not path.exists():
        raise FileNotFoundError(f"Missing ground truth data: {path}")
    with open(path) as f:
        return json.load(f)


def _find_decision(responses: list[dict], decision_type: str) -> dict | None:
    """Find the first response with the given decision type."""
    for entry in responses:
        if isinstance(entry, dict) and entry.get("decision") == decision_type:
            return entry
    return None


def _find_all_decisions(responses: list[dict], decision_type: str) -> list[dict]:
    """Find all responses matching a given decision type."""
    return [
        entry for entry in responses
        if isinstance(entry, dict) and entry.get("decision") == decision_type
    ]


# ---------------------------------------------------------------------------
# Mock controller (same pattern as test_tui_screens.py)
# ---------------------------------------------------------------------------

def _make_mock_controller(next_state: dict | None = None) -> MagicMock:
    """Build a mock GameController that returns next_state for all async methods."""
    if next_state is None:
        next_state = {"type": "decision", "decision": "map_select", "choices": []}

    ctrl = MagicMock()
    for method_name in [
        "play_card", "end_turn", "choose", "select_map_node",
        "select_card_reward", "skip_card_reward", "use_potion",
        "proceed", "leave_room", "select_bundle", "select_cards",
        "skip_select", "get_state", "start_run", "quit",
    ]:
        setattr(ctrl, method_name, AsyncMock(return_value=next_state))

    # get_map returns a non-map response by default (triggers fallback rendering)
    ctrl.get_map = AsyncMock(return_value={"type": "error", "message": "mock"})
    return ctrl


# ---------------------------------------------------------------------------
# Per-screen harness apps (one screen each, isolated)
# ---------------------------------------------------------------------------

class CombatScreenApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.combat import CombatScreen
        self.push_screen(CombatScreen(self._state, controller=self._controller))


class MapScreenApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.map import MapScreen
        self.push_screen(MapScreen(self._state, controller=self._controller))


class CardRewardScreenApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.card_reward import CardRewardScreen
        self.push_screen(CardRewardScreen(self._state, controller=self._controller))


class RestScreenApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.rest import RestScreen
        self.push_screen(RestScreen(self._state, controller=self._controller))


class EventScreenApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.event import EventScreen
        self.push_screen(EventScreen(self._state, controller=self._controller))


class CharacterSelectApp(App):
    CSS_PATH = str(CSS_PATH)

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.character_select import CharacterSelectScreen
        self.push_screen(CharacterSelectScreen())


class ShopScreenApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.shop import ShopScreen
        self.push_screen(ShopScreen(self._state, controller=self._controller))


class GenericScreenApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.generic import GenericScreen
        self.push_screen(GenericScreen(self._state, controller=self._controller))


class DeckViewerApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, deck: list[dict]) -> None:
        super().__init__()
        self._deck = deck

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.deck_viewer import DeckViewerOverlay
        self.push_screen(DeckViewerOverlay(self._deck))


class RelicViewerApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, relics: list[dict], potions: list[dict]) -> None:
        super().__init__()
        self._relics = relics
        self._potions = potions

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.deck_viewer import RelicViewerOverlay
        self.push_screen(RelicViewerOverlay(self._relics, self._potions))


class GlobalHelpApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, screen_name: str = "") -> None:
        super().__init__()
        self._screen_name = screen_name

    def on_mount(self) -> None:
        from sts2_tui.tui.shared import GlobalHelpOverlay
        self.push_screen(GlobalHelpOverlay(self._screen_name))


class ErrorRecoveryApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, error_message: str = "") -> None:
        super().__init__()
        self._error_message = error_message

    def on_mount(self) -> None:
        from sts2_tui.tui.shared import ErrorRecoveryScreen
        self.push_screen(ErrorRecoveryScreen(self._error_message))


class DefeatOverlayApp(App):
    CSS_PATH = str(CSS_PATH)

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.combat import DefeatOverlay
        self.push_screen(DefeatOverlay())


class VictoryOverlayApp(App):
    CSS_PATH = str(CSS_PATH)

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.combat import VictoryOverlay
        self.push_screen(VictoryOverlay())


class GameOverApp(App):
    """Simulates the game over screen shown by the main app."""
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict) -> None:
        super().__init__()
        self._state = state

    def on_mount(self) -> None:
        from sts2_tui.tui.controller import extract_player
        from sts2_tui.tui.i18n import L
        from textual.widgets import Static
        from rich.text import Text

        victory = self._state.get("victory", False)
        player_data = extract_player(self._state)
        ctx = self._state.get("context", {})
        hp = player_data.get("hp", 0)
        max_hp = player_data.get("max_hp", 0)
        gold = player_data.get("gold", 0)
        deck_size = player_data.get("deck_size", 0)
        act = ctx.get("act", "?")
        floor = ctx.get("floor", "?")
        relics = player_data.get("relics", [])

        t = Text(justify="center")
        if victory:
            t.append(f"\n\n  {L('victory')}  \n\n", style="bold white on dark_green")
        else:
            t.append(f"\n\n  {L('game_over')}  \n\n", style="bold white on dark_red")

        t.append(f"\n  {L('act')} {act}, {L('floor')} {floor}\n", style="bold white")
        t.append(f"\n  HP: {hp}/{max_hp}", style="white")
        t.append(f"  |  Gold: {gold}", style="bold yellow")
        t.append(f"  |  {L('deck')}: {deck_size}\n", style="white")

        if relics:
            t.append(f"\n  {L('relics')} ({len(relics)}): ", style="dim")
            for i, r in enumerate(relics):
                if i > 0:
                    t.append(", ", style="dim")
                t.append(r.get("name", "?"), style="bold cyan")
            t.append("\n")

        t.append(f"\n\n[Q] {L('quit')}", style="bold yellow")
        self.mount(Static(t))


# ---------------------------------------------------------------------------
# Screenshot capture helper
# ---------------------------------------------------------------------------

async def _capture(
    app: App,
    filename: str,
    *,
    size: tuple[int, int] = (120, 40),
    pause_delay: float = 0.5,
    pre_keys: list[str] | None = None,
) -> str:
    """Run an app headlessly, optionally press keys, and save a screenshot.

    Returns the path of the saved SVG file.
    """
    out_path = SCREENSHOT_DIR / filename
    async with app.run_test(size=size) as pilot:
        await pilot.pause(delay=pause_delay)
        if pre_keys:
            for key in pre_keys:
                await pilot.press(key)
                await pilot.pause(delay=0.3)
        # Use export_screenshot to get SVG string, then save
        svg = app.export_screenshot(title=filename.replace(".svg", ""))
        # Handle potential surrogate characters from emoji in widget text
        svg_clean = svg.encode("utf-8", errors="replace").decode("utf-8")
        out_path.write_text(svg_clean)
    print(f"  [ok] {filename}")
    return str(out_path)


# ---------------------------------------------------------------------------
# Screen capture functions
# ---------------------------------------------------------------------------

async def capture_character_select() -> list[str]:
    """Screenshot the character select screen (default + with selection)."""
    paths = []

    # Default view (Ironclad selected)
    app = CharacterSelectApp()
    paths.append(await _capture(app, "01_character_select.svg"))

    # With Silent selected
    app = CharacterSelectApp()
    paths.append(await _capture(app, "02_character_select_silent.svg", pre_keys=["2"]))

    return paths


async def capture_event_screens(responses_s1: list[dict]) -> list[str]:
    """Screenshot all event screens (Neow + random events)."""
    paths = []
    events = _find_all_decisions(responses_s1, "event_choice")

    for i, state in enumerate(events):
        event_name = state.get("event_name", "unknown")
        # Sanitize filename
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in str(event_name))
        safe_name = safe_name.strip().replace(" ", "_").lower()

        ctrl = _make_mock_controller()

        # Default view
        app = EventScreenApp(state, ctrl)
        fname = f"03_event_{i:02d}_{safe_name}.svg"
        paths.append(await _capture(app, fname))

        # With first option selected
        app = EventScreenApp(state, ctrl)
        fname = f"03_event_{i:02d}_{safe_name}_selected.svg"
        paths.append(await _capture(app, fname, pre_keys=["1"]))

    return paths


async def capture_map_screens(responses_s1: list[dict]) -> list[str]:
    """Screenshot the map screen."""
    paths = []
    maps = _find_all_decisions(responses_s1, "map_select")

    if not maps:
        print("  [skip] No map_select states found")
        return paths

    # First map screen (start of game)
    ctrl = _make_mock_controller()
    app = MapScreenApp(maps[0], ctrl)
    paths.append(await _capture(app, "04_map_first.svg"))

    # Later map screen (mid-game, if available)
    if len(maps) > 3:
        ctrl = _make_mock_controller()
        app = MapScreenApp(maps[3], ctrl)
        paths.append(await _capture(app, "04_map_midgame.svg"))

    # Last map screen
    if len(maps) > 1:
        ctrl = _make_mock_controller()
        app = MapScreenApp(maps[-1], ctrl)
        paths.append(await _capture(app, "04_map_late.svg"))

    return paths


async def capture_combat_screens(responses_s1: list[dict]) -> list[str]:
    """Screenshot combat at various phases."""
    paths = []
    combats = _find_all_decisions(responses_s1, "combat_play")

    if not combats:
        print("  [skip] No combat_play states found")
        return paths

    # --- Start of first combat (round 1, full energy, full hand) ---
    first_combat = combats[0]
    ctrl = _make_mock_controller()
    app = CombatScreenApp(first_combat, ctrl)
    paths.append(await _capture(app, "05_combat_start.svg"))

    # --- With a card selected ---
    ctrl = _make_mock_controller()
    app = CombatScreenApp(first_combat, ctrl)
    paths.append(await _capture(app, "05_combat_card_selected.svg", pre_keys=["1"]))

    # --- Mid-combat: after some cards played (fewer cards, less energy) ---
    mid_states = [
        s for s in combats
        if len(s.get("hand", [])) < 5 and s.get("energy", 3) < 3
    ]
    if mid_states:
        ctrl = _make_mock_controller()
        app = CombatScreenApp(mid_states[0], ctrl)
        paths.append(await _capture(app, "05_combat_mid_turn.svg"))

    # --- New turn (round 2+) ---
    later_turns = [s for s in combats if s.get("round", 1) >= 2 and s.get("energy", 0) == 3]
    if later_turns:
        ctrl = _make_mock_controller()
        app = CombatScreenApp(later_turns[0], ctrl)
        paths.append(await _capture(app, "05_combat_round2.svg"))

    # --- Multi-enemy combat ---
    multi_enemy = [s for s in combats if len(s.get("enemies", [])) > 1 and s.get("round", 0) == 1]
    if multi_enemy:
        ctrl = _make_mock_controller()
        app = CombatScreenApp(multi_enemy[0], ctrl)
        paths.append(await _capture(app, "05_combat_multi_enemy.svg"))

        # With target cycling
        ctrl = _make_mock_controller()
        app = CombatScreenApp(multi_enemy[0], ctrl)
        paths.append(await _capture(app, "05_combat_multi_enemy_target.svg", pre_keys=["1", "tab"]))

    # --- Combat with player powers ---
    with_powers = [s for s in combats if s.get("player_powers")]
    if with_powers:
        ctrl = _make_mock_controller()
        app = CombatScreenApp(with_powers[0], ctrl)
        paths.append(await _capture(app, "05_combat_player_powers.svg"))

    # --- Low HP combat ---
    low_hp = [
        s for s in combats
        if s.get("player", {}).get("hp", 999) < s.get("player", {}).get("max_hp", 1) * 0.3
    ]
    if low_hp:
        ctrl = _make_mock_controller()
        app = CombatScreenApp(low_hp[0], ctrl)
        paths.append(await _capture(app, "05_combat_low_hp.svg"))

    return paths


async def capture_card_reward_screens(responses_s1: list[dict]) -> list[str]:
    """Screenshot card reward screens."""
    paths = []
    rewards = _find_all_decisions(responses_s1, "card_reward")

    if not rewards:
        print("  [skip] No card_reward states found")
        return paths

    # Default view
    ctrl = _make_mock_controller()
    app = CardRewardScreenApp(rewards[0], ctrl)
    paths.append(await _capture(app, "06_card_reward.svg"))

    # With a card selected
    ctrl = _make_mock_controller()
    app = CardRewardScreenApp(rewards[0], ctrl)
    paths.append(await _capture(app, "06_card_reward_selected.svg", pre_keys=["1"]))

    # Second reward (if available, different cards)
    if len(rewards) > 1:
        ctrl = _make_mock_controller()
        app = CardRewardScreenApp(rewards[1], ctrl)
        paths.append(await _capture(app, "06_card_reward_second.svg"))

    return paths


async def capture_rest_screens(responses_s1: list[dict]) -> list[str]:
    """Screenshot rest site screens."""
    paths = []
    rests = _find_all_decisions(responses_s1, "rest_site")

    if not rests:
        print("  [skip] No rest_site states found")
        return paths

    # Default view
    ctrl = _make_mock_controller()
    app = RestScreenApp(rests[0], ctrl)
    paths.append(await _capture(app, "07_rest_site.svg"))

    # With option selected
    ctrl = _make_mock_controller()
    app = RestScreenApp(rests[0], ctrl)
    paths.append(await _capture(app, "07_rest_site_selected.svg", pre_keys=["1"]))

    return paths


async def capture_shop_screens(responses_s2: list[dict]) -> list[str]:
    """Screenshot shop screens (from seed 2 which has shops)."""
    paths = []
    shops = _find_all_decisions(responses_s2, "shop")

    if not shops:
        print("  [skip] No shop states found (need seed 2 data)")
        return paths

    # Default view
    ctrl = _make_mock_controller()
    app = ShopScreenApp(shops[0], ctrl)
    paths.append(await _capture(app, "08_shop.svg"))

    # With an item selected
    ctrl = _make_mock_controller()
    app = ShopScreenApp(shops[0], ctrl)
    paths.append(await _capture(app, "08_shop_selected.svg", pre_keys=["1"]))

    return paths


async def capture_generic_screens(responses_s1: list[dict]) -> list[str]:
    """Screenshot generic/fallback screens (card_select, bundle_select)."""
    paths = []

    # card_select
    card_selects = _find_all_decisions(responses_s1, "card_select")
    if card_selects:
        ctrl = _make_mock_controller()
        app = GenericScreenApp(card_selects[0], ctrl)
        paths.append(await _capture(app, "09_card_select.svg"))

    # bundle_select (may not exist in seed 1)
    bundle_selects = _find_all_decisions(responses_s1, "bundle_select")
    if bundle_selects:
        ctrl = _make_mock_controller()
        app = GenericScreenApp(bundle_selects[0], ctrl)
        paths.append(await _capture(app, "09_bundle_select.svg"))

    # Synthetic generic screen with options
    synthetic_state = {
        "type": "decision",
        "decision": "unknown_type",
        "context": {"act": 1, "floor": 5},
        "options": [
            {"index": 0, "name": "Mystery Option A", "description": "Something happens."},
            {"index": 1, "name": "Mystery Option B", "description": "Something else happens."},
            {"index": 2, "name": "Mystery Option C", "description": "Who knows?"},
        ],
        "player": {
            "name": "Ironclad", "hp": 60, "max_hp": 80, "block": 0,
            "gold": 150, "relics": [], "potions": [], "deck_size": 15,
        },
    }
    ctrl = _make_mock_controller()
    app = GenericScreenApp(synthetic_state, ctrl)
    paths.append(await _capture(app, "09_generic_fallback.svg"))

    return paths


async def capture_combat_edge_cases(responses_s1: list[dict]) -> list[str]:
    """Screenshot edge-case combat states."""
    paths = []
    combats = _find_all_decisions(responses_s1, "combat_play")

    if not combats:
        return paths

    base = combats[0]

    # Empty hand
    empty_hand_state = dict(base)
    empty_hand_state["hand"] = []
    ctrl = _make_mock_controller()
    app = CombatScreenApp(empty_hand_state, ctrl)
    paths.append(await _capture(app, "10_combat_empty_hand.svg"))

    # Enemy with block and powers
    with_block_state = dict(base)
    with_block_state["enemies"] = [
        {
            "index": 0, "name": "Elite Guardian", "hp": 80, "max_hp": 100,
            "block": 15,
            "intents": [{"type": "Attack", "damage": 20, "hits": 3}],
            "intends_attack": True,
            "powers": [
                {"name": "Strength", "amount": 5},
                {"name": "Vulnerable", "amount": 2},
            ],
        },
    ]
    ctrl = _make_mock_controller()
    app = CombatScreenApp(with_block_state, ctrl)
    paths.append(await _capture(app, "10_combat_elite_block_powers.svg"))

    # Dead enemy alongside living enemies
    mixed_state = dict(base)
    mixed_state["enemies"] = [
        {
            "index": 0, "name": "Dead Slime", "hp": 0, "max_hp": 30,
            "block": 0, "intents": [], "intends_attack": False, "powers": None,
        },
        {
            "index": 1, "name": "Living Slime", "hp": 25, "max_hp": 40,
            "block": 5,
            "intents": [{"type": "Attack", "damage": 10}],
            "intends_attack": True,
            "powers": [{"name": "Curl Up", "amount": 8}],
        },
    ]
    ctrl = _make_mock_controller()
    app = CombatScreenApp(mixed_state, ctrl)
    paths.append(await _capture(app, "10_combat_dead_and_alive.svg"))

    return paths


# ---------------------------------------------------------------------------
# Character-specific combat states (Defect orbs, Necrobinder Osty, Regent stars)
# ---------------------------------------------------------------------------


async def capture_combat_defect_orbs(responses_s1: list[dict]) -> list[str]:
    """Screenshot combat as Defect with orb slots filled."""
    paths = []
    combats = _find_all_decisions(responses_s1, "combat_play")
    if not combats:
        return paths

    import copy
    base = copy.deepcopy(combats[0])

    # Patch the state to look like a Defect character with orbs
    base["player"]["name"] = "Defect"
    base["orbs"] = [
        {"type": "Lightning", "passive_amount": 3, "evoke_amount": 8},
        {"type": "Frost", "passive_amount": 2, "evoke_amount": 5},
        {"type": "Dark", "passive_amount": 6, "evoke_amount": 6},
    ]
    base["orb_slots"] = 5  # 5 slots, 3 filled, 2 empty

    # Give some Defect-flavored cards in hand
    base["hand"] = [
        {
            "index": 0, "name": "Ball Lightning", "type": "Attack",
            "cost": 1, "description": "Deal 7 damage. Channel 1 Lightning orb.",
            "stats": {"damage": 7}, "upgraded": False, "playable": True,
        },
        {
            "index": 1, "name": "Glacier", "type": "Skill",
            "cost": 2, "description": "Gain 7 Block. Channel 2 Frost orbs.",
            "stats": {"block": 7}, "upgraded": False, "playable": True,
        },
        {
            "index": 2, "name": "Defragment", "type": "Power",
            "cost": 1, "description": "Gain 1 Focus.",
            "stats": {"focus": 1}, "upgraded": False, "playable": True,
        },
        {
            "index": 3, "name": "Zap", "type": "Skill",
            "cost": 0, "description": "Channel 1 Lightning orb.",
            "stats": {}, "upgraded": False, "playable": True,
        },
    ]

    # Defect-appropriate powers
    base["player_powers"] = [
        {"name": "Focus", "amount": 2},
    ]

    ctrl = _make_mock_controller()
    app = CombatScreenApp(base, ctrl)
    paths.append(await _capture(app, "11_combat_defect_orbs.svg"))

    return paths


async def capture_combat_necrobinder_osty(responses_s1: list[dict]) -> list[str]:
    """Screenshot combat as Necrobinder with Osty companion visible."""
    paths = []
    combats = _find_all_decisions(responses_s1, "combat_play")
    if not combats:
        return paths

    import copy
    base = copy.deepcopy(combats[0])

    # Patch state for Necrobinder with Osty alive
    base["player"]["name"] = "Necrobinder"
    base["osty"] = {
        "name": "Osty",
        "hp": 15,
        "max_hp": 20,
        "block": 3,
        "alive": True,
    }

    # Necrobinder-flavored hand
    base["hand"] = [
        {
            "index": 0, "name": "Bone Spear", "type": "Attack",
            "cost": 1, "description": "Deal 9 damage.",
            "stats": {"damage": 9}, "upgraded": False, "playable": True,
        },
        {
            "index": 1, "name": "Spirit Shield", "type": "Skill",
            "cost": 1, "description": "Gain 8 Block. Osty gains 4 Block.",
            "stats": {"block": 8, "osty_block": 4}, "upgraded": False, "playable": True,
        },
        {
            "index": 2, "name": "Soul Drain", "type": "Attack",
            "cost": 2, "description": "Deal 12 damage. Heal Osty 3 HP.",
            "stats": {"damage": 12, "heal": 3}, "upgraded": False, "playable": True,
        },
    ]

    base["player_powers"] = [
        {"name": "Dark Pact", "amount": 1},
    ]

    ctrl = _make_mock_controller()
    app = CombatScreenApp(base, ctrl)
    paths.append(await _capture(app, "11_combat_necrobinder_osty.svg"))

    # Also capture with Osty fallen
    fallen = copy.deepcopy(base)
    fallen["osty"]["alive"] = False
    fallen["osty"]["hp"] = 0

    ctrl = _make_mock_controller()
    app = CombatScreenApp(fallen, ctrl)
    paths.append(await _capture(app, "11_combat_necrobinder_osty_fallen.svg"))

    return paths


async def capture_combat_regent_stars(responses_s1: list[dict]) -> list[str]:
    """Screenshot combat as Regent with star resource visible."""
    paths = []
    combats = _find_all_decisions(responses_s1, "combat_play")
    if not combats:
        return paths

    import copy
    base = copy.deepcopy(combats[0])

    # Patch state for Regent with stars
    base["player"]["name"] = "Regent"
    base["stars"] = 3

    # Regent-flavored hand
    base["hand"] = [
        {
            "index": 0, "name": "Royal Decree", "type": "Skill",
            "cost": 1, "description": "Gain 1 Star. Gain 5 Block.",
            "stats": {"block": 5}, "upgraded": False, "playable": True,
        },
        {
            "index": 1, "name": "Starfall", "type": "Attack",
            "cost": 2, "description": "Spend all Stars. Deal 8 damage per Star.",
            "stats": {"damage": 8}, "upgraded": False, "playable": True,
        },
        {
            "index": 2, "name": "Constellation", "type": "Power",
            "cost": 3, "description": "At end of turn, gain 1 Star.",
            "stats": {}, "upgraded": False, "playable": True,
        },
        {
            "index": 3, "name": "Strike", "type": "Attack",
            "cost": 1, "description": "Deal 6 damage.",
            "stats": {"damage": 6}, "upgraded": False, "playable": True,
        },
    ]

    base["player_powers"] = [
        {"name": "Celestial Aura", "amount": 1},
    ]

    ctrl = _make_mock_controller()
    app = CombatScreenApp(base, ctrl)
    paths.append(await _capture(app, "11_combat_regent_stars.svg"))

    return paths


# ---------------------------------------------------------------------------
# Overlay screens (Deck viewer, Relic viewer, Help, Error, Game over)
# ---------------------------------------------------------------------------


async def capture_deck_viewer() -> list[str]:
    """Screenshot the deck viewer overlay with a sample deck."""
    paths = []

    sample_deck = [
        # Attacks
        {
            "name": "Strike", "type": "Attack", "cost": 1,
            "description": "Deal 6 damage.", "stats": {"damage": 6},
            "upgraded": False,
        },
        {
            "name": "Strike", "type": "Attack", "cost": 1,
            "description": "Deal 6 damage.", "stats": {"damage": 6},
            "upgraded": False,
        },
        {
            "name": "Pommel Strike", "type": "Attack", "cost": 1,
            "description": "Deal 9 damage. Draw 1 card.",
            "stats": {"damage": 9}, "upgraded": True,
            "after_upgrade": {"cost": 1, "stats": {"damage": 10}},
        },
        {
            "name": "Heavy Blade", "type": "Attack", "cost": 2,
            "description": "Deal 14 damage. Strength affects this 3 times.",
            "stats": {"damage": 14}, "upgraded": False,
            "after_upgrade": {"cost": 2, "stats": {"damage": 14}},
        },
        {
            "name": "Carnage", "type": "Attack", "cost": 2,
            "description": "Ethereal. Deal 20 damage.",
            "stats": {"damage": 20}, "upgraded": False,
            "after_upgrade": {"cost": 2, "stats": {"damage": 28}},
        },
        # Skills
        {
            "name": "Defend", "type": "Skill", "cost": 1,
            "description": "Gain 5 Block.", "stats": {"block": 5},
            "upgraded": False,
        },
        {
            "name": "Defend", "type": "Skill", "cost": 1,
            "description": "Gain 5 Block.", "stats": {"block": 5},
            "upgraded": False,
        },
        {
            "name": "Shrug It Off", "type": "Skill", "cost": 1,
            "description": "Gain 8 Block. Draw 1 card.",
            "stats": {"block": 8}, "upgraded": False,
            "after_upgrade": {"cost": 1, "stats": {"block": 11}},
        },
        {
            "name": "Battle Trance", "type": "Skill", "cost": 0,
            "description": "Draw 3 cards. You can't draw additional cards this turn.",
            "stats": {"draw": 3}, "upgraded": False,
            "after_upgrade": {"cost": 0, "stats": {"draw": 4}},
        },
        # Powers
        {
            "name": "Inflame", "type": "Power", "cost": 1,
            "description": "Gain 2 Strength.",
            "stats": {"strength": 2}, "upgraded": False,
            "after_upgrade": {"cost": 1, "stats": {"strength": 3}},
        },
        {
            "name": "Demon Form", "type": "Power", "cost": 3,
            "description": "At the start of each turn, gain 2 Strength.",
            "stats": {"strength": 2}, "upgraded": False,
            "after_upgrade": {"cost": 3, "stats": {"strength": 3}},
        },
        # Status
        {
            "name": "Wound", "type": "Status", "cost": -1,
            "description": "Unplayable.", "stats": {},
            "upgraded": False,
        },
        # Curse
        {
            "name": "Regret", "type": "Curse", "cost": -1,
            "description": "Unplayable. At end of turn, lose 1 HP per card in hand.",
            "stats": {}, "upgraded": False,
        },
    ]

    app = DeckViewerApp(sample_deck)
    paths.append(await _capture(app, "12_deck_viewer.svg"))

    # Empty deck
    app = DeckViewerApp([])
    paths.append(await _capture(app, "12_deck_viewer_empty.svg"))

    return paths


async def capture_relic_viewer() -> list[str]:
    """Screenshot the relic viewer overlay with sample relics and potions."""
    paths = []

    sample_relics = [
        {"name": "Burning Blood", "description": "At the end of combat, heal 6 HP."},
        {"name": "Vajra", "description": "At the start of each combat, gain 1 Strength."},
        {"name": "Lantern", "description": "Gain 1 Energy at the start of each combat."},
        {"name": "Bag of Marbles", "description": "At the start of each combat, apply 1 Vulnerable to ALL enemies."},
        {"name": "Pen Nib", "description": "Every 10th Attack deals double damage."},
    ]

    sample_potions = [
        {
            "name": "Fire Potion", "description": "Deal 20 damage to target enemy.",
            "target_type": "AnyEnemy",
        },
        {
            "name": "Block Potion", "description": "Gain 12 Block.",
            "target_type": "Self",
        },
        {
            "name": "Strength Potion", "description": "Gain 2 Strength.",
            "target_type": "Self",
        },
    ]

    app = RelicViewerApp(sample_relics, sample_potions)
    paths.append(await _capture(app, "12_relic_viewer.svg"))

    # Empty relics/potions
    app = RelicViewerApp([], [])
    paths.append(await _capture(app, "12_relic_viewer_empty.svg"))

    return paths


async def capture_global_help_overlay() -> list[str]:
    """Screenshot the global help overlay for various screen contexts."""
    paths = []

    # Help from combat context
    app = GlobalHelpApp("CombatScreen")
    paths.append(await _capture(app, "12_help_combat.svg"))

    # Help from shop context
    app = GlobalHelpApp("ShopScreen")
    paths.append(await _capture(app, "12_help_shop.svg"))

    # Help with no screen context (general only)
    app = GlobalHelpApp("")
    paths.append(await _capture(app, "12_help_general.svg"))

    return paths


async def capture_error_recovery() -> list[str]:
    """Screenshot the error recovery screen."""
    paths = []

    # Short error
    app = ErrorRecoveryApp("Connection lost: server did not respond within 30s.")
    paths.append(await _capture(app, "13_error_recovery.svg"))

    # Longer error with detail
    app = ErrorRecoveryApp(
        "Bridge error: unexpected response from sts2-cli (exit code 1). "
        "The game process may have crashed. Check logs for details."
    )
    paths.append(await _capture(app, "13_error_recovery_detailed.svg"))

    return paths


async def capture_game_over_screens() -> list[str]:
    """Screenshot game over states: defeat overlay, victory overlay, and full game over."""
    paths = []

    # Defeat overlay (shown during combat when player HP reaches 0)
    app = DefeatOverlayApp()
    paths.append(await _capture(app, "14_defeat_overlay.svg"))

    # Victory overlay (shown when all enemies are defeated)
    app = VictoryOverlayApp()
    paths.append(await _capture(app, "14_victory_overlay.svg"))

    # Full game over screen (defeat)
    defeat_state = {
        "type": "game_over",
        "decision": "game_over",
        "victory": False,
        "context": {"act": 2, "floor": 14},
        "player": {
            "name": "Ironclad", "hp": 0, "max_hp": 80, "block": 0,
            "gold": 234, "deck_size": 28,
            "relics": [
                {"name": "Burning Blood", "description": "Heal 6 HP at end of combat."},
                {"name": "Vajra", "description": "Start combat with 1 Strength."},
                {"name": "Lantern", "description": "Gain 1 Energy first turn."},
            ],
            "potions": [],
        },
    }
    app = GameOverApp(defeat_state)
    paths.append(await _capture(app, "14_game_over_defeat.svg"))

    # Full game over screen (victory)
    victory_state = {
        "type": "game_over",
        "decision": "game_over",
        "victory": True,
        "context": {"act": 3, "floor": 51},
        "player": {
            "name": "Silent", "hp": 42, "max_hp": 70, "block": 0,
            "gold": 512, "deck_size": 35,
            "relics": [
                {"name": "Ring of the Snake", "description": "Draw 2 extra cards first turn."},
                {"name": "Kunai", "description": "Every 3rd Attack, gain 1 Dexterity."},
                {"name": "Shuriken", "description": "Every 3rd Attack, gain 1 Strength."},
                {"name": "Ornamental Fan", "description": "Every 3rd Attack, gain 4 Block."},
                {"name": "Ice Cream", "description": "Energy is conserved between turns."},
            ],
            "potions": [],
        },
    }
    app = GameOverApp(victory_state)
    paths.append(await _capture(app, "14_game_over_victory.svg"))

    return paths


async def capture_shop_purchase_flow(responses_s2: list[dict]) -> list[str]:
    """Screenshot shop with item selected and purchase confirmation attempt."""
    paths = []
    shops = _find_all_decisions(responses_s2, "shop")

    if not shops:
        print("  [skip] No shop states found (need seed 2 data)")
        return paths

    # Select first item and press Enter to attempt purchase
    ctrl = _make_mock_controller()
    # Mock the bridge for buy attempts -- return the same shop state
    ctrl.bridge = MagicMock()
    ctrl.bridge.send = AsyncMock(return_value=shops[0])

    app = ShopScreenApp(shops[0], ctrl)
    paths.append(await _capture(
        app, "08_shop_purchase_confirm.svg",
        pre_keys=["1", "enter"],
    ))

    # Select second item (if more than one) to show different selection
    if len(_find_all_decisions(responses_s2, "shop")) > 0:
        ctrl = _make_mock_controller()
        ctrl.bridge = MagicMock()
        ctrl.bridge.send = AsyncMock(return_value=shops[0])

        app = ShopScreenApp(shops[0], ctrl)
        paths.append(await _capture(
            app, "08_shop_second_item_selected.svg",
            pre_keys=["2"],
        ))

    return paths


# ---------------------------------------------------------------------------
# Chinese (zh) screenshot capture functions
# ---------------------------------------------------------------------------

def _set_lang(lang: str) -> None:
    """Set the TUI i18n language for subsequent captures."""
    from sts2_tui.tui.i18n import set_language
    set_language(lang)


async def capture_character_select_zh() -> list[str]:
    """Screenshot the character select screen in Chinese."""
    _set_lang("zh")
    paths = []

    app = CharacterSelectApp()
    paths.append(await _capture(app, "01_character_select_zh.svg"))

    app = CharacterSelectApp()
    paths.append(await _capture(app, "02_character_select_silent_zh.svg", pre_keys=["2"]))

    _set_lang("en")
    return paths


async def capture_combat_screens_zh(responses_s1: list[dict]) -> list[str]:
    """Screenshot combat screens in Chinese."""
    _set_lang("zh")
    paths = []
    combats = _find_all_decisions(responses_s1, "combat_play")

    if not combats:
        print("  [skip] No combat_play states found")
        _set_lang("en")
        return paths

    # Start of first combat
    first_combat = combats[0]
    ctrl = _make_mock_controller()
    app = CombatScreenApp(first_combat, ctrl)
    paths.append(await _capture(app, "05_combat_start_zh.svg"))

    # With a card selected
    ctrl = _make_mock_controller()
    app = CombatScreenApp(first_combat, ctrl)
    paths.append(await _capture(app, "05_combat_card_selected_zh.svg", pre_keys=["1"]))

    # Multi-enemy combat
    multi_enemy = [s for s in combats if len(s.get("enemies", [])) > 1 and s.get("round", 0) == 1]
    if multi_enemy:
        ctrl = _make_mock_controller()
        app = CombatScreenApp(multi_enemy[0], ctrl)
        paths.append(await _capture(app, "05_combat_multi_enemy_zh.svg"))

    # Combat with player powers
    with_powers = [s for s in combats if s.get("player_powers")]
    if with_powers:
        ctrl = _make_mock_controller()
        app = CombatScreenApp(with_powers[0], ctrl)
        paths.append(await _capture(app, "05_combat_player_powers_zh.svg"))

    _set_lang("en")
    return paths


async def capture_card_reward_screens_zh(responses_s1: list[dict]) -> list[str]:
    """Screenshot card reward screens in Chinese."""
    _set_lang("zh")
    paths = []
    rewards = _find_all_decisions(responses_s1, "card_reward")

    if not rewards:
        print("  [skip] No card_reward states found")
        _set_lang("en")
        return paths

    # Default view
    ctrl = _make_mock_controller()
    app = CardRewardScreenApp(rewards[0], ctrl)
    paths.append(await _capture(app, "06_card_reward_zh.svg"))

    # With a card selected
    ctrl = _make_mock_controller()
    app = CardRewardScreenApp(rewards[0], ctrl)
    paths.append(await _capture(app, "06_card_reward_selected_zh.svg", pre_keys=["1"]))

    _set_lang("en")
    return paths


async def capture_event_screens_zh(responses_s1: list[dict]) -> list[str]:
    """Screenshot event screens in Chinese (first 2 events)."""
    _set_lang("zh")
    paths = []
    events = _find_all_decisions(responses_s1, "event_choice")

    for i, state in enumerate(events[:2]):
        event_name = state.get("event_name", "unknown")
        safe_name = "".join(c if c.isalnum() or c in "-_ " else "" for c in str(event_name))
        safe_name = safe_name.strip().replace(" ", "_").lower()

        ctrl = _make_mock_controller()
        app = EventScreenApp(state, ctrl)
        fname = f"03_event_{i:02d}_{safe_name}_zh.svg"
        paths.append(await _capture(app, fname))

    _set_lang("en")
    return paths


async def capture_map_screens_zh(responses_s1: list[dict]) -> list[str]:
    """Screenshot map screens in Chinese."""
    _set_lang("zh")
    paths = []
    maps = _find_all_decisions(responses_s1, "map_select")

    if not maps:
        print("  [skip] No map_select states found")
        _set_lang("en")
        return paths

    ctrl = _make_mock_controller()
    app = MapScreenApp(maps[0], ctrl)
    paths.append(await _capture(app, "04_map_first_zh.svg"))

    _set_lang("en")
    return paths


async def capture_rest_screens_zh(responses_s1: list[dict]) -> list[str]:
    """Screenshot rest site screens in Chinese."""
    _set_lang("zh")
    paths = []
    rests = _find_all_decisions(responses_s1, "rest_site")

    if not rests:
        print("  [skip] No rest_site states found")
        _set_lang("en")
        return paths

    ctrl = _make_mock_controller()
    app = RestScreenApp(rests[0], ctrl)
    paths.append(await _capture(app, "07_rest_site_zh.svg"))

    _set_lang("en")
    return paths


async def capture_shop_screens_zh(responses_s2: list[dict]) -> list[str]:
    """Screenshot shop screens in Chinese."""
    _set_lang("zh")
    paths = []
    shops = _find_all_decisions(responses_s2, "shop")

    if not shops:
        print("  [skip] No shop states found (need seed 2 data)")
        _set_lang("en")
        return paths

    ctrl = _make_mock_controller()
    app = ShopScreenApp(shops[0], ctrl)
    paths.append(await _capture(app, "08_shop_zh.svg"))

    _set_lang("en")
    return paths


# ---------------------------------------------------------------------------
# HTML index generator
# ---------------------------------------------------------------------------

def _generate_index_html(svg_files: list[str]) -> str:
    """Generate an HTML page that embeds all SVG screenshots for easy review."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SLS-CLI Visual Test Screenshots</title>
<style>
body {
    background: #1a1a2e;
    color: #e0e0e0;
    font-family: "SF Mono", "Fira Code", monospace;
    margin: 0;
    padding: 20px;
}
h1 {
    color: #ff5555;
    text-align: center;
    margin-bottom: 10px;
}
.subtitle {
    text-align: center;
    color: #888;
    margin-bottom: 40px;
}
.screenshot {
    margin: 30px auto;
    max-width: 1200px;
    background: #0f0f1a;
    border: 1px solid #333;
    border-radius: 8px;
    padding: 15px;
}
.screenshot h2 {
    color: #ffcc00;
    margin: 0 0 10px 0;
    font-size: 16px;
}
.screenshot object, .screenshot img {
    width: 100%;
    border-radius: 4px;
}
.toc {
    max-width: 800px;
    margin: 0 auto 40px auto;
    background: #0f0f1a;
    padding: 20px;
    border-radius: 8px;
    border: 1px solid #333;
}
.toc a {
    color: #5588ff;
    text-decoration: none;
    display: block;
    padding: 4px 0;
}
.toc a:hover { color: #88bbff; }
</style>
</head>
<body>
<h1>SLS-CLI Visual Test Screenshots</h1>
<p class="subtitle">Generated from ground truth data -- open SVGs individually for full quality</p>
<div class="toc">
<h2 style="color: #55ff55;">Table of Contents</h2>
"""

    # Sort files for consistent ordering
    svg_files_sorted = sorted(svg_files)

    for svg_path in svg_files_sorted:
        name = Path(svg_path).stem
        html += f'<a href="#{name}">{name}</a>\n'

    html += "</div>\n"

    for svg_path in svg_files_sorted:
        name = Path(svg_path).stem
        rel_path = Path(svg_path).name
        html += f"""
<div class="screenshot" id="{name}">
<h2>{name}</h2>
<object type="image/svg+xml" data="{rel_path}"></object>
</div>
"""

    html += """
</body>
</html>
"""
    return html


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main() -> None:
    print("=" * 60)
    print("  SLS-CLI Visual Screenshot Test")
    print("=" * 60)
    print(f"  Output: {SCREENSHOT_DIR}")
    print()

    # Load ground truth data
    print("Loading ground truth data...")
    try:
        responses_s1 = _load_raw(seed=1)
        print(f"  Seed 1: {len(responses_s1)} entries")
    except FileNotFoundError as e:
        print(f"  ERROR: {e}")
        print("  Run `python3 -m tests.ground_truth` first to generate data.")
        sys.exit(1)

    try:
        responses_s2 = _load_raw(seed=2)
        print(f"  Seed 2: {len(responses_s2)} entries")
    except FileNotFoundError:
        responses_s2 = []
        print("  Seed 2: not available (shop screenshots will be skipped)")

    all_paths: list[str] = []

    # --- Capture every screen type ---

    print("\n--- Character Select ---")
    all_paths.extend(await capture_character_select())

    print("\n--- Events (Neow + Random) ---")
    all_paths.extend(await capture_event_screens(responses_s1))

    print("\n--- Map ---")
    all_paths.extend(await capture_map_screens(responses_s1))

    print("\n--- Combat ---")
    all_paths.extend(await capture_combat_screens(responses_s1))

    print("\n--- Card Reward ---")
    all_paths.extend(await capture_card_reward_screens(responses_s1))

    print("\n--- Rest Site ---")
    all_paths.extend(await capture_rest_screens(responses_s1))

    print("\n--- Shop ---")
    all_paths.extend(await capture_shop_screens(responses_s2))

    print("\n--- Generic / Fallback ---")
    all_paths.extend(await capture_generic_screens(responses_s1))

    print("\n--- Combat Edge Cases ---")
    all_paths.extend(await capture_combat_edge_cases(responses_s1))

    print("\n--- Combat: Defect with Orbs ---")
    all_paths.extend(await capture_combat_defect_orbs(responses_s1))

    print("\n--- Combat: Necrobinder with Osty ---")
    all_paths.extend(await capture_combat_necrobinder_osty(responses_s1))

    print("\n--- Combat: Regent with Stars ---")
    all_paths.extend(await capture_combat_regent_stars(responses_s1))

    print("\n--- Deck Viewer Overlay ---")
    all_paths.extend(await capture_deck_viewer())

    print("\n--- Relic Viewer Overlay ---")
    all_paths.extend(await capture_relic_viewer())

    print("\n--- Global Help Overlay ---")
    all_paths.extend(await capture_global_help_overlay())

    print("\n--- Error Recovery Screen ---")
    all_paths.extend(await capture_error_recovery())

    print("\n--- Game Over / Victory / Defeat ---")
    all_paths.extend(await capture_game_over_screens())

    print("\n--- Shop Purchase Flow ---")
    all_paths.extend(await capture_shop_purchase_flow(responses_s2))

    # --- Chinese (zh) screenshots ---

    print("\n--- [ZH] Character Select ---")
    all_paths.extend(await capture_character_select_zh())

    print("\n--- [ZH] Events ---")
    all_paths.extend(await capture_event_screens_zh(responses_s1))

    print("\n--- [ZH] Map ---")
    all_paths.extend(await capture_map_screens_zh(responses_s1))

    print("\n--- [ZH] Combat ---")
    all_paths.extend(await capture_combat_screens_zh(responses_s1))

    print("\n--- [ZH] Card Reward ---")
    all_paths.extend(await capture_card_reward_screens_zh(responses_s1))

    print("\n--- [ZH] Rest Site ---")
    all_paths.extend(await capture_rest_screens_zh(responses_s1))

    print("\n--- [ZH] Shop ---")
    all_paths.extend(await capture_shop_screens_zh(responses_s2))

    # --- Generate index HTML ---
    index_html = _generate_index_html(all_paths)
    index_path = SCREENSHOT_DIR / "index.html"
    index_path.write_text(index_html)
    print(f"\n  Index page: {index_path}")

    # --- Summary ---
    print(f"\n{'=' * 60}")
    print(f"  DONE: {len(all_paths)} screenshots saved to {SCREENSHOT_DIR}")
    print(f"{'=' * 60}")
    print(f"\n  Open {index_path} in a browser to review all screenshots.")
    print("  Or open any individual .svg file directly.\n")

    # Optional: open in browser
    if "--open" in sys.argv:
        webbrowser.open(f"file://{index_path}")


if __name__ == "__main__":
    asyncio.run(main())
