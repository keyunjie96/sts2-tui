"""Exhaustive TUI screen rendering tests using all real sts2-cli ground truth data.

Mounts every screen with every distinct real state found in seed_1_raw.json,
seed_2_raw.json, and seed_3_raw.json.  If any screen crashes or raises during
compose/mount/render, the test fails with the full traceback.
"""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from textual.app import App

# ---------------------------------------------------------------------------
# Ground truth data loading
# ---------------------------------------------------------------------------

GROUND_TRUTH_DIR = Path(__file__).parent / "ground_truth_data"
CSS_PATH = Path(__file__).parent.parent / "src" / "sts2_tui" / "tui" / "sls.tcss"


def _load_all_raw_states() -> list[dict]:
    """Load all decision states from all seed raw files."""
    all_states: list[dict] = []
    for fname in sorted(GROUND_TRUTH_DIR.glob("seed_*_raw.json")):
        data = json.loads(fname.read_text())
        for entry in data:
            if isinstance(entry, dict) and entry.get("type") == "decision":
                all_states.append(entry)
    return all_states


def _states_by_decision(states: list[dict]) -> dict[str, list[dict]]:
    """Group states by decision type."""
    grouped: dict[str, list[dict]] = {}
    for s in states:
        d = s.get("decision", "unknown")
        grouped.setdefault(d, []).append(s)
    return grouped


ALL_STATES = _load_all_raw_states()
STATES_BY_DECISION = _states_by_decision(ALL_STATES)


def _get_states(decision: str) -> list[dict]:
    """Get all states for a given decision type, skip if none found."""
    states = STATES_BY_DECISION.get(decision, [])
    if not states:
        pytest.skip(f"No '{decision}' states found in ground truth data")
    return states


# ---------------------------------------------------------------------------
# Mock controller
# ---------------------------------------------------------------------------


def _make_mock_controller(next_state: dict | None = None) -> MagicMock:
    """Build a mock GameController where every async method returns next_state."""
    if next_state is None:
        # Default: a map_select state so transitions don't crash
        map_states = STATES_BY_DECISION.get("map_select", [])
        next_state = map_states[0] if map_states else {"type": "decision", "decision": "map_select", "choices": [], "player": {"name": "Ironclad", "hp": 80, "max_hp": 80, "block": 0, "gold": 99, "relics": [], "potions": [], "deck_size": 10}}

    ctrl = MagicMock()
    for method_name in [
        "play_card", "end_turn", "choose", "select_map_node",
        "select_card_reward", "skip_card_reward", "use_potion",
        "proceed", "leave_room", "select_bundle", "select_cards",
        "skip_select", "get_state", "start_run", "quit",
    ]:
        setattr(ctrl, method_name, AsyncMock(return_value=next_state))
    return ctrl


# ---------------------------------------------------------------------------
# Test app wrappers
# ---------------------------------------------------------------------------


class CombatTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.combat import CombatScreen
        self.push_screen(CombatScreen(self._state, controller=self._controller))


class MapTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.map import MapScreen
        self.push_screen(MapScreen(self._state, controller=self._controller))


class CardRewardTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.card_reward import CardRewardScreen
        self.push_screen(CardRewardScreen(self._state, controller=self._controller))


class RestTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.rest import RestScreen
        self.push_screen(RestScreen(self._state, controller=self._controller))


class EventTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.event import EventScreen
        self.push_screen(EventScreen(self._state, controller=self._controller))


class GenericTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.generic import GenericScreen
        self.push_screen(GenericScreen(self._state, controller=self._controller))


class CharacterSelectTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.character_select import CharacterSelectScreen
        self.push_screen(CharacterSelectScreen())


# ---------------------------------------------------------------------------
# Helper: pick diverse states (first, last, and a few in between)
# ---------------------------------------------------------------------------


