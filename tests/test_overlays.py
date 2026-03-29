"""Headless Textual tests for overlay screens.

Covers:
1. DeckViewerOverlay  -- mount with sample deck, verify cards grouped and displayed
2. RelicViewerOverlay -- mount with sample relics/potions, verify descriptions
3. GlobalHelpOverlay  -- mount for each screen context, verify bindings listed
4. ErrorRecoveryScreen -- mount with error message, verify R/M/Q buttons

Usage:
    pytest tests/test_overlays.py -v --tb=short
"""

from __future__ import annotations

from pathlib import Path

import pytest

from textual.app import App
from textual.widgets import Static

from sts2_tui.tui.screens.deck_viewer import DeckViewerOverlay, RelicViewerOverlay
from sts2_tui.tui.shared import (
    ErrorRecoveryScreen,
    ErrorRetryMessage,
    ErrorGoMapMessage,
    ErrorQuitMessage,
    GlobalHelpOverlay,
    SCREEN_BINDINGS,
)

# ---------------------------------------------------------------------------
# CSS path shared with production app
# ---------------------------------------------------------------------------

CSS_PATH = Path(__file__).parent.parent / "src" / "sts2_tui" / "tui" / "sls.tcss"


# ---------------------------------------------------------------------------
# Helper: extract all text from a container widget (e.g. VerticalScroll)
# ---------------------------------------------------------------------------


def _collect_text(container) -> str:
    """Collect all visible text from a container's child Static widgets.

    For VerticalScroll and other containers, render() returns a Blank
    renderable. We instead query all child Static widgets and call
    str(child.render()) on each to get the actual text content.
    """
    parts: list[str] = []
    for child in container.query(Static):
        parts.append(str(child.render()))
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Sample data fixtures
# ---------------------------------------------------------------------------

SAMPLE_DECK: list[dict] = [
    {
        "name": "Strike",
        "cost": 1,
        "type": "Attack",
        "upgraded": False,
        "stats": {"damage": 6},
        "description": "Deal {Damage} damage.",
        "after_upgrade": {"cost": 1, "stats": {"damage": 9}},
    },
    {
        "name": "Strike",
        "cost": 1,
        "type": "Attack",
        "upgraded": True,
        "stats": {"damage": 9},
        "description": "Deal {Damage} damage.",
    },
    {
        "name": "Defend",
        "cost": 1,
        "type": "Skill",
        "upgraded": False,
        "stats": {"block": 5},
        "description": "Gain {Block} Block.",
        "after_upgrade": {"cost": 1, "stats": {"block": 8}},
    },
    {
        "name": "Bash",
        "cost": 2,
        "type": "Attack",
        "upgraded": False,
        "stats": {"damage": 8, "vulnerablepower": 2},
        "description": "Deal {Damage} damage. Apply {VulnerablePower} Vulnerable.",
        "after_upgrade": {"cost": 2, "stats": {"damage": 10, "vulnerablepower": 3}},
    },
    {
        "name": "Offering",
        "cost": 0,
        "type": "Skill",
        "upgraded": False,
        "stats": {"hploss": 6, "cards": 3, "energy": 2},
        "description": "Lose {HpLoss} HP. Gain {Energy} Energy. Draw {Cards} cards.",
    },
    {
        "name": "Inflame",
        "cost": 1,
        "type": "Power",
        "upgraded": False,
        "stats": {"strength": 2},
        "description": "Gain {Strength} Strength.",
        "after_upgrade": {"cost": 1, "stats": {"strength": 3}},
    },
    {
        "name": "Slimed",
        "cost": 1,
        "type": "Status",
        "upgraded": False,
        "stats": {},
        "description": "Exhaust.",
    },
    {
        "name": "Regret",
        "cost": -1,
        "type": "Curse",
        "upgraded": False,
        "stats": {},
        "description": "Unplayable. At the end of your turn, lose 1 HP per card in hand.",
    },
]

SAMPLE_RELICS: list[dict] = [
    {
        "name": "Burning Blood",
        "description": "At the end of combat, heal 6 HP.",
    },
    {
        "name": "Vajra",
        "description": "At the start of each combat, gain 1 Strength.",
    },
]

