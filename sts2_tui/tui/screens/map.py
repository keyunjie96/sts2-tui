"""Map screen -- full visual node-graph map for path selection.

Shows the entire multi-floor map like Slay the Spire -- a visual node graph
where you can see your path, visited nodes, and upcoming floors.

The screen fetches full map data via ``get_map`` from the engine to display
all nodes and their connections, then falls back to showing just the next
choices if the full map is unavailable.
"""

from __future__ import annotations

import logging

from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static
from rich.text import Text

from sts2_tui.tui.controller import GameController, extract_player, _name_str
from sts2_tui.tui.i18n import L
from sts2_tui.tui.shared import build_status_footer, hp_color

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Node display config
# ---------------------------------------------------------------------------

# (icon letter, base_color)
NODE_DISPLAY: dict[str, tuple[str, str]] = {
    "Monster":  ("M", "#ff5555"),
    "Elite":    ("E", "#ffaa00"),
    "RestSite": ("R", "#55ff55"),
    "Shop":     ("$", "#ffff55"),
    "Event":    ("?", "#aa88ff"),
    "Boss":     ("B", "#ff2222"),
    "Treasure": ("T", "#ffcc00"),
    "Unknown":  ("?", "#aa88ff"),
    "Ancient":  ("A", "#ff88cc"),
}

# Width of each column cell in characters for map rendering.
# Compact: 5 chars per column fits ~12 columns in 80 chars (with left margin).
COL_WIDTH = 5


# ---------------------------------------------------------------------------
# Messages
# ---------------------------------------------------------------------------


class MapNodeSelectedMessage(Message):
    """Posted when the player selects a map node to travel to."""

    def __init__(self, choice: dict, next_state: dict) -> None:
        super().__init__()
        self.choice = choice
        self.next_state = next_state


# ---------------------------------------------------------------------------
# Map rendering helpers
# ---------------------------------------------------------------------------


def _center_of(col: int) -> int:
    """Return the character position for the center of a column cell."""
    return col * COL_WIDTH + COL_WIDTH // 2


def _build_connection_line(
    lower_nodes: list[dict],
    upper_row_num: int,
    total_cols: int,
) -> str:
    r"""Build a connector line between two adjacent rows using box-drawing chars.

    Uses ``\u2502`` (``|``) for straight vertical, ``\u2571`` (``/``) for
    right-rising diagonals, and ``\u2572`` (``\``) for left-rising diagonals.
    For connections that span multiple columns, draws a horizontal segment
    with corners for clarity.
    """
    width = COL_WIDTH * total_cols
    buf = list(" " * width)
    for nd in lower_nodes:
        from_col = nd.get("col", 0)
        for ch in nd.get("children") or []:
            to_col = ch.get("col", 0)
            to_row = ch.get("row", -1)
            if to_row != upper_row_num:
                continue
            fc = _center_of(from_col)
            tc = _center_of(to_col)
            if from_col == to_col:
                # Straight vertical
                if 0 <= fc < len(buf):
                    buf[fc] = "\u2502"  # │
            elif abs(from_col - to_col) == 1:
                # Adjacent column -- single diagonal character at midpoint
                mid = (fc + tc) // 2
                if from_col < to_col:
                    ch_char = "\u2571"  # ╱
                else:
                    ch_char = "\u2572"  # ╲
                if 0 <= mid < len(buf):
                    buf[mid] = ch_char
            else:
                # Multi-column span -- draw corner + horizontal + corner
                lo = min(fc, tc)
                hi = max(fc, tc)
                if from_col < to_col:
                    # Rising right: ╰──╮  (bottom-left to top-right)
                    if 0 <= lo < len(buf):
                        buf[lo] = "\u2570"  # ╰
                    if 0 <= hi < len(buf):
                        buf[hi] = "\u256e"  # ╮
                else:
                    # Rising left: ╭──╯  (bottom-right to top-left)
                    if 0 <= lo < len(buf):
                        buf[lo] = "\u256d"  # ╭
                    if 0 <= hi < len(buf):
                        buf[hi] = "\u256f"  # ╯
                for x in range(lo + 1, hi):
                    if 0 <= x < len(buf) and buf[x] == " ":
                        buf[x] = "\u2500"  # ─
    return "".join(buf)


