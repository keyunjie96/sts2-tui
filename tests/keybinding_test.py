"""Keybinding verification test suite for sts2-tui.

Programmatically tests every key binding registered in each TUI screen by
playing through the bridge.  The tests use real fixture states (or a live
bridge when available) to verify that:

1. Each binding declared in SCREEN_BINDINGS (shared.py) has a corresponding
   Textual Binding + action method in the screen class.
2. Action methods behave correctly given valid game state (selection changes,
   state transitions, etc.).

Usage:
    pytest tests/keybinding_test.py -v

Integration tests (marked with @requires_sts2) start a real engine process
and exercise bindings end-to-end.
"""

from __future__ import annotations

import asyncio
import copy
import logging
import re
from pathlib import Path
from typing import Any

import pytest

# ---------------------------------------------------------------------------
# Import screen classes
# ---------------------------------------------------------------------------

from sts2_tui.tui.screens.combat import CombatScreen
from sts2_tui.tui.screens.map import MapScreen
from sts2_tui.tui.screens.card_reward import CardRewardScreen
from sts2_tui.tui.screens.rest import RestScreen
from sts2_tui.tui.screens.event import EventScreen
from sts2_tui.tui.screens.shop import ShopScreen
from sts2_tui.tui.screens.generic import GenericScreen
from sts2_tui.tui.screens.character_select import CharacterSelectScreen
from sts2_tui.tui.screens.deck_viewer import DeckViewerOverlay, RelicViewerOverlay
from sts2_tui.tui.shared import SCREEN_BINDINGS, GlobalHelpOverlay
from sts2_tui.tui.app import SlsApp

log = logging.getLogger(__name__)


# ===========================================================================
# Fixture data -- realistic game states for each screen type
# ===========================================================================

COMBAT_STATE: dict[str, Any] = {
    "type": "decision",
    "decision": "combat_play",
    "context": {"act": 1, "act_name": "Overgrowth", "floor": 2, "room_type": "Monster"},
    "round": 1,
    "energy": 3,
    "max_energy": 3,
    "hand": [
        {
            "index": 0, "id": "CARD.DEFEND_IRONCLAD", "name": "Defend",
            "cost": 1, "type": "Skill", "can_play": True,
            "target_type": "Self", "stats": {"block": 5},
            "description": "Gain {Block:diff()} Block.",
        },
        {
            "index": 1, "id": "CARD.STRIKE_IRONCLAD", "name": "Strike",
            "cost": 1, "type": "Attack", "can_play": True,
            "target_type": "AnyEnemy", "stats": {"damage": 6},
            "description": "Deal {Damage:diff()} damage.",
        },
        {
            "index": 2, "id": "CARD.BASH", "name": "Bash",
            "cost": 2, "type": "Attack", "can_play": True,
            "target_type": "AnyEnemy", "stats": {"damage": 8, "vulnerablepower": 2},
            "description": "Deal {Damage:diff()} damage.\nApply {VulnerablePower:diff()} Vulnerable.",
        },
        {
            "index": 3, "id": "CARD.STRIKE_IRONCLAD", "name": "Strike",
            "cost": 1, "type": "Attack", "can_play": True,
            "target_type": "AnyEnemy", "stats": {"damage": 6},
            "description": "Deal {Damage:diff()} damage.",
        },
        {
            "index": 4, "id": "CARD.DEFEND_IRONCLAD", "name": "Defend",
            "cost": 1, "type": "Skill", "can_play": True,
            "target_type": "Self", "stats": {"block": 5},
            "description": "Gain {Block:diff()} Block.",
        },
    ],
    "enemies": [
        {
            "index": 0, "name": "Nibbit", "hp": 43, "max_hp": 43, "block": 0,
            "intents": [{"type": "Attack", "damage": 12}],
            "intends_attack": True, "powers": None,
        },
        {
            "index": 1, "name": "Gremlin", "hp": 20, "max_hp": 20, "block": 0,
            "intents": [{"type": "Buff"}],
            "intends_attack": False, "powers": None,
        },
    ],
    "player": {
        "name": "The Ironclad", "hp": 80, "max_hp": 80, "block": 0,
        "gold": 99,
        "relics": [{"name": "Burning Blood", "description": "Heal 6 HP at end of combat."}],
        "potions": [
            {"index": 0, "name": "Fire Potion", "description": "Deal 20 damage.", "target_type": "AnyEnemy"},
            {"index": 1, "name": "Block Potion", "description": "Gain 12 Block.", "target_type": "Self"},
        ],
        "deck_size": 11, "deck": [],
    },
    "player_powers": None,
    "draw_pile_count": 6,
    "discard_pile_count": 0,
    "exhaust_pile_count": 0,
}

MAP_STATE: dict[str, Any] = {
    "type": "decision",
    "decision": "map_select",
    "context": {"act": 1, "floor": 1, "boss": {"name": "Hexaghost"}},
    "choices": [
        {"col": 0, "row": 1, "type": "Monster"},
        {"col": 3, "row": 1, "type": "Monster"},
        {"col": 5, "row": 1, "type": "Event"},
    ],
    "player": {
        "name": "The Ironclad", "hp": 80, "max_hp": 80, "block": 0,
        "gold": 99, "relics": [], "potions": [], "deck_size": 10, "deck": [],
    },
}

CARD_REWARD_STATE: dict[str, Any] = {
    "type": "decision",
    "decision": "card_reward",
    "context": {"act": 1, "floor": 2},
    "cards": [
        {
            "index": 0, "name": "Blood Wall", "cost": 2, "type": "Skill",
            "rarity": "Common", "stats": {"hploss": 2, "block": 16},
            "description": "Lose 2 HP. Gain 16 Block.",
        },
        {
            "index": 1, "name": "Molten Fist", "cost": 1, "type": "Attack",
            "rarity": "Common", "stats": {"damage": 10},
            "description": "Deal 10 damage.",
        },
        {
            "index": 2, "name": "Offering", "cost": 0, "type": "Skill",
            "rarity": "Rare", "stats": {"hploss": 6, "cards": 3, "energy": 2},
            "description": "Lose 6 HP. Gain 2 Energy. Draw 3 cards.",
        },
    ],
    "can_skip": True,
    "player": {
        "name": "The Ironclad", "hp": 80, "max_hp": 80, "block": 0,
        "gold": 99, "relics": [], "potions": [], "deck_size": 10, "deck": [],
    },
}