SAMPLE_POTIONS: list[dict] = [
    {
        "name": "Fire Potion",
        "description": "Deal 20 damage to a target enemy.",
        "target_type": "AnyEnemy",
    },
    {
        "name": "Block Potion",
        "description": "Gain 12 Block.",
        "target_type": "Self",
    },
]


# ---------------------------------------------------------------------------
# Minimal harness apps -- push the overlay as the first screen
# ---------------------------------------------------------------------------


class DeckViewerTestApp(App):
    """Pushes DeckViewerOverlay on mount."""

    CSS_PATH = str(CSS_PATH)

    def __init__(self, deck: list[dict]) -> None:
        super().__init__()
        self._deck = deck

    def on_mount(self) -> None:
        self.push_screen(DeckViewerOverlay(self._deck))


class RelicViewerTestApp(App):
    """Pushes RelicViewerOverlay on mount."""

    CSS_PATH = str(CSS_PATH)

    def __init__(self, relics: list[dict], potions: list[dict]) -> None:
        super().__init__()
        self._relics = relics
        self._potions = potions

    def on_mount(self) -> None:
        self.push_screen(RelicViewerOverlay(self._relics, self._potions))


class GlobalHelpTestApp(App):
    """Pushes GlobalHelpOverlay on mount."""

    CSS_PATH = str(CSS_PATH)

    def __init__(self, screen_name: str = "") -> None:
        super().__init__()
        self._screen_name = screen_name

    def on_mount(self) -> None:
        self.push_screen(GlobalHelpOverlay(self._screen_name))


class ErrorRecoveryTestApp(App):
    """Pushes ErrorRecoveryScreen on mount and records messages."""

    CSS_PATH = str(CSS_PATH)

    def __init__(self, error_message: str = "Test error") -> None:
        super().__init__()
        self._error_message = error_message
        self.received_messages: list[str] = []

    def on_mount(self) -> None:
        self.push_screen(ErrorRecoveryScreen(self._error_message))

    def on_error_retry_message(self, message: ErrorRetryMessage) -> None:
        self.received_messages.append("retry")

    def on_error_go_map_message(self, message: ErrorGoMapMessage) -> None:
        self.received_messages.append("go_map")

    def on_error_quit_message(self, message: ErrorQuitMessage) -> None:
        self.received_messages.append("quit")


# ===================================================================
# 1. DeckViewerOverlay
# ===================================================================