def _render_full_map(
    map_data: dict,
    choice_set: set[tuple[int, int]],
    choice_indices: dict[tuple[int, int], int],
    current_floor: int,
) -> Text:
    """Render the complete map as a Rich Text object.

    Returns a multi-line Text suitable for display in a Static widget.
    Uses a compact layout with Unicode box-drawing connections and
    a prominent current-position indicator.
    """
    rows_data = map_data.get("rows", [])
    boss = map_data.get("boss", {})
    cur_coord = map_data.get("current_coord")
    ctx = map_data.get("context", {})
    act_name = _name_str(ctx.get("act_name")) if ctx.get("act_name") else "?"

    if not rows_data:
        t = Text()
        t.append(f"  {L('no_map_data')}\n", style="dim")
        return t

    # Build lookup: (col, row) -> node
    node_map: dict[tuple[int, int], dict] = {}
    max_col = 0
    row_numbers: list[int] = []
    seen_rows: set[int] = set()

    for row_list in rows_data:
        for nd in row_list:
            col = nd.get("col", 0)
            rn = nd.get("row", 0)
            node_map[(col, rn)] = nd
            if col > max_col:
                max_col = col
            if rn not in seen_rows:
                seen_rows.add(rn)
                row_numbers.append(rn)

    row_numbers.sort()
    total_cols = max_col + 1
    line_width = COL_WIDTH * total_cols

    # Build row-indexed list for connection rendering
    nodes_by_row: dict[int, list[dict]] = {}
    for (c, r), nd in node_map.items():
        nodes_by_row.setdefault(r, []).append(nd)

    t = Text()

    # -- Act header --
    t.append(f"  {act_name}\n\n", style="bold white")

    # -- Boss row --
    boss_col = boss.get("col", total_cols // 2)
    boss_row = boss.get("row", -1)
    boss_name = _name_str(boss.get("name")) if boss.get("name") else "BOSS"
    boss_type = boss.get("type", "Boss")
    boss_icon, boss_color = NODE_DISPLAY.get(boss_type, ("B", "#ff2222"))

    # Boss line
    buf = [" "] * line_width
    center = _center_of(boss_col)
    label = f"[{boss_icon}]"
    start_pos = center - 1
    for i, ch in enumerate(label):
        pos = start_pos + i
        if 0 <= pos < len(buf):
            buf[pos] = ch
    t.append("  B ", style="dim white")
    # Build the boss line with color
    plain = "".join(buf)
    before = plain[:max(0, start_pos)]
    after = plain[start_pos + len(label):]
    t.append(before)
    t.append(label, style=f"bold {boss_color}")
    t.append(after)
    t.append(f"  {boss_name}", style=f"bold {boss_color}")
    t.append("\n")

    # Connection from top row to boss
    top_rn = row_numbers[-1] if row_numbers else -1
    top_nodes = nodes_by_row.get(top_rn, [])
    top_to_boss: list[dict] = []
    for nd in top_nodes:
        fake_children = []
        for ch in nd.get("children") or []:
            if ch.get("row") == boss_row:
                fake_children.append(ch)
        if fake_children:
            top_to_boss.append({**nd, "children": fake_children})
    if top_to_boss:
        conn_str = _build_connection_line(top_to_boss, boss_row, total_cols)
        t.append("    ", style="dim")
        t.append(conn_str, style="dim white")
        t.append("\n")

    # -- Map rows (top to bottom) --
    for idx in range(len(row_numbers) - 1, -1, -1):
        rn = row_numbers[idx]

        # --- Current-position banner (above the node row) ---
        is_current_row = cur_coord and cur_coord.get("row") == rn
        if is_current_row:
            cur_center = _center_of(cur_coord.get("col", 0))
            banner = f"\u25b6 {L('you_are_here')} \u25c0"
            banner_start = max(0, cur_center - len(banner) // 2)
            t.append("    ", style="dim")
            t.append(" " * banner_start)
            t.append(banner, style="bold reverse #55ff55")
            t.append("\n")
            # Down arrow pointing at the node
            t.append("    ", style="dim")
            t.append(" " * cur_center)
            t.append("\u25bc", style="bold #55ff55")  # ▼
            t.append("\n")

        # Node line
        buf = [" "] * line_width
        segments: list[tuple[int, str, str]] = []  # (start_pos, text, style)

        for col in range(total_cols):
            nd = node_map.get((col, rn))
            if not nd:
                continue
            ntype = nd.get("type", "?")
            icon, color = NODE_DISPLAY.get(ntype, ("?", "white"))
            is_cur = (cur_coord and cur_coord.get("col") == col
                      and cur_coord.get("row") == rn)
            visited = nd.get("visited", False)

            center = _center_of(col)
            choice_idx = choice_indices.get((col, rn))

            if is_cur:
                label = f"[{icon}]"
                style = "bold reverse #55ff55"
            elif choice_idx is not None:
                label = f"[{icon}]"
                style = f"bold {color}"
            elif visited:
                label = f"\u00b7{icon}\u00b7"  # ·M· for visited
                style = "dim"
            else:
                label = f" {icon} "
                style = f"{color}"

            start_pos = center - 1
            segments.append((start_pos, label, style))
            for i, ch in enumerate(label):
                pos = start_pos + i
                if 0 <= pos < len(buf):
                    buf[pos] = ch

        # Row number label (compact: 4 chars left margin)
        t.append(f" {rn:>2} ", style="dim white")

        # Build colored line from segments
        if not segments:
            t.append("".join(buf))
        else:
            segments.sort(key=lambda s: s[0])
            pos = 0
            for start_pos, label, style in segments:
                if start_pos > pos:
                    t.append("".join(buf[pos:start_pos]))
                t.append(label, style=style)
                pos = start_pos + len(label)
            if pos < len(buf):
                t.append("".join(buf[pos:]))
        t.append("\n")

        # Choice index annotation line (only when there are selectable nodes)
        row_choices = {
            col: choice_indices[(col, rn)]
            for col in range(total_cols)
            if (col, rn) in choice_indices
        }
        if row_choices:
            ann = [" "] * line_width
            ann_segments: list[tuple[int, str]] = []
            for col, ci in row_choices.items():
                label = f"^{ci + 1}"
                center = _center_of(col)
                start_pos = center - 1
                for i, ch in enumerate(label):
                    pos = start_pos + i
                    if 0 <= pos < len(ann):
                        ann[pos] = ch
                ann_segments.append((start_pos, label))
            t.append("    ", style="dim")
            ann_segments.sort(key=lambda s: s[0])
            ann_pos = 0
            ann_plain = "".join(ann)
            for start_pos, label in ann_segments:
                if start_pos > ann_pos:
                    t.append(ann_plain[ann_pos:start_pos])
                t.append(label, style="bold yellow")
                ann_pos = start_pos + len(label)
            if ann_pos < len(ann):
                t.append(ann_plain[ann_pos:])
            t.append("\n")

        # Connection line to the row below
        if idx > 0:
            below_rn = row_numbers[idx - 1]
            below_nodes = nodes_by_row.get(below_rn, [])
            filtered: list[dict] = []
            for nd in below_nodes:
                relevant_children = [
                    ch for ch in (nd.get("children") or [])
                    if ch.get("row") == rn
                ]
                if relevant_children:
                    filtered.append({**nd, "children": relevant_children})
            if filtered:
                conn_str = _build_connection_line(filtered, rn, total_cols)
                t.append("    ", style="dim")
                t.append(conn_str, style="dim white")
                t.append("\n")

    # -- Floor type summary --
    t.append("\n")
    _append_floor_summary(t, rows_data, choice_set, choice_indices, row_numbers)

    # -- Legend (compact) --
    t.append("  ")
    for ntype, (icon, color) in NODE_DISPLAY.items():
        if ntype in ("Unknown",):
            continue
        t.append(f"[{icon}]", style=f"bold {color}")
        t.append(f"={ntype} ", style="dim")
    t.append("\n")
    t.append("  ", style="dim")
    t.append("[X]", style="bold reverse #55ff55")
    t.append("=You ", style="dim")
    t.append("^N", style="bold yellow")
    t.append("=Select(press N) ", style="dim")
    t.append("\u00b7X\u00b7", style="dim")
    t.append(f"={L('visited')}", style="dim")
    t.append("\n")

    return t


def _append_floor_summary(
    t: Text,
    rows_data: list[list[dict]],
    choice_set: set[tuple[int, int]],
    choice_indices: dict[tuple[int, int], int],
    row_numbers: list[int],
) -> None:
    """Append a compact summary of remaining node types and next choices."""
    # Count remaining (unvisited) node types
    type_counts: dict[str, int] = {}
    for row_list in rows_data:
        for nd in row_list:
            if not nd.get("visited", False):
                ntype = nd.get("type", "?")
                icon, _ = NODE_DISPLAY.get(ntype, ("?", "white"))
                type_counts[icon] = type_counts.get(icon, 0) + 1

    # Next choices summary
    next_types: list[str] = []
    for (col, rn), idx in sorted(choice_indices.items(), key=lambda x: x[1]):
        # Find the node type for this choice
        for row_list in rows_data:
            for nd in row_list:
                if nd.get("col") == col and nd.get("row") == rn:
                    ntype = nd.get("type", "?")
                    next_types.append(ntype)
                    break

    if type_counts:
        t.append(f"  {L('remaining')}: ", style="dim")
        for icon, cnt in type_counts.items():
            _, color = "?", "white"
            for ntype_name, (ni, nc) in NODE_DISPLAY.items():
                if ni == icon:
                    color = nc
                    break
            t.append(f"{cnt}{icon}", style=f"bold {color}")
            t.append(" ", style="dim")

    if next_types:
        t.append(f" | {L('next')}: ", style="dim")
        for i, ntype in enumerate(next_types):
            if i > 0:
                t.append(", ", style="dim")
            icon, color = NODE_DISPLAY.get(ntype, ("?", "white"))
            t.append(ntype, style=f"bold {color}")

    if type_counts or next_types:
        t.append("\n")


def _render_fallback_choices(state: dict) -> Text:
    """Fallback: path-focused view showing path history and next choices.

    Displays a compact view of the player's path so far and upcoming
    choices as a branching tree.
    """
    choices = state.get("choices", [])
    ctx = state.get("context", {})
    raw_floor = ctx.get("floor", 0)
    floor = int(raw_floor) if isinstance(raw_floor, (int, float)) else 0
    t = Text()

    t.append(f"\n  {L('choose_path')}", style="bold white")
    t.append(f"  ({L('floor')} {floor})\n\n", style="dim white")

    if not choices:
        t.append(f"  {L('no_paths')}\n", style="dim")
        return t

    # Show choices as a branching tree
    for i, choice in enumerate(choices):
        ntype = choice.get("type", "?")
        col = choice.get("col", "?")
        icon, color = NODE_DISPLAY.get(ntype, ("?", "white"))

        is_last = i == len(choices) - 1
        prefix = "\u2514\u2500\u2500" if is_last else "\u251c\u2500\u2500"  # └── or ├──

        t.append(f"   {prefix} ", style="dim white")
        t.append(f"[{i + 1}]", style="bold yellow")
        t.append(f" [{icon}] ", style=f"bold {color}")
        t.append(f"{ntype}", style=f"bold {color}")
        t.append(f"  (col {col})", style="dim")
        t.append("\n")

    t.append("\n")
    return t


# ---------------------------------------------------------------------------
# MapScreen
# ---------------------------------------------------------------------------


class MapScreen(Screen):
    """Full map visualization. Shows the entire node graph with connections.

    Fetches full map data from the engine on mount.  If unavailable, falls
    back to showing just the next-step choices.
    """

    BINDINGS = [
        Binding("1", "select_path(0)", "Path 1", show=False),
        Binding("2", "select_path(1)", "Path 2", show=False),
        Binding("3", "select_path(2)", "Path 3", show=False),
        Binding("4", "select_path(3)", "Path 4", show=False),
        Binding("5", "select_path(4)", "Path 5", show=False),
        Binding("6", "select_path(5)", "Path 6", show=False),
        Binding("7", "select_path(6)", "Path 7", show=False),
        Binding("8", "select_path(7)", "Path 8", show=False),
        Binding("9", "select_path(8)", "Path 9", show=False),
        Binding("escape", "go_back", "Back", show=False),
    ]

    def __init__(self, state: dict, *, controller: GameController) -> None:
        super().__init__()
        self.state = state
        self.controller = controller
        self._busy = False
        self._map_data: dict | None = None
        self._esc_warned = False

    def compose(self) -> ComposeResult:
        with Vertical(id="map-screen"):
            yield Static(self._header_text(), id="map-header")
            with VerticalScroll(id="map-viewport"):
                yield Static(L("loading_map"), id="map-content")
            yield Static(self._player_status_text(), id="map-player-status")
            yield Static(self._footer_text(), id="map-footer")

    async def on_mount(self) -> None:
        """Fetch full map data from the engine and render."""
        try:
            self._map_data = await self.controller.get_map()
            if self._map_data.get("type") != "map":
                self._map_data = None
        except Exception:
            log.exception("Failed to fetch map data")
            self._map_data = None

        self._refresh_map()
        # Scroll to current position
        self.call_after_refresh(self._scroll_to_current)

    def _scroll_to_current(self) -> None:
        """Scroll the viewport so the current position is visible."""
        viewport = self.query_one("#map-viewport", VerticalScroll)
        # Scroll to about 60% from the bottom as a reasonable default
        # for showing current position with some upcoming context
        viewport.scroll_end(animate=False)
        ctx = self.state.get("context", {})
        floor = ctx.get("floor", 0)
        if isinstance(floor, int) and floor > 0:
            # Estimate: each row takes ~3 lines. Current floor is near bottom.
            # We want the current floor to be roughly centered.
            total = viewport.max_scroll_y
            if total > 0:
                # Rough ratio: floor / max_floor
                map_data = self._map_data
                if map_data:
                    rows = map_data.get("rows", [])
                    max_row = 0
                    for row_list in rows:
                        for nd in row_list:
                            rn = nd.get("row", 0)
                            if rn > max_row:
                                max_row = rn
                    if max_row > 0:
                        # Invert: row 1 is at the bottom of the display
                        ratio = 1.0 - (floor / max_row)
                        target_y = int(total * ratio)
                        viewport.scroll_to(y=target_y, animate=False)

    def _refresh_map(self) -> None:
        """Re-render the map content."""
        content = self.query_one("#map-content", Static)
        # Deduplicate choices by (col, row) -- keep the first occurrence
        raw_choices = self.state.get("choices", [])
        seen_coords: set[tuple[int, int]] = set()
        choices: list[dict] = []
        for ch in raw_choices:
            coord = (ch.get("col", 0), ch.get("row", 0))
            if coord not in seen_coords:
                seen_coords.add(coord)
                choices.append(ch)
        choice_set = {(ch.get("col", 0), ch.get("row", 0)) for ch in choices}
        choice_indices = {(ch.get("col", 0), ch.get("row", 0)): i for i, ch in enumerate(choices)}
        ctx = self.state.get("context", {})
        raw_floor = ctx.get("floor", 0)
        floor = int(raw_floor) if isinstance(raw_floor, (int, float)) else 0

        if self._map_data and self._map_data.get("type") == "map":
            text = _render_full_map(self._map_data, choice_set, choice_indices, floor)
        else:
            text = _render_fallback_choices(self.state)

        content.update(text)

    def _header_text(self) -> Text:
        ctx = self.state.get("context", {})
        act = ctx.get("act", "?")
        raw_floor = ctx.get("floor", 0)
        floor = int(raw_floor) if isinstance(raw_floor, (int, float)) else 0
        boss = ctx.get("boss", {})
        boss_name = _name_str(boss.get("name")) if boss else "?"
        # Display floor 0 (act transition) as floor 1 for player clarity
        display_floor = floor if floor > 0 else 1

        t = Text(justify="center")
        t.append(f"  {L('map')}  ", style="bold white")
        t.append(f"  {L('act')} {act}", style="dim white")
        t.append(f"  {L('floor')} {display_floor}", style="dim white")
        t.append("  |  ", style="dim")
        t.append(f"{L('boss')}: {boss_name}", style="bold red")
        return t

    def _player_status_text(self) -> Text:
        player = extract_player(self.state)
        hp = player.get("hp", 0)
        max_hp = player.get("max_hp", 0)
        gold = player.get("gold", 0)
        color = hp_color(hp, max_hp)

        t = Text(justify="center")
        t.append("\u2764 ", style=f"bold {color}")
        t.append(f"{hp}/{max_hp}", style=f"bold {color}")
        t.append("  |  ", style="dim")
        t.append("\u25c9 ", style="bold yellow")
        t.append(f"{gold}", style="bold yellow")
        t.append("  |  ", style="dim")
        t.append(f"{L('deck')} ", style="dim")
        t.append(f"{player.get('deck_size', 0)}", style="bold white")

        potions = player.get("potions", [])
        if potions:
            t.append("  |  ", style="dim")
            t.append(f"{L('potions')} ", style="dim")
            for pot in potions:
                pname = pot.get("name", "?")
                t.append(f"[{pname[:3]}]", style="bold cyan")

        relics = player.get("relics", [])
        if relics:
            t.append("  |  ", style="dim")
            t.append(f"{L('relics')}: ", style="dim")
            for i, r in enumerate(relics):
                if i > 0:
                    t.append(", ", style="dim")
                t.append(r["name"], style="bold cyan")

        return t

    def _footer_text(self) -> Text:
        choices = self.state.get("choices", [])
        bindings = Text()
        if choices:
            max_idx = min(len(choices), 9)
            if max_idx == 1:
                bindings.append("[1]", style="bold yellow")
            else:
                bindings.append(f"[1-{max_idx}]", style="bold yellow")
            bindings.append(f" {L('select_path')}  ", style="dim")
        bindings.append("[Q]", style="bold yellow")
        bindings.append(f" {L('quit')}", style="dim")
        # Pass state=None to avoid duplicating HP/gold already shown in _player_status_text
        # Note: build_status_footer already appends [?] help, so don't add it here
        return build_status_footer(bindings, state=None)

    def action_go_back(self) -> None:
        # Don't quit the whole app -- just dismiss this screen.
        # The map is typically the "idle" screen between rooms, so Esc
        # should be a no-op rather than killing the session.
        if not self._esc_warned:
            self.notify(L("press_q_quit"), severity="warning")
            self._esc_warned = True

    async def action_select_path(self, index: int) -> None:
        if self._busy:
            return
        choices = self.state.get("choices", [])
        if index < 0 or index >= len(choices):
            self.notify(L("no_path_at_index"), severity="warning")
            return

        choice = choices[index]

        self._busy = True
        try:
            state = await self.controller.select_map_node(
                col=choice.get("col", 0),
                row=choice.get("row", 0),
            )

            if state.get("type") == "error":
                self.notify(state.get("message", "Error selecting path."), severity="error")
                self._busy = False
                return

            # Tell the app about the transition
            self.app.post_message(MapNodeSelectedMessage(choice, state))
        finally:
            self._busy = False
