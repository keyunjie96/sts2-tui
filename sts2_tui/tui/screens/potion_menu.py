"""Potion menu overlay -- modal for using or discarding potions in combat.

Opened by pressing [P] during combat. Shows all potion slots with
descriptions. The player presses [1-3] to use a potion (with targeting
prompt if the potion requires a target), [D] then [1-3] to discard a
potion, or [Esc] to close the menu.
"""

from __future__ import annotations

import logging
from typing import Any

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static
from rich.text import Text

from sts2_tui.tui.i18n import L

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class PotionUseRequest(Message):
    """Posted when the player confirms using a potion."""

    def __init__(self, potion_index: int, target_index: int | None = None) -> None:
        super().__init__()
        self.potion_index = potion_index
        self.target_index = target_index


class PotionDiscardRequest(Message):
    """Posted when the player confirms discarding a potion."""

    def __init__(self, potion_index: int) -> None:
        super().__init__()
        self.potion_index = potion_index


# ---------------------------------------------------------------------------
# Overlay screen
# ---------------------------------------------------------------------------


class PotionMenuOverlay(Screen):
    """Modal overlay showing all potion slots with use/discard options.

    State machine:
    - IDLE: waiting for a key. [1-N] starts USE flow, [D] enters DISCARD mode.
    - TARGETING: a targeted potion was selected; Tab cycles targets, Enter confirms.
    - DISCARD: waiting for [1-N] to pick a potion to discard.
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel", show=False),
        Binding("d", "enter_discard", "Discard mode", show=False),
        Binding("1", "slot(0)", "Slot 1", show=False),
        Binding("2", "slot(1)", "Slot 2", show=False),
        Binding("3", "slot(2)", "Slot 3", show=False),
        Binding("4", "slot(3)", "Slot 4", show=False),
        Binding("5", "slot(4)", "Slot 5", show=False),
        Binding("tab", "cycle_target", "Next target", show=False),
        Binding("shift+tab", "cycle_target_back", "Prev target", show=False),
        Binding("up", "cycle_target_back", "Prev target", show=False),
        Binding("down", "cycle_target", "Next target", show=False),
        Binding("enter", "confirm_target", "Confirm target", show=False),
    ]

    def __init__(
        self,
        potions: list[dict[str, Any]],
        max_slots: int = 3,
        enemies: list[dict[str, Any]] | None = None,
    ) -> None:
        super().__init__()
        self.potions = potions
        self.max_slots = max(max_slots, len(potions))
        self.enemies = [e for e in (enemies or []) if not e.get("is_dead")]
        self._mode: str = "idle"  # idle | targeting | discard
        self._pending_potion: dict[str, Any] | None = None
        self._target_index: int = 0

    # -- compose ---------------------------------------------------------------

    def compose(self) -> ComposeResult:
        with Container(id="potion-overlay"):
            with Vertical(id="potion-container"):
                yield Static(self._title_text(), id="potion-title")
                yield Static(self._body_text(), id="potion-body")
                yield Static(self._footer_text(), id="potion-footer")

    # -- rendering helpers -----------------------------------------------------

    def _title_text(self) -> Text:
        t = Text(justify="center")
        if self._mode == "discard":
            t.append(f"  {L('potion_menu_title')} -- {L('potion_discard_mode')}  ",
                     style="bold white on dark_red")
        elif self._mode == "targeting":
            pot_name = (self._pending_potion or {}).get("name", "?")
            t.append(f"  {L('potion_menu_title')} -- {L('potion_select_target')}: {pot_name}  ",
                     style="bold white on dark_blue")
        else:
            t.append(f"  {L('potion_menu_title')}  ", style="bold white on dark_blue")
        return t

    def _body_text(self) -> Text:
        t = Text()

        if self._mode == "targeting":
            # Show enemy list for targeting
            t.append(f"\n  {L('potion_select_target')}:\n", style="bold yellow")
            for i, e in enumerate(self.enemies):
                marker = ">>>" if i == self._target_index else "   "
                style = "bold yellow" if i == self._target_index else "white"
                hp = e.get("hp", 0)
                max_hp = e.get("max_hp", 0)
                t.append(f"\n  {marker} [{i + 1}] ", style=style)
                t.append(f"{e.get('name', '?')}", style=f"bold {style}")
                t.append(f"  ({hp}/{max_hp} HP)", style="dim")
            t.append("\n")
            return t

        # Normal or discard mode -- show potion slots
        filled_indices = {p.get("index", i): p for i, p in enumerate(self.potions)}

        for slot in range(self.max_slots):
            pot = filled_indices.get(slot)
            t.append(f"\n  [{slot + 1}] ", style="bold bright_yellow")
            if pot:
                name = pot.get("name", "?")
                desc = pot.get("description", "")
                target_type = pot.get("target_type", "")
                t.append(name, style="bold cyan")
                if desc:
                    t.append(f" -- {desc}", style="dim white")
                if target_type == "AnyEnemy":
                    t.append(f" ({L('potion_targeted')})", style="dim yellow")
                elif target_type == "AllEnemy":
                    t.append(f" ({L('potion_aoe')})", style="dim yellow")
            else:
                t.append(f"({L('potion_empty')})", style="dim")
        t.append("\n")
        return t

    def _footer_text(self) -> Text:
        t = Text(justify="center")
        if self._mode == "targeting":
            t.append(f"[Tab] {L('potion_next_target')}  ", style="dim")
            t.append(f"[Enter] {L('confirm')}  ", style="dim")
            t.append(f"[Esc] {L('potion_cancel')}", style="dim")
        elif self._mode == "discard":
            t.append(f"[1-{self.max_slots}] {L('potion_discard_slot')}  ", style="dim")
            t.append(f"[Esc] {L('potion_cancel')}", style="dim")
        else:
            t.append(f"[1-{self.max_slots}] {L('potion_use')}  ", style="dim")
            t.append(f"[D+1-{self.max_slots}] {L('potion_discard_label')}  ", style="dim")
            t.append(f"[Esc] {L('potion_cancel')}", style="dim")
        return t

    def _refresh_content(self) -> None:
        """Re-render the overlay content without remounting."""
        try:
            self.query_one("#potion-title", Static).update(self._title_text())
            self.query_one("#potion-body", Static).update(self._body_text())
            self.query_one("#potion-footer", Static).update(self._footer_text())
        except Exception:
            pass

    # -- actions ---------------------------------------------------------------

    def action_cancel(self) -> None:
        if self._mode in ("targeting", "discard"):
            # Go back to idle mode
            self._mode = "idle"
            self._pending_potion = None
            self._refresh_content()
        else:
            self.app.pop_screen()

    def action_enter_discard(self) -> None:
        if self._mode == "idle":
            self._mode = "discard"
            self._refresh_content()

    def action_slot(self, slot: int) -> None:
        if self._mode == "targeting":
            # In targeting mode, number keys select a target enemy
            if 0 <= slot < len(self.enemies):
                self._target_index = slot
                self._confirm_use()
            return

        # Find the potion at this slot
        pot = self._potion_at_slot(slot)

        if self._mode == "discard":
            if pot is None:
                self.notify(L("potion_empty_slot"), severity="warning")
                return
            self.app.pop_screen()
            self.app.post_message(PotionDiscardRequest(pot.get("index", slot)))
            return

        # idle mode -> use potion
        if pot is None:
            self.notify(L("potion_empty_slot"), severity="warning")
            return

        if pot.get("target_type") == "AnyEnemy":
            if not self.enemies:
                self.notify(L("potion_no_targets"), severity="warning")
                return
            self._mode = "targeting"
            self._pending_potion = pot
            self._target_index = 0
            self._refresh_content()
        else:
            # Non-targeted potion -- use immediately
            self.app.pop_screen()
            self.app.post_message(PotionUseRequest(pot.get("index", slot)))

    def action_cycle_target(self) -> None:
        if self._mode == "targeting" and self.enemies:
            self._target_index = (self._target_index + 1) % len(self.enemies)
            self._refresh_content()

    def action_cycle_target_back(self) -> None:
        if self._mode == "targeting" and self.enemies:
            self._target_index = (self._target_index - 1) % len(self.enemies)
            self._refresh_content()

    def action_confirm_target(self) -> None:
        if self._mode == "targeting":
            self._confirm_use()

    def _confirm_use(self) -> None:
        """Confirm use of the pending targeted potion."""
        pot = self._pending_potion
        if pot is None:
            return
        target_idx: int | None = None
        if self.enemies:
            actual = min(self._target_index, len(self.enemies) - 1)
            target_idx = self.enemies[actual].get("index", 0)
        self.app.pop_screen()
        self.app.post_message(PotionUseRequest(pot.get("index", 0), target_idx))

    def _potion_at_slot(self, slot: int) -> dict[str, Any] | None:
        """Return the potion dict occupying the given slot index, or None."""
        for p in self.potions:
            if p.get("index", -1) == slot:
                return p
        return None
