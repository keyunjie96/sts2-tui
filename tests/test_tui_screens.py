"""Headless Textual tests for every TUI screen.

Uses real sts2-cli response data from ground_truth_data to ensure screens
render correctly and respond to keyboard input without crashing.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from textual.app import App

# ---------------------------------------------------------------------------
# Fixture: load real sts2-cli responses from seed_1_raw.json
# ---------------------------------------------------------------------------

GROUND_TRUTH_DIR = Path(__file__).parent / "ground_truth_data"
_GROUND_TRUTH_FILE = GROUND_TRUTH_DIR / "seed_1_raw.json"

# Skip the entire module at collection time if ground truth data is missing.
# Using skipif avoids the collection error that pytest.skip() causes at
# module level.
pytestmark = pytest.mark.skipif(
    not _GROUND_TRUTH_FILE.exists(),
    reason="seed_1_raw.json not found -- run ground truth generator first",
)


def _load_raw_responses() -> list[dict]:
    """Load all raw sts2-cli responses from seed_1_raw.json."""
    if not _GROUND_TRUTH_FILE.exists():
        pytest.skip("seed_1_raw.json not found")
    with open(_GROUND_TRUTH_FILE) as f:
        return json.load(f)


def _find_decision(responses: list[dict], decision_type: str) -> dict:
    """Find the first response with the given decision type."""
    for entry in responses:
        if isinstance(entry, dict) and entry.get("decision") == decision_type:
            return entry
    pytest.skip(f"No '{decision_type}' decision found in seed_1_raw.json")


# Preload all raw data once at module level (safe because pytestmark skips
# the module when the file is absent).
_RAW_RESPONSES: list[dict] = []
if _GROUND_TRUTH_FILE.exists():
    _RAW_RESPONSES = _load_raw_responses()


def _get_combat_state() -> dict:
    return _find_decision(_RAW_RESPONSES, "combat_play")


def _get_map_state() -> dict:
    return _find_decision(_RAW_RESPONSES, "map_select")


def _get_card_reward_state() -> dict:
    return _find_decision(_RAW_RESPONSES, "card_reward")


def _get_rest_state() -> dict:
    return _find_decision(_RAW_RESPONSES, "rest_site")


def _get_event_state() -> dict:
    return _find_decision(_RAW_RESPONSES, "event_choice")


# ---------------------------------------------------------------------------
# Mock controller that returns a next-state dict without any real bridge
# ---------------------------------------------------------------------------


def _make_mock_controller(next_state: dict | None = None) -> MagicMock:
    """Build a mock GameController.

    Every async method returns *next_state* (defaults to a simple map_select
    so screens can transition cleanly).
    """
    if next_state is None:
        next_state = _get_map_state()

    ctrl = MagicMock()
    for method_name in [
        "play_card",
        "end_turn",
        "choose",
        "select_map_node",
        "select_card_reward",
        "skip_card_reward",
        "use_potion",
        "proceed",
        "leave_room",
        "select_bundle",
        "select_cards",
        "skip_select",
        "get_state",
        "start_run",
        "quit",
    ]:
        setattr(ctrl, method_name, AsyncMock(return_value=next_state))
    # get_map returns a non-map response by default (triggers fallback rendering)
    ctrl.get_map = AsyncMock(return_value={"type": "error", "message": "mock"})
    return ctrl


# ---------------------------------------------------------------------------
# Harness apps -- each wraps a single screen so we can test in isolation
# ---------------------------------------------------------------------------

CSS_PATH = Path(__file__).parent.parent / "src" / "sts2_tui" / "tui" / "sls.tcss"


class CombatTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self.state = state
        self.controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.combat import CombatScreen
        self.push_screen(CombatScreen(self.state, controller=self.controller))


class MapTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self.state = state
        self.controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.map import MapScreen
        self.push_screen(MapScreen(self.state, controller=self.controller))


class CardRewardTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self.state = state
        self.controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.card_reward import CardRewardScreen
        self.push_screen(CardRewardScreen(self.state, controller=self.controller))


class RestTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self.state = state
        self.controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.rest import RestScreen
        self.push_screen(RestScreen(self.state, controller=self.controller))


class EventTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self.state = state
        self.controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.event import EventScreen
        self.push_screen(EventScreen(self.state, controller=self.controller))


class CharacterSelectTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.character_select import CharacterSelectScreen
        self.push_screen(CharacterSelectScreen())


class GenericTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self.state = state
        self.controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.generic import GenericScreen
        self.push_screen(GenericScreen(self.state, controller=self.controller))


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.asyncio
class TestCombatScreen:
    """Combat screen -- the most complex screen."""

    async def test_combat_screen_renders(self):
        """CombatScreen renders without exceptions."""
        state = _get_combat_state()
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Verify key widgets are present
            screen = app.screen
            assert screen.query("#combat-screen"), "Missing #combat-screen"
            assert screen.query("#top-bar"), "Missing #top-bar"
            assert screen.query("#enemy-area"), "Missing #enemy-area"
            assert screen.query("#hand-area"), "Missing #hand-area"
            assert screen.query("#player-stats"), "Missing #player-stats"
            assert screen.query("#pile-counts"), "Missing #pile-counts"
            assert screen.query("#relic-bar"), "Missing #relic-bar"

    async def test_combat_enemy_widgets(self):
        """Enemy widgets render with HP and intent."""
        state = _get_combat_state()
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            enemy_panels = app.screen.query(".enemy-panel")
            # Should have at least 1 enemy
            assert len(enemy_panels) > 0, "No enemy panels rendered"

    async def test_combat_card_widgets(self):
        """Card widgets render for the hand."""
        state = _get_combat_state()
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            card_widgets = app.screen.query(".card-widget")
            hand_size = len(state.get("hand", []))
            assert len(card_widgets) == hand_size, (
                f"Expected {hand_size} card widgets, got {len(card_widgets)}"
            )

    async def test_combat_select_card(self):
        """Pressing 1 selects the first card."""
        state = _get_combat_state()
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("1")
            await pilot.pause()
            # The screen should now have selected_card == 0
            from sts2_tui.tui.screens.combat import CombatScreen
            combat = app.screen
            if isinstance(combat, CombatScreen):
                assert combat.selected_card == 0

    async def test_combat_end_turn(self):
        """Pressing E triggers end turn."""
        state = _get_combat_state()
        # Return a new combat state so the screen stays in combat
        next_combat = dict(state)
        next_combat["round"] = 2
        ctrl = _make_mock_controller(next_combat)
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("e")
            await pilot.pause()
            ctrl.end_turn.assert_called_once()

    async def test_combat_cycle_target(self):
        """Pressing Tab cycles through targets."""
        # Use a state with multiple enemies if possible
        state = _get_combat_state()
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            # Should not crash even with one enemy

    async def test_combat_play_card_enter(self):
        """Pressing Enter after selecting a card plays it."""
        state = _get_combat_state()
        next_combat = dict(state)
        next_combat["round"] = 1
        ctrl = _make_mock_controller(next_combat)
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("1")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            ctrl.play_card.assert_called_once()


@pytest.mark.asyncio
class TestMapScreen:
    """Map screen -- path selection."""

    async def test_map_screen_renders(self):
        """MapScreen renders without exceptions."""
        state = _get_map_state()
        ctrl = _make_mock_controller()
        app = MapTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#map-screen"), "Missing #map-screen"
            assert app.screen.query("#map-header"), "Missing #map-header"
            assert app.screen.query("#map-footer"), "Missing #map-footer"

    async def test_map_choices_display(self):
        """Map choices are listed in the viewport."""
        state = _get_map_state()
        ctrl = _make_mock_controller()
        app = MapTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            viewport = app.screen.query_one("#map-viewport")
            assert viewport is not None

    async def test_map_select_path(self):
        """Pressing 1 selects the first path."""
        state = _get_map_state()
        # Return a combat state when a map node is selected
        next_state = _get_combat_state()
        ctrl = _make_mock_controller(next_state)
        app = MapTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("1")
            await pilot.pause()
            ctrl.select_map_node.assert_called_once()


@pytest.mark.asyncio
class TestCardRewardScreen:
    """Card reward screen."""

    async def test_card_reward_renders(self):
        """CardRewardScreen renders without exceptions."""
        state = _get_card_reward_state()
        ctrl = _make_mock_controller()
        app = CardRewardTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#card-reward-screen"), "Missing #card-reward-screen"
            assert app.screen.query("#reward-title"), "Missing #reward-title"
            assert app.screen.query("#reward-footer"), "Missing #reward-footer"

    async def test_card_reward_cards_display(self):
        """Reward cards render correctly."""
        state = _get_card_reward_state()
        ctrl = _make_mock_controller()
        app = CardRewardTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            cards = app.screen.query(".reward-card")
            expected = len(state.get("cards", []))
            assert len(cards) == expected, (
                f"Expected {expected} reward cards, got {len(cards)}"
            )

    async def test_card_reward_select(self):
        """Pressing 1 selects the first card."""
        state = _get_card_reward_state()
        ctrl = _make_mock_controller()
        app = CardRewardTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("1")
            await pilot.pause()
            from sts2_tui.tui.screens.card_reward import CardRewardScreen
            screen = app.screen
            if isinstance(screen, CardRewardScreen):
                assert screen.selected == 0

    async def test_card_reward_skip(self):
        """Pressing Escape skips the reward."""
        state = _get_card_reward_state()
        ctrl = _make_mock_controller()
        app = CardRewardTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            ctrl.skip_card_reward.assert_called_once()


@pytest.mark.asyncio
class TestRestScreen:
    """Rest site screen."""

    async def test_rest_screen_renders(self):
        """RestScreen renders without exceptions."""
        state = _get_rest_state()
        ctrl = _make_mock_controller()
        app = RestTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#rest-screen"), "Missing #rest-screen"
            assert app.screen.query("#rest-title"), "Missing #rest-title"
            assert app.screen.query("#rest-footer"), "Missing #rest-footer"

    async def test_rest_options_display(self):
        """Rest options render correctly."""
        state = _get_rest_state()
        ctrl = _make_mock_controller()
        app = RestTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            options = app.screen.query(".rest-option")
            expected = len(state.get("options", []))
            assert len(options) == expected, (
                f"Expected {expected} rest options, got {len(options)}"
            )

    async def test_rest_select_option(self):
        """Pressing 1 selects the first option."""
        state = _get_rest_state()
        ctrl = _make_mock_controller()
        app = RestTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("1")
            await pilot.pause()
            from sts2_tui.tui.screens.rest import RestScreen
            screen = app.screen
            if isinstance(screen, RestScreen):
                assert screen.selected == 0


@pytest.mark.asyncio
class TestEventScreen:
    """Event screen."""

    async def test_event_screen_renders(self):
        """EventScreen renders without exceptions."""
        state = _get_event_state()
        ctrl = _make_mock_controller()
        app = EventTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#event-screen"), "Missing #event-screen"
            assert app.screen.query("#rest-title"), "Missing #rest-title"
            assert app.screen.query("#rest-footer"), "Missing #rest-footer"

    async def test_event_options_display(self):
        """Event options render correctly."""
        state = _get_event_state()
        ctrl = _make_mock_controller()
        app = EventTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            options = app.screen.query(".rest-option")
            expected = len(state.get("options", []))
            assert len(options) == expected, (
                f"Expected {expected} event options, got {len(options)}"
            )

    async def test_event_select_option(self):
        """Pressing 1 selects the first option."""
        state = _get_event_state()
        ctrl = _make_mock_controller()
        app = EventTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("1")
            await pilot.pause()
            from sts2_tui.tui.screens.event import EventScreen
            screen = app.screen
            if isinstance(screen, EventScreen):
                assert screen.selected == 0


@pytest.mark.asyncio
class TestCharacterSelectScreen:
    """Character select screen."""

    async def test_character_select_renders(self):
        """CharacterSelectScreen renders without exceptions."""
        app = CharacterSelectTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#char-select-screen"), "Missing #char-select-screen"
            assert app.screen.query("#rest-title"), "Missing #rest-title"
            assert app.screen.query("#rest-footer"), "Missing #rest-footer"

    async def test_character_select_shows_all_characters(self):
        """All 5 character widgets are displayed."""
        app = CharacterSelectTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            chars = app.screen.query(".rest-option")
            assert len(chars) == 5, f"Expected 5 character widgets, got {len(chars)}"

    async def test_character_select_keyboard(self):
        """Pressing 1-5 selects different characters."""
        app = CharacterSelectTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("2")
            await pilot.pause()
            from sts2_tui.tui.screens.character_select import CharacterSelectScreen
            screen = app.screen
            if isinstance(screen, CharacterSelectScreen):
                assert screen.selected == 1


@pytest.mark.asyncio
class TestGenericScreen:
    """Generic fallback screen."""

    async def test_generic_screen_renders(self):
        """GenericScreen renders without exceptions."""
        state = {
            "type": "decision",
            "decision": "shop",
            "context": {"act": 1, "floor": 5},
            "options": [
                {"index": 0, "name": "Item A", "description": "Buy something"},
                {"index": 1, "name": "Item B", "description": "Buy something else"},
            ],
            "player": {
                "name": "Ironclad",
                "hp": 60,
                "max_hp": 80,
                "block": 0,
                "gold": 200,
                "relics": [],
                "potions": [],
                "deck_size": 12,
            },
        }
        ctrl = _make_mock_controller()
        app = GenericTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#generic-screen"), "Missing #generic-screen"

    async def test_generic_screen_no_options(self):
        """GenericScreen renders even with no options."""
        state = {
            "type": "decision",
            "decision": "unknown_type",
            "context": {"act": 1, "floor": 1},
            "player": {
                "name": "Ironclad",
                "hp": 80,
                "max_hp": 80,
                "block": 0,
                "gold": 99,
                "relics": [],
                "potions": [],
                "deck_size": 10,
            },
        }
        ctrl = _make_mock_controller()
        app = GenericTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#generic-screen"), "Missing #generic-screen"


@pytest.mark.asyncio
class TestHelpOverlay:
    """Help overlay for the combat screen."""

    async def test_help_overlay_renders(self):
        """Pressing ? in combat opens the help overlay."""
        state = _get_combat_state()
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            # Should have the help overlay
            assert app.screen.query("#help-overlay"), "Help overlay not shown"


@pytest.mark.asyncio
class TestCombatEdgeCases:
    """Edge cases and stress tests for the combat screen."""

    async def test_combat_empty_hand(self):
        """Combat with an empty hand does not crash."""
        state = dict(_get_combat_state())
        state["hand"] = []
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            cards = app.screen.query(".card-widget")
            assert len(cards) == 0

    async def test_combat_dead_enemies(self):
        """Combat with all dead enemies does not crash."""
        state = dict(_get_combat_state())
        # Set all enemies to 0 HP
        state["enemies"] = [
            {
                "index": 0, "name": "Dead Monster", "hp": 0, "max_hp": 40,
                "block": 0, "intents": [], "intends_attack": False,
                "powers": None,
            }
        ]
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Should render without crash

    async def test_combat_null_player_powers(self):
        """Combat with null player_powers does not crash."""
        state = dict(_get_combat_state())
        state["player_powers"] = None
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

    async def test_combat_multi_enemy(self):
        """Combat with multiple enemies renders all of them."""
        state = dict(_get_combat_state())
        state["enemies"] = [
            {
                "index": 0, "name": "Louse A", "hp": 16, "max_hp": 16,
                "block": 0, "intents": [{"type": "Attack", "damage": 6}],
                "intends_attack": True, "powers": None,
            },
            {
                "index": 1, "name": "Louse B", "hp": 12, "max_hp": 18,
                "block": 3, "intents": [{"type": "Debuff"}],
                "intends_attack": False, "powers": [{"name": "Curl Up", "amount": 3}],
            },
        ]
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            panels = app.screen.query(".enemy-panel")
            assert len(panels) == 2

    async def test_combat_rapid_card_selection(self):
        """Rapidly pressing card keys does not cause duplicate ID errors."""
        state = _get_combat_state()
        ctrl = _make_mock_controller(state)
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("1")
            await pilot.press("2")
            await pilot.press("3")
            await pilot.pause()
            # Should not crash

    async def test_combat_select_out_of_range_card(self):
        """Pressing 9 when there are only 5 cards does nothing."""
        state = _get_combat_state()
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("9")
            await pilot.pause()
            from sts2_tui.tui.screens.combat import CombatScreen
            screen = app.screen
            if isinstance(screen, CombatScreen):
                assert screen.selected_card == -1

    async def test_combat_enemy_with_block_and_powers(self):
        """Enemy with block and powers renders correctly."""
        state = dict(_get_combat_state())
        state["enemies"] = [
            {
                "index": 0, "name": "Elite Boss", "hp": 100, "max_hp": 100,
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
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            panels = app.screen.query(".enemy-panel")
            assert len(panels) == 1

    async def test_combat_player_with_potions(self):
        """Player with potions renders the top bar correctly."""
        state = dict(_get_combat_state())
        state["player"] = dict(state["player"])
        state["player"]["potions"] = [
            {"index": 0, "name": "Fire Potion", "description": "Deal 20 damage.",
             "target_type": "AnyEnemy"},
        ]
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

    async def test_combat_no_context(self):
        """Combat state with missing context does not crash."""
        state = dict(_get_combat_state())
        state.pop("context", None)
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()


@pytest.mark.asyncio
class TestMapEdgeCases:
    """Edge cases for the map screen."""

    async def test_map_no_choices(self):
        """Map with empty choices renders without crash."""
        state = dict(_get_map_state())
        state["choices"] = []
        ctrl = _make_mock_controller()
        app = MapTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

    async def test_map_out_of_range_selection(self):
        """Pressing 9 when there are only 4 paths shows warning."""
        state = _get_map_state()
        ctrl = _make_mock_controller()
        app = MapTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("9")
            await pilot.pause()
            # Should not crash, and select_map_node should not be called
            ctrl.select_map_node.assert_not_called()

    async def test_map_no_boss(self):
        """Map without boss info renders without crash."""
        state = dict(_get_map_state())
        state["context"] = {"act": 1, "floor": 1}
        ctrl = _make_mock_controller()
        app = MapTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()


@pytest.mark.asyncio
class TestCardRewardEdgeCases:
    """Edge cases for the card reward screen."""

    async def test_card_reward_no_cards(self):
        """Card reward with empty cards list renders without crash."""
        state = dict(_get_card_reward_state())
        state["cards"] = []
        ctrl = _make_mock_controller()
        app = CardRewardTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

    async def test_card_reward_select_then_confirm(self):
        """Select a card then confirm with Enter does not cause duplicate ID."""
        state = _get_card_reward_state()
        ctrl = _make_mock_controller()
        app = CardRewardTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("1")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            ctrl.select_card_reward.assert_called_once()


@pytest.mark.asyncio
class TestEventEdgeCases:
    """Edge cases for the event screen."""

    async def test_event_no_options(self):
        """Event with empty options list renders without crash."""
        state = dict(_get_event_state())
        state["options"] = []
        ctrl = _make_mock_controller()
        app = EventTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

    async def test_event_locked_option(self):
        """Selecting a locked option does nothing."""
        state = dict(_get_event_state())
        state["options"] = [
            {"index": 0, "title": "Locked Choice", "description": "Cannot choose.",
             "is_locked": True, "vars": None},
        ]
        ctrl = _make_mock_controller()
        app = EventTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("1")
            await pilot.pause()
            from sts2_tui.tui.screens.event import EventScreen
            screen = app.screen
            if isinstance(screen, EventScreen):
                assert screen.selected == -1  # Should not select locked option

    async def test_event_with_template_vars(self):
        """Event option with template variables renders correctly."""
        state = dict(_get_event_state())
        state["options"] = [
            {
                "index": 0, "title": "Test Option",
                "description": "Gain {Gold} gold and {Cards} {Cards:plural:card|cards}.",
                "is_locked": False,
                "vars": {"Gold": 50, "Cards": 3},
            },
        ]
        ctrl = _make_mock_controller()
        app = EventTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()


@pytest.mark.asyncio
class TestCharacterSelectEdgeCases:
    """Edge cases for the character select screen."""

    async def test_character_rapid_selection(self):
        """Rapidly changing character selection does not cause duplicate ID."""
        app = CharacterSelectTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("1")
            await pilot.press("2")
            await pilot.press("3")
            await pilot.press("4")
            await pilot.press("5")
            await pilot.pause()
            from sts2_tui.tui.screens.character_select import CharacterSelectScreen
            screen = app.screen
            if isinstance(screen, CharacterSelectScreen):
                assert screen.selected == 4


class TestResolveCardDescription:
    """Unit tests for resolve_card_description template resolution."""

    def test_resolve_damage(self):
        """Damage template resolves correctly."""
        from sts2_tui.tui.controller import resolve_card_description
        desc = "Deal {Damage:diff()} damage."
        stats = {"damage": 6}
        assert resolve_card_description(desc, stats) == "Deal 6 damage."

    def test_resolve_block(self):
        """Block template resolves correctly."""
        from sts2_tui.tui.controller import resolve_card_description
        desc = "Gain {Block:diff()} Block."
        stats = {"block": 5}
        assert resolve_card_description(desc, stats) == "Gain 5 Block."

    def test_resolve_multiple_vars(self):
        """Multiple template vars in one description resolve correctly."""
        from sts2_tui.tui.controller import resolve_card_description
        desc = "Deal {Damage:diff()} damage.\nApply {VulnerablePower:diff()} Vulnerable."
        stats = {"damage": 8, "vulnerablepower": 2}
        assert resolve_card_description(desc, stats) == "Deal 8 damage.\nApply 2 Vulnerable."

    def test_resolve_hploss_and_block(self):
        """HpLoss + Block template (Blood Wall) resolves correctly."""
        from sts2_tui.tui.controller import resolve_card_description
        desc = "Lose {HpLoss:diff()} HP.\nGain {Block:diff()} Block."
        stats = {"hploss": 2, "block": 16}
        assert resolve_card_description(desc, stats) == "Lose 2 HP.\nGain 16 Block."

    def test_resolve_power_var(self):
        """Power template (Juggernaut) resolves correctly."""
        from sts2_tui.tui.controller import resolve_card_description
        desc = "Whenever you gain Block, deal {JuggernautPower:diff()} damage to a random enemy."
        stats = {"juggernautpower": 5}
        assert resolve_card_description(desc, stats) == "Whenever you gain Block, deal 5 damage to a random enemy."

    def test_resolve_no_stats(self):
        """Description without stats returns cleaned text."""
        from sts2_tui.tui.controller import resolve_card_description
        desc = "Double the enemy's Vulnerable."
        assert resolve_card_description(desc, {}) == "Double the enemy's Vulnerable."
        assert resolve_card_description(desc, None) == "Double the enemy's Vulnerable."

    def test_resolve_empty_description(self):
        """Empty description returns empty string."""
        from sts2_tui.tui.controller import resolve_card_description
        assert resolve_card_description("", {"damage": 6}) == ""

    def test_resolve_strips_bbcode(self):
        """BBCode tags are stripped from descriptions."""
        from sts2_tui.tui.controller import resolve_card_description
        desc = "[b]Deal[/b] {Damage:diff()} [color=#ff0000]damage[/color]."
        stats = {"damage": 10}
        assert resolve_card_description(desc, stats) == "Deal 10 damage."

    def test_resolve_unmatched_var_preserved(self):
        """Template vars without matching stats show 'X' placeholder."""
        from sts2_tui.tui.controller import resolve_card_description
        desc = "Deal {Damage:diff()} damage. Apply {UnknownVar:diff()} stacks."
        stats = {"damage": 6}
        result = resolve_card_description(desc, stats)
        assert "Deal 6 damage." in result
        # Unmatched variables with formatters show "X" to avoid garbled text
        # like "Apply UnknownVar stacks" -- "X" is the universal placeholder
        assert "Apply X stacks." in result

    def test_extract_hand_resolves_descriptions(self):
        """extract_hand resolves template descriptions for all cards."""
        from sts2_tui.tui.controller import extract_hand
        state = _get_combat_state()
        hand = extract_hand(state)
        for card in hand:
            desc = card["description"]
            # No card in hand should still have unresolved {Var:diff()} templates
            # if the stats dict contained the matching key
            assert "{Damage:diff()}" not in desc, (
                f"Card '{card['name']}' has unresolved Damage template: {desc}"
            )
            assert "{Block:diff()}" not in desc, (
                f"Card '{card['name']}' has unresolved Block template: {desc}"
            )

    def test_card_reward_descriptions_resolvable(self):
        """Card reward descriptions can be resolved using stats."""
        from sts2_tui.tui.controller import resolve_card_description
        state = _get_card_reward_state()
        for card in state.get("cards", []):
            stats = card.get("stats", {}) or {}
            raw_desc = card.get("description", "")
            resolved = resolve_card_description(raw_desc, stats)
            # Verify known templates are resolved
            if stats.get("damage") is not None:
                assert "{Damage:diff()}" not in resolved, (
                    f"Card '{card.get('name')}' has unresolved Damage: {resolved}"
                )
            if stats.get("block") is not None:
                assert "{Block:diff()}" not in resolved, (
                    f"Card '{card.get('name')}' has unresolved Block: {resolved}"
                )


@pytest.mark.asyncio
class TestFullAppFlow:
    """Integration: start SlsApp with a mock bridge."""

    async def test_app_starts_headless(self):
        """SlsApp starts headlessly without the real engine."""
        from sts2_tui.tui.app import SlsApp
        app = SlsApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # The app will show an error because sts2-cli is not available,
            # but it should not crash.
            # Just verify the app is running and has a screen
            assert app.screen is not None
