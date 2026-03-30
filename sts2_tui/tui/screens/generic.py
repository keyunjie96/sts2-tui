"""Generic screen -- fallback for unsupported decision types.

Shows the raw decision type and options, and lets the user proceed
or pick a choice by index.
"""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static
from textual.reactive import reactive
from rich.text import Text

from sts2_tui.tui.controller import GameController, _name_str, resolve_card_description
from sts2_tui.tui.i18n import L
from sts2_tui.tui.shared import CARD_TYPE_COLORS, KEYWORD_ICONS, RARITY_COLORS, build_status_footer, build_upgrade_preview

log = logging.getLogger(__name__)


class GenericDoneMessage(Message):
    """Posted when the generic screen is dismissed."""

    def __init__(self, next_state: dict) -> None:
        super().__init__()
        self.next_state = next_state


class GenericScreen(Screen):
    """Fallback screen for unimplemented decision types.

    Tries to show options if present, otherwise offers a "proceed" button.
    Handles: shop, bundle_select, card_select, and any unknown decisions.
    """

    BINDINGS = [
        Binding("up,k", "move_selection(-1)", "Up", show=False),
        Binding("down,j", "move_selection(1)", "Down", show=False),
        Binding("enter", "proceed", "Proceed"),
        Binding("escape", "leave", "Leave"),
    ]

    selected: reactive[int] = reactive(-1, init=False)

    def __init__(self, state: dict, *, controller: GameController) -> None:
        super().__init__()
        self.state = state
        self.controller = controller
        self._busy = False
        # Gather options from various fields the engine might use
        self.options: list[dict] = (
            state.get("options", [])
            or state.get("choices", [])
            or state.get("cards", [])
            or state.get("bundles", [])
            or []
        )

    def compose(self) -> ComposeResult:
        decision = self.state.get("decision", "unknown")
        with Vertical(id="generic-screen"):
            title = Text(justify="center")
            # Show engine-provided title if available, otherwise use decision type
            engine_title = self.state.get("title")
            if engine_title:
                title.append(f"  {_name_str(engine_title)}  ", style="bold white on dark_blue")
            else:
                title.append(f"  {decision.upper().replace('_', ' ')}  ", style="bold white on dark_blue")
            # Show engine-provided description below the title
            engine_desc = self.state.get("description")
            if engine_desc:
                title.append(f"\n {engine_desc}", style="dim white")
            # Show select_type context if available (e.g., "Discard", "Exhaust")
            select_type = self.state.get("select_type")
            if select_type:
                title.append(f"\n [{select_type}]", style="bold cyan")
            yield Static(title, id="rest-title")

            if self.options:
                with VerticalScroll(id="map-viewport"):
                    yield Static(self._options_text())
            else:
                yield Static(Text(f"\n  {L('press_enter')}\n", style="dim"), id="map-viewport")

            bindings = Text()
            if self.options:
                bindings.append("[up/down]", style="bold yellow")
                bindings.append(f" {L('navigate')}  ", style="dim")
            bindings.append("[Enter]", style="bold yellow")
            bindings.append(f" {L('confirm')}  ", style="dim")
            bindings.append("[Esc]", style="bold yellow")
            bindings.append(f" {L('leave')}", style="dim")
            yield Static(build_status_footer(bindings, self.state), id="rest-footer")

    def _options_text(self) -> Text:
        t = Text()
        decision = self.state.get("decision", "")
        t.append(f"\n {L('options')}\n", style="bold white")
        # Show selection constraints for card_select
        if decision == "card_select":
            min_sel = self.state.get("min_select")
            max_sel = self.state.get("max_select")
            if min_sel is not None or max_sel is not None:
                constraint = Text()
                constraint.append(" ", style="dim")
                if min_sel is not None and max_sel is not None:
                    if min_sel == max_sel:
                        s = "s" if min_sel != 1 else ""
                        constraint.append(L("select_exactly").format(min_sel, s), style="bold cyan")
                    else:
                        constraint.append(L("select_range").format(min_sel, max_sel), style="bold cyan")
                elif max_sel is not None:
                    s = "s" if max_sel != 1 else ""
                    constraint.append(L("select_up_to").format(max_sel, s), style="bold cyan")
                elif min_sel is not None:
                    s = "s" if min_sel != 1 else ""
                    constraint.append(L("select_at_least").format(min_sel, s), style="bold cyan")
                t.append_text(constraint)
                t.append("\n")
        t.append("\n")
        for i, opt in enumerate(self.options):
            raw_title = opt.get("title") or opt.get("name")
            name = _name_str(raw_title) if raw_title else f"Option {i + 1}"
            desc = opt.get("description", "")
            stats = opt.get("stats") or {}

            # Resolve template variables in descriptions (card_select, etc.)
            if desc and stats:
                desc = resolve_card_description(desc, stats)

            # For card_select, show cost and type alongside name
            cost = opt.get("cost")
            card_type = opt.get("type", "")

            # Type-based color for card_select
            type_color = CARD_TYPE_COLORS.get(card_type, "white")

            marker = " >>>" if i == self.selected else "    "
            t.append(f"{marker} [{i + 1}] ", style="bold yellow")
            # Show "+" suffix for upgraded cards
            if opt.get("upgraded"):
                t.append(f"{name}+", style=f"bold {type_color}")
            else:
                t.append(f"{name}", style=f"bold {type_color}")
            # Show keyword icons
            for kw in opt.get("keywords") or []:
                if isinstance(kw, str):
                    icon = KEYWORD_ICONS.get(kw.title(), "")
                    if icon:
                        t.append(f" {icon}", style="bold red" if kw.title() == "Exhaust" else "bold cyan")
            # Show enchantment badge (Regent mechanic, same as combat CardWidget)
            enchantment = opt.get("enchantment")
            if enchantment:
                ench_name = _name_str(enchantment) if isinstance(enchantment, dict) else str(enchantment)
                ench_amount = opt.get("enchantment_amount")
                if ench_amount:
                    t.append(f" \u2728{ench_name} +{ench_amount}", style="bold bright_green")
                else:
                    t.append(f" \u2728{ench_name}", style="bold bright_green")
            # Show affliction badge
            affliction = opt.get("affliction")
            if affliction:
                aff_name = _name_str(affliction) if isinstance(affliction, dict) else str(affliction)
                aff_amount = opt.get("affliction_amount")
                if aff_amount:
                    t.append(f" \u2620{aff_name} {aff_amount}", style="bold bright_red")
                else:
                    t.append(f" \u2620{aff_name}", style="bold bright_red")
            if cost is not None:
                t.append(f" ({cost})", style="yellow")
            star_cost = opt.get("star_cost")
            if star_cost is not None:
                t.append(f"+\u2605{star_cost}", style="bold bright_yellow")
            if card_type:
                t.append(f" [{card_type}]", style="dim cyan")
            # Show rarity for card_select (consistent with card_reward and shop)
            rarity = opt.get("rarity", "")
            if rarity and decision == "card_select":
                rarity_label, rarity_color = RARITY_COLORS.get(
                    rarity, (rarity, "dim")
                )
                t.append(f" {rarity_label}", style=f"bold {rarity_color}")
            if desc:
                t.append(f"  - {desc[:120]}", style="dim")
            t.append("\n")

            # Show upgrade preview for card_select (Smith at rest site, etc.)
            if decision == "card_select":
                after_upgrade = opt.get("after_upgrade")
                if after_upgrade:
                    upgrade_str = self._build_upgrade_preview(opt, after_upgrade)
                    if upgrade_str:
                        t.append(f"          {L('upgrade')}: {upgrade_str}\n", style="dim cyan")
        return t

    @staticmethod
    def _build_upgrade_preview(card: dict, after_upgrade: dict) -> str:
        """Build a concise upgrade preview string showing stat changes."""
        return build_upgrade_preview(card, after_upgrade)

    def action_move_selection(self, delta: int) -> None:
        if not self.options:
            return
        if self.selected < 0:
            self.selected = 0
        else:
            self.selected = max(0, min(len(self.options) - 1, self.selected + delta))
        # Re-render and auto-scroll to keep selection visible
        try:
            viewport = self.query_one("#map-viewport")
            for child in viewport.children:
                if isinstance(child, Static):
                    child.update(self._options_text())
                    break
            # Estimate line height and scroll to keep selected item visible
            # Each option takes ~2-4 lines. Scroll so selected item is in view.
            lines_per_item = 3
            target_scroll = max(0, (self.selected - 3) * lines_per_item)
            viewport.scroll_to(y=target_scroll, animate=False)
        except Exception:
            pass

    async def action_proceed(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            decision = self.state.get("decision", "")

            if self.selected >= 0 and self.options:
                opt = self.options[self.selected]
                # Try various action formats depending on decision type
                if decision == "bundle_select":
                    state = await self.controller.select_bundle(
                        opt.get("index", self.selected),
                    )
                elif decision == "card_select":
                    state = await self.controller.select_cards(
                        str(opt.get("index", self.selected)),
                    )
                else:
                    state = await self.controller.choose(
                        opt.get("index", self.selected),
                    )
            else:
                # No selection -- just proceed
                if decision == "shop":
                    state = await self.controller.leave_room()
                elif decision == "card_select":
                    state = await self.controller.skip_select()
                elif decision == "bundle_select":
                    state = await self.controller.select_bundle(0)
                else:
                    state = await self.controller.proceed()

            if state.get("type") == "error":
                self.notify(state.get("message", "Error."), severity="error")
                # Try proceed as fallback
                state = await self.controller.proceed()

            self.app.post_message(GenericDoneMessage(state))
            self.app.pop_screen()
        finally:
            self._busy = False

    async def action_leave(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            state = await self.controller.leave_room()

            if state.get("type") == "error":
                state = await self.controller.proceed()

            self.app.post_message(GenericDoneMessage(state))
            self.app.pop_screen()
        finally:
            self._busy = False