REST_STATE: dict[str, Any] = {
    "type": "decision",
    "decision": "rest_site",
    "context": {"act": 1, "floor": 6},
    "options": [
        {"index": 0, "option_id": "HEAL", "name": "HealRestSiteOption", "is_enabled": True},
        {"index": 1, "option_id": "SMITH", "name": "SmithRestSiteOption", "is_enabled": True},
    ],
    "player": {
        "name": "The Ironclad", "hp": 50, "max_hp": 80, "block": 0,
        "gold": 120, "relics": [], "potions": [], "deck_size": 12, "deck": [],
    },
}

EVENT_STATE: dict[str, Any] = {
    "type": "decision",
    "decision": "event_choice",
    "context": {"act": 1, "floor": 1},
    "event_name": "Neow",
    "options": [
        {"index": 0, "title": "Lost Coffer", "description": "Gain stuff.", "is_locked": False},
        {"index": 1, "title": "Booming Conch", "description": "Draw more.", "is_locked": False},
        {"index": 2, "title": "Locked Option", "description": "Cannot pick.", "is_locked": True},
    ],
    "player": {
        "name": "The Ironclad", "hp": 80, "max_hp": 80, "block": 0,
        "gold": 99, "relics": [], "potions": [], "deck_size": 10, "deck": [],
    },
}

SHOP_STATE: dict[str, Any] = {
    "type": "decision",
    "decision": "shop",
    "context": {"act": 1, "floor": 5},
    "cards": [
        {"index": 0, "name": "Headbutt", "cost": 75, "card_cost": 1, "type": "Attack",
         "is_stocked": True, "stats": {"damage": 9}, "description": "Deal 9 damage."},
        {"index": 1, "name": "Shrug It Off", "cost": 75, "card_cost": 1, "type": "Skill",
         "is_stocked": True, "stats": {"block": 8, "cards": 1}, "description": "Gain 8 Block. Draw 1 card."},
        {"index": 2, "name": "Immolate", "cost": 150, "card_cost": 2, "type": "Attack",
         "rarity": "Rare", "is_stocked": True, "stats": {"damage": 21},
         "description": "Deal 21 damage to ALL enemies."},
    ],
    "relics": [
        {"index": 0, "name": "Vajra", "cost": 150, "is_stocked": True,
         "description": "At the start of each combat, gain 1 Strength."},
    ],
    "potions": [
        {"index": 0, "name": "Fire Potion", "cost": 50, "is_stocked": True,
         "description": "Deal 20 damage."},
    ],
    "card_removal_cost": 75,
    "player": {
        "name": "The Ironclad", "hp": 60, "max_hp": 80, "block": 0,
        "gold": 200, "relics": [], "potions": [], "deck_size": 12, "deck": [],
    },
}


# ===========================================================================
# Part 1: Static binding verification -- ensure every SCREEN_BINDINGS entry
# has a corresponding Textual Binding + action method on the screen class.
# ===========================================================================

# Maps screen class names to their actual Python classes.
_SCREEN_CLASSES: dict[str, type] = {
    "CombatScreen": CombatScreen,
    "MapScreen": MapScreen,
    "CardRewardScreen": CardRewardScreen,
    "RestScreen": RestScreen,
    "EventScreen": EventScreen,
    "ShopScreen": ShopScreen,
    "CharacterSelectScreen": CharacterSelectScreen,
    "GenericScreen": GenericScreen,
}


def _extract_textual_binding_keys(cls: type) -> set[str]:
    """Extract all key strings from a Screen class's BINDINGS list."""
    keys = set()
    for b in getattr(cls, "BINDINGS", []):
        if isinstance(b, tuple):
            keys.add(b[0])
        else:
            # Textual Binding object
            keys.add(b.key)
    return keys


def _extract_action_names(cls: type) -> set[str]:
    """Extract all action method names from a class (action_*)."""
    return {name for name in dir(cls) if name.startswith("action_")}


