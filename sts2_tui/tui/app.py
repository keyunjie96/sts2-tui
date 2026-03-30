"""Main Textual application for sts2-tui -- Slay the Spire 2 terminal client.

Now driven by sts2-cli (real game engine) via EngineBridge.
"""

from __future__ import annotations

import logging
from pathlib import Path

from textual.app import App
from textual.binding import Binding
from textual.widgets import Static
from rich.text import Text

from sts2_tui.tui.controller import GameController
from sts2_tui.tui.i18n import L

from sts2_tui.tui.screens.combat import (
    CombatScreen,
    CombatVictoryMessage,
    CombatDefeatMessage,
    CombatTransitionMessage,
)
from sts2_tui.tui.screens.map import MapScreen, MapNodeSelectedMessage
from sts2_tui.tui.screens.card_reward import CardRewardScreen, CardRewardDoneMessage
from sts2_tui.tui.screens.rest import RestScreen, RestDoneMessage
from sts2_tui.tui.screens.event import EventScreen, EventDoneMessage
from sts2_tui.tui.screens.character_select import CharacterSelectScreen, CharacterSelectedMessage
from sts2_tui.tui.screens.shop import ShopScreen, ShopDoneMessage
from sts2_tui.tui.screens.generic import GenericScreen, GenericDoneMessage
from sts2_tui.tui.screens.deck_viewer import DeckViewerOverlay, RelicViewerOverlay
from sts2_tui.tui.shared import (
    GlobalHelpOverlay,
    ErrorRecoveryScreen,
    ErrorRetryMessage,
    ErrorGoMapMessage,
    ErrorQuitMessage,
)

log = logging.getLogger(__name__)

CSS_PATH = Path(__file__).parent / "sls.tcss"


# ---------------------------------------------------------------------------
# Application
# ---------------------------------------------------------------------------


