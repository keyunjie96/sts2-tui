"""Deck viewer overlay -- shows the player's full deck from any screen.

Accessible globally by pressing D. Displays cards grouped by type with
resolved descriptions and upgrade preview information.
"""

from __future__ import annotations

import logging
from collections import defaultdict

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical, VerticalScroll
from textual.screen import Screen
from textual.widgets import Static
from rich.text import Text

from sts2_tui.tui.controller import _name_str, resolve_card_description
from sts2_tui.tui.i18n import L
from sts2_tui.tui.shared import CARD_TYPE_COLORS, build_upgrade_preview

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Type -> (display label, color)
# ---------------------------------------------------------------------------

_TYPE_I18N_KEYS: dict[str, str] = {
    "Attack": "deck_attacks",
    "Skill": "deck_skills",
    "Power": "deck_powers",
    "Status": "deck_status",
    "Curse": "deck_curses",
}

_TYPE_COLORS: dict[str, tuple[str, str]] = {
    "Attack": ("ATTACKS", CARD_TYPE_COLORS["Attack"]),
    "Skill": ("SKILLS", CARD_TYPE_COLORS["Skill"]),
    "Power": ("POWERS", CARD_TYPE_COLORS["Power"]),
    "Status": ("STATUS", CARD_TYPE_COLORS["Status"]),
    "Curse": ("CURSES", CARD_TYPE_COLORS["Curse"]),
}


def _type_label(card_type: str) -> tuple[str, str]:
    """Return (localized label, color) for a card type."""
    i18n_key = _TYPE_I18N_KEYS.get(card_type)
    if i18n_key:
        return (L(i18n_key), CARD_TYPE_COLORS.get(card_type, "white"))
    return (card_type.upper(), "white")

_TYPE_ORDER = ["Attack", "Skill", "Power", "Status", "Curse"]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _format_deck_card(card: dict) -> Text:
    """Build a Rich Text line for a single deck card."""
    name = _name_str(card.get("name"))
    cost = card.get("cost", 0)
    ctype = card.get("type", "")
    upgraded = card.get("upgraded", False)
    stats = card.get("stats") or {}
    raw_desc = card.get("description", "")
    resolved_desc = resolve_card_description(raw_desc, stats)

    # Name color based on type
    _, color = _TYPE_COLORS.get(ctype, ("?", "white"))

    star_cost = card.get("star_cost")

    t = Text()
    # Cost (with star_cost for Regent cards)
    cost_str = str(cost) if cost >= 0 else "X"
    if star_cost is not None:
        if cost >= 0:
            t.append(f"  ({cost_str}+\u2605{star_cost}) ", style="bold bright_yellow")
        else:
            t.append(f"  (\u2605{star_cost}) ", style="bold bright_yellow")
    else:
        t.append(f"  ({cost_str}) ", style="bold yellow")
    # Name (with + suffix if upgraded)
    display_name = f"{name}+" if upgraded else name
    t.append(display_name, style=f"bold {color}")
    # Description
    if resolved_desc:
        t.append(f"  {resolved_desc}", style="dim white")

    # Upgrade preview (only for non-upgraded cards)
    after_upgrade = card.get("after_upgrade")
    if after_upgrade and not upgraded:
        upgrade_parts = _build_upgrade_preview(card, after_upgrade)
        if upgrade_parts:
            t.append(f"\n          {L('upgrade')}: ", style="dim cyan")
            t.append(upgrade_parts, style="dim cyan")

    return t


def _build_upgrade_preview(card: dict, after_upgrade: dict) -> str:
    """Build a concise upgrade preview string showing stat changes."""
    return build_upgrade_preview(card, after_upgrade)


# ---------------------------------------------------------------------------
# DeckViewerOverlay
# ---------------------------------------------------------------------------