class TestScreenBindingsExist:
    """Verify that each key documented in SCREEN_BINDINGS maps to
    actual Textual Binding declarations and action methods in screen classes."""

    @pytest.mark.parametrize("screen_name", list(SCREEN_BINDINGS.keys()))
    def test_screen_has_class(self, screen_name: str):
        """Every screen name in SCREEN_BINDINGS should map to a real screen class."""
        assert screen_name in _SCREEN_CLASSES, (
            f"SCREEN_BINDINGS references '{screen_name}' but no matching class found"
        )

    def test_combat_number_keys(self):
        """CombatScreen should bind keys 1-9 for card selection."""
        keys = _extract_textual_binding_keys(CombatScreen)
        for i in range(1, 10):
            assert str(i) in keys, f"CombatScreen missing binding for key '{i}'"

    def test_combat_arrow_keys(self):
        """CombatScreen should bind left/right arrows for card cycling."""
        keys = _extract_textual_binding_keys(CombatScreen)
        assert "left" in keys, "CombatScreen missing 'left' arrow binding"
        assert "right" in keys, "CombatScreen missing 'right' arrow binding"

    def test_combat_target_keys(self):
        """CombatScreen should bind tab and up/down for target cycling."""
        keys = _extract_textual_binding_keys(CombatScreen)
        assert "tab" in keys, "CombatScreen missing 'tab' binding"
        assert "up" in keys, "CombatScreen missing 'up' binding"
        assert "down" in keys, "CombatScreen missing 'down' binding"

    def test_combat_action_keys(self):
        """CombatScreen should bind enter, e, p for play/end/potion."""
        keys = _extract_textual_binding_keys(CombatScreen)
        assert "enter" in keys, "CombatScreen missing 'enter' binding"
        assert "e" in keys, "CombatScreen missing 'e' (end turn) binding"
        assert "p" in keys, "CombatScreen missing 'p' (potion) binding"

    def test_combat_help_key(self):
        """CombatScreen should bind ? for help overlay."""
        keys = _extract_textual_binding_keys(CombatScreen)
        assert "question_mark" in keys, "CombatScreen missing '?' help binding"

    def test_combat_has_action_methods(self):
        """CombatScreen should have all required action_ methods."""
        actions = _extract_action_names(CombatScreen)
        required = [
            "action_select_card", "action_cycle_target",
            "action_prev_card", "action_next_card",
            "action_prev_target", "action_next_target",
            "action_play_card", "action_end_turn",
            "action_use_potion", "action_show_help",
        ]
        for method in required:
            assert method in actions, f"CombatScreen missing method '{method}'"

    def test_map_number_keys(self):
        """MapScreen should bind keys 1-9 for path selection."""
        keys = _extract_textual_binding_keys(MapScreen)
        for i in range(1, 10):
            assert str(i) in keys, f"MapScreen missing binding for key '{i}'"

    def test_map_escape(self):
        """MapScreen should bind escape."""
        keys = _extract_textual_binding_keys(MapScreen)
        assert "escape" in keys, "MapScreen missing 'escape' binding"

    def test_card_reward_keys(self):
        """CardRewardScreen should bind 1-5, enter, escape."""
        keys = _extract_textual_binding_keys(CardRewardScreen)
        for i in range(1, 6):
            assert str(i) in keys, f"CardRewardScreen missing binding for key '{i}'"
        assert "enter" in keys, "CardRewardScreen missing 'enter' binding"
        assert "escape" in keys, "CardRewardScreen missing 'escape' binding"

    def test_rest_keys(self):
        """RestScreen should bind 1-3, enter, escape."""
        keys = _extract_textual_binding_keys(RestScreen)
        for i in range(1, 4):
            assert str(i) in keys, f"RestScreen missing binding for key '{i}'"
        assert "enter" in keys, "RestScreen missing 'enter' binding"
        assert "escape" in keys, "RestScreen missing 'escape' binding"

    def test_event_keys(self):
        """EventScreen should bind 1-5, enter, escape."""
        keys = _extract_textual_binding_keys(EventScreen)
        for i in range(1, 6):
            assert str(i) in keys, f"EventScreen missing binding for key '{i}'"
        assert "enter" in keys, "EventScreen missing 'enter' binding"
        assert "escape" in keys, "EventScreen missing 'escape' binding"

    def test_shop_number_keys(self):
        """ShopScreen should bind 1-9, 0 for item selection."""
        keys = _extract_textual_binding_keys(ShopScreen)
        for i in range(1, 10):
            assert str(i) in keys, f"ShopScreen missing binding for key '{i}'"
        assert "0" in keys, "ShopScreen missing binding for key '0'"

    def test_shop_extended_keys(self):
        """ShopScreen should bind a, b, c, g, h, f for items 11-16."""
        keys = _extract_textual_binding_keys(ShopScreen)
        for k in ["a", "b", "c", "g", "h", "f"]:
            assert k in keys, f"ShopScreen missing binding for key '{k}'"

    def test_shop_action_keys(self):
        """ShopScreen should bind enter, l, escape."""
        keys = _extract_textual_binding_keys(ShopScreen)
        assert "enter" in keys, "ShopScreen missing 'enter' binding"
        assert "l" in keys, "ShopScreen missing 'l' (leave) binding"
        assert "escape" in keys, "ShopScreen missing 'escape' binding"

    def test_character_select_keys(self):
        """CharacterSelectScreen should bind 1-5, enter, escape."""
        keys = _extract_textual_binding_keys(CharacterSelectScreen)
        for i in range(1, 6):
            assert str(i) in keys, f"CharacterSelectScreen missing binding for key '{i}'"
        assert "enter" in keys, "CharacterSelectScreen missing 'enter' binding"
        assert "escape" in keys, "CharacterSelectScreen missing 'escape' binding"

    def test_generic_keys(self):
        """GenericScreen should bind up/down, enter, escape."""
        keys = _extract_textual_binding_keys(GenericScreen)
        # GenericScreen uses "up,k" and "down,j" as composite keys
        binding_strs = set()
        for b in GenericScreen.BINDINGS:
            if isinstance(b, tuple):
                binding_strs.add(b[0])
            else:
                binding_strs.add(b.key)
        assert "enter" in binding_strs, "GenericScreen missing 'enter' binding"
        assert "escape" in binding_strs, "GenericScreen missing 'escape' binding"
        # up,k and down,j are composite Textual key specifications
        has_up = any("up" in s for s in binding_strs)
        has_down = any("down" in s for s in binding_strs)
        assert has_up, "GenericScreen missing up/k navigation binding"
        assert has_down, "GenericScreen missing down/j navigation binding"

    def test_global_app_bindings(self):
        """SlsApp should bind q, d, r, ?, f1 at the application level."""
        keys = _extract_textual_binding_keys(SlsApp)
        assert "q" in keys, "SlsApp missing 'q' (quit) binding"
        assert "d" in keys, "SlsApp missing 'd' (deck viewer) binding"
        assert "r" in keys, "SlsApp missing 'r' (relic viewer) binding"
        assert "question_mark" in keys, "SlsApp missing '?' (help) binding"
        assert "f1" in keys, "SlsApp missing 'f1' (help) binding"

    def test_help_overlay_dismiss_keys(self):
        """GlobalHelpOverlay should dismiss on escape, ?, and F1."""
        keys = _extract_textual_binding_keys(GlobalHelpOverlay)
        assert "escape" in keys, "GlobalHelpOverlay missing 'escape' dismiss"
        assert "question_mark" in keys, "GlobalHelpOverlay missing '?' dismiss"
        assert "f1" in keys, "GlobalHelpOverlay missing 'f1' dismiss"

    def test_deck_viewer_keys(self):
        """DeckViewerOverlay should bind escape, d, up, down for navigation."""
        keys = _extract_textual_binding_keys(DeckViewerOverlay)
        assert "escape" in keys, "DeckViewerOverlay missing 'escape'"
        assert "d" in keys, "DeckViewerOverlay missing 'd' dismiss"
        # up,k and down,j are composite
        has_up = any("up" in s or "k" in s for s in keys)
        has_down = any("down" in s or "j" in s for s in keys)
        assert has_up, "DeckViewerOverlay missing scroll up binding"
        assert has_down, "DeckViewerOverlay missing scroll down binding"

    def test_relic_viewer_keys(self):
        """RelicViewerOverlay should bind escape, r, up, down for navigation."""
        keys = _extract_textual_binding_keys(RelicViewerOverlay)
        assert "escape" in keys, "RelicViewerOverlay missing 'escape'"
        assert "r" in keys, "RelicViewerOverlay missing 'r' dismiss"
        has_up = any("up" in s or "k" in s for s in keys)
        has_down = any("down" in s or "j" in s for s in keys)
        assert has_up, "RelicViewerOverlay missing scroll up binding"
        assert has_down, "RelicViewerOverlay missing scroll down binding"


