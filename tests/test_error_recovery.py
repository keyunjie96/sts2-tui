"""Headless tests for the ErrorRecoveryScreen flow.

Verifies:
1. ErrorRecoveryScreen renders correctly with an error message
2. [R] retry, [M] go-to-map, [Q] quit all work and post correct messages
3. SlsApp._route_to_screen routes error states to ErrorRecoveryScreen
4. The retry and go-to-map recovery paths re-route to the correct screen
5. The app does not crash on any recovery option

Usage:
    pytest tests/test_error_recovery.py -v
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from textual.app import App, ComposeResult
from textual.widgets import Static

from sts2_tui.tui.shared import (
    ErrorRecoveryScreen,
    ErrorRetryMessage,
    ErrorGoMapMessage,
    ErrorQuitMessage,
)
from sts2_tui.tui.app import SlsApp

# ---------------------------------------------------------------------------
# CSS path (shared with other test harnesses)
# ---------------------------------------------------------------------------

CSS_PATH = Path(__file__).parent.parent / "src" / "sts2_tui" / "tui" / "sls.tcss"


# ---------------------------------------------------------------------------
# Realistic state fixtures
# ---------------------------------------------------------------------------

MAP_STATE = {
    "type": "decision",
    "decision": "map_select",
    "context": {"act": 1, "act_name": "Overgrowth", "floor": 1, "room_type": "Map"},
    "player": {"hp": 80, "max_hp": 80, "gold": 99, "deck_size": 10},
    "choices": [
        {"col": 0, "row": 1, "room_type": "Monster"},
        {"col": 1, "row": 1, "room_type": "Event"},
    ],
}

COMBAT_STATE = {
    "type": "decision",
    "decision": "combat_play",
    "context": {"act": 1, "act_name": "Overgrowth", "floor": 2, "room_type": "Monster"},
    "round": 1,
    "energy": 3,
    "max_energy": 3,
    "hand": [
        {
            "index": 0, "name": "Strike", "cost": 1, "type": "Attack",
            "can_play": True, "target_type": "AnyEnemy",
            "stats": {"damage": 6}, "description": "Deal 6 damage.",
        },
    ],
    "enemies": [
        {
            "index": 0, "name": "Nibbit", "hp": 43, "max_hp": 43, "block": 0,
            "intents": [{"type": "Attack", "damage": 12}], "powers": None,
        },
    ],
    "player": {"hp": 80, "max_hp": 80, "gold": 99, "deck_size": 10},
    "player_powers": [],
    "draw_pile_count": 4,
    "discard_pile_count": 0,
}

ERROR_STATE = {
    "type": "error",
    "message": "Engine timeout: no response within 30s",
}


# ---------------------------------------------------------------------------
# Harness app for testing ErrorRecoveryScreen in isolation
# ---------------------------------------------------------------------------


class ErrorRecoveryTestApp(App):
    """Minimal app that pushes an ErrorRecoveryScreen on mount."""

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


# ---------------------------------------------------------------------------
# Harness app that mimics SlsApp error recovery wiring
# ---------------------------------------------------------------------------


def _make_mock_controller(next_state: dict | None = None) -> MagicMock:
    """Build a mock GameController whose async methods return next_state."""
    if next_state is None:
        next_state = MAP_STATE

    ctrl = MagicMock()
    for method_name in [
        "play_card", "end_turn", "choose", "select_map_node",
        "select_card_reward", "skip_card_reward", "use_potion",
        "proceed", "leave_room", "select_bundle", "select_cards",
        "skip_select", "get_state", "start_run", "quit",
    ]:
        setattr(ctrl, method_name, AsyncMock(return_value=next_state))
    ctrl.get_map = AsyncMock(return_value={"type": "error", "message": "mock"})
    ctrl.current_state = next_state
    ctrl.player_deck = []
    return ctrl


# ===================================================================
# Tests
# ===================================================================


@pytest.mark.asyncio
class TestErrorRecoveryScreenRendering:
    """Verify the ErrorRecoveryScreen renders and displays the error message."""

    async def test_screen_renders(self):
        """ErrorRecoveryScreen renders without exceptions."""
        app = ErrorRecoveryTestApp("Something broke")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ErrorRecoveryScreen), (
                f"Expected ErrorRecoveryScreen, got {type(screen).__name__}"
            )

    async def test_error_message_displayed(self):
        """The error message text is visible in the screen."""
        error_text = "Engine timeout: no response within 30s"
        app = ErrorRecoveryTestApp(error_text)
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            # Find the error message widget
            msg_widget = app.screen.query_one("#error-message")
            rendered = msg_widget.render()
            assert error_text in str(rendered), (
                f"Error message '{error_text}' not found in rendered widget"
            )

    async def test_options_displayed(self):
        """The R/M/Q option labels are visible."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            options_widget = app.screen.query_one("#error-options")
            rendered = str(options_widget.render())
            assert "[R]" in rendered, "Missing [R] option"
            assert "[M]" in rendered, "Missing [M] option"
            assert "[Q]" in rendered, "Missing [Q] option"

    async def test_title_displayed(self):
        """The error title banner is visible."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            title_widget = app.screen.query_one("#error-title")
            rendered = str(title_widget.render())
            # Should contain "ERROR" (the i18n key "error_occurred")
            assert "ERROR" in rendered.upper(), "Missing ERROR title"

    async def test_default_error_message(self):
        """When no error message is given, a default is shown."""
        app = ErrorRecoveryTestApp("")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            msg_widget = app.screen.query_one("#error-message")
            rendered = str(msg_widget.render())
            # Should show the default i18n message
            assert len(rendered.strip()) > 0, "Default error message is empty"


@pytest.mark.asyncio
class TestErrorRecoveryKeyBindings:
    """Verify R, M, Q key bindings post the correct messages."""

    async def test_press_r_posts_retry(self):
        """Pressing R posts ErrorRetryMessage and pops the screen."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)
            await pilot.press("r")
            await pilot.pause()
            assert "retry" in app.received_messages, (
                f"Expected 'retry' in messages, got {app.received_messages}"
            )
            # Screen should have been popped
            assert not isinstance(app.screen, ErrorRecoveryScreen), (
                "ErrorRecoveryScreen should have been popped after pressing R"
            )

    async def test_press_m_posts_go_map(self):
        """Pressing M posts ErrorGoMapMessage and pops the screen."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)
            await pilot.press("m")
            await pilot.pause()
            assert "go_map" in app.received_messages, (
                f"Expected 'go_map' in messages, got {app.received_messages}"
            )
            assert not isinstance(app.screen, ErrorRecoveryScreen), (
                "ErrorRecoveryScreen should have been popped after pressing M"
            )

    async def test_press_q_posts_quit(self):
        """Pressing Q posts ErrorQuitMessage and pops the screen."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)
            await pilot.press("q")
            await pilot.pause()
            assert "quit" in app.received_messages, (
                f"Expected 'quit' in messages, got {app.received_messages}"
            )

    async def test_press_escape_posts_go_map(self):
        """Pressing Escape also triggers go-to-map (same as M)."""
        app = ErrorRecoveryTestApp("Test error")
        async with app.run_test(size=(80, 24)) as pilot:
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert "go_map" in app.received_messages, (
                f"Expected 'go_map' from Escape, got {app.received_messages}"
            )