@pytest.mark.asyncio
class TestDeckViewerOverlay:
    """Verify DeckViewerOverlay renders cards grouped by type."""

    async def test_renders_without_crash(self):
        """DeckViewerOverlay mounts successfully with a sample deck."""
        app = DeckViewerTestApp(SAMPLE_DECK)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, DeckViewerOverlay)

    async def test_title_shows_card_count(self):
        """The title bar shows the total number of cards."""
        app = DeckViewerTestApp(SAMPLE_DECK)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = str(app.screen.query_one("#deck-title").render())
            assert str(len(SAMPLE_DECK)) in rendered, (
                f"Expected card count {len(SAMPLE_DECK)} in title, got: {rendered}"
            )

    async def test_type_group_headers_present(self):
        """Each card type present in the deck has a group header."""
        app = DeckViewerTestApp(SAMPLE_DECK)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            for expected_label in ["ATTACKS", "SKILLS", "POWERS", "STATUS", "CURSES"]:
                assert expected_label in rendered.upper(), (
                    f"Expected group header '{expected_label}' in deck body"
                )

    async def test_card_names_displayed(self):
        """Individual card names appear in the rendered body."""
        app = DeckViewerTestApp(SAMPLE_DECK)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            for card_name in ["Strike", "Defend", "Bash", "Inflame", "Slimed", "Regret"]:
                assert card_name in rendered, (
                    f"Expected card name '{card_name}' in deck body"
                )

    async def test_upgraded_card_has_plus_suffix(self):
        """An upgraded card's name is rendered with a '+' suffix."""
        app = DeckViewerTestApp(SAMPLE_DECK)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            assert "Strike+" in rendered, (
                "Expected 'Strike+' for the upgraded Strike card"
            )

    async def test_upgrade_preview_shown(self):
        """Non-upgraded cards with after_upgrade data show an upgrade preview."""
        app = DeckViewerTestApp(SAMPLE_DECK)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            # Bash has damage 8->10
            assert "10" in rendered, (
                "Expected upgrade preview showing Bash damage upgrading to 10"
            )

    async def test_cost_displayed(self):
        """Card cost values appear in the rendered output."""
        app = DeckViewerTestApp(SAMPLE_DECK)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            assert "(2)" in rendered, "Expected '(2)' for Bash's cost"
            assert "(0)" in rendered, "Expected '(0)' for Offering's cost"

    async def test_negative_cost_shows_x(self):
        """Cards with negative cost display 'X' instead of a number."""
        app = DeckViewerTestApp(SAMPLE_DECK)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            assert "(X)" in rendered, "Expected '(X)' for Regret's negative cost"

    async def test_empty_deck(self):
        """An empty deck displays the 'deck empty' message."""
        app = DeckViewerTestApp([])
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, DeckViewerOverlay)
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            assert "empty" in rendered.lower() or "0" in rendered, (
                "Expected empty deck message in body"
            )

    async def test_footer_shows_close_hint(self):
        """The footer shows Esc/D close hint."""
        app = DeckViewerTestApp(SAMPLE_DECK)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = str(app.screen.query_one("#deck-footer").render())
            assert "Esc" in rendered or "D" in rendered, (
                "Expected close hint in footer"
            )

    async def test_escape_dismisses(self):
        """Pressing Escape dismisses the overlay."""
        app = DeckViewerTestApp(SAMPLE_DECK)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, DeckViewerOverlay)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, DeckViewerOverlay), (
                "DeckViewerOverlay should be dismissed after Escape"
            )

    async def test_d_key_dismisses(self):
        """Pressing D also dismisses the overlay."""
        app = DeckViewerTestApp(SAMPLE_DECK)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, DeckViewerOverlay)
            await pilot.press("d")
            await pilot.pause()
            assert not isinstance(app.screen, DeckViewerOverlay), (
                "DeckViewerOverlay should be dismissed after pressing D"
            )

    async def test_title_shows_type_counts(self):
        """The title shows per-type card counts (e.g. '3 ATTACKS')."""
        app = DeckViewerTestApp(SAMPLE_DECK)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = str(app.screen.query_one("#deck-title").render())
            # 3 Attacks, 2 Skills, 1 Power, 1 Status, 1 Curse
            assert "3" in rendered, "Expected '3' for 3 Attack cards in title"


# ===================================================================
# 2. RelicViewerOverlay
# ===================================================================


