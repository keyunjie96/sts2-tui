"""Event screen -- shows event options (Neow, random events, etc.).

Driven by raw dict state from sts2-cli (decision == "event_choice").
"""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, Horizontal
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static
from textual.reactive import reactive
from rich.text import Text

from sts2_tui.tui.controller import GameController, _name_str, _resolve_inline_loc_keys, resolve_card_description
from sts2_tui.tui.i18n import L
from sts2_tui.tui.shared import build_status_footer

log = logging.getLogger(__name__)


class EventDoneMessage(Message):
    """Posted when the event screen is dismissed."""

    def __init__(self, next_state: dict) -> None:
        super().__init__()
        self.next_state = next_state


class EventOptionWidget(Static):
    """A single event option."""

    def __init__(self, option: dict, display_index: int, selected: bool = False) -> None:
        classes = "rest-option"  # Reuse rest-option styling for visual consistency
        if selected:
            classes += " --selected"
        super().__init__(classes=classes)
        self.option = option
        self.display_index = display_index

    def compose(self) -> ComposeResult:
        opt = self.option
        title = _name_str(opt.get("title")) or f"Option {self.display_index + 1}"
        desc = opt.get("description", "")
        is_locked = opt.get("is_locked", False)
        is_enabled = opt.get("is_enabled", True)

        title_text = Text(justify="center")
        title_text.append(f"[{self.display_index + 1}] ", style="bold yellow")
        color = "dim" if (is_locked or not is_enabled) else "bold white"
        title_text.append(title, style=color)
        if is_locked:
            title_text.append(f" ({L('locked')})", style="dim red")
        elif not is_enabled:
            title_text.append(f" ({L('unavailable')})", style="dim red")
        yield Static(title_text, classes="rest-option-title")

        if desc:
            # Resolve template vars using the full resolver (handles
            # {Var:diff()}, {Var:plural:...}, BBCode, etc.)
            option_vars = opt.get("vars") or {}
            # Pre-resolve any localization keys in var values
            # (e.g., "character": "DEFECT.title" -> "Defect")
            resolved_vars = {
                k: _name_str(v) if isinstance(v, str) and "." in v and v[0].isupper() else v
                for k, v in option_vars.items()
            }
            resolved = resolve_card_description(desc, resolved_vars)
            # Resolve literal localization keys embedded in text
            # (e.g. "Add CLUMSY.title to your Deck" -> "Add Clumsy to your Deck")
            resolved = _resolve_inline_loc_keys(resolved)

            desc_text = Text(justify="center")
            desc_text.append(resolved, style="dim white")
            yield Static(desc_text, classes="rest-option-desc")