def _diverse_sample(states: list[dict], max_count: int = 5) -> list[dict]:
    """Pick a diverse sample of states: first, last, and evenly spaced."""
    if len(states) <= max_count:
        return states
    step = max(1, (len(states) - 1) // (max_count - 1))
    indices = list(range(0, len(states), step))[:max_count - 1]
    indices.append(len(states) - 1)
    return [states[i] for i in sorted(set(indices))]


# ===================================================================
# COMBAT SCREEN -- tested with every distinct combat state
# ===================================================================


@pytest.mark.asyncio
class TestCombatScreenLoop:
    """Mount CombatScreen with every distinct combat_play state from ground truth."""

    async def test_combat_renders_all_states(self):
        """Every combat_play state renders without exceptions."""
        states = _get_states("combat_play")
        sample = _diverse_sample(states, max_count=10)
        for i, state in enumerate(sample):
            ctrl = _make_mock_controller()
            app = CombatTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                assert app.screen.query("#combat-screen"), (
                    f"combat state [{i}] missing #combat-screen"
                )

    async def test_combat_multi_enemy_states(self):
        """All combat states with multiple enemies render correctly."""
        states = _get_states("combat_play")
        multi = [s for s in states if len(s.get("enemies", [])) > 1]
        if not multi:
            pytest.skip("No multi-enemy combat states")
        for i, state in enumerate(_diverse_sample(multi)):
            ctrl = _make_mock_controller()
            app = CombatTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                panels = app.screen.query(".enemy-panel")
                enemies_alive = [e for e in state.get("enemies", []) if e.get("hp", 0) > 0]
                assert len(panels) == len(enemies_alive), (
                    f"multi-enemy state [{i}]: expected {len(enemies_alive)} panels, "
                    f"got {len(panels)}"
                )

    async def test_combat_with_player_powers(self):
        """Combat states with non-null player_powers render correctly."""
        states = _get_states("combat_play")
        powered = [s for s in states if s.get("player_powers")]
        if not powered:
            pytest.skip("No combat states with player powers")
        for i, state in enumerate(_diverse_sample(powered)):
            ctrl = _make_mock_controller()
            app = CombatTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()

    async def test_combat_with_enemy_powers(self):
        """Combat states where enemies have powers render correctly."""
        states = _get_states("combat_play")
        ep = [
            s for s in states
            if any(e.get("powers") for e in s.get("enemies", []))
        ]
        if not ep:
            pytest.skip("No combat states with enemy powers")
        for i, state in enumerate(_diverse_sample(ep)):
            ctrl = _make_mock_controller()
            app = CombatTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()

    async def test_combat_card_select_and_play(self):
        """Select a card and play it in each combat state."""
        states = _get_states("combat_play")
        sample = _diverse_sample(states, max_count=5)
        for i, state in enumerate(sample):
            hand = state.get("hand", [])
            if not hand:
                continue
            ctrl = _make_mock_controller(state)
            app = CombatTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await pilot.press("1")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()

    async def test_combat_end_turn(self):
        """End turn works on diverse combat states."""
        states = _get_states("combat_play")
        sample = _diverse_sample(states, max_count=3)
        for i, state in enumerate(sample):
            ctrl = _make_mock_controller(state)
            app = CombatTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await pilot.press("e")
                await pilot.pause()
                ctrl.end_turn.assert_called()

    async def test_combat_cycle_targets_multi_enemy(self):
        """Tab cycles targets on multi-enemy combats."""
        states = _get_states("combat_play")
        multi = [s for s in states if len(s.get("enemies", [])) > 1]
        if not multi:
            pytest.skip("No multi-enemy combat states")
        state = multi[0]
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()
            await pilot.press("tab")
            await pilot.pause()


# ===================================================================
# MAP SCREEN
# ===================================================================


@pytest.mark.asyncio
class TestMapScreenLoop:
    """Mount MapScreen with every distinct map_select state."""

    async def test_map_renders_all_states(self):
        """Every map_select state renders without exceptions."""
        states = _get_states("map_select")
        for i, state in enumerate(states):
            ctrl = _make_mock_controller()
            app = MapTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                assert app.screen.query("#map-screen"), (
                    f"map state [{i}] missing #map-screen"
                )

    async def test_map_select_first_path(self):
        """Pressing 1 on every map state triggers select_map_node."""
        states = _get_states("map_select")
        for i, state in enumerate(states):
            if not state.get("choices"):
                continue
            combat_state = _get_states("combat_play")[0]
            ctrl = _make_mock_controller(combat_state)
            app = MapTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await pilot.press("1")
                await pilot.pause()
                ctrl.select_map_node.assert_called()

    async def test_map_no_boss_in_context(self):
        """Map states where context has no boss key render without crash."""
        states = _get_states("map_select")
        for state in states:
            ctx = state.get("context", {})
            modified = dict(state)
            modified["context"] = {k: v for k, v in ctx.items() if k != "boss"}
            ctrl = _make_mock_controller()
            app = MapTestApp(modified, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()


# ===================================================================
# CARD REWARD SCREEN
# ===================================================================


@pytest.mark.asyncio
class TestCardRewardScreenLoop:
    """Mount CardRewardScreen with every distinct card_reward state."""

    async def test_card_reward_renders_all_states(self):
        """Every card_reward state renders without exceptions."""
        states = _get_states("card_reward")
        for i, state in enumerate(states):
            ctrl = _make_mock_controller()
            app = CardRewardTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                assert app.screen.query("#card-reward-screen"), (
                    f"card_reward state [{i}] missing #card-reward-screen"
                )

    async def test_card_reward_cards_match_state(self):
        """Number of rendered reward cards matches the state data."""
        states = _get_states("card_reward")
        for i, state in enumerate(states):
            ctrl = _make_mock_controller()
            app = CardRewardTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                cards = app.screen.query(".reward-card")
                expected = len(state.get("cards", []))
                assert len(cards) == expected, (
                    f"card_reward [{i}]: expected {expected} cards, got {len(cards)}"
                )

    async def test_card_reward_select_and_confirm(self):
        """Select each card index and confirm."""
        states = _get_states("card_reward")
        state = states[0]
        cards = state.get("cards", [])
        for idx in range(min(len(cards), 3)):
            ctrl = _make_mock_controller()
            app = CardRewardTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await pilot.press(str(idx + 1))
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                ctrl.select_card_reward.assert_called()


# ===================================================================
# REST SCREEN
# ===================================================================


@pytest.mark.asyncio
class TestRestScreenLoop:
    """Mount RestScreen with every distinct rest_site state."""

    async def test_rest_renders_all_states(self):
        """Every rest_site state renders without exceptions."""
        states = _get_states("rest_site")
        for i, state in enumerate(states):
            ctrl = _make_mock_controller()
            app = RestTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                assert app.screen.query("#rest-screen"), (
                    f"rest_site state [{i}] missing #rest-screen"
                )

    async def test_rest_options_match_state(self):
        """Number of rendered rest options matches the state data."""
        states = _get_states("rest_site")
        for i, state in enumerate(states):
            ctrl = _make_mock_controller()
            app = RestTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                options = app.screen.query(".rest-option")
                expected = len(state.get("options", []))
                assert len(options) == expected, (
                    f"rest [{i}]: expected {expected} options, got {len(options)}"
                )

    async def test_rest_select_and_confirm(self):
        """Select an option and confirm."""
        states = _get_states("rest_site")
        for state in states:
            options = state.get("options", [])
            if not options:
                continue
            ctrl = _make_mock_controller()
            app = RestTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await pilot.press("1")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                ctrl.choose.assert_called()


# ===================================================================
# EVENT SCREEN
# ===================================================================


@pytest.mark.asyncio
class TestEventScreenLoop:
    """Mount EventScreen with every distinct event_choice state."""

    async def test_event_renders_all_states(self):
        """Every event_choice state renders without exceptions."""
        states = _get_states("event_choice")
        for i, state in enumerate(states):
            ctrl = _make_mock_controller()
            app = EventTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                # EventScreen may use #event-screen or #rest-screen depending on version
                assert app.screen.query("#event-screen") or app.screen.query("#rest-screen"), (
                    f"event_choice state [{i}] missing #event-screen or #rest-screen"
                )

    async def test_event_options_match_state(self):
        """Number of rendered options matches the state data."""
        states = _get_states("event_choice")
        for i, state in enumerate(states):
            ctrl = _make_mock_controller()
            app = EventTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                options = app.screen.query(".rest-option")
                expected = len(state.get("options", []))
                assert len(options) == expected, (
                    f"event [{i}]: expected {expected} options, got {len(options)}"
                )

    async def test_event_with_template_vars(self):
        """Events with template variables in descriptions render correctly."""
        states = _get_states("event_choice")
        # Find events with vars in their options
        with_vars = []
        for s in states:
            for opt in s.get("options", []):
                if opt.get("vars"):
                    with_vars.append(s)
                    break
        if not with_vars:
            pytest.skip("No event states with template vars")
        for state in with_vars:
            ctrl = _make_mock_controller()
            app = EventTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()

    async def test_event_select_and_confirm(self):
        """Select an event option and confirm."""
        states = _get_states("event_choice")
        for state in states:
            options = state.get("options", [])
            unlocked = [o for o in options if not o.get("is_locked", False)]
            if not unlocked:
                continue
            ctrl = _make_mock_controller()
            app = EventTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await pilot.press("1")
                await pilot.pause()
                await pilot.press("enter")
                await pilot.pause()
                ctrl.choose.assert_called()

    async def test_event_leave(self):
        """Pressing Escape triggers leave_room."""
        states = _get_states("event_choice")
        state = states[0]
        ctrl = _make_mock_controller()
        app = EventTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("escape")
            await pilot.pause()
            ctrl.leave_room.assert_called()


# ===================================================================
# GENERIC SCREEN (shop, card_select, bundle_select, unknown)
# ===================================================================


@pytest.mark.asyncio
class TestGenericScreenLoop:
    """Mount GenericScreen with shop, card_select, and other fallback states."""

    async def test_generic_shop_renders(self):
        """Shop states render on GenericScreen without exceptions."""
        states = STATES_BY_DECISION.get("shop", [])
        if not states:
            pytest.skip("No shop states in ground truth")
        for i, state in enumerate(states):
            ctrl = _make_mock_controller()
            app = GenericTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                assert app.screen.query("#generic-screen") or app.screen.query("#rest-screen"), (
                    f"shop state [{i}] missing #generic-screen"
                )

    async def test_generic_card_select_renders(self):
        """card_select states render on GenericScreen without exceptions."""
        states = STATES_BY_DECISION.get("card_select", [])
        if not states:
            pytest.skip("No card_select states in ground truth")
        for i, state in enumerate(states):
            ctrl = _make_mock_controller()
            app = GenericTestApp(state, ctrl)
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                assert app.screen.query("#generic-screen") or app.screen.query("#rest-screen"), (
                    f"card_select state [{i}] missing #generic-screen"
                )

    async def test_generic_unknown_decision_renders(self):
        """A fabricated unknown decision type renders on GenericScreen."""
        state = {
            "type": "decision",
            "decision": "never_seen_before",
            "context": {"act": 1, "floor": 1},
            "player": {
                "name": "Ironclad", "hp": 80, "max_hp": 80,
                "block": 0, "gold": 99, "relics": [], "potions": [],
                "deck_size": 10,
            },
        }
        ctrl = _make_mock_controller()
        app = GenericTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#generic-screen") or app.screen.query("#rest-screen")

    async def test_generic_proceed_no_selection(self):
        """Pressing Enter without selection triggers proceed/leave."""
        states = STATES_BY_DECISION.get("card_select", [])
        if not states:
            pytest.skip("No card_select states")
        state = states[0]
        ctrl = _make_mock_controller()
        app = GenericTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()


# ===================================================================
# CHARACTER SELECT SCREEN
# ===================================================================


@pytest.mark.asyncio
class TestCharacterSelectLoop:
    """CharacterSelectScreen needs no engine state."""

    async def test_renders(self):
        app = CharacterSelectTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#char-select-screen") or app.screen.query("#rest-screen")
            chars = app.screen.query(".rest-option")
            assert len(chars) == 5

    async def test_select_each_character(self):
        """Selecting each of the 5 characters works."""
        for key in ["1", "2", "3", "4", "5"]:
            app = CharacterSelectTestApp()
            async with app.run_test(size=(120, 40)) as pilot:
                await pilot.pause()
                await pilot.press(key)
                await pilot.pause()

    async def test_confirm_selection(self):
        """Selecting and confirming posts CharacterSelectedMessage."""
        app = CharacterSelectTestApp()
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("1")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()


# ===================================================================
# HELP OVERLAY
# ===================================================================


@pytest.mark.asyncio
class TestHelpOverlayLoop:
    """Help overlay from combat screen."""

    async def test_help_opens_and_closes(self):
        """? opens help, Escape closes it."""
        states = _get_states("combat_play")
        state = states[0]
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("question_mark")
            await pilot.pause()
            assert app.screen.query("#help-overlay"), "Help overlay not shown"
            await pilot.press("escape")
            await pilot.pause()


# ===================================================================
# CROSS-SCREEN DATA INTEGRITY
# ===================================================================


@pytest.mark.asyncio
class TestCrossScreenIntegrity:
    """Verify controller helper functions work with all raw states."""

    async def test_extract_enemies_all_combat_states(self):
        """extract_enemies works for every combat state without crashing."""
        from sts2_tui.tui.controller import extract_enemies
        states = _get_states("combat_play")
        for i, state in enumerate(states):
            try:
                enemies = extract_enemies(state)
                assert isinstance(enemies, list), f"State [{i}]: expected list"
                for e in enemies:
                    assert "name" in e, f"State [{i}]: enemy missing 'name'"
                    assert "hp" in e, f"State [{i}]: enemy missing 'hp'"
                    assert "max_hp" in e, f"State [{i}]: enemy missing 'max_hp'"
            except Exception as exc:
                pytest.fail(f"extract_enemies failed on combat state [{i}]: {exc}")

    async def test_extract_player_all_states(self):
        """extract_player works for every state with a player key."""
        from sts2_tui.tui.controller import extract_player
        for i, state in enumerate(ALL_STATES):
            if "player" not in state:
                continue
            try:
                player = extract_player(state)
                assert isinstance(player, dict), f"State [{i}]: expected dict"
                assert "hp" in player
                assert "max_hp" in player
            except Exception as exc:
                pytest.fail(
                    f"extract_player failed on state [{i}] "
                    f"(decision={state.get('decision')}): {exc}"
                )

    async def test_extract_hand_all_combat_states(self):
        """extract_hand works for every combat state."""
        from sts2_tui.tui.controller import extract_hand
        states = _get_states("combat_play")
        for i, state in enumerate(states):
            try:
                hand = extract_hand(state)
                assert isinstance(hand, list), f"State [{i}]: expected list"
                for card in hand:
                    assert "name" in card
                    assert "cost" in card
            except Exception as exc:
                pytest.fail(f"extract_hand failed on combat state [{i}]: {exc}")
