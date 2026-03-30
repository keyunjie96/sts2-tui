"""Rest site screen -- choose an option (heal, smith, etc.).

Now driven by raw dict state from sts2-cli (decision == "rest_site").
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

from sts2_tui.tui.controller import GameController, extract_player
from sts2_tui.tui.i18n import L
from sts2_tui.tui.shared import build_status_footer, hp_color

log = logging.getLogger(__name__)

# Base heal percentage at rest sites.  The engine does not send the actual
# heal amount; relics like Regal Pillow may change it.  This constant is
# the STS2 base value and is used only for the preview text.
_REST_HEAL_FRACTION = 0.3


# Display info for rest site options
# option_id -> (icon, i18n_key_or_fallback, color)
# Labels resolved at render time via L() for i18n support.
OPTION_DISPLAY: dict[str, tuple[str, str, str]] = {
    "HEAL": ("\u2764", "rest", "green"),
    "SMITH": ("\u2692", "smith", "cyan"),
    "LIFT": ("\u2b06", "lift", "yellow"),
    "TOKE": ("\ud83d\udca8", "toke", "magenta"),
    "DIG": ("\u26cf", "dig", "yellow"),
    "RECALL": ("\u21ba", "recall", "blue"),
}


class RestDoneMessage(Message):
    """Posted when the rest screen is dismissed."""

    def __init__(self, next_state: dict) -> None:
        super().__init__()
        self.next_state = next_state


class RestOptionWidget(Static):
    """A single rest site option."""

    def __init__(
        self,
        option: dict,
        display_index: int,
        selected: bool = False,
        player_hp: int = 0,
        player_max_hp: int = 0,
    ) -> None:
        classes = "rest-option"
        if selected:
            classes += " --selected"
        super().__init__(classes=classes)
        self.option = option
        self.display_index = display_index
        self.player_hp = player_hp
        self.player_max_hp = player_max_hp

    def compose(self) -> ComposeResult:
        opt = self.option
        option_id = opt.get("option_id", "")
        name = opt.get("name", option_id)
        is_enabled = opt.get("is_enabled", True)

        icon, label_key, color = OPTION_DISPLAY.get(option_id, ("?", name, "white"))
        label = L(label_key)
        if not is_enabled:
            color = "dim"

        title_text = Text(justify="center")
        title_text.append(f"[{self.display_index + 1}] ", style="bold yellow")
        title_text.append(f"{icon} {label}", style=f"bold {color}")
        if not is_enabled:
            title_text.append(f" ({L('unavailable')})", style="dim red")
        yield Static(title_text, classes="rest-option-title")

        desc_text = Text(justify="center")
        if option_id == "HEAL":
            heal_amount = int(self.player_max_hp * _REST_HEAL_FRACTION)
            new_hp = min(self.player_hp + heal_amount, self.player_max_hp)
            # Show "~" prefix because relics may modify the actual heal amount
            desc_text.append(
                "~" + L("heal_desc").format(heal_amount, self.player_hp, new_hp),
                style="dim white",
            )
        elif option_id == "SMITH":
            desc_text.append(L("smith_desc"), style="dim white")
        else:
            desc_text.append(name, style="dim white")
        yield Static(desc_text, classes="rest-option-desc")


class RestScreen(Screen):
    """Rest site -- choose between available options."""

    BINDINGS = [
        Binding("1", "select_option(0)", "Option 1", show=False),
        Binding("2", "select_option(1)", "Option 2", show=False),
        Binding("3", "select_option(2)", "Option 3", show=False),
        Binding("4", "select_option(3)", "Option 4", show=False),
        Binding("5", "select_option(4)", "Option 5", show=False),
        Binding("6", "select_option(5)", "Option 6", show=False),
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

    def _player_hp(self) -> tuple[int, int]:
        """Return (current_hp, max_hp) for the player."""
        player = extract_player(self.state)
        return player.get("hp", 0), player.get("max_hp", 0)

    def compose(self) -> ComposeResult:
        hp, max_hp = self._player_hp()
        with Vertical(id="rest-screen"):
            yield Static(self._title_text(), id="rest-title")
            yield Horizontal(
                *[RestOptionWidget(opt, i, selected=(i == self.selected),
                                   player_hp=hp, player_max_hp=max_hp)
                  for i, opt in enumerate(self.options)],
                id="rest-options",
            )
            yield Static(self._footer_text(), id="rest-footer")

    def on_mount(self) -> None:
        self._is_composed = True

    def _title_text(self) -> Text:
        player = extract_player(self.state)
        title = Text(justify="center")
        title.append(f"  {L('rest_site')}  ", style="bold white on dark_green")
        hp = player.get("hp", 0)
        max_hp = player.get("max_hp", 0)
        color = hp_color(hp, max_hp)
        title.append(f"\n \u2764 {hp}/{max_hp}", style=f"bold {color}")
        return title

    def _footer_text(self) -> Text:
        max_idx = min(len(self.options), 3)
        bindings = Text()
        for i in range(max_idx):
            bindings.append(f"[{i + 1}]", style="bold yellow")
            bindings.append(f" {L('option')} {i + 1}  ", style="dim")
        bindings.append("[Enter]", style="bold yellow")
        bindings.append(f" {L('confirm')}  ", style="dim")
        bindings.append("[Esc]", style="bold yellow")
        bindings.append(f" {L('leave')}", style="dim")
        return build_status_footer(bindings, self.state)

    async def _refresh_display(self) -> None:
        if not self._is_composed or self._refreshing:
            return
        self._refreshing = True
        hp, max_hp = self._player_hp()
        try:
            for old in self.query("#rest-screen"):
                await old.remove()
            await self.mount(
                Vertical(
                    Static(self._title_text(), id="rest-title"),
                    Horizontal(
                        *[RestOptionWidget(opt, i, selected=(i == self.selected),
                                           player_hp=hp, player_max_hp=max_hp)
                          for i, opt in enumerate(self.options)],
                        id="rest-options",
                    ),
                    Static(self._footer_text(), id="rest-footer"),
                    id="rest-screen",
                )
            )
        finally:
            self._refreshing = False

    async def watch_selected(self, value: int) -> None:
        await self._refresh_display()

    def action_select_option(self, index: int) -> None:
        if 0 <= index < len(self.options):
            opt = self.options[index]
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

            self.app.post_message(RestDoneMessage(state))
            self.app.pop_screen()
        finally:
            self._busy = False

    async def action_leave(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            state = await self.controller.leave_room()
            self.app.post_message(RestDoneMessage(state))
            self.app.pop_screen()
        finally:
            self._busy = False