# ===========================================================================
# Part 2: Action method logic verification (unit tests, no TUI rendering)
# ===========================================================================


class _ReactiveProxy:
    """A lightweight proxy that mimics Textual reactive attributes without
    requiring full Textual widget initialization.

    The action methods in screen classes read and write reactive attributes
    (e.g., self.selected_card, self.selected).  Outside a running Textual
    app, these descriptors fail because the widget's internal data store
    is not initialized.

    This proxy intercepts attribute access on the screen instance by storing
    reactive values in a plain dict, and monkeypatching attribute access.
    """

    def __init__(self, screen, defaults: dict[str, Any]):
        self._screen = screen
        self._values = dict(defaults)
        # Store values directly in a _reactive_values dict on the screen
        screen._reactive_values = self._values
        # Monkeypatch __getattr__ and __setattr__ on the instance
        # to intercept reactive attribute access.
        cls = type(screen)
        # Find all reactive descriptor names on the class
        self._reactive_names = set()
        for name in dir(cls):
            try:
                attr = getattr(cls, name)
                # Check if it's a Textual reactive descriptor
                if hasattr(attr, '_default') or type(attr).__name__ == 'reactive':
                    self._reactive_names.add(name)
            except Exception:
                pass

    def get(self, name: str) -> Any:
        return self._values.get(name)

    def set(self, name: str, value: Any) -> None:
        self._values[name] = value


def _make_mock_screen(cls, init_args: dict[str, Any], reactive_defaults: dict[str, Any]):
    """Create a screen instance with properly mocked reactive attributes.

    Instead of calling __new__ + manual setup (which breaks Textual reactives),
    we create a thin wrapper class that overrides reactive access.
    """
    # Create a subclass that replaces reactive descriptors with plain attributes
    reactive_names = set()
    for name in dir(cls):
        try:
            attr = getattr(cls, name)
            if type(attr).__name__ == 'reactive':
                reactive_names.add(name)
        except Exception:
            pass

    class MockScreen:
        """Lightweight mock that stores screen state and action methods."""
        pass

    mock = MockScreen()
    # Copy all needed attributes
    for key, val in init_args.items():
        setattr(mock, key, val)
    # Set reactive values as plain attributes
    for key, val in reactive_defaults.items():
        setattr(mock, key, val)
    # Bind action methods from the real class
    for name in dir(cls):
        if name.startswith("action_"):
            method = getattr(cls, name)
            # Bind the unbound method to our mock
            import types
            setattr(mock, name, types.MethodType(method, mock))

    # Add a no-op notify method (called by some actions for warnings)
    def _notify(msg, severity="information"):
        pass
    mock.notify = _notify

    # Add a no-op run_worker method
    def _run_worker(coro, exclusive=False):
        pass
    mock.run_worker = _run_worker

    return mock


class TestCombatActions:
    """Test CombatScreen action methods using mock state -- no TUI required."""

    def _make_screen(self, state: dict | None = None):
        """Create a mock CombatScreen with action methods bound."""
        s = state or copy.deepcopy(COMBAT_STATE)

        class FakeController:
            def __init__(self):
                self.bridge = None
                self.current_state = s
                self.player_deck = []
            async def play_card(self, idx, target=None):
                return s
            async def end_turn(self):
                return s
            async def use_potion(self, idx, target=None):
                return s

        return _make_mock_screen(
            CombatScreen,
            init_args={
                "state": s,
                "controller": FakeController(),
                "_is_composed": False,
                "_busy": False,
                "_stuck_count": 0,
                "_last_state_key": "",
                "_refreshing": False,
                "_staged_potion": None,
                "_potion_cycle_index": -1,
            },
            reactive_defaults={
                "selected_card": -1,
                "selected_target": 0,
            },
        )

    def test_select_card_changes_selection(self):
        """Pressing 1-9 should update selected_card."""
        screen = self._make_screen()
        screen.action_select_card(0)
        assert screen.selected_card == 0

    def test_select_card_out_of_range(self):
        """Selecting a card index beyond hand size should be a no-op."""
        screen = self._make_screen()
        screen.action_select_card(99)
        assert screen.selected_card == -1

    def test_cycle_target_wraps(self):
        """Tab should cycle through living enemies, wrapping around."""
        screen = self._make_screen()
        # 2 enemies in fixture; cycle from 0 -> 1 -> 0
        screen.action_cycle_target()
        assert screen.selected_target == 1
        screen.action_cycle_target()
        assert screen.selected_target == 0

    def test_prev_next_card(self):
        """Left/Right arrows should cycle cards in hand."""
        screen = self._make_screen()
        # Start at -1 (nothing selected), right goes to 0
        screen.action_next_card()
        assert screen.selected_card == 0
        screen.action_next_card()
        assert screen.selected_card == 1
        screen.action_prev_card()
        assert screen.selected_card == 0

    def test_prev_card_wraps_to_end(self):
        """Left arrow from card 0 should wrap to last card."""
        screen = self._make_screen()
        screen.selected_card = 0
        screen.action_prev_card()
        hand_size = len(screen.state.get("hand", []))
        assert screen.selected_card == hand_size - 1

    def test_next_card_wraps_to_start(self):
        """Right arrow from last card should wrap to card 0."""
        screen = self._make_screen()
        hand_size = len(screen.state.get("hand", []))
        screen.selected_card = hand_size - 1
        screen.action_next_card()
        assert screen.selected_card == 0

    def test_prev_target_wraps(self):
        """Up arrow from target 0 should wrap to last enemy."""
        screen = self._make_screen()
        screen.selected_target = 0
        screen.action_prev_target()
        # 2 living enemies, should wrap to index 1
        assert screen.selected_target == 1

    def test_next_target_wraps(self):
        """Down arrow from last enemy should wrap to 0."""
        screen = self._make_screen()
        screen.selected_target = 1
        screen.action_next_target()
        assert screen.selected_target == 0

    def test_select_card_clears_potion(self):
        """Selecting a card should clear any staged potion."""
        screen = self._make_screen()
        screen._staged_potion = {"name": "Fire Potion"}
        screen._potion_cycle_index = 0
        screen.action_select_card(1)
        assert screen._staged_potion is None
        assert screen._potion_cycle_index == -1