class DeckViewerOverlay(Screen):
    """Shows the player's full deck as a modal overlay."""

    BINDINGS = [
        Binding("escape", "dismiss_deck", "Close"),
        Binding("d", "dismiss_deck", "Close"),
        Binding("up,k", "scroll_up", "Up"),
        Binding("down,j", "scroll_down", "Down"),
    ]

    def __init__(self, deck: list[dict]) -> None:
        super().__init__()
        self.deck = deck

    def compose(self) -> ComposeResult:
        with Container(id="deck-overlay"):
            with Vertical(id="deck-container"):
                yield Static(self._title_text(), id="deck-title")
                with VerticalScroll(id="deck-list"):
                    yield Static(self._deck_body())
                yield Static(
                    Text(f"[Esc/D] {L('close')}  [Up/Down] {L('scroll')}", style="dim", justify="center"),
                    id="deck-footer",
                )

    def _title_text(self) -> Text:
        t = Text(justify="center")
        t.append(f"  {L('your_deck').format(len(self.deck))}  ", style="bold white on dark_blue")
        # Card count per type summary
        type_counts: dict[str, int] = {}
        for card in self.deck:
            ctype = card.get("type", "Unknown")
            type_counts[ctype] = type_counts.get(ctype, 0) + 1
        if type_counts:
            t.append("\n")
            parts = []
            for type_key in _TYPE_ORDER:
                count = type_counts.get(type_key, 0)
                if count > 0:
                    label, color = _type_label(type_key)
                    parts.append((f"{count} {label}", color))
            # Any unknown types
            for type_key, count in type_counts.items():
                if type_key not in _TYPE_ORDER and count > 0:
                    parts.append((f"{count} {type_key}", "white"))
            for i, (text, color) in enumerate(parts):
                if i > 0:
                    t.append(", ", style="dim")
                t.append(text, style=f"bold {color}")
        return t

    def _deck_body(self) -> Text:
        t = Text()

        # Group cards by type
        groups: dict[str, list[dict]] = defaultdict(list)
        for card in self.deck:
            ctype = card.get("type", "Unknown")
            groups[ctype].append(card)

        # Render each type group in order
        for type_key in _TYPE_ORDER:
            cards = groups.get(type_key)
            if not cards:
                continue
            label, color = _type_label(type_key)
            t.append(f"\n  {label} ({len(cards)})\n", style=f"bold {color} underline")
            for card in cards:
                t.append_text(_format_deck_card(card))
                t.append("\n")

        # Any unknown types
        for type_key, cards in groups.items():
            if type_key not in _TYPE_ORDER:
                t.append(f"\n  {type_key.upper()} ({len(cards)})\n", style="bold white underline")
                for card in cards:
                    t.append_text(_format_deck_card(card))
                    t.append("\n")

        if not self.deck:
            t.append(f"\n  {L('deck_empty')}\n", style="dim")

        return t

    def action_dismiss_deck(self) -> None:
        self.app.pop_screen()

    def action_scroll_up(self) -> None:
        try:
            scroll = self.query_one("#deck-list", VerticalScroll)
            scroll.scroll_up(animate=False)
        except Exception:
            pass

    def action_scroll_down(self) -> None:
        try:
            scroll = self.query_one("#deck-list", VerticalScroll)
            scroll.scroll_down(animate=False)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# RelicViewerOverlay
# ---------------------------------------------------------------------------


class RelicViewerOverlay(Screen):
    """Shows the player's relics and potions as a modal overlay.

    Accessible globally by pressing R. Displays all relics with full
    descriptions and all potions with their effects.
    """

    BINDINGS = [
        Binding("escape", "dismiss_relics", "Close"),
        Binding("r", "dismiss_relics", "Close"),
        Binding("up,k", "scroll_up", "Up"),
        Binding("down,j", "scroll_down", "Down"),
    ]

    def __init__(self, relics: list[dict], potions: list[dict]) -> None:
        super().__init__()
        self.relics = relics
        self.potions = potions

    def compose(self) -> ComposeResult:
        with Container(id="deck-overlay"):
            with Vertical(id="deck-container"):
                yield Static(self._title_text(), id="deck-title")
                with VerticalScroll(id="deck-list"):
                    yield Static(self._body())
                yield Static(
                    Text(f"[Esc/R] {L('close')}  [Up/Down] {L('scroll')}", style="dim", justify="center"),
                    id="deck-footer",
                )

    def _title_text(self) -> Text:
        t = Text(justify="center")
        t.append(f"  {L('relics')} ({len(self.relics)})  &  {L('potions')} ({len(self.potions)})  ",
                 style="bold white on dark_blue")
        return t

    def _body(self) -> Text:
        t = Text()

        # Relics section
        t.append(f"\n  {L('relics')}\n", style="bold cyan underline")
        if self.relics:
            for i, r in enumerate(self.relics):
                name = r.get("name", "?")
                desc = r.get("description", "")
                counter = r.get("counter", -1)
                t.append(f"\n  {i + 1}. ", style="dim")
                t.append(name, style="bold cyan")
                # Show counter when present (>= 0)
                if isinstance(counter, int) and counter >= 0:
                    t.append(f" [{counter}]", style="bold yellow")
                if desc:
                    t.append(f"\n     {desc}", style="dim white")
        else:
            t.append("\n  (none)\n", style="dim")

        # Potions section
        t.append(f"\n\n  {L('potions')}\n", style="bold green underline")
        if self.potions:
            for i, p in enumerate(self.potions):
                name = p.get("name", "?")
                desc = p.get("description", "")
                target = p.get("target_type", "")
                t.append(f"\n  {i + 1}. ", style="dim")
                t.append(name, style="bold green")
                if target == "AnyEnemy":
                    t.append(" (targeted)", style="dim yellow")
                if desc:
                    t.append(f"\n     {desc}", style="dim white")
        else:
            t.append("\n  (none)\n", style="dim")

        t.append("\n")
        return t

    def action_dismiss_relics(self) -> None:
        self.app.pop_screen()

    def action_scroll_up(self) -> None:
        try:
            scroll = self.query_one("#deck-list", VerticalScroll)
            scroll.scroll_up(animate=False)
        except Exception:
            pass

    def action_scroll_down(self) -> None:
        try:
            scroll = self.query_one("#deck-list", VerticalScroll)
            scroll.scroll_down(animate=False)
        except Exception:
            pass