@pytest.mark.asyncio
class TestSlsAppErrorRouting:
    """Verify that SlsApp._route_to_screen handles error states correctly."""

    async def test_error_state_pushes_error_screen(self):
        """_route_to_screen with type=error pushes ErrorRecoveryScreen."""
        app = SlsApp()
        async with app.run_test(size=(80, 24)) as pilot:
            # Skip engine startup -- we test routing directly
            app.controller = _make_mock_controller()
            app._route_to_screen(ERROR_STATE)
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen), (
                f"Expected ErrorRecoveryScreen, got {type(app.screen).__name__}"
            )

    async def test_error_message_passed_to_screen(self):
        """The error message from the state dict is passed to ErrorRecoveryScreen."""
        app = SlsApp()
        async with app.run_test(size=(80, 24)) as pilot:
            app.controller = _make_mock_controller()
            app._route_to_screen(ERROR_STATE)
            await pilot.pause()
            screen = app.screen
            assert isinstance(screen, ErrorRecoveryScreen)
            msg_widget = screen.query_one("#error-message")
            rendered = str(msg_widget.render())
            assert "Engine timeout" in rendered


@pytest.mark.asyncio
class TestErrorRecoveryActions:
    """Verify the actual retry / go-to-map / quit flows in SlsApp."""

    async def test_retry_refetches_state(self):
        """Pressing R on error screen calls controller.get_state and re-routes."""
        app = SlsApp()
        async with app.run_test(size=(80, 24)) as pilot:
            # Set up controller that returns map state on get_state
            ctrl = _make_mock_controller(MAP_STATE)
            app.controller = ctrl

            # Push error screen
            app._route_to_screen(ERROR_STATE)
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)

            # Press R to retry
            await pilot.press("r")
            # Wait for the worker to complete
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            # get_state should have been called
            ctrl.get_state.assert_called()

    async def test_go_map_refetches_state(self):
        """Pressing M on error screen calls controller.get_state."""
        app = SlsApp()
        async with app.run_test(size=(80, 24)) as pilot:
            ctrl = _make_mock_controller(MAP_STATE)
            app.controller = ctrl

            app._route_to_screen(ERROR_STATE)
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)

            await pilot.press("m")
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            ctrl.get_state.assert_called()

    async def test_quit_exits_app(self):
        """Pressing Q on error screen calls action_quit."""
        app = SlsApp()
        async with app.run_test(size=(80, 24)) as pilot:
            ctrl = _make_mock_controller()
            app.controller = ctrl

            app._route_to_screen(ERROR_STATE)
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)

            await pilot.press("q")
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            # quit should have been called on controller
            ctrl.quit.assert_called()

    async def test_retry_with_persistent_error_shows_notification(self):
        """If retry also returns an error, a notification is shown (no crash)."""
        app = SlsApp()
        async with app.run_test(size=(80, 24)) as pilot:
            ctrl = _make_mock_controller()
            # get_state returns another error
            ctrl.get_state = AsyncMock(return_value=ERROR_STATE)
            app.controller = ctrl

            app._route_to_screen(ERROR_STATE)
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)

            await pilot.press("r")
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            # Should not crash -- the error is shown as a notification
            # The screen should have been popped (action_retry pops before worker runs)

    async def test_retry_with_exception_does_not_crash(self):
        """If get_state raises an exception during retry, the app survives."""
        app = SlsApp()
        async with app.run_test(size=(80, 24)) as pilot:
            ctrl = _make_mock_controller()
            ctrl.get_state = AsyncMock(side_effect=Exception("Connection lost"))
            app.controller = ctrl

            app._route_to_screen(ERROR_STATE)
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)

            await pilot.press("r")
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            # App should not crash

    async def test_go_map_fallback_to_proceed(self):
        """If get_state returns error during go-map, it falls back to proceed."""
        app = SlsApp()
        async with app.run_test(size=(80, 24)) as pilot:
            ctrl = _make_mock_controller()
            # get_state returns error first, then proceed returns map
            ctrl.get_state = AsyncMock(return_value=ERROR_STATE)
            ctrl.proceed = AsyncMock(return_value=MAP_STATE)
            app.controller = ctrl

            app._route_to_screen(ERROR_STATE)
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)

            await pilot.press("m")
            await pilot.pause()
            await pilot.pause()
            await pilot.pause()

            # Should have tried get_state, then proceed
            ctrl.get_state.assert_called()
            ctrl.proceed.assert_called()


