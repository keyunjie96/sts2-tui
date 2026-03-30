"""Shared UI components for sls-cli TUI screens.

Provides:
- GlobalHelpOverlay: context-aware help overlay accessible from any screen
- ErrorRecoveryScreen: shown when the bridge returns an error
- build_status_footer: builds a consistent status bar for any screen
"""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static
from rich.text import Text

from sts2_tui.tui.i18n import L

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Shared color constants
# ---------------------------------------------------------------------------

# Card type colors -- used across combat, card_reward, shop, deck_viewer, generic
CARD_TYPE_COLORS: dict[str, str] = {
    "Attack": "#ff5555",
    "Skill": "#55ff55",
    "Power": "#5588ff",
    "Status": "dim",
    "Curse": "#cc44cc",
}

# Rarity colors -- used across card_reward, shop, deck_viewer
RARITY_COLORS: dict[str, tuple[str, str]] = {
    "Common": ("Common", "white"),
    "Uncommon": ("Uncommon", "#5588ff"),
    "Rare": ("Rare", "#ffcc00"),
    "Special": ("Special", "#ff88cc"),
    "Curse": ("Curse", "#cc44cc"),
    "Basic": ("Basic", "dim"),
}


# Keyword icons -- used across combat, card_reward, shop, generic
KEYWORD_ICONS: dict[str, str] = {
    "Exhaust": "\u2716",
    "Ethereal": "\u2728",
    "Innate": "\u2605",
    "Retain": "\u21ba",
    "Sly": "\u2694",
}

# Room type colors for combat TopBar
ROOM_TYPE_COLORS: dict[str, str] = {
    "Boss": "bold red",
    "Elite": "bold bright_magenta",
    "Monster": "dim white",
}


# ---------------------------------------------------------------------------
# HP color helper
# ---------------------------------------------------------------------------

def hp_color(hp: int, max_hp: int) -> str:
    """Return a color string based on the HP ratio."""
    ratio = hp / max_hp if max_hp else 0
    return "green" if ratio > 0.5 else "yellow" if ratio > 0.25 else "red"


# ---------------------------------------------------------------------------
# Upgrade preview builder (shared across card_reward, deck_viewer, generic)
# ---------------------------------------------------------------------------

def build_upgrade_preview(card: dict, after_upgrade: dict) -> str:
    """Build a concise upgrade preview string showing stat changes.

    Used by card_reward, deck_viewer, and generic screens to show
    how a card changes when upgraded.
    """
    from sts2_tui.tui.controller import humanize_stat_key, resolve_card_description

    parts: list[str] = []
    current_cost = card.get("cost", 0)
    upgraded_cost = after_upgrade.get("cost", current_cost)
    if upgraded_cost != current_cost:
        parts.append(f"Cost {current_cost} -> {upgraded_cost}")

    current_stats = card.get("stats") or {}
    upgraded_stats = after_upgrade.get("stats") or {}
    all_keys = set(current_stats.keys()) | set(upgraded_stats.keys())
    for key in sorted(all_keys):
        current_val = current_stats.get(key)
        upgraded_val = upgraded_stats.get(key)
        if current_val != upgraded_val and current_val is not None and upgraded_val is not None:
            display_key = humanize_stat_key(key)
            parts.append(f"{display_key} {current_val} -> {upgraded_val}")
        elif current_val is None and upgraded_val is not None:
            display_key = humanize_stat_key(key)
            parts.append(f"{display_key} +{upgraded_val}")

    # Show keyword changes from upgrade
    added_kws = after_upgrade.get("added_keywords") or []
    for kw in added_kws:
        kw_name = kw if isinstance(kw, str) else str(kw)
        parts.append(f"+{kw_name}")
    removed_kws = after_upgrade.get("removed_keywords") or []
    for kw in removed_kws:
        kw_name = kw if isinstance(kw, str) else str(kw)
        parts.append(f"-{kw_name}")

    if not parts:
        # Fall back to showing upgraded description if stats differ
        up_stats = after_upgrade.get("stats") or {}
        up_desc_raw = after_upgrade.get("description", "")
        if up_desc_raw:
            up_desc = resolve_card_description(up_desc_raw, up_stats)
            current_desc_raw = card.get("description", "")
            current_desc = resolve_card_description(current_desc_raw, current_stats)
            if up_desc and up_desc != current_desc:
                return up_desc
        return ""

    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Per-screen key binding descriptions for the help overlay