class EventScreen(Screen):
    """Event screen -- show options and let the player choose."""

    BINDINGS = [
        Binding("1", "select_option(0)", "Option 1", show=False),
        Binding("2", "select_option(1)", "Option 2", show=False),
        Binding("3", "select_option(2)", "Option 3", show=False),
        Binding("4", "select_option(3)", "Option 4", show=False),
        Binding("5", "select_option(4)", "Option 5", show=False),
        Binding("enter", "confirm", "Confirm"),
        Binding("escape", "leave", "Leave"),
    ]

    selected: reactive[int] = reactive(-1, init=False)

    def __init__(self, state: dict, *, controller: GameController) -> None:
        super().__init__()
        self.state = state
        self.controller = controller
        self.options: list[dict] = state.get("options", [])
        self._is_composed = False
        self._busy = False
        self._refreshing = False
        self._can_leave = self._check_can_leave()

    def _check_can_leave(self) -> bool:
        """Determine whether the player can leave this event via Esc.

        Returns True when the state explicitly allows leaving or when one
        of the options looks like a "leave" choice.  Returns False for
        mandatory events (e.g. Neow) where the player must pick.
        """
        # Explicit engine flag takes priority
        if "can_leave" in self.state:
            return bool(self.state["can_leave"])
        # Heuristic: check if any option title contains "leave" (case-insensitive)
        for opt in self.options:
            title = _name_str(opt.get("title")) or ""
            if "leave" in title.lower():
                return True
        # No options at all -> allow leaving to avoid softlock
        if not self.options:
            return True
        # Default: mandatory event (no leave option found)
        return False

    def compose(self) -> ComposeResult:
        with Vertical(id="event-screen"):
            yield Static(self._title_text(), id="rest-title")

            if self.options:
                yield Horizontal(
                    *[EventOptionWidget(opt, i, selected=(i == self.selected))
                      for i, opt in enumerate(self.options)],
                    id="rest-options",
                )
            else:
                yield Static(
                    Text(f"  {L('no_options')}\n", style="dim"),
                    id="rest-options",
                )

            yield Static(self._footer_text(), id="rest-footer")

    def on_mount(self) -> None:
        self._is_composed = True

    def _title_text(self) -> Text:
        event_name = _name_str(self.state.get("event_name"))
        title = Text(justify="center")
        title.append(f"  {L('event')}: {event_name}  ", style="bold white on dark_blue")
        description = self.state.get("description")
        if description:
            # Strip BBCode/rich markup tags the engine sends (e.g. [rainbow ...])
            import re
            description = re.sub(r"\[/?[a-zA-Z][^\]]*\]", "", description)
            # Resolve literal localization keys (e.g. CLUMSY.title -> Clumsy)
            description = _resolve_inline_loc_keys(description)
            title.append(f"\n{description}", style="dim")
        title.append(f"\n {L('choose_option')}", style="white")
        return title

    def _footer_text(self) -> Text:
        max_idx = min(len(self.options), 5)
        bindings = Text()
        if max_idx > 0:
            bindings.append(f"[1-{max_idx}]", style="bold yellow")
            bindings.append(f" {L('select')}  ", style="dim")
            bindings.append("[Enter]", style="bold yellow")
            bindings.append(f" {L('confirm')}  ", style="dim")
        if self._can_leave:
            bindings.append("[Esc]", style="bold yellow")
            bindings.append(f" {L('leave')}", style="dim")
        return build_status_footer(bindings, self.state)

    async def _refresh_display(self) -> None:
        if not self._is_composed or self._refreshing:
            return
        self._refreshing = True
        try:
            for old in self.query("#event-screen"):
                await old.remove()

            widgets = []
            if self.options:
                widgets = [EventOptionWidget(opt, i, selected=(i == self.selected))
                           for i, opt in enumerate(self.options)]

            await self.mount(
                Vertical(
                    Static(self._title_text(), id="rest-title"),
                    Horizontal(
                        *widgets,
                        id="rest-options",
                    ) if widgets else Static(
                        Text("  No options available.\n", style="dim"),
                        id="rest-options",
                    ),
                    Static(self._footer_text(), id="rest-footer"),
                    id="event-screen",
                )
            )
        finally:
            self._refreshing = False

    async def watch_selected(self, value: int) -> None:
        await self._refresh_display()

    def action_select_option(self, index: int) -> None:
        if 0 <= index < len(self.options):
            opt = self.options[index]
            if opt.get("is_locked", False):
                self.notify("That option is locked.", severity="warning")
                return
            if not opt.get("is_enabled", True):
                self.notify("That option is unavailable.", severity="warning")
                return
            self.selected = index

    async def action_confirm(self) -> None:
        if self._busy:
            return
        if self.selected < 0:
            self.notify("Select an option first!", severity="warning")
            return

        opt = self.options[self.selected]
        if opt.get("is_locked", False):
            self.notify("That option is locked.", severity="warning")
            return
        if not opt.get("is_enabled", True):
            self.notify("That option is unavailable.", severity="warning")
            return

        option_index = opt.get("index", self.selected)

        self._busy = True
        try:
            state = await self.controller.choose(option_index)

            if state.get("type") == "error":
                self.notify(state.get("message", "Error."), severity="error")
                # Try leaving the room on error
                state = await self.controller.leave_room()

            self.app.post_message(EventDoneMessage(state))
            self.app.pop_screen()
        finally:
            self._busy = False

    async def action_leave(self) -> None:
        if self._busy:
            return
        if not self._can_leave:
            self.notify("You must choose an option.", severity="warning")
            return
        self._busy = True
        try:
            state = await self.controller.leave_room()
            self.app.post_message(EventDoneMessage(state))
            self.app.pop_screen()
        finally:
            self._busy = False
