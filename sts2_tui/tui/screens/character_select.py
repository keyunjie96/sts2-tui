"""Character select screen -- pick a character before starting a run."""

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

from sts2_tui.tui.i18n import L
from sts2_tui.tui.shared import build_status_footer

log = logging.getLogger(__name__)


# Available characters
CHARACTERS = [
    {
        "id": "Ironclad",
        "name": "The Ironclad",
        "description": "A hardened warrior. Starts with Burning Blood.",
        "color": "red",
        "icon": "\u2694",   # ⚔ crossed swords
    },
    {
        "id": "Silent",
        "name": "The Silent",
        "description": "A deadly huntress. Starts with Ring of the Snake.",
        "color": "green",
        "icon": "\u2660",   # ♠ spade (shivs & poison)
    },
    {
        "id": "Defect",
        "name": "The Defect",
        "description": "A sentient construct. Starts with Cracked Core.",
        "color": "blue",
        "icon": "\u26a1",
    },
    {
        "id": "Necrobinder",
        "name": "The Necrobinder",
        "description": "A dark summoner.",
        "color": "magenta",
        "icon": "\u2620",
    },
    {
        "id": "Regent",
        "name": "The Regent",
        "description": "A royal commander.",
        "color": "yellow",
        "icon": "\u265a",
    },
]


class CharacterSelectedMessage(Message):
    """Posted when the user picks a character."""

    def __init__(self, character_id: str) -> None:
        super().__init__()
        self.character_id = character_id


class CharacterWidget(Static):
    """A single character option."""

    def __init__(self, char: dict, index: int, selected: bool = False) -> None:
        classes = "rest-option"  # Reuse rest-option styling for visual consistency
        if selected:
            classes += " --selected"
        super().__init__(classes=classes)
        self.char = char
        self.index = index

    def compose(self) -> ComposeResult:
        c = self.char
        color = c.get("color", "white")

        title_text = Text(justify="center")
        title_text.append(f"[{self.index + 1}] ", style="bold yellow")
        title_text.append(f"{c['icon']} {c['name']}", style=f"bold {color}")
        yield Static(title_text, classes="rest-option-title")

        desc_text = Text(justify="center")
        desc_text.append(c.get("description", ""), style="dim white")
        yield Static(desc_text, classes="rest-option-desc")


class CharacterSelectScreen(Screen):
    """Pick a character to start a run."""

    BINDINGS = [
        Binding("1", "select_char(0)", "Char 1", show=False),
        Binding("2", "select_char(1)", "Char 2", show=False),
        Binding("3", "select_char(2)", "Char 3", show=False),
        Binding("4", "select_char(3)", "Char 4", show=False),
        Binding("5", "select_char(4)", "Char 5", show=False),
        Binding("enter", "confirm", "Confirm"),
        Binding("escape", "quit_app", "Quit"),
    ]

    selected: reactive[int] = reactive(0, init=False)

    def __init__(self) -> None:
        super().__init__()
        self.characters = CHARACTERS
        self._is_composed = False
        self._refreshing = False

    def _build_footer(self) -> Text:
        bindings = Text()
        bindings.append("[1-5]", style="bold yellow")
        bindings.append(f" {L('select')}  ", style="dim")
        bindings.append("[Enter]", style="bold yellow")
        bindings.append(f" {L('start')}  ", style="dim")
        bindings.append("[Esc]", style="bold yellow")
        bindings.append(f" {L('quit')}", style="dim")
        return build_status_footer(bindings)

    def compose(self) -> ComposeResult:
        with Vertical(id="char-select-screen"):
            title = Text(justify="center")
            title.append(f"  {L('sls_cli')}  ", style="bold white on dark_blue")
            title.append(f"\n  {L('terminal_client')}  \n", style="dim")
            title.append(f"\n {L('choose_character')}", style="white")
            yield Static(title, id="rest-title")

            yield Horizontal(
                *[CharacterWidget(c, i, selected=(i == self.selected))
                  for i, c in enumerate(self.characters)],
                id="rest-options",
            )

            yield Static(self._build_footer(), id="rest-footer")

    def on_mount(self) -> None:
        self._is_composed = True

    async def _refresh_display(self) -> None:
        if not self._is_composed or self._refreshing:
            return
        self._refreshing = True
        try:
            for old in self.query("#char-select-screen"):
                await old.remove()

            title = Text(justify="center")
            title.append(f"  {L('sls_cli')}  ", style="bold white on dark_blue")
            title.append(f"\n  {L('terminal_client')}  \n", style="dim")
            title.append(f"\n {L('choose_character')}", style="white")

            await self.mount(
                Vertical(
                    Static(title, id="rest-title"),
                    Horizontal(
                        *[CharacterWidget(c, i, selected=(i == self.selected))
                          for i, c in enumerate(self.characters)],
                        id="rest-options",
                    ),
                    Static(self._build_footer(), id="rest-footer"),
                    id="char-select-screen",
                )
            )
        finally:
            self._refreshing = False

    async def watch_selected(self, value: int) -> None:
        await self._refresh_display()

    def action_select_char(self, index: int) -> None:
        if 0 <= index < len(self.characters):
            self.selected = index

    def action_confirm(self) -> None:
        char = self.characters[self.selected]
        self.app.post_message(CharacterSelectedMessage(char["id"]))
        self.app.pop_screen()

    def action_quit_app(self) -> None:
        self.app.exit()