@pytest.mark.asyncio
class TestRelicViewerOverlay:
    """Verify RelicViewerOverlay renders relics and potions with descriptions."""

    async def test_renders_without_crash(self):
        """RelicViewerOverlay mounts successfully with sample data."""
        app = RelicViewerTestApp(SAMPLE_RELICS, SAMPLE_POTIONS)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, RelicViewerOverlay)

    async def test_title_shows_counts(self):
        """Title shows relic count and potion count."""
        app = RelicViewerTestApp(SAMPLE_RELICS, SAMPLE_POTIONS)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = str(app.screen.query_one("#deck-title").render())
            assert str(len(SAMPLE_RELICS)) in rendered, (
                f"Expected relic count {len(SAMPLE_RELICS)} in title"
            )
            assert str(len(SAMPLE_POTIONS)) in rendered, (
                f"Expected potion count {len(SAMPLE_POTIONS)} in title"
            )

    async def test_relic_names_displayed(self):
        """Each relic name appears in the rendered body."""
        app = RelicViewerTestApp(SAMPLE_RELICS, SAMPLE_POTIONS)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            for relic in SAMPLE_RELICS:
                name = relic["name"]
                assert name in rendered, f"Expected relic name '{name}' in body"

    async def test_relic_descriptions_displayed(self):
        """Each relic's description appears in the rendered body."""
        app = RelicViewerTestApp(SAMPLE_RELICS, SAMPLE_POTIONS)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            for relic in SAMPLE_RELICS:
                desc = relic["description"]
                assert desc in rendered, (
                    f"Expected relic description '{desc}' in body"
                )

    async def test_potion_names_displayed(self):
        """Each potion name appears in the rendered body."""
        app = RelicViewerTestApp(SAMPLE_RELICS, SAMPLE_POTIONS)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            for potion in SAMPLE_POTIONS:
                name = potion["name"]
                assert name in rendered, f"Expected potion name '{name}' in body"

    async def test_potion_descriptions_displayed(self):
        """Each potion's description appears in the rendered body."""
        app = RelicViewerTestApp(SAMPLE_RELICS, SAMPLE_POTIONS)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            for potion in SAMPLE_POTIONS:
                desc = potion["description"]
                assert desc in rendered, (
                    f"Expected potion description '{desc}' in body"
                )

    async def test_targeted_potion_shows_indicator(self):
        """A potion with target_type 'AnyEnemy' shows a '(targeted)' label."""
        app = RelicViewerTestApp(SAMPLE_RELICS, SAMPLE_POTIONS)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            assert "targeted" in rendered.lower(), (
                "Expected '(targeted)' for Fire Potion with AnyEnemy target"
            )

    async def test_empty_relics_shows_none(self):
        """When no relics are provided, '(none)' is displayed."""
        app = RelicViewerTestApp([], SAMPLE_POTIONS)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            assert "none" in rendered.lower(), (
                "Expected '(none)' for empty relics section"
            )

    async def test_empty_potions_shows_none(self):
        """When no potions are provided, '(none)' is displayed."""
        app = RelicViewerTestApp(SAMPLE_RELICS, [])
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            assert "none" in rendered.lower(), (
                "Expected '(none)' for empty potions section"
            )

    async def test_both_empty(self):
        """Overlay renders correctly even when both relics and potions are empty."""
        app = RelicViewerTestApp([], [])
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, RelicViewerOverlay)

    async def test_escape_dismisses(self):
        """Pressing Escape dismisses the overlay."""
        app = RelicViewerTestApp(SAMPLE_RELICS, SAMPLE_POTIONS)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, RelicViewerOverlay)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, RelicViewerOverlay), (
                "RelicViewerOverlay should be dismissed after Escape"
            )

    async def test_r_key_dismisses(self):
        """Pressing R also dismisses the overlay."""
        app = RelicViewerTestApp(SAMPLE_RELICS, SAMPLE_POTIONS)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, RelicViewerOverlay)
            await pilot.press("r")
            await pilot.pause()
            assert not isinstance(app.screen, RelicViewerOverlay), (
                "RelicViewerOverlay should be dismissed after pressing R"
            )

    async def test_footer_shows_close_hint(self):
        """Footer displays the Esc/R close hint."""
        app = RelicViewerTestApp(SAMPLE_RELICS, SAMPLE_POTIONS)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = str(app.screen.query_one("#deck-footer").render())
            assert "Esc" in rendered or "R" in rendered, (
                "Expected close hint in footer"
            )

    async def test_numbered_relic_listing(self):
        """Relics are numbered sequentially (1., 2., ...)."""
        app = RelicViewerTestApp(SAMPLE_RELICS, SAMPLE_POTIONS)
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#deck-list"))
            assert "1." in rendered, "Expected numbered listing starting with '1.'"
            assert "2." in rendered, "Expected numbered listing continuing with '2.'"


# ===================================================================
# 3. GlobalHelpOverlay
# ===================================================================