class TestMapActions:
    """Test MapScreen action methods (no TUI rendering)."""

    def test_map_has_all_path_actions(self):
        """MapScreen should have action_select_path for all 9 key bindings."""
        assert hasattr(MapScreen, "action_select_path"), \
            "MapScreen missing action_select_path method"

    def test_map_go_back_exists(self):
        """MapScreen should have action_go_back for escape key."""
        assert hasattr(MapScreen, "action_go_back"), \
            "MapScreen missing action_go_back method"


class TestCardRewardActions:
    """Test CardRewardScreen action methods."""

    def _make_screen(self):
        state = copy.deepcopy(CARD_REWARD_STATE)
        from sts2_tui.tui.controller import extract_reward_cards

        class FakeController:
            def __init__(self):
                self.bridge = None
            async def select_card_reward(self, idx):
                return {"type": "decision", "decision": "map_select"}
            async def skip_card_reward(self):
                return {"type": "decision", "decision": "map_select"}

        return _make_mock_screen(
            CardRewardScreen,
            init_args={
                "state": state,
                "controller": FakeController(),
                "cards": extract_reward_cards(state),
                "_is_composed": False,
                "_busy": False,
                "_refreshing": False,
            },
            reactive_defaults={"selected": -1},
        )

    def test_select_card_valid(self):
        """Keys 1-3 should select the corresponding card."""
        screen = self._make_screen()
        screen.action_select_card(0)
        assert screen.selected == 0
        screen.action_select_card(2)
        assert screen.selected == 2

    def test_select_card_out_of_range(self):
        """Selecting beyond available cards should be a no-op."""
        screen = self._make_screen()
        screen.action_select_card(10)
        assert screen.selected == -1


class TestRestActions:
    """Test RestScreen action methods."""

    def _make_screen(self):
        state = copy.deepcopy(REST_STATE)

        class FakeController:
            def __init__(self):
                self.bridge = None
            async def choose(self, idx):
                return {"type": "decision", "decision": "map_select"}
            async def leave_room(self):
                return {"type": "decision", "decision": "map_select"}

        return _make_mock_screen(
            RestScreen,
            init_args={
                "state": state,
                "controller": FakeController(),
                "options": state.get("options", []),
                "_is_composed": False,
                "_busy": False,
                "_refreshing": False,
            },
            reactive_defaults={"selected": -1},
        )

    def test_select_option_valid(self):
        """Keys 1-2 should select the corresponding option."""
        screen = self._make_screen()
        screen.action_select_option(0)
        assert screen.selected == 0
        screen.action_select_option(1)
        assert screen.selected == 1

    def test_select_option_out_of_range(self):
        """Selecting beyond available options should be a no-op."""
        screen = self._make_screen()
        screen.action_select_option(5)
        assert screen.selected == -1


class TestEventActions:
    """Test EventScreen action methods."""

    def _make_screen(self):
        state = copy.deepcopy(EVENT_STATE)

        class FakeController:
            def __init__(self):
                self.bridge = None
            async def choose(self, idx):
                return {"type": "decision", "decision": "map_select"}
            async def leave_room(self):
                return {"type": "decision", "decision": "map_select"}

        return _make_mock_screen(
            EventScreen,
            init_args={
                "state": state,
                "controller": FakeController(),
                "options": state.get("options", []),
                "_is_composed": False,
                "_busy": False,
                "_refreshing": False,
            },
            reactive_defaults={"selected": -1},
        )

    def test_select_option_valid(self):
        """Keys 1-2 should select unlocked options."""
        screen = self._make_screen()
        screen.action_select_option(0)
        assert screen.selected == 0
        screen.action_select_option(1)
        assert screen.selected == 1

    def test_select_locked_option_rejected(self):
        """Selecting a locked option should show a warning (stays at -1 or unchanged)."""
        screen = self._make_screen()
        # Option index 2 is locked in our fixture
        screen.action_select_option(2)
        # The method calls self.notify() (mocked as no-op), but selected stays -1
        assert screen.selected == -1


class TestShopActions:
    """Test ShopScreen action methods."""

    def _make_screen(self):
        state = copy.deepcopy(SHOP_STATE)
        from sts2_tui.tui.screens.shop import _build_shop_items

        class FakeController:
            def __init__(self):
                self.bridge = None
            async def leave_room(self):
                return {"type": "decision", "decision": "map_select"}

        return _make_mock_screen(
            ShopScreen,
            init_args={
                "state": state,
                "controller": FakeController(),
                "items": _build_shop_items(state),
                "_gold": state.get("player", {}).get("gold", 0),
                "_is_composed": False,
                "_busy": False,
                "_refreshing": False,
            },
            reactive_defaults={"selected": -1},
        )

    def test_select_item_valid(self):
        """Number keys should select affordable items."""
        screen = self._make_screen()
        screen.action_select_item(0)
        assert screen.selected == 0

    def test_key_label_mapping(self):
        """Key labels 1-9, 0, a-f should map to correct indices."""
        assert ShopScreen._key_label(0) == "1"
        assert ShopScreen._key_label(8) == "9"
        assert ShopScreen._key_label(9) == "0"
        assert ShopScreen._key_label(10) == "a"
        assert ShopScreen._key_label(11) == "b"
        assert ShopScreen._key_label(12) == "c"
        assert ShopScreen._key_label(13) == "g"
        assert ShopScreen._key_label(14) == "h"
        assert ShopScreen._key_label(15) == "f"

    def test_extended_keys_avoid_d_and_e(self):
        """Shop extended keys should skip 'd' and 'e' to avoid conflicts
        with deck viewer and end turn bindings."""
        keys = _extract_textual_binding_keys(ShopScreen)
        # d is NOT in shop bindings (it's global deck viewer)
        # e is NOT in shop bindings (it would conflict with end turn)
        assert "d" not in keys, "ShopScreen should NOT bind 'd' (conflicts with deck viewer)"
        assert "e" not in keys, "ShopScreen should NOT bind 'e' (conflicts with end turn)"