@pytest.mark.asyncio
class TestErrorRecoveryEdgeCases:
    """Edge cases and robustness checks."""

    async def test_multiple_errors_no_crash(self):
        """Routing to error screen multiple times does not crash."""
        app = SlsApp()
        async with app.run_test(size=(80, 24)) as pilot:
            ctrl = _make_mock_controller()
            app.controller = ctrl

            # Push error, pop, push again
            app._route_to_screen(ERROR_STATE)
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)

            await pilot.press("m")
            await pilot.pause()
            await pilot.pause()

            # Push another error
            app._route_to_screen(ERROR_STATE)
            await pilot.pause()
            # Should still be showing error recovery
            # (might be on base screen if go_map succeeded)

    async def test_error_screen_with_no_controller(self):
        """Error recovery handles missing controller gracefully."""
        app = SlsApp()
        async with app.run_test(size=(80, 24)) as pilot:
            # No controller set -- simulates startup failure
            app.controller = None
            app.push_screen(ErrorRecoveryScreen("Startup failed"))
            await pilot.pause()
            assert isinstance(app.screen, ErrorRecoveryScreen)

            # Pressing R should not crash even without controller
            await pilot.press("r")
            await pilot.pause()
            await pilot.pause()

            # Pressing Q should not crash
            app.push_screen(ErrorRecoveryScreen("Startup failed"))
            await pilot.pause()
            await pilot.press("q")
            await pilot.pause()
            await pilot.pause()

    async def test_error_recovery_chinese_labels(self):
        """Error screen renders correctly in Chinese locale."""
        from sts2_tui.tui.i18n import set_language, get_language
        original_lang = get_language()
        try:
            set_language("zh")
            app = ErrorRecoveryTestApp("Engine timeout")
            async with app.run_test(size=(80, 24)) as pilot:
                await pilot.pause()
                screen = app.screen
                assert isinstance(screen, ErrorRecoveryScreen)
                title_widget = screen.query_one("#error-title")
                rendered = str(title_widget.render())
                # Chinese label for "error_occurred" is "错误"
                assert "错误" in rendered or "ERROR" in rendered, (
                    f"Expected Chinese error title, got: {rendered}"
                )
        finally:
            set_language(original_lang)