class SlsApp(App):
    """Slay the Spire 2 -- Terminal Client (sts2-cli backend)."""

    TITLE = "SLS-CLI  |  Slay the Spire 2"
    SUB_TITLE = "Terminal Client"
    CSS_PATH = str(CSS_PATH)

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("ctrl+q", "quit", "Quit", show=False),
        Binding("d", "view_deck", "Deck", show=False),
        Binding("r", "view_relics", "Relics", show=False),
        Binding("question_mark", "show_global_help", "Help", show=False),
        Binding("f1", "show_global_help", "Help", show=False),
    ]

    def __init__(self, character: str | None = None, seed: str | None = None, lang: str = "en") -> None:
        super().__init__()
        self._character = character
        self._seed = seed
        self._lang = lang
        self.bridge = None
        self.controller: GameController | None = None
        self._last_decision: str = ""  # track for transition messages

    async def on_mount(self) -> None:
        """Start the engine and show character select (or start directly)."""
        # Set global UI language before anything renders
        from sts2_tui.tui.i18n import set_language
        set_language(self._lang)

        try:
            from sts2_tui.bridge import EngineBridge
            self.bridge = EngineBridge()
            ready = await self.bridge.start()
            if ready.get("type") != "ready":
                self._show_error(f"Engine returned unexpected init: {ready}")
                return
            self.controller = GameController(self.bridge)
            log.info("EngineBridge connected: %s", ready)
        except Exception as e:
            from sts2_tui.bridge import _STS2_CLI_SEARCH_PATHS
            search_paths = ", ".join(str(p) for p in _STS2_CLI_SEARCH_PATHS)
            self._show_error(
                f"Could not start sts2-cli engine.\n\n"
                f"Error: {e}\n\n"
                f"Set STS2_CLI_PATH or place sts2-cli at one of:\n"
                f"  {search_paths}\n"
                f"See README for setup instructions."
            )
            return

        if self._character:
            # Character specified on command line -- start immediately
            await self._start_run(self._character)
        else:
            # Show character select screen
            self.push_screen(CharacterSelectScreen())

    def _show_error(self, message: str) -> None:
        """Show a static error screen."""
        t = Text(justify="center")
        t.append("\n\n  ERROR  \n\n", style="bold white on dark_red")
        t.append(f"\n{message}\n", style="white")
        t.append("\n[Q] Quit", style="bold yellow")
        self.mount(Static(t))

    # ------------------------------------------------------------------
    # Run lifecycle
    # ------------------------------------------------------------------

    async def _start_run(self, character: str) -> None:
        """Start a run and route to the first screen."""
        assert self.controller is not None
        try:
            self.notify(f"Starting run as {character}...")
            state = await self.controller.start_run(character, self._seed, lang=self._lang)
            if state.get("type") == "error":
                self.notify(state.get("message", "Error starting run"), severity="error")
                return
            self._route_to_screen(state)
        except Exception as e:
            log.exception("Error starting run")
            self.notify(f"Error: {e}", severity="error")

    # ------------------------------------------------------------------
    # Screen router -- the central dispatcher
    # ------------------------------------------------------------------

    def _route_to_screen(self, state: dict) -> None:
        """Push the appropriate screen based on the response decision type."""
        if state.get("type") in ("error", "error_recovery"):
            error_msg = state.get("message") or state.get("error") or "Engine error"
            self.push_screen(ErrorRecoveryScreen(error_msg))
            return

        decision = state.get("decision", "")
        controller = self.controller
        assert controller is not None

        # -- Screen transition feedback --
        prev = self._last_decision
        self._last_decision = decision
        _TRANSITION_MESSAGES: dict[tuple[str, str], str] = {
            ("combat_play", "card_reward"): "transition_combat_victory",
            ("combat_play", "map_select"): "transition_combat_victory",
            ("map_select", "combat_play"): "",  # no message for entering combat
            ("map_select", "rest_site"): "transition_rest_site",
            ("map_select", "event_choice"): "transition_event",
            ("map_select", "shop"): "transition_shop",
        }
        transition_key = _TRANSITION_MESSAGES.get((prev, decision))
        if transition_key is None:
            # Generic transitions
            _DECISION_MESSAGES: dict[str, str] = {
                "card_reward": "transition_card_reward",
                "rest_site": "transition_rest_site",
                "event_choice": "transition_event",
                "shop": "transition_shop",
                "map_select": "transition_entered_map",
            }
            transition_key = _DECISION_MESSAGES.get(decision, "")
        if transition_key:
            self.notify(L(transition_key), timeout=2)

        # Pop back to the base screen before pushing a new game screen.
        # Use a bounded loop to avoid infinite pop in edge cases (e.g. if
        # an overlay's dismiss handler pushes another screen).
        max_pops = len(self.screen_stack)
        for _ in range(max_pops):
            if len(self.screen_stack) <= 1:
                break
            self.pop_screen()

        match decision:
            case "combat_play":
                self.push_screen(CombatScreen(state, controller=controller))
            case "map_select":
                self.push_screen(MapScreen(state, controller=controller))
            case "card_reward":
                self.push_screen(CardRewardScreen(state, controller=controller))
            case "rest_site":
                self.push_screen(RestScreen(state, controller=controller))
            case "event_choice":
                self.push_screen(EventScreen(state, controller=controller))
            case "game_over":
                self._handle_game_over(state)
            case "shop":
                self.push_screen(ShopScreen(state, controller=controller))
            case "bundle_select" | "card_select" | "unknown":
                self.push_screen(GenericScreen(state, controller=controller))
            case _:
                # Unknown decision -- use generic screen
                log.warning("Unknown decision type: %s", decision)
                self.push_screen(GenericScreen(state, controller=controller))

    def _handle_game_over(self, state: dict) -> None:
        """Show game over info with run summary."""
        from sts2_tui.tui.controller import extract_player
        victory = state.get("victory", False)
        player_data = extract_player(state)
        ctx = state.get("context", {})
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

        # Run summary — include room type and boss/enemy name when available
        room_type = ctx.get("room_type", "")
        boss_info = ctx.get("boss", {})
        boss_name = boss_info.get("name", "") if isinstance(boss_info, dict) else ""
        floor_text = f"{L('act')} {act}, {L('floor')} {floor}"
        if room_type:
            floor_text += f" ({room_type})"
        t.append(f"\n  {floor_text}\n", style="bold white")
        if boss_name and not victory and room_type == "Boss":
            t.append(f"  vs. {boss_name}\n", style="bold bright_red")
        t.append(f"\n  {L('hp_label')}: {hp}/{max_hp}", style="white")
        t.append(f"  |  {L('gold_label')}: {gold}", style="bold yellow")
        t.append(f"  |  {L('deck')}: {deck_size}\n", style="white")

        # Potions held
        potions = player_data.get("potions", [])
        if potions:
            t.append(f"\n  {L('potions')} ({len(potions)}): ", style="dim")
            for i, p in enumerate(potions):
                if i > 0:
                    t.append(", ", style="dim")
                t.append(p.get("name", "?"), style="bold bright_magenta")
            t.append("\n")

        # Relics collected
        if relics:
            t.append(f"\n  {L('relics')} ({len(relics)}): ", style="dim")
            for i, r in enumerate(relics):
                if i > 0:
                    t.append(", ", style="dim")
                t.append(r.get("name", "?"), style="bold cyan")
            t.append("\n")

        t.append(f"\n\n[Q] {L('quit')}", style="bold yellow")

        while len(self.screen_stack) > 1:
            self.pop_screen()
        # Guard against mounting the game-over widget twice (DuplicateIds)
        try:
            existing = self.screen.query_one("#game-over-display")
            if existing:
                return
        except Exception:
            pass
        # Mount on the current screen (not the App) so the widget has a
        # proper parent and gets cleaned up on next screen transition.
        self.screen.mount(Static(t, id="game-over-display"))

    # ------------------------------------------------------------------
    # Message handlers for screen transitions
    # ------------------------------------------------------------------

    def on_character_selected_message(self, message: CharacterSelectedMessage) -> None:
        """Character was picked -- start the run."""
        self.run_worker(self._start_run(message.character_id), exclusive=True)

    def on_map_node_selected_message(self, message: MapNodeSelectedMessage) -> None:
        """Map node selected -- route to the next screen."""
        self._route_to_screen(message.next_state)

    def on_combat_victory_message(self, message: CombatVictoryMessage) -> None:
        """Combat won -- route based on next state from engine."""
        self._route_to_screen(message.next_state)

    def on_combat_defeat_message(self, message: CombatDefeatMessage) -> None:
        """Player died."""
        self._route_to_screen(message.next_state)

    def on_combat_transition_message(self, message: CombatTransitionMessage) -> None:
        """Combat ended with a non-combat decision (card_reward, map, etc.)."""
        self._route_to_screen(message.next_state)

    def on_card_reward_done_message(self, message: CardRewardDoneMessage) -> None:
        """Card reward finished -- route to next screen."""
        self._route_to_screen(message.next_state)

    def on_rest_done_message(self, message: RestDoneMessage) -> None:
        """Rest site finished -- route to next screen."""
        self._route_to_screen(message.next_state)

    def on_event_done_message(self, message: EventDoneMessage) -> None:
        """Event finished -- route to next screen."""
        self._route_to_screen(message.next_state)

    def on_shop_done_message(self, message: ShopDoneMessage) -> None:
        """Shop screen finished -- route to next screen."""
        self._route_to_screen(message.next_state)

    def on_generic_done_message(self, message: GenericDoneMessage) -> None:
        """Generic screen finished -- route to next screen."""
        self._route_to_screen(message.next_state)

    # ------------------------------------------------------------------
    # Global help overlay
    # ------------------------------------------------------------------

    def action_show_global_help(self) -> None:
        """Open the global help overlay, showing context-aware bindings."""
        # Don't open if a help overlay is already showing
        if any(isinstance(s, GlobalHelpOverlay) for s in self.screen_stack):
            return
        # Determine which screen is currently active (skip overlays)
        screen_name = ""
        for s in reversed(self.screen_stack):
            name = type(s).__name__
            if name not in ("GlobalHelpOverlay", "DeckViewerOverlay", "RelicViewerOverlay"):
                screen_name = name
                break
        self.push_screen(GlobalHelpOverlay(screen_name))

    # ------------------------------------------------------------------
    # Error recovery handlers
    # ------------------------------------------------------------------

    def on_error_retry_message(self, message: ErrorRetryMessage) -> None:
        """Retry: re-fetch the current state from the engine."""
        if self.controller:
            self.run_worker(self._retry_last_action(), exclusive=True)

    def on_error_go_map_message(self, message: ErrorGoMapMessage) -> None:
        """Go to map: try to get back to map by fetching current state."""
        if self.controller:
            self.run_worker(self._error_go_map(), exclusive=True)

    def on_error_quit_message(self, message: ErrorQuitMessage) -> None:
        """Quit the game from error screen."""
        self.run_worker(self.action_quit(), exclusive=True)

    async def _retry_last_action(self) -> None:
        """Re-fetch the current state and route to appropriate screen."""
        assert self.controller is not None
        try:
            state = await self.controller.get_state()
            if state.get("type") == "error":
                self.notify(state.get("message", "Still failing"), severity="error")
                return
            self._route_to_screen(state)
        except Exception as e:
            self.notify(f"Retry failed: {e}", severity="error")

    async def _error_go_map(self) -> None:
        """Try to navigate back to the map."""
        assert self.controller is not None
        try:
            state = await self.controller.get_state()
            if state.get("type") == "error":
                state = await self.controller.proceed()
            self._route_to_screen(state)
        except Exception as e:
            self.notify(f"Cannot return to map: {e}", severity="error")

    # ------------------------------------------------------------------
    # Deck viewer
    # ------------------------------------------------------------------

    def action_view_deck(self) -> None:
        """Open the deck viewer overlay showing the player's current deck."""
        if self.controller is None:
            return
        # Don't open deck viewer if one is already open
        if any(isinstance(s, DeckViewerOverlay) for s in self.screen_stack):
            return
        deck = self.controller.player_deck
        if not deck:
            self.notify(L("no_deck_data"), severity="warning")
            return
        self.push_screen(DeckViewerOverlay(deck))

    # ------------------------------------------------------------------
    # Relic & potion viewer
    # ------------------------------------------------------------------

    def action_view_relics(self) -> None:
        """Open the relic/potion viewer overlay."""
        if self.controller is None:
            return
        # Don't open if one is already open
        if any(isinstance(s, RelicViewerOverlay) for s in self.screen_stack):
            return
        state = self.controller.current_state
        if not state:
            self.notify(L("no_game_data"), severity="warning")
            return
        from sts2_tui.tui.controller import extract_player
        player = extract_player(state)
        relics = player.get("relics", [])
        potions = player.get("potions", [])
        if not relics and not potions:
            self.notify(L("no_relics_potions"), severity="warning")
            return
        self.push_screen(RelicViewerOverlay(relics, potions))

    # ------------------------------------------------------------------
    # Cleanup
    # ------------------------------------------------------------------

    async def action_quit(self) -> None:
        """Shut down the engine and quit."""
        if self.controller:
            try:
                await self.controller.quit()
            except Exception:
                pass
        self.exit()


def main() -> None:
    import argparse
    parser = argparse.ArgumentParser(description="SLS-CLI: Slay the Spire 2 Terminal Client")
    parser.add_argument("--character", "-c", default=None, help="Character to play (Ironclad, Silent, Defect, Necrobinder, Regent)")
    parser.add_argument("--seed", "-s", default=None, help="Game seed")
    parser.add_argument("--lang", "-l", default="en", choices=["en", "zh"],
                        help="Display language: en (English) or zh (Chinese). Default: en")
    args = parser.parse_args()
    app = SlsApp(character=args.character, seed=args.seed, lang=args.lang)
    app.run()


if __name__ == "__main__":
    main()