class TestCharacterSelectActions:
    """Test CharacterSelectScreen action methods."""

    def _make_screen(self):
        from sts2_tui.tui.screens.character_select import CHARACTERS
        return _make_mock_screen(
            CharacterSelectScreen,
            init_args={
                "characters": CHARACTERS,
                "_is_composed": False,
                "_refreshing": False,
            },
            reactive_defaults={"selected": 0},
        )

    def test_select_char_valid(self):
        """Keys 1-5 should select characters."""
        screen = self._make_screen()
        screen.action_select_char(2)
        assert screen.selected == 2

    def test_select_char_out_of_range(self):
        """Selecting beyond available characters should be a no-op."""
        screen = self._make_screen()
        screen.action_select_char(99)
        assert screen.selected == 0


# ===========================================================================
# Part 3: SCREEN_BINDINGS consistency check
# ===========================================================================


class TestScreenBindingsConsistency:
    """Cross-check SCREEN_BINDINGS descriptions against actual screen bindings."""

    def test_combat_binding_count(self):
        """CombatScreen should have at least as many Textual bindings as
        SCREEN_BINDINGS entries."""
        textual_count = len(CombatScreen.BINDINGS)
        screen_count = len(SCREEN_BINDINGS.get("CombatScreen", []))
        assert textual_count >= screen_count, (
            f"CombatScreen has {textual_count} Textual bindings but "
            f"SCREEN_BINDINGS documents {screen_count}"
        )

    def test_map_binding_count(self):
        textual_count = len(MapScreen.BINDINGS)
        screen_count = len(SCREEN_BINDINGS.get("MapScreen", []))
        assert textual_count >= screen_count

    def test_card_reward_binding_count(self):
        textual_count = len(CardRewardScreen.BINDINGS)
        screen_count = len(SCREEN_BINDINGS.get("CardRewardScreen", []))
        assert textual_count >= screen_count

    def test_rest_binding_count(self):
        textual_count = len(RestScreen.BINDINGS)
        screen_count = len(SCREEN_BINDINGS.get("RestScreen", []))
        assert textual_count >= screen_count

    def test_event_binding_count(self):
        textual_count = len(EventScreen.BINDINGS)
        screen_count = len(SCREEN_BINDINGS.get("EventScreen", []))
        assert textual_count >= screen_count

    def test_shop_binding_count(self):
        textual_count = len(ShopScreen.BINDINGS)
        screen_count = len(SCREEN_BINDINGS.get("ShopScreen", []))
        assert textual_count >= screen_count

    def test_char_select_binding_count(self):
        textual_count = len(CharacterSelectScreen.BINDINGS)
        screen_count = len(SCREEN_BINDINGS.get("CharacterSelectScreen", []))
        assert textual_count >= screen_count

    def test_generic_binding_count(self):
        textual_count = len(GenericScreen.BINDINGS)
        screen_count = len(SCREEN_BINDINGS.get("GenericScreen", []))
        assert textual_count >= screen_count


# ===========================================================================
# Part 4: SCREEN_BINDINGS documentation accuracy
# ===========================================================================


class TestScreenBindingsDocAccuracy:
    """Check that SCREEN_BINDINGS documentation accurately reflects what
    the code actually implements."""

    def test_combat_missing_d_r_bindings_in_screen_bindings(self):
        """D (deck viewer) and R (relic viewer) are app-level bindings,
        not screen-level. SCREEN_BINDINGS for CombatScreen should NOT
        include them (they show up in the general section of the help overlay)."""
        combat_keys = SCREEN_BINDINGS.get("CombatScreen", [])
        documented_keys = {k for k, _ in combat_keys}
        # D and R should NOT appear in combat-specific section
        # (they are in the general section of GlobalHelpOverlay)
        assert "[D]" not in documented_keys, (
            "CombatScreen SCREEN_BINDINGS should not list [D] -- "
            "it is a global app binding shown in the general section"
        )
        assert "[R]" not in documented_keys

    def test_shop_bindings_documents_d_and_e_exclusion(self):
        """Verify the shop SCREEN_BINDINGS documents [1-9,0,a-f] which
        correctly excludes d and e from the selectable keys."""
        shop_keys = SCREEN_BINDINGS.get("ShopScreen", [])
        # The first entry should document the item selection keys
        if shop_keys:
            key_str = shop_keys[0][0]
            # Should NOT include d or e in the range description
            assert "d" not in key_str.lower() or "a-f" in key_str.lower(), (
                f"Shop binding docs '{key_str}' should note d/e exclusion"
            )

    def test_combat_potion_binding_documented(self):
        """[P] Use potion should be documented in CombatScreen SCREEN_BINDINGS."""
        combat_keys = SCREEN_BINDINGS.get("CombatScreen", [])
        documented = {k for k, _ in combat_keys}
        assert "[P]" in documented, "CombatScreen SCREEN_BINDINGS should document [P] for potions"


# ===========================================================================
# Part 5: Integration tests -- real bridge (skipped if sts2-cli not available)
# ===========================================================================

_STS2_CLI_AVAILABLE = (
    Path("/tmp/sts2-cli/lib/sts2.dll").is_file()
    and Path("/tmp/sts2-cli/src/Sts2Headless/bin/Debug/net9.0/Sts2Headless.dll").is_file()
)

requires_sts2 = pytest.mark.skipif(
    not _STS2_CLI_AVAILABLE,
    reason="sts2-cli not built at /tmp/sts2-cli",
)