@pytest.mark.asyncio
class TestGlobalHelpOverlay:
    """Verify GlobalHelpOverlay shows context-aware bindings for each screen."""

    async def test_renders_without_crash(self):
        """GlobalHelpOverlay mounts successfully with no screen name."""
        app = GlobalHelpTestApp("")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, GlobalHelpOverlay)

    async def test_title_shows_keyboard_shortcuts(self):
        """Title displays 'Keyboard Shortcuts' (or i18n equivalent)."""
        app = GlobalHelpTestApp("")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = str(app.screen.query_one("#help-title").render())
            assert "Keyboard Shortcuts" in rendered or "shortcut" in rendered.lower(), (
                f"Expected 'Keyboard Shortcuts' in title, got: {rendered}"
            )

    async def test_general_controls_always_shown(self):
        """General controls ([D], [R], [Q], [Esc], [?/F1]) appear for any context."""
        app = GlobalHelpTestApp("")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#help-content"))
            for key in ["[D]", "[R]", "[Q]", "[Esc]", "[?/F1]"]:
                assert key in rendered, (
                    f"Expected general control '{key}' in help content"
                )

    async def test_general_controls_section_header(self):
        """A 'GENERAL CONTROLS' section header is displayed."""
        app = GlobalHelpTestApp("")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#help-content")).upper()
            assert "GENERAL" in rendered, (
                "Expected 'GENERAL CONTROLS' header in help content"
            )

    async def test_combat_screen_bindings(self):
        """When screen_name='CombatScreen', combat-specific bindings appear."""
        app = GlobalHelpTestApp("CombatScreen")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#help-content"))
            for key, desc in SCREEN_BINDINGS["CombatScreen"]:
                assert key in rendered, (
                    f"Expected CombatScreen binding '{key}' in help content"
                )
                assert desc in rendered, (
                    f"Expected CombatScreen description '{desc}' in help content"
                )

    async def test_map_screen_bindings(self):
        """When screen_name='MapScreen', map-specific bindings appear."""
        app = GlobalHelpTestApp("MapScreen")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#help-content"))
            for key, desc in SCREEN_BINDINGS["MapScreen"]:
                assert key in rendered, (
                    f"Expected MapScreen binding '{key}' in help content"
                )

    async def test_card_reward_screen_bindings(self):
        """When screen_name='CardRewardScreen', card reward bindings appear."""
        app = GlobalHelpTestApp("CardRewardScreen")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#help-content"))
            for key, desc in SCREEN_BINDINGS["CardRewardScreen"]:
                assert key in rendered, (
                    f"Expected CardRewardScreen binding '{key}' in help content"
                )

    async def test_rest_screen_bindings(self):
        """When screen_name='RestScreen', rest site bindings appear."""
        app = GlobalHelpTestApp("RestScreen")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#help-content"))
            for key, desc in SCREEN_BINDINGS["RestScreen"]:
                assert key in rendered, (
                    f"Expected RestScreen binding '{key}' in help content"
                )

    async def test_event_screen_bindings(self):
        """When screen_name='EventScreen', event bindings appear."""
        app = GlobalHelpTestApp("EventScreen")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#help-content"))
            for key, desc in SCREEN_BINDINGS["EventScreen"]:
                assert key in rendered, (
                    f"Expected EventScreen binding '{key}' in help content"
                )

    async def test_shop_screen_bindings(self):
        """When screen_name='ShopScreen', shop bindings appear."""
        app = GlobalHelpTestApp("ShopScreen")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#help-content"))
            for key, desc in SCREEN_BINDINGS["ShopScreen"]:
                assert key in rendered, (
                    f"Expected ShopScreen binding '{key}' in help content"
                )

    async def test_character_select_screen_bindings(self):
        """When screen_name='CharacterSelectScreen', character-select bindings appear."""
        app = GlobalHelpTestApp("CharacterSelectScreen")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#help-content"))
            for key, desc in SCREEN_BINDINGS["CharacterSelectScreen"]:
                assert key in rendered, (
                    f"Expected CharacterSelectScreen binding '{key}' in help content"
                )

    async def test_generic_screen_bindings(self):
        """When screen_name='GenericScreen', generic bindings appear."""
        app = GlobalHelpTestApp("GenericScreen")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#help-content"))
            for key, desc in SCREEN_BINDINGS["GenericScreen"]:
                assert key in rendered, (
                    f"Expected GenericScreen binding '{key}' in help content"
                )

    async def test_unknown_screen_shows_only_general(self):
        """An unknown screen name shows only general controls, no screen-specific."""
        app = GlobalHelpTestApp("NonExistentScreen")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#help-content"))
            assert "GENERAL" in rendered.upper(), "Expected general controls"
            assert "[D]" in rendered, "General [D] binding should appear"

    async def test_screen_controls_header_present_for_known_screen(self):
        """A 'SCREEN CONTROLS' header appears when there are screen-specific bindings."""
        app = GlobalHelpTestApp("CombatScreen")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = _collect_text(app.screen.query_one("#help-content")).upper()
            assert "SCREEN" in rendered and "CONTROL" in rendered, (
                "Expected 'SCREEN CONTROLS' header for CombatScreen"
            )

    async def test_escape_dismisses(self):
        """Pressing Escape dismisses the help overlay."""
        app = GlobalHelpTestApp("CombatScreen")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, GlobalHelpOverlay)
            await pilot.press("escape")
            await pilot.pause()
            assert not isinstance(app.screen, GlobalHelpOverlay), (
                "GlobalHelpOverlay should be dismissed after Escape"
            )

    async def test_footer_shows_close_hint(self):
        """Footer displays the Esc/? close hint."""
        app = GlobalHelpTestApp("")
        async with app.run_test(size=(100, 40)) as pilot:
            await pilot.pause()
            rendered = str(app.screen.query_one("#help-footer").render())
            assert "Esc" in rendered or "?" in rendered, (
                "Expected close hint in footer"
            )