# ---------------------------------------------------------------------------

# Maps screen class name -> list of (key, description) tuples
SCREEN_BINDINGS: dict[str, list[tuple[str, str]]] = {
    "CombatScreen": [
        ("[1-9]", "Select card"),
        ("[Left/Right]", "Cycle cards"),
        ("[Tab]", "Cycle target"),
        ("[Up/Down]", "Cycle targets"),
        ("[Enter]", "Play card"),
        ("[E]", "End turn"),
        ("[P]", "Use potion"),
    ],
    "MapScreen": [
        ("[1-9]", "Select path"),
    ],
    "CardRewardScreen": [
        ("[1-5]", "Select card"),
        ("[Enter]", "Confirm selection"),
        ("[Esc]", "Skip reward"),
    ],
    "RestScreen": [
        ("[1-3]", "Select option"),
        ("[Enter]", "Confirm"),
        ("[Esc]", "Leave"),
    ],
    "EventScreen": [
        ("[1-5]", "Select option"),
        ("[Enter]", "Confirm"),
        ("[Esc]", "Leave"),
    ],
    "ShopScreen": [
        ("[1-9,0,a-f]", "Select item"),
        ("[Enter]", "Buy"),
        ("[L/Esc]", "Leave shop"),
    ],
    "CharacterSelectScreen": [
        ("[1-5]", "Select character"),
        ("[Enter]", "Start game"),
        ("[Esc]", "Quit"),
    ],
    "GenericScreen": [
        ("[Up/Down]", "Navigate"),
        ("[Enter]", "Confirm"),
        ("[Esc]", "Leave"),
    ],
}


# ---------------------------------------------------------------------------
# Global Help Overlay
# ---------------------------------------------------------------------------


class GlobalHelpOverlay(Screen):
    """Context-aware help overlay showing bindings for the current screen.

    Accessible from any screen via ? or F1.  Shows both screen-specific
    bindings and general bindings (D/R/Q/Esc).
    """

    BINDINGS = [
        Binding("escape", "dismiss_help", "Close"),
        Binding("question_mark", "dismiss_help", "Close"),
        Binding("f1", "dismiss_help", "Close"),
    ]

    def __init__(self, screen_name: str = "") -> None:
        super().__init__()
        self._screen_name = screen_name

    def compose(self) -> ComposeResult:
        screen_bindings = SCREEN_BINDINGS.get(self._screen_name, [])

        with Container(id="help-overlay"):
            with Vertical(id="help-container"):
                yield Static(
                    Text(f" {L('keyboard_shortcuts')} ", style="bold white", justify="center"),
                    id="help-title",
                )
                with VerticalScroll(id="help-content"):
                    # Screen-specific bindings
                    if screen_bindings:
                        header = Text()
                        header.append(f" {L('screen_controls')}", style="bold underline white")
                        yield Static(header)
                        yield Static(Text(""))
                        for key, desc in screen_bindings:
                            line = Text()
                            # Pad key to 14 chars for alignment
                            line.append(f" {key:<14}", style="bold yellow")
                            line.append(desc, style="white")
                            yield Static(line)
                        yield Static(Text(""))

                    # General bindings
                    gen_header = Text()
                    gen_header.append(f" {L('general_controls')}", style="bold underline white")
                    yield Static(gen_header)
                    yield Static(Text(""))

                    general = [
                        ("[D]", L("view_deck")),
                        ("[R]", "View relics & potions"),
                        ("[Esc]", L("back_close")),
                        ("[Q]", L("quit_game")),
                        ("[?/F1]", L("this_help")),
                    ]
                    for key, desc in general:
                        line = Text()
                        line.append(f" {key:<14}", style="bold yellow")
                        line.append(desc, style="white")
                        yield Static(line)

                yield Static(
                    Text(f"[Esc/?] {L('close')}", style="dim", justify="center"),
                    id="help-footer",
                )

    def action_dismiss_help(self) -> None:
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# Error Recovery Screen
# ---------------------------------------------------------------------------