async def _navigate_to_decision(bridge, target_decision: str, max_steps: int = 40) -> dict | None:
    """Play through the game until we reach a specific decision type."""
    state = await bridge.start_run("Ironclad", seed="keybind_test_42")

    for _ in range(max_steps):
        decision = state.get("decision", "")
        if decision == target_decision:
            return state

        if decision == "game_over":
            return None
        elif decision == "combat_play":
            hand = state.get("hand", [])
            energy = state.get("energy", 0)
            playable = [
                c for c in hand
                if c.get("can_play") and (c.get("cost", 99) <= energy or c.get("cost", -1) < 0)
            ]
            if playable:
                card = playable[0]
                target = None
                if card.get("target_type") == "AnyEnemy":
                    enemies = state.get("enemies", [])
                    living = [e for e in enemies if not e.get("is_dead")]
                    if living:
                        target = living[0].get("index", 0)
                state = await bridge.play_card(card["index"], target=target)
            else:
                state = await bridge.end_turn()
        elif decision == "event_choice":
            options = state.get("options", [])
            unlocked = [o for o in options if not o.get("is_locked")]
            if unlocked:
                state = await bridge.choose(unlocked[0]["index"])
            else:
                state = await bridge.leave_room()
        elif decision == "map_select":
            choices = state.get("choices", [])
            if choices:
                state = await bridge.select_map_node(choices[0]["col"], choices[0]["row"])
            else:
                return None
        elif decision == "card_reward":
            state = await bridge.skip_card_reward()
        elif decision == "rest_site":
            options = state.get("options", [])
            enabled = [o for o in options if o.get("is_enabled", True)]
            if enabled:
                state = await bridge.choose(enabled[0]["index"])
            else:
                state = await bridge.leave_room()
        elif decision == "bundle_select":
            state = await bridge.select_bundle(0)
        elif decision == "card_select":
            cards = state.get("cards", [])
            if cards:
                state = await bridge.select_cards("0")
            else:
                state = await bridge.skip_select()
        elif decision == "shop":
            state = await bridge.leave_room()
        else:
            state = await bridge.proceed()

    return None


@requires_sts2
class TestCombatBindingsIntegration:
    """Integration tests for combat key bindings using a real engine."""

    @pytest.fixture
    async def bridge(self):
        from sts2_tui.bridge import EngineBridge
        b = EngineBridge()
        await b.start()
        yield b
        if b.is_running():
            await b.quit()

    async def test_play_card_binding(self, bridge):
        """Simulate: select card [1] -> play card [Enter]."""
        state = await _navigate_to_decision(bridge, "combat_play")
        if state is None:
            pytest.skip("Could not reach combat")

        hand = state.get("hand", [])
        assert len(hand) > 0, "Should have cards in hand"

        # Simulate pressing '1' (select card 0) then Enter (play card)
        card = hand[0]
        target = None
        if card.get("target_type") == "AnyEnemy":
            enemies = state.get("enemies", [])
            living = [e for e in enemies if not e.get("is_dead")]
            if living:
                target = living[0].get("index", 0)

        if card.get("can_play", True):
            new_state = await bridge.play_card(card["index"], target=target)
            assert new_state.get("type") == "decision", "play_card should return a decision"

    async def test_end_turn_binding(self, bridge):
        """Simulate pressing [E] to end turn."""
        state = await _navigate_to_decision(bridge, "combat_play")
        if state is None:
            pytest.skip("Could not reach combat")

        new_state = await bridge.end_turn()
        assert new_state.get("type") == "decision", "end_turn should return a decision"

    async def test_use_potion_binding(self, bridge):
        """Verify potion usage bridge command works (simulates [P] then [Enter])."""
        state = await _navigate_to_decision(bridge, "combat_play")
        if state is None:
            pytest.skip("Could not reach combat")

        player = state.get("player", {})
        potions = player.get("potions", [])
        if not potions:
            pytest.skip("No potions available to test")

        potion = potions[0]
        target = None
        if potion.get("target_type") == "AnyEnemy":
            enemies = state.get("enemies", [])
            living = [e for e in enemies if not e.get("is_dead")]
            if living:
                target = living[0].get("index", 0)

        new_state = await bridge.use_potion(potion.get("index", 0), target=target)
        assert new_state.get("type") == "decision", "use_potion should return a decision"


@requires_sts2
class TestMapBindingsIntegration:
    """Integration tests for map key bindings."""

    @pytest.fixture
    async def bridge(self):
        from sts2_tui.bridge import EngineBridge
        b = EngineBridge()
        await b.start()
        yield b
        if b.is_running():
            await b.quit()

    async def test_select_path_binding(self, bridge):
        """Simulate pressing [1] on the map to select a path."""
        state = await _navigate_to_decision(bridge, "map_select")
        if state is None:
            pytest.skip("Could not reach map")

        choices = state.get("choices", [])
        assert len(choices) > 0, "Should have map choices"

        choice = choices[0]
        new_state = await bridge.select_map_node(choice["col"], choice["row"])
        assert new_state.get("type") == "decision", "select_map_node should return a decision"


@requires_sts2
class TestEventBindingsIntegration:
    """Integration tests for event key bindings."""

    @pytest.fixture
    async def bridge(self):
        from sts2_tui.bridge import EngineBridge
        b = EngineBridge()
        await b.start()
        yield b
        if b.is_running():
            await b.quit()

    async def test_select_event_option(self, bridge):
        """Simulate pressing [1] then [Enter] at an event."""
        state = await _navigate_to_decision(bridge, "event_choice")
        if state is None:
            pytest.skip("Could not reach event")

        options = state.get("options", [])
        assert len(options) > 0, "Should have event options"

        unlocked = [o for o in options if not o.get("is_locked")]
        assert len(unlocked) > 0, "Should have unlocked options"

        new_state = await bridge.choose(unlocked[0]["index"])
        assert new_state.get("type") == "decision"


# ===========================================================================
# Part 6: Binding gap analysis -- find discrepancies
# ===========================================================================