# ===================================================================
# 4. ErrorRecoveryScreen
# ===================================================================


@pytest.mark.asyncio
class TestErrorRecoveryScreenOverlay:
    """Verify ErrorRecoveryScreen renders error message and R/M/Q buttons."""

    async def test_renders_without_crash(self):
        """ErrorRecoveryScreen mounts successfully with an error message."""
        app = ErrorRecoveryTestApp("Connection failed")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)

    async def test_error_message_displayed(self):
        """The provided error message text is visible in the screen."""
        error_text = "Engine timeout: no response within 30s"
        app = ErrorRecoveryTestApp(error_text)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            rendered = str(app.screen.query_one("#error-message").render())
            assert error_text in rendered, (
                f"Expected error text '{error_text}' in rendered widget, got: {rendered}"
            )

    async def test_error_title_displayed(self):
        """The ERROR title banner is rendered."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            rendered = str(app.screen.query_one("#error-title").render())
            assert "ERROR" in rendered.upper(), (
                f"Expected 'ERROR' in title, got: {rendered}"
            )

    async def test_r_button_displayed(self):
        """The [R] Retry option label is visible."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            rendered = str(app.screen.query_one("#error-options").render())
            assert "[R]" in rendered, "Missing [R] option label"

    async def test_m_button_displayed(self):
        """The [M] Go to Map option label is visible."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            rendered = str(app.screen.query_one("#error-options").render())
            assert "[M]" in rendered, "Missing [M] option label"

    async def test_q_button_displayed(self):
        """The [Q] Quit option label is visible."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            rendered = str(app.screen.query_one("#error-options").render())
            assert "[Q]" in rendered, "Missing [Q] option label"

    async def test_press_r_posts_retry_message(self):
        """Pressing R posts ErrorRetryMessage and pops the screen."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)
            await pilot.press("r")
            await pilot.pause()
            assert "retry" in app.received_messages, (
                f"Expected 'retry' message, got: {app.received_messages}"
            )
            assert not isinstance(app.screen, ErrorRecoveryScreen), (
                "ErrorRecoveryScreen should be popped after R"
            )

    async def test_press_m_posts_go_map_message(self):
        """Pressing M posts ErrorGoMapMessage and pops the screen."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)
            await pilot.press("m")
            await pilot.pause()
            assert "go_map" in app.received_messages, (
                f"Expected 'go_map' message, got: {app.received_messages}"
            )
            assert not isinstance(app.screen, ErrorRecoveryScreen), (
                "ErrorRecoveryScreen should be popped after M"
            )

    async def test_press_q_posts_quit_message(self):
        """Pressing Q posts ErrorQuitMessage and pops the screen."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)
            await pilot.press("q")
            await pilot.pause()
            assert "quit" in app.received_messages, (
                f"Expected 'quit' message, got: {app.received_messages}"
            )

    async def test_press_escape_posts_go_map(self):
        """Pressing Escape triggers go-to-map (same binding as M)."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert "go_map" in app.received_messages, (
                f"Expected 'go_map' from Escape, got: {app.received_messages}"
            )

    async def test_default_error_message(self):
        """When no error message is provided, a default placeholder is shown."""
        app = ErrorRecoveryTestApp("")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)
            rendered = str(app.screen.query_one("#error-message").render())
            assert len(rendered.strip()) > 0, (
                "Expected a non-empty default error message"
            )

    async def test_long_error_message(self):
        """A very long error message renders without crash."""
        long_msg = "Error: " + "x" * 500
        app = ErrorRecoveryTestApp(long_msg)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)
            rendered = str(app.screen.query_one("#error-message").render())
            assert "Error:" in rendered, (
                "Expected the long error message to be rendered"
            )