class ErrorRetryMessage(Message):
    """Posted when user wants to retry the last action."""

    pass


class ErrorGoMapMessage(Message):
    """Posted when user wants to go back to the map."""

    pass


class ErrorQuitMessage(Message):
    """Posted when user wants to quit from the error screen."""

    pass


class ErrorRecoveryScreen(Screen):
    """Shown when the bridge returns an error.

    Offers three options: retry, go to map, or quit.
    """

    BINDINGS = [
        Binding("r", "retry", "Retry"),
        Binding("m", "go_map", "Map"),
        Binding("q", "quit_game", "Quit"),
        Binding("escape", "go_map", "Back"),
    ]

    def __init__(self, error_message: str = "") -> None:
        super().__init__()
        self._error_message = error_message or L("error_message")

    def compose(self) -> ComposeResult:
        with Vertical(id="error-recovery-screen"):
            # Title
            title = Text(justify="center")
            title.append(f"\n\n  {L('error_occurred')}  \n\n", style="bold white on dark_red")
            yield Static(title, id="error-title")

            # Error message
            msg = Text(justify="center")
            msg.append(f"\n{self._error_message}\n\n", style="white")
            yield Static(msg, id="error-message")

            # Options
            options = Text(justify="center")
            options.append("[R]", style="bold yellow")
            options.append(f" {L('error_retry')}    ", style="white")
            options.append("[M]", style="bold yellow")
            options.append(f" {L('error_go_map')}    ", style="white")
            options.append("[Q]", style="bold yellow")
            options.append(f" {L('error_quit')}", style="white")
            yield Static(options, id="error-options")

    def action_retry(self) -> None:
        self.app.post_message(ErrorRetryMessage())
        self.app.pop_screen()

    def action_go_map(self) -> None:
        self.app.post_message(ErrorGoMapMessage())
        self.app.pop_screen()

    def action_quit_game(self) -> None:
        self.app.post_message(ErrorQuitMessage())
        self.app.pop_screen()


# ---------------------------------------------------------------------------
# Status footer builder
# ---------------------------------------------------------------------------


def build_status_footer(
    bindings_text: Text,
    state: dict | None = None,
) -> Text:
    """Build a consistent status bar combining key bindings and player info.

    Parameters
    ----------
    bindings_text:
        Rich Text with the screen-specific key binding hints.
    state:
        The current game state dict (if available) to extract HP/gold/act/floor.

    Returns a single-line Text suitable for a footer Static widget.
    """
    t = Text(justify="center")

    # Player info (HP, gold, act/floor) when state is available
    if state:
        player = state.get("player", {})
        ctx = state.get("context", {})
        hp = player.get("hp")
        max_hp = player.get("max_hp")
        gold = player.get("gold")
        act = ctx.get("act")
        floor = ctx.get("floor")

        if hp is not None and max_hp is not None:
            color = hp_color(hp, max_hp)
            t.append(f"\u2764 {hp}/{max_hp}", style=f"bold {color}")
            t.append("  ", style="dim")

        if gold is not None:
            t.append(f"\u25c9 {gold}", style="bold yellow")
            t.append("  ", style="dim")

        if act is not None and floor is not None:
            t.append(f"{L('act')} {act} {L('floor')} {floor}", style="dim white")
            t.append("  ", style="dim")

        t.append("|  ", style="dim")

    # Key bindings
    t.append_text(bindings_text)

    # Global hint
    t.append("  [?]", style="bold yellow")
    t.append(f" {L('help')}", style="dim")

    return t