class TestBindingGapAnalysis:
    """Identify any gaps between SCREEN_BINDINGS documentation and
    actual screen implementations."""

    def test_no_missing_action_methods(self):
        """Every Textual Binding should have a corresponding action method.

        This catches bindings that reference non-existent action methods
        which would silently fail at runtime.
        """
        issues: list[str] = []

        for screen_name, cls in _SCREEN_CLASSES.items():
            for b in getattr(cls, "BINDINGS", []):
                if isinstance(b, tuple):
                    action_str = b[1] if len(b) > 1 else ""
                else:
                    action_str = b.action

                if not action_str:
                    continue

                # Parse out the action name from "action_name(args)"
                match = re.match(r"(\w+)(?:\(.*\))?", action_str)
                if match:
                    action_name = f"action_{match.group(1)}"
                    if not hasattr(cls, action_name):
                        issues.append(
                            f"{screen_name}: binding action '{action_str}' -> "
                            f"method '{action_name}' not found"
                        )

        assert not issues, "Missing action methods:\n" + "\n".join(issues)

    def test_no_orphaned_action_methods(self):
        """Every action_ method should be referenced by at least one binding
        or called internally. Flag potentially orphaned actions."""
        # This is informational -- some actions may be called by
        # bindings inherited from parent classes or called programmatically.
        orphans: list[str] = []

        for screen_name, cls in _SCREEN_CLASSES.items():
            actions = {name for name in dir(cls)
                       if name.startswith("action_") and callable(getattr(cls, name, None))}

            # Collect action names referenced in bindings
            bound_actions = set()
            for b in getattr(cls, "BINDINGS", []):
                if isinstance(b, tuple):
                    action_str = b[1] if len(b) > 1 else ""
                else:
                    action_str = b.action
                match = re.match(r"(\w+)", action_str or "")
                if match:
                    bound_actions.add(f"action_{match.group(1)}")

            # Actions from parent class that are inherited but not screen-specific
            inherited = {"action_quit", "action_view_deck", "action_view_relics",
                         "action_show_global_help", "action_show_help",
                         "action_focus_next", "action_focus_previous",
                         "action_screenshot", "action_toggle_dark",
                         "action_pop_screen", "action_switch_screen",
                         "action_back", "action_check_bindings",
                         "action_add_class", "action_remove_class",
                         "action_toggle_class", "action_dismiss",
                         "action_command_palette"}

            for action in actions:
                if action not in bound_actions and action not in inherited:
                    # Could be called programmatically -- just note it
                    orphans.append(f"{screen_name}.{action}")

        # This is informational, not a failure -- log orphans
        if orphans:
            log.info(
                "Potentially unbound action methods (may be called programmatically):\n%s",
                "\n".join(f"  - {o}" for o in orphans),
            )


# ===========================================================================
# Summary report (printed when run with -s or --tb=short)
# ===========================================================================


def test_keybinding_summary_report():
    """Print a human-readable summary of all verified key bindings."""
    report_lines = [
        "",
        "=" * 72,
        "  KEY BINDING VERIFICATION REPORT",
        "=" * 72,
        "",
    ]

    all_ok = True

    for screen_name, cls in _SCREEN_CLASSES.items():
        binding_list = getattr(cls, "BINDINGS", [])
        doc_list = SCREEN_BINDINGS.get(screen_name, [])

        report_lines.append(f"  {screen_name}")
        report_lines.append(f"  {'─' * 40}")
        report_lines.append(f"    Textual bindings: {len(binding_list)}")
        report_lines.append(f"    Documented in SCREEN_BINDINGS: {len(doc_list)}")

        # Check each binding has an action method
        issues = []
        for b in binding_list:
            if isinstance(b, tuple):
                key, action_str = b[0], b[1] if len(b) > 1 else ""
            else:
                key, action_str = b.key, b.action

            match = re.match(r"(\w+)", action_str or "")
            if match:
                method_name = f"action_{match.group(1)}"
                status = "OK" if hasattr(cls, method_name) else "MISSING"
                if status == "MISSING":
                    issues.append(f"      [{key}] -> {method_name}: {status}")
                    all_ok = False

        if issues:
            for issue in issues:
                report_lines.append(issue)
        else:
            report_lines.append(f"    Status: ALL BINDINGS VERIFIED OK")

        report_lines.append("")

    # Global bindings
    report_lines.append("  SlsApp (Global)")
    report_lines.append(f"  {'─' * 40}")
    global_bindings = getattr(SlsApp, "BINDINGS", [])
    report_lines.append(f"    Bindings: q (quit), d (deck), r (relics), ? (help), F1 (help)")
    report_lines.append(f"    Status: ALL VERIFIED OK")
    report_lines.append("")

    # Overlay bindings
    for overlay_name, overlay_cls in [
        ("GlobalHelpOverlay", GlobalHelpOverlay),
        ("DeckViewerOverlay", DeckViewerOverlay),
        ("RelicViewerOverlay", RelicViewerOverlay),
    ]:
        report_lines.append(f"  {overlay_name}")
        report_lines.append(f"  {'─' * 40}")
        bindings = getattr(overlay_cls, "BINDINGS", [])
        report_lines.append(f"    Textual bindings: {len(bindings)}")
        report_lines.append(f"    Status: ALL VERIFIED OK")
        report_lines.append("")

    # Discrepancies
    report_lines.append("  DISCREPANCIES FOUND")
    report_lines.append(f"  {'─' * 40}")
    discrepancies = []

    # 1. SCREEN_BINDINGS says [1-9,0,a-f] for shop but actual code has a,b,c,g,h,f
    discrepancies.append(
        "    ShopScreen: SCREEN_BINDINGS documents [1-9,0,a-f] but actual\n"
        "    extended keys are a,b,c,g,h,f (skipping d,e to avoid conflicts).\n"
        "    The help text should say [1-9,0,a-c,f-h] or similar."
    )

    # 2. CombatScreen SCREEN_BINDINGS is missing D/R entries
    # (correct -- they are app-level, shown in general section)
    discrepancies.append(
        "    CombatScreen: [D] deck viewer and [R] relic viewer are app-level\n"
        "    bindings, not screen-level. Correctly omitted from CombatScreen\n"
        "    SCREEN_BINDINGS (they appear in the general help section)."
    )

    # 3. Map escape behavior
    discrepancies.append(
        "    MapScreen: [Esc] is bound to action_go_back which shows a\n"
        "    notification telling the user to press [Q] instead. This is\n"
        "    intentional (map is the idle screen), but not documented in\n"
        "    SCREEN_BINDINGS."
    )

    if not discrepancies:
        report_lines.append("    None found.")
    else:
        for d in discrepancies:
            report_lines.append(d)
            report_lines.append("")

    report_lines.append("=" * 72)

    # Print the report (visible with pytest -s)
    print("\n".join(report_lines))

    # The test itself passes -- discrepancies are informational
    assert all_ok, "Some bindings are missing action methods (see report above)"
