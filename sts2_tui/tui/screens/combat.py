"""Combat screen -- the core gameplay view (80% of playtime).

Now driven entirely by raw dict state from sts2-cli.  No Pydantic models needed.
"""

from __future__ import annotations

import logging
import re
from textual.app import ComposeResult
from textual.binding import Binding
from collections import Counter
from textual.containers import Container, Horizontal, Vertical, VerticalScroll
from textual.message import Message
from textual.screen import Screen
from textual.widgets import Static
from textual.reactive import reactive
from rich.text import Text

from sts2_tui.tui.controller import (
    GameController,
    calculate_display_block,
    calculate_display_damage,
    extract_enemies,
    extract_hand,
    extract_pile_contents,
    extract_pile_counts,
    extract_player,
    _name_str,
)
from sts2_tui.tui.i18n import L
from sts2_tui.tui.screens.potion_menu import PotionMenuOverlay, PotionUseRequest, PotionDiscardRequest
from sts2_tui.tui.shared import CARD_TYPE_COLORS, KEYWORD_ICONS, ROOM_TYPE_COLORS, GlobalHelpOverlay, hp_color

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Buff / debuff name sets (used for coloring powers on enemies and player)
# ---------------------------------------------------------------------------

DEBUFF_NAMES: frozenset[str] = frozenset({
    "Vulnerable", "Weak", "Frail", "Poison", "Constricted",
    "Hex", "Entangled", "Infested",
    "Constrict", "Shrink",
    "Doom", "Ringing",
    "Tangled", "Tender",
    # v5 Round 1 additions
    "Neurosurge",
})

BUFF_NAMES: frozenset[str] = frozenset({
    "Strength", "Dexterity", "Artifact", "Metallicize", "Plated Armor",
    "Ritual", "Thorns", "Regenerate", "Angry", "Curl Up",
    "Illusion", "Slippery", "Minion",
    "Juggernaut", "Feel No Pain", "Combust", "Dark Embrace", "Evolve",
    "Fire Breathing", "Flame Barrier", "Focus", "Heatsink",
    "Electrodynamics", "Storm", "Creative AI", "Accuracy", "Envenom",
    "Noxious Fumes", "After Image", "A Thousand Cuts", "Footwork",
    "Phantasmal Killer", "Sadistic Nature",
    "Phantom Blades", "Serpent Form", "Nightmare",
    "Imbalanced",
    "Buffer", "Feral", "Pagestorm", "Friendship", "Free Power",
    "Energy Next Turn",
    "Territorial", "Burrowed", "Flutter",
    # v3 Round 1 additions (Act 2 powers)
    "Echo Form", "Hailstorm", "Iteration", "Loop",
    "Pale Blue Dot", "Parry", "Royalties", "Seeking Edge",
    "Smokestack", "Spinner", "Subroutine", "Trash to Treasure",
    "Unmovable", "Vigor",
    # Enemy powers that benefit the player or alert about enemy capability
    "Slow", "Hard to Kill",
    # v4 Round 1 additions
    "Calcify", "Foregone Conclusion", "Lethality", "Machine Learning",
    "One-Two Punch", "Orbit", "Reaper Form", "Reflect",
    "Void Form", "Well-Laid Plans",
    # Enemy powers (v4 Round 1)
    "Grapple", "Personal Hive",
    # v5 Round 1 additions (player buffs)
    "Child of the Stars", "Colossus", "Consuming Shadow", "Fasten",
    "Nostalgia", "Plating", "Retain Hand", "The Gambit", "Thunder",
    # v5 Round 1 additions (enemy buffs)
    "Conqueror", "Debilitate", "Vital Spark",
    # v6 Round 1 additions
    "Automation", "Black Hole", "Block Next Turn", "Coolant", "Demon Form",
    "Haunt", "Rolling Boulder", "Spectrum Shift", "Sword Sage",
    # v7 additions
    "Afterimage", "Blur", "Demesne", "Double Damage", "Pillar of Creation",
    "Shadow Step", "Sleight of Flesh", "Synchronize",
})


# ---------------------------------------------------------------------------
# Small reusable widgets (dict-driven)
# ---------------------------------------------------------------------------


class TopBar(Static):
    """Act / floor, HP, gold, potions -- single-line display."""

    def __init__(self, state: dict) -> None:
        super().__init__(id="top-bar")
        self.state = state

    def render(self) -> Text:
        player = extract_player(self.state)
        ctx = self.state.get("context", {})
        act = ctx.get("act", "?")
        floor = ctx.get("floor", "?")
        turn = self.state.get("round", "?")

        hp = player["hp"]
        max_hp = player["max_hp"]
        ratio = hp / max_hp if max_hp else 0
        color = hp_color(hp, max_hp)

        # Mini HP bar (10 chars wide)
        bar_w = 10
        filled = int(ratio * bar_w)
        empty = bar_w - filled

        room_type = ctx.get("room_type", "")

        t = Text()
        t.append(f" {L('act')} {act}", style="bold white")
        t.append(f"  {L('floor')} {floor}", style="dim white")
        if room_type:
            t.append(f"  [{room_type}]", style=ROOM_TYPE_COLORS.get(room_type, "dim"))
        t.append("  ", style="dim")
        t.append(f"{L('turn')} {turn}", style="bold bright_cyan")
        t.append("  |  ", style="dim")
        t.append(f"{player['name']}", style="bold red")
        t.append("  |  ", style="dim")
        t.append("\u2764 ", style=f"bold {color}")
        t.append(f"{hp}/{max_hp}", style=f"bold {color}")
        t.append(" [", style="dim")
        t.append("\u2588" * filled, style=color)
        t.append("\u2591" * empty, style="dim")
        t.append("]", style="dim")
        t.append("  ", style="dim")
        t.append("\u25c9 ", style="bold yellow")
        t.append(f"{player['gold']}", style="bold yellow")
        # Regent stars
        stars = player.get("stars")
        if stars is not None:
            t.append("  ", style="dim")
            t.append(f"\u2605 {stars}", style="bold bright_yellow")

        # Necrobinder Osty summary
        osty = player.get("osty")
        if osty is not None:
            t.append("  ", style="dim")
            if osty.get("alive"):
                osty_hp = osty.get("hp", 0)
                osty_max = osty.get("max_hp", 0)
                t.append(f"\u2620 {osty_hp}/{osty_max}", style="bold magenta")
            else:
                t.append(f"\u2620 {L('fallen')}", style="dim red")

        t.append("  ", style="dim")
        t.append(f"{L('potions')} ", style="dim")
        potions = player["potions"]
        if potions:
            for i, pot in enumerate(potions):
                if i > 0:
                    t.append(" ", style="dim")
                t.append(f"[{pot['name']}]", style="bold cyan")
        else:
            t.append("(none)", style="dim")
        return t


class TurnIndicator(Static):
    """Prominent YOUR TURN / ENEMY TURN banner."""

    def __init__(self, state: dict) -> None:
        super().__init__(id="turn-indicator")
        self.state = state

    def render(self) -> Text:
        # In sts2, when the player has a hand and the decision is combat_play,
        # it's the player's turn. Otherwise it's the enemy turn.
        decision = self.state.get("decision", "")
        turn = self.state.get("round", "?")
        t = Text(justify="center")
        if decision == "combat_play":
            t.append(f" {L('turn')} {turn}  ", style="bold bright_cyan")
            t.append(f" {L('your_turn')} ", style="bold white on dark_green")
        else:
            t.append(f" {L('turn')} {turn}  ", style="bold bright_cyan")
            t.append(f" {L('enemy_turn')} ", style="bold white on dark_red")
        return t


class IncomingSummary(Static):
    """Summary of total incoming damage from all enemies vs player block."""

    def __init__(self, state: dict) -> None:
        super().__init__(id="incoming-summary")
        self.state = state

    def render(self) -> Text:
        enemies = extract_enemies(self.state)
        player = extract_player(self.state)
        player_block = player.get("block", 0)

        total_damage = 0
        attack_parts: list[str] = []
        for e in enemies:
            if e.get("is_dead"):
                continue
            dmg = e.get("intent_damage")
            if dmg is not None:
                hits = e.get("intent_hits")
                # Engine sends TOTAL damage — dmg is already per_hit * hits
                enemy_total = dmg
                if hits and hits > 1:
                    per_hit = dmg // hits
                    attack_parts.append(f"{e['name']} {per_hit}x{hits}")
                else:
                    attack_parts.append(f"{e['name']} {dmg}")
                total_damage += enemy_total

        t = Text(justify="center")
        if total_damage > 0:
            t.append(f"{L('incoming')}: ", style="bold red")
            t.append(f"{total_damage} {L('damage')}", style="bold bright_red")
            if attack_parts:
                t.append(f" ({' + '.join(attack_parts)})", style="red")
            t.append("  |  ", style="dim")
            t.append(f"{L('you_have')}: ", style="bold cyan")
            t.append(f"{player_block} {L('block')}", style="bold bright_cyan")
            shortfall = total_damage - player_block
            if shortfall > 0:
                t.append(f"  ({L('need_more_block').format(shortfall)})", style="bold yellow")
            else:
                t.append(f"  ({L('fully_blocked')})", style="bold green")
        else:
            t.append(L("no_incoming"), style="dim green")
            if player_block > 0:
                t.append(f"  |  {L('you_have')}: {player_block} {L('block')}", style="dim cyan")
        return t


class EnemyWidget(Static):
    """Renders a single enemy with HP, intent, block, powers."""

    def __init__(self, enemy: dict, index: int, is_targeted: bool = False) -> None:
        super().__init__(classes="enemy-panel")
        self.enemy = enemy
        self.index = index
        self.is_targeted = is_targeted

    def compose(self) -> ComposeResult:
        e = self.enemy
        if self.is_targeted:
            yield Static(Text(f">>> {L('target')} <<<", style="bold yellow"), classes="target-indicator")

        if e.get("is_dead"):
            yield Static(self._defeated_text(), classes="enemy-name")
            return

        yield Static(self._name_text(), classes="enemy-name")
        yield Static(self._hp_bar(), classes="enemy-hp")
        if e.get("block", 0) > 0:
            yield Static(self._block_text(), classes="enemy-block")
        yield Static(self._intent_text(), classes="enemy-intent")
        if e.get("powers"):
            yield Static(self._powers_text(), classes="enemy-powers")

    def _defeated_text(self) -> Text:
        t = Text(justify="center")
        t.append(f"[{self.index + 1}] ", style="dim")
        t.append(self.enemy["name"], style="dim strike")
        t.append(f"  {L('defeated')}", style="bold green")
        return t

    def _name_text(self) -> Text:
        t = Text(justify="center")
        t.append(f"[{self.index + 1}] ", style="bold yellow")
        t.append(self.enemy["name"], style="bold red")
        return t

    def _hp_bar(self) -> Text:
        e = self.enemy
        hp = e.get("hp", 0)
        max_hp = e.get("max_hp", 1)
        ratio = hp / max_hp if max_hp else 0
        bar_width = 20
        filled = int(ratio * bar_width)
        empty = bar_width - filled
        color = hp_color(hp, max_hp)

        t = Text(justify="center")
        t.append("[", style="dim")
        t.append("\u2588" * filled, style=color)
        t.append("\u2591" * empty, style="dim")
        t.append("]", style="dim")
        t.append(f" {hp}/{max_hp}", style=f"bold {color}")
        return t

    def _block_text(self) -> Text:
        t = Text(justify="center")
        t.append("\u26e8 ", style="bold cyan")
        t.append(f"{self.enemy['block']} {L('block')}", style="bold cyan")
        return t

    def _intent_text(self) -> Text:
        e = self.enemy
        t = Text(justify="center")

        dmg = e.get("intent_damage")
        hits = e.get("intent_hits")

        # Show attack damage if present
        has_attack = False
        if dmg is not None:
            if hits and hits > 1:
                # Engine sends TOTAL damage — show per-hit × hits (total)
                per_hit = dmg // hits
                t.append("\u2694 ", style="bold red")
                t.append(f"Attack {per_hit}x{hits}", style="bold red")
                t.append(f" ({dmg})", style="red")
            else:
                t.append("\u2694 ", style="bold red")
                t.append(f"Attack {dmg}", style="bold red")
            has_attack = True

        # Show additional intents (Defend, Buff, etc.) alongside attack
        # For multi-intent enemies like Attack+Defend, show both
        _SECONDARY_INTENTS: list[tuple[str, str, str, str]] = [
            # (flag_key, icon, label, style)
            ("is_defend", "\u26e8", "Defend", "bold cyan"),
            ("is_buff", "\u2b06", "Buff", "bold green"),
            ("is_debuff_strong", "\u2b07\u2b07", "Strong Debuff", "bold bright_magenta"),
            ("is_debuff", "\u2b07", "Debuff", "bold magenta"),
            ("is_status_card", "\u2753", "Status", "bold white"),
            ("is_heal", "\u2764", "Heal", "bold green"),
            ("is_stun", "\u26a1", "Stun", "bold yellow"),
            ("is_summon", "\u2728", "Summon", "bold white"),
            ("is_sleep", "\U0001f4a4", "Zzz", "dim cyan"),
            ("is_card_debuff", "\U0001f0cf", "Card Debuff", "bold magenta"),
            ("is_escape", "\U0001f3c3", "Escape", "bold yellow"),
        ]

        secondary_shown = False
        debuff_strong_shown = False
        for flag_key, icon, label, style in _SECONDARY_INTENTS:
            if e.get(flag_key):
                # Skip plain "Debuff" when "Strong Debuff" is already shown
                if flag_key == "is_debuff" and debuff_strong_shown:
                    continue
                if has_attack or secondary_shown:
                    t.append(" + ", style="dim")
                t.append(f"{icon} ", style=style)
                t.append(label, style=style)
                secondary_shown = True
                if flag_key == "is_debuff_strong":
                    debuff_strong_shown = True

        if not has_attack and not secondary_shown:
            summary = e.get("intent_summary", "")
            if summary:
                t.append(summary, style="dim white")
            else:
                t.append("???", style="dim")

        return t

    # Powers that tick for their amount value each turn -- show amount prominently
    _TICK_POWERS: frozenset[str] = frozenset({"Poison", "Constrict"})

    def _powers_text(self) -> Text:
        t = Text(justify="center")
        for i, pw in enumerate(self.enemy.get("powers", [])):
            if i > 0:
                t.append("  ", style="dim")
            name = pw.get("name", "?")
            amount = pw.get("amount", 0)
            desc = pw.get("description", "")
            # Debuffs in magenta, buffs in green, neutral in cyan
            if name in DEBUFF_NAMES:
                style = "magenta"
            elif name in BUFF_NAMES:
                style = "green"
            else:
                style = "cyan"
            # Special display for tick-based powers (Poison, Constrict)
            if name in self._TICK_POWERS and amount > 0:
                t.append(f"{name}", style=f"bold {style}")
                t.append(f" {amount}", style=f"bold {style}")
                t.append("/turn", style=f"dim {style}")
            else:
                t.append(f"{name}", style=style)
                if amount != 0:
                    sign = "+" if amount > 0 and name in BUFF_NAMES else ""
                    t.append(f" {sign}{amount}", style=f"bold {style}")
            if desc:
                t.append(f" ({desc})", style=f"dim {style}")
        return t


class PlayerStats(Static):
    """Energy, HP, block, powers -- compact single-line display."""

    def __init__(self, state: dict) -> None:
        super().__init__(id="player-stats")
        self.state = state

    def render(self) -> Text:
        player = extract_player(self.state)
        t = Text()

        energy = player.get("energy", 0)
        max_energy = player.get("max_energy", 3)
        t.append(f" [{energy}/{max_energy}]", style="bold yellow")
        t.append(f" {L('energy')}", style="dim yellow")

        block = player.get("block", 0)
        if block > 0:
            t.append("  |  ", style="dim")
            t.append(f"\u26e8 {block}", style="bold cyan")
            t.append(f" {L('block')}", style="dim cyan")

        # Powers that tick for their amount value each turn
        _tick_powers = EnemyWidget._TICK_POWERS
        for pw in player.get("powers", []):
            t.append("  |  ", style="dim")
            name = pw.get("name", "?")
            amount = pw.get("amount", 0)
            desc = pw.get("description", "")
            if name in DEBUFF_NAMES:
                style = "magenta"
            elif name in BUFF_NAMES:
                style = "green"
            else:
                style = "cyan"
            if name in _tick_powers and amount > 0:
                t.append(f"{name}", style=f"bold {style}")
                t.append(f" {amount}", style=f"bold {style}")
                t.append("/turn", style=f"dim {style}")
            else:
                t.append(f"{name}", style=style)
                if amount != 0:
                    sign = "+" if amount > 0 and name in BUFF_NAMES else ""
                    t.append(f" {sign}{amount}", style=f"bold {style}")
            if desc:
                t.append(f" ({desc})", style=f"dim {style}")

        return t


class OrbDisplay(Static):
    """Renders the Defect's orb slots with type icons and values.

    Only shown when the player has orb slots (i.e. playing as Defect).
    """

    # Orb type -> (icon, color)
    ORB_STYLES: dict[str, tuple[str, str]] = {
        "Lightning": ("\u26a1", "yellow"),
        "Frost": ("\u2744", "blue"),
        "Dark": ("\u25cf", "magenta"),
        "Plasma": ("\u2600", "white"),
        "Glass": ("\u2662", "cyan"),  # diamond suit for Glass orb (decays each turn)
    }

    def __init__(self, state: dict) -> None:
        super().__init__(id="orb-display")
        self.state = state

    def render(self) -> Text:
        player = extract_player(self.state)
        orbs = player.get("orbs", [])
        orb_slots = player.get("orb_slots", 0)
        if orb_slots <= 0 and not orbs:
            return Text("")

        t = Text()
        t.append(" Orbs ", style="dim cyan")

        # Show Focus value prominently next to orb display
        focus_val = None
        for pw in player.get("powers", []):
            if pw.get("name") == "Focus":
                focus_val = pw.get("amount", 0)
                break
        if focus_val is not None:
            focus_style = "bold green" if focus_val >= 0 else "bold red"
            sign = "+" if focus_val > 0 else ""
            t.append(f"[Focus {sign}{focus_val}]", style=focus_style)
            t.append(" ", style="dim")

        # Render each filled orb slot
        for orb in orbs:
            otype = orb.get("type", "Empty")
            passive = orb.get("passive_amount", 0)
            evoke = orb.get("evoke_amount", 0)
            icon, color = self.ORB_STYLES.get(otype, ("\u25cb", "dim"))
            t.append(f" {icon}", style=f"bold {color}")
            t.append(f" {passive}", style=f"dim {color}")
            t.append(f"/{evoke}", style=f"bold {color}")
            # Annotate Glass orbs with decay indicator
            if otype == "Glass":
                t.append("\u2193", style="dim red")  # down arrow = decaying

        # Render empty slots
        empty_count = max(0, orb_slots - len(orbs))
        for _ in range(empty_count):
            t.append(" \u25cb", style="dim")

        return t


class OstyDisplay(Static):
    """Renders the Necrobinder's companion Osty with HP bar and status.

    Only shown when the player is Necrobinder (osty data present).
    """

    def __init__(self, state: dict) -> None:
        super().__init__(id="osty-display")
        self.state = state

    def render(self) -> Text:
        player = extract_player(self.state)
        osty = player.get("osty")
        if not osty:
            return Text("")

        t = Text()
        name = osty.get("name", "Osty")
        alive = osty.get("alive", False)
        hp = osty.get("hp", 0)
        max_hp = osty.get("max_hp", 0)
        block = osty.get("block", 0)

        t.append(" \u2620 ", style="bold magenta")  # skull icon
        t.append(f"{name}", style="bold magenta")

        if not alive:
            t.append(f"  {L('fallen')}", style="dim red")
            return t

        # HP display
        ratio = hp / max_hp if max_hp else 0
        color = hp_color(hp, max_hp)
        bar_w = 8
        filled = int(ratio * bar_w)
        empty = bar_w - filled

        t.append("  \u2764 ", style=f"bold {color}")
        t.append(f"{hp}/{max_hp}", style=f"bold {color}")
        t.append(" [", style="dim")
        t.append("\u2588" * filled, style=color)
        t.append("\u2591" * empty, style="dim")
        t.append("]", style="dim")

        if block > 0:
            t.append("  \u26e8 ", style="bold cyan")
            t.append(f"{block}", style="bold cyan")

        return t


class StarsDisplay(Static):
    """Renders the Regent's star resource counter.

    Only shown when the player is Regent (stars data present).
    """

    def __init__(self, state: dict) -> None:
        super().__init__(id="stars-display")
        self.state = state

    def render(self) -> Text:
        player = extract_player(self.state)
        stars = player.get("stars")
        if stars is None:
            return Text("")

        t = Text()
        t.append(" \u2605 ", style="bold bright_yellow")  # filled star
        t.append(f"{stars}", style="bold bright_yellow")
        t.append(f" {L('stars')}", style="dim yellow")
        # Show star icons for visual clarity
        t.append("  ", style="dim")
        for _ in range(min(stars, 10)):
            t.append("\u2605", style="bright_yellow")
        return t


class PileCountWidget(Static):
    """Draw / discard / exhaust counts -- compact single-line."""

    def __init__(self, state: dict) -> None:
        super().__init__(id="pile-counts")
        self.state = state

    def render(self) -> Text:
        piles = extract_pile_counts(self.state)
        t = Text(justify="right")
        t.append(f"{L('draw')} ", style="dim")
        t.append(f"{piles['draw']}", style="bold white")
        t.append(f"  {L('discard')} ", style="dim")
        t.append(f"{piles['discard']}", style="bold white")
        t.append(f"  {L('exhaust')} ", style="dim")
        exhaust = piles["exhaust"]
        t.append(f"{exhaust} ", style="bold red" if exhaust > 0 else "dim")
        return t


class CardWidget(Static):
    """A single card in the hand."""

    def __init__(self, card: dict, index: int, selected: bool = False,
                 energy: int = 99, player: dict | None = None,
                 target: dict | None = None,
                 target_index: int = -1) -> None:
        ctype = card.get("type", "").lower()
        type_cls = f"card-type-{ctype}" if ctype else "card-type-attack"
        sel_cls = " --selected" if selected else ""
        # Dim cards the player cannot afford or that are marked unplayable
        can_play = card.get("can_play", True)
        cost = card.get("cost", 0)
        # X-cost cards (cost == -1) are playable as long as can_play is true
        too_expensive = cost > energy if cost >= 0 else False
        unplayable_cls = " --unplayable" if (not can_play or too_expensive) else ""
        super().__init__(classes=f"card-widget {type_cls}{sel_cls}{unplayable_cls}")
        self.card = card
        self.index = index
        self.player = player or {}
        self.target = target
        self.target_index = target_index

    def compose(self) -> ComposeResult:
        yield Static(self._header(), classes="card-header")
        yield Static(self._desc(), classes="card-desc")

    def _header(self) -> Text:
        c = self.card
        t = Text()
        t.append(f"[{self.index + 1}]", style="bold bright_yellow")
        t.append(" ")
        cost = c.get("cost", 0)
        star_cost = c.get("star_cost")
        cost_str = str(cost) if cost >= 0 else "X"
        if star_cost is not None:
            # Regent card: show both energy cost and star cost
            if cost > 0:
                t.append(f"({cost_str}+\u2605{star_cost}) ", style="bold bright_yellow")
            else:
                t.append(f"(\u2605{star_cost}) ", style="bold bright_yellow")
        else:
            t.append(f"({cost_str}) ", style="bold yellow")
        color = CARD_TYPE_COLORS.get(c.get("type", ""), "white")
        name = _name_str(c.get("name"))
        # Show "+" suffix for upgraded cards so players can distinguish them
        if c.get("upgraded"):
            t.append(f"{name}+", style=f"bold {color}")
        else:
            t.append(name, style=f"bold {color}")
        if not c.get("can_play", True):
            t.append(f" ({L('unplayable')})", style="dim red")
        # Show keyword tags on the header line for quick visibility
        kws = c.get("keywords") or []
        for kw in kws:
            if isinstance(kw, str):
                icon = KEYWORD_ICONS.get(kw.title(), "")
                style = "bold red" if kw.title() == "Exhaust" else "bold cyan"
                if icon:
                    t.append(f" {icon}", style=style)
                else:
                    t.append(f" [{kw}]", style=style)
        # Show enchantment badge (Regent mechanic)
        enchantment = c.get("enchantment")
        if enchantment:
            ench_name = _name_str(enchantment) if isinstance(enchantment, dict) else str(enchantment)
            ench_amount = c.get("enchantment_amount")
            if ench_amount:
                t.append(f" \u2728{ench_name} +{ench_amount}", style="bold bright_green")
            else:
                t.append(f" \u2728{ench_name}", style="bold bright_green")
        # Show affliction badge
        affliction = c.get("affliction")
        if affliction:
            aff_name = _name_str(affliction) if isinstance(affliction, dict) else str(affliction)
            aff_amount = c.get("affliction_amount")
            if aff_amount:
                t.append(f" \u2620{aff_name} {aff_amount}", style="bold bright_red")
            else:
                t.append(f" \u2620{aff_name}", style="bold bright_red")
        return t

    def _get_effective_damage(self) -> int | None:
        """Return the engine-calculated effective damage for the selected target.

        Uses the ``effective_damage`` list (one value per alive enemy) when
        available and a valid target is selected.  Returns None otherwise.
        """
        eff = self.card.get("effective_damage")
        if eff and isinstance(eff, list) and 0 <= self.target_index < len(eff):
            return eff[self.target_index]
        return None

    def _desc(self) -> Text:
        c = self.card
        t = Text()
        # Description is already resolved by extract_hand() in controller.py
        desc = c.get("description", "")
        if desc:
            # For Attack cards with base damage, show the modified damage preview
            base_damage = c.get("damage")
            base_block = c.get("block")
            card_type = c.get("type", "")

            modified_desc = desc

            # Prefer engine effective_damage when available; fall back to local calc
            display_damage: int | None = None
            if base_damage is not None and base_damage > 0 and card_type == "Attack":
                eff_dmg = self._get_effective_damage()
                if eff_dmg is not None:
                    display_damage = eff_dmg
                elif self.player:
                    display_damage = calculate_display_damage(
                        base_damage, self.player, self.target,
                    )
                if display_damage is not None and display_damage != base_damage:
                    modified_desc = re.sub(
                        rf'\b{base_damage}\b',
                        str(display_damage),
                        modified_desc,
                        count=1,
                    )

            if base_block is not None and base_block > 0 and self.player:
                display_block = calculate_display_block(
                    base_block, self.player,
                )
                if display_block != base_block:
                    modified_desc = re.sub(
                        rf'\b{base_block}\b',
                        str(display_block),
                        modified_desc,
                        count=1,
                    )

            # Determine if damage/block changed for coloring
            damage_changed = (
                display_damage is not None
                and base_damage is not None
                and display_damage != base_damage
            )
            block_changed = (
                base_block is not None
                and self.player
                and calculate_display_block(base_block, self.player) != base_block
            )

            if damage_changed or block_changed:
                # Color the whole description to hint that numbers are modified
                # We build a rich text with the modified numbers colored
                self._append_colored_desc(t, modified_desc, c, display_damage)
            else:
                t.append(modified_desc, style="dim white")
        kws = c.get("keywords") or []
        kw_labels = []
        for kw in kws:
            if isinstance(kw, str):
                kw_labels.append(kw)
        if kw_labels:
            t.append(f"\n{', '.join(kw_labels)}", style="dim magenta")
        return t

    def _append_colored_desc(self, t: Text, desc: str, card: dict,
                             precomputed_damage: int | None = None) -> None:
        """Append card description with modified numbers colored green/red."""
        base_damage = card.get("damage")
        base_block = card.get("block")
        card_type = card.get("type", "")

        # Use precomputed damage (from effective_damage or local calc) when given
        display_damage = None
        damage_higher = False
        if base_damage is not None and card_type == "Attack":
            if precomputed_damage is not None:
                display_damage = precomputed_damage
            elif self.player:
                display_damage = calculate_display_damage(
                    base_damage, self.player, self.target,
                )
            if display_damage is not None:
                damage_higher = display_damage > base_damage

        display_block = None
        block_higher = False
        if base_block is not None and self.player:
            display_block = calculate_display_block(base_block, self.player)
            block_higher = display_block > base_block

        # Find and color modified numbers in the description
        # We look for the display values and color them appropriately
        numbers_to_color: dict[str, str] = {}
        if display_damage is not None and display_damage != base_damage:
            color = "bold green" if damage_higher else "bold red"
            numbers_to_color[str(display_damage)] = color
        if display_block is not None and display_block != base_block:
            color = "bold green" if block_higher else "bold red"
            numbers_to_color[str(display_block)] = color

        if not numbers_to_color:
            t.append(desc, style="dim white")
            return

        # Split description on number boundaries and color matches
        # Build a pattern that matches any of the display values as whole words
        pattern_parts = [rf'\b{re.escape(num)}\b' for num in numbers_to_color]
        pattern = '|'.join(pattern_parts)
        parts = re.split(f'({pattern})', desc)
        colored_one = {k: False for k in numbers_to_color}
        for part in parts:
            if part in numbers_to_color and not colored_one[part]:
                t.append(part, style=numbers_to_color[part])
                colored_one[part] = True
            else:
                t.append(part, style="dim white")


class HandLabel(Static):
    """Shows hand card count: 'Hand: 5/10'."""

    def __init__(self, state: dict) -> None:
        super().__init__(id="hand-label")
        self.state = state

    def render(self) -> Text:
        hand = extract_hand(self.state)
        player = extract_player(self.state)
        energy = player.get("energy", 0)
        hand_size = len(hand)
        # Max hand size in STS2 is 10
        max_hand = 10
        t = Text(justify="center")
        t.append(f"{L('hand')}: {hand_size}/{max_hand}", style="bold white")

        # Show end-turn hint when hand is empty or all cards unplayable
        if hand_size == 0:
            t.append("  --  ", style="dim")
            t.append("[E]", style="bold yellow")
            t.append(f" {L('end_turn')}", style="dim yellow")
        else:
            all_unplayable = all(
                not c.get("can_play", True) or (c.get("cost", 0) > energy and c.get("cost", 0) >= 0)
                for c in hand
            )
            if all_unplayable:
                t.append("  --  ", style="dim")
                t.append("[E]", style="bold yellow")
                t.append(f" {L('end_turn')}", style="dim yellow")
        return t


class HandArea(Static):
    """Renders the full hand of cards."""

    def __init__(self, state: dict, selected_card: int = -1,
                 selected_target: int = 0) -> None:
        super().__init__(id="hand-area")
        self.state = state
        self.selected_card = selected_card
        self.selected_target = selected_target

    def compose(self) -> ComposeResult:
        hand = extract_hand(self.state)
        player = extract_player(self.state)
        energy = player.get("energy", 0)
        # Get the selected target enemy for damage preview
        enemies = extract_enemies(self.state)
        living = [e for e in enemies if not e.get("is_dead")]
        target = None
        target_idx = -1
        if living:
            target_idx = min(self.selected_target, len(living) - 1)
            target = living[target_idx] if target_idx >= 0 else None
        for i, card in enumerate(hand):
            yield CardWidget(card, i, selected=(i == self.selected_card),
                             energy=energy, player=player, target=target,
                             target_index=target_idx)


class RelicBar(Static):
    """Footer bar showing relics and keyboard shortcuts."""

    def __init__(self, state: dict) -> None:
        super().__init__(id="relic-bar")
        self.state = state

    def compose(self) -> ComposeResult:
        yield Static(self._relic_text(), id="relic-list")
        yield Static(self._shortcut_text(), id="shortcut-hints")

    def _relic_text(self) -> Text:
        player = extract_player(self.state)
        relics = player.get("relics", [])
        t = Text()
        t.append(f" {L('relics')}: ", style="dim")
        if not relics:
            t.append("(none)", style="dim")
            return t
        for i, r in enumerate(relics):
            if i > 0:
                t.append(" | ", style="dim")
            t.append(r["name"], style="bold cyan")
            # Show counter when present (>= 0)
            counter = r.get("counter", -1)
            if isinstance(counter, int) and counter >= 0:
                t.append(f" [{counter}]", style="bold yellow")
        return t

    def _shortcut_text(self) -> Text:
        t = Text(justify="right")
        t.append("[1-9]", style="bold yellow")
        t.append(f" {L('card')}  ", style="dim")
        t.append("[Tab]", style="bold yellow")
        t.append(f" {L('target_label')}  ", style="dim")
        t.append("[Enter]", style="bold yellow")
        t.append(f" {L('play')}  ", style="dim")
        t.append("[E]", style="bold yellow")
        t.append(f" {L('end')}  ", style="dim")
        t.append("[P]", style="bold yellow")
        t.append(f" {L('potion')}  ", style="dim")
        t.append("[D/S/X]", style="bold yellow")
        t.append(" piles  ", style="dim")
        t.append("[?]", style="bold yellow")
        t.append(f" {L('help')} ", style="dim")
        return t


# ---------------------------------------------------------------------------
# Pile viewer overlay
# ---------------------------------------------------------------------------


class PileViewerOverlay(Screen):
    """Shows the contents of draw, discard, or exhaust pile as a modal overlay."""

    BINDINGS = [
        Binding("escape", "dismiss_pile", "Close"),
        Binding("d", "dismiss_pile", "Close"),
        Binding("s", "dismiss_pile", "Close"),
        Binding("x", "dismiss_pile", "Close"),
        Binding("up,k", "scroll_up", "Up"),
        Binding("down,j", "scroll_down", "Down"),
    ]

    def __init__(self, title: str, cards: list[str]) -> None:
        super().__init__()
        self.pile_title = title
        self.cards = cards

    def compose(self) -> ComposeResult:
        with Container(id="pile-overlay"):
            with Vertical(id="pile-container"):
                yield Static(self._title_text(), id="pile-title")
                with VerticalScroll(id="pile-list"):
                    yield Static(self._body())
                yield Static(
                    Text("[Esc] Close  [Up/Down] Scroll", style="dim", justify="center"),
                )

    def _title_text(self) -> Text:
        t = Text(justify="center")
        t.append(f"  {self.pile_title} ({len(self.cards)})  ", style="bold white on dark_blue")
        return t

    def _body(self) -> Text:
        t = Text()
        if not self.cards:
            t.append("\n  (empty)\n", style="dim")
            return t

        # Group duplicate card names and show counts
        counts = Counter(self.cards)
        for i, (name, count) in enumerate(sorted(counts.items())):
            t.append(f"\n  {i + 1}. ", style="dim")
            t.append(name, style="bold white")
            if count > 1:
                t.append(f" x{count}", style="bold yellow")
        t.append("\n")
        return t

    def action_dismiss_pile(self) -> None:
        self.app.pop_screen()

    def action_scroll_up(self) -> None:
        try:
            scroll = self.query_one("#pile-list", VerticalScroll)
            scroll.scroll_up(animate=False)
        except Exception:
            pass

    def action_scroll_down(self) -> None:
        try:
            scroll = self.query_one("#pile-list", VerticalScroll)
            scroll.scroll_down(animate=False)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Combat-end overlays
# ---------------------------------------------------------------------------


class VictoryOverlay(Screen):
    """Displayed when all monsters are defeated."""

    BINDINGS = [
        Binding("enter", "continue_run", "Continue"),
        Binding("escape", "continue_run", "Continue"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="help-overlay"):
            with Vertical(id="help-container"):
                t = Text(justify="center")
                t.append(f"\n\n  {L('victory')}  \n\n", style="bold white on dark_green")
                t.append(f"\n{L('all_enemies_defeated')}\n", style="dim")
                t.append(f"\n[Enter] {L('continue')}", style="bold yellow")
                yield Static(t)

    def action_continue_run(self) -> None:
        self.dismiss(True)


class DefeatOverlay(Screen):
    """Displayed when the player dies."""

    BINDINGS = [
        Binding("enter", "game_over", "Game Over"),
        Binding("escape", "game_over", "Game Over"),
    ]

    def compose(self) -> ComposeResult:
        with Container(id="help-overlay"):
            with Vertical(id="help-container"):
                t = Text(justify="center")
                t.append(f"\n\n  {L('defeat')}  \n\n", style="bold white on dark_red")
                t.append(f"\n{L('you_have_been_slain')}\n", style="dim")
                t.append(f"\n[Enter] {L('continue')}", style="bold yellow")
                yield Static(t)

    def action_game_over(self) -> None:
        self.dismiss(False)


# ---------------------------------------------------------------------------
# Messages for app-level transitions
# ---------------------------------------------------------------------------


class CombatVictoryMessage(Message):
    """Posted to the app when combat is won and the victory overlay is dismissed."""

    def __init__(self, next_state: dict) -> None:
        super().__init__()
        self.next_state = next_state


class CombatDefeatMessage(Message):
    """Posted to the app when the player dies."""

    def __init__(self, next_state: dict) -> None:
        super().__init__()
        self.next_state = next_state


class CombatTransitionMessage(Message):
    """Posted when combat ends and a non-combat decision follows."""

    def __init__(self, next_state: dict) -> None:
        super().__init__()
        self.next_state = next_state


# ---------------------------------------------------------------------------
# Main combat screen
# ---------------------------------------------------------------------------


class CombatScreen(Screen):
    """Primary combat view -- renders the full battlefield from raw dicts."""

    BINDINGS = [
        Binding("1", "select_card(0)", "Card 1", show=False),
        Binding("2", "select_card(1)", "Card 2", show=False),
        Binding("3", "select_card(2)", "Card 3", show=False),
        Binding("4", "select_card(3)", "Card 4", show=False),
        Binding("5", "select_card(4)", "Card 5", show=False),
        Binding("6", "select_card(5)", "Card 6", show=False),
        Binding("7", "select_card(6)", "Card 7", show=False),
        Binding("8", "select_card(7)", "Card 8", show=False),
        Binding("9", "select_card(8)", "Card 9", show=False),
        Binding("0", "select_card(9)", "Card 10", show=False),
        Binding("tab", "cycle_target", "Next Target", show=False),
        Binding("left", "prev_card", "Prev Card", show=False),
        Binding("right", "next_card", "Next Card", show=False),
        Binding("up", "prev_target", "Prev Target", show=False),
        Binding("down", "next_target", "Next Target", show=False),
        Binding("enter", "play_card", "Play Card", show=False),
        Binding("e", "end_turn", "End Turn", show=False),
        Binding("p", "use_potion", "Use Potion", show=False),
        Binding("d", "view_draw_pile", "Draw Pile", show=False),
        Binding("s", "view_discard_pile", "Discard Pile", show=False),
        Binding("x", "view_exhaust_pile", "Exhaust Pile", show=False),
        Binding("question_mark", "show_help", "Help", show=False),
    ]

    selected_card: reactive[int] = reactive(-1, init=False)
    selected_target: reactive[int] = reactive(0, init=False)

    def __init__(self, state: dict, *, controller: GameController) -> None:
        super().__init__()
        self.state = state
        self.controller = controller
        self._is_composed = False
        self._busy = False
        self._stuck_count = 0
        self._last_state_key = ""
        self._refreshing = False

    def _has_orbs(self) -> bool:
        """Check if the player has orb slots (Defect character)."""
        player = extract_player(self.state)
        return bool(player.get("orbs") or player.get("orb_slots", 0) > 0)

    def _has_osty(self) -> bool:
        """Check if the player has an Osty companion (Necrobinder character)."""
        player = extract_player(self.state)
        return player.get("osty") is not None

    def _has_stars(self) -> bool:
        """Check if the player has stars resource (Regent character)."""
        player = extract_player(self.state)
        return player.get("stars") is not None

    def compose(self) -> ComposeResult:
        with Vertical(id="combat-screen"):
            yield TopBar(self.state)
            yield TurnIndicator(self.state)
            yield Horizontal(
                *self._enemy_widgets(),
                id="enemy-area",
            )
            yield IncomingSummary(self.state)
            if self._has_orbs():
                yield OrbDisplay(self.state)
            if self._has_osty():
                yield OstyDisplay(self.state)
            if self._has_stars():
                yield StarsDisplay(self.state)
            yield HandLabel(self.state)
            yield HandArea(self.state, self.selected_card, self.selected_target)
            yield Horizontal(
                PlayerStats(self.state),
                PileCountWidget(self.state),
                id="player-area",
            )
            yield RelicBar(self.state)

    def on_mount(self) -> None:
        self._is_composed = True

    def _enemy_widgets(self) -> list[EnemyWidget]:
        enemies = extract_enemies(self.state)
        living = [e for e in enemies if not e.get("is_dead")]
        widgets = []
        for i, e in enumerate(living):
            widgets.append(EnemyWidget(e, i, is_targeted=(i == self.selected_target)))
        return widgets

    async def _refresh_display(self) -> None:
        """Full re-render of the combat screen."""
        if not self._is_composed or self._refreshing:
            return
        self._refreshing = True
        try:
            results = self.query("#combat-screen")
            for old in results:
                await old.remove()

            children: list = [
                TopBar(self.state),
                TurnIndicator(self.state),
                Horizontal(
                    *self._enemy_widgets(),
                    id="enemy-area",
                ),
                IncomingSummary(self.state),
            ]
            if self._has_orbs():
                children.append(OrbDisplay(self.state))
            if self._has_osty():
                children.append(OstyDisplay(self.state))
            if self._has_stars():
                children.append(StarsDisplay(self.state))
            children.extend([
                HandLabel(self.state),
                HandArea(self.state, self.selected_card, self.selected_target),
                Horizontal(
                    PlayerStats(self.state),
                    PileCountWidget(self.state),
                    id="player-area",
                ),
                RelicBar(self.state),
            ])

            await self.mount(
                Vertical(
                    *children,
                    id="combat-screen",
                )
            )
        finally:
            self._refreshing = False

    async def watch_selected_card(self, value: int) -> None:
        await self._refresh_display()

    async def watch_selected_target(self, value: int) -> None:
        await self._refresh_display()

    # -- Route based on response decision --

    def _state_fingerprint(self, state: dict) -> str:
        """Build a fingerprint to detect engine stuck states."""
        hand_len = len(state.get("hand", []))
        enemy_hp = sum(e.get("hp", 0) for e in state.get("enemies", []))
        energy = state.get("energy", 0)
        round_ = state.get("round", 0)
        player_hp = state.get("player", {}).get("hp", 0)
        return f"{round_}:{player_hp}:{hand_len}:{enemy_hp}:{energy}"

    async def _handle_response(self, state: dict) -> None:
        """After any action, check the response decision and route accordingly."""
        self.state = state

        if state.get("type") == "error":
            self.notify(state.get("message", "Engine error"), severity="error")
            return

        decision = state.get("decision", "")

        if decision == "combat_play":
            # Check for stuck state (engine bug: end_turn doesn't advance)
            fp = self._state_fingerprint(state)
            if fp == self._last_state_key:
                self._stuck_count += 1
                if self._stuck_count > 3:
                    self.notify(
                        "Engine stuck -- combat cannot advance. Please press [Esc] to leave.",
                        severity="error",
                    )
                    return
            else:
                self._stuck_count = 0
                self._last_state_key = fp

            # Still in combat -- just update display
            enemies = extract_enemies(state)
            living = [e for e in enemies if not e.get("is_dead")]
            if living and self.selected_target >= len(living):
                self.selected_target = max(0, len(living) - 1)
            await self._refresh_display()

        elif decision == "game_over":
            await self._refresh_display()
            victory = state.get("victory", False)
            if victory:

                def on_victory_dismiss(won: bool | None) -> None:
                    self.app.post_message(CombatVictoryMessage(state))

                self.app.push_screen(VictoryOverlay(), callback=on_victory_dismiss)
            else:
                self.notify("Defeated!", severity="error")

                def on_defeat_dismiss(won: bool | None) -> None:
                    self.app.post_message(CombatDefeatMessage(state))

                self.app.push_screen(DefeatOverlay(), callback=on_defeat_dismiss)

        else:
            # Decision changed to something non-combat (card_reward, map_select, etc.)
            # Post a transition message so the app can route to the right screen
            self.app.post_message(CombatTransitionMessage(state))

    # -- Actions --

    def action_select_card(self, index: int) -> None:
        hand = extract_hand(self.state)
        if 0 <= index < len(hand):
            if self.selected_card == index:
                # Double-press same number: auto-play the card
                self.run_worker(self.action_play_card(), exclusive=True)
            else:
                self.selected_card = index

    def action_cycle_target(self) -> None:
        enemies = extract_enemies(self.state)
        living = [e for e in enemies if not e.get("is_dead")]
        if not living:
            return
        self.selected_target = (self.selected_target + 1) % len(living)

    def action_prev_card(self) -> None:
        """Arrow left: select previous card in hand."""
        hand = extract_hand(self.state)
        if not hand:
            return
        if self.selected_card <= 0:
            self.selected_card = len(hand) - 1
        else:
            self.selected_card = self.selected_card - 1

    def action_next_card(self) -> None:
        """Arrow right: select next card in hand."""
        hand = extract_hand(self.state)
        if not hand:
            return
        if self.selected_card < 0 or self.selected_card >= len(hand) - 1:
            self.selected_card = 0
        else:
            self.selected_card = self.selected_card + 1

    def action_prev_target(self) -> None:
        """Arrow up: select previous target."""
        enemies = extract_enemies(self.state)
        living = [e for e in enemies if not e.get("is_dead")]
        if not living:
            return
        if self.selected_target <= 0:
            self.selected_target = len(living) - 1
        else:
            self.selected_target = self.selected_target - 1

    def action_next_target(self) -> None:
        """Arrow down: select next target."""
        enemies = extract_enemies(self.state)
        living = [e for e in enemies if not e.get("is_dead")]
        if not living:
            return
        self.selected_target = (self.selected_target + 1) % len(living)

    async def action_play_card(self) -> None:
        if self._busy:
            return
        # Reset stuck counter on meaningful action
        self._stuck_count = 0
        if self.selected_card < 0:
            self.notify("No card selected! Press [1-9]", severity="warning")
            return
        hand = extract_hand(self.state)
        if self.selected_card >= len(hand):
            self.notify("Invalid card selection", severity="error")
            return

        card = hand[self.selected_card]
        if not card.get("can_play", True):
            self.notify("Cannot play that card!", severity="error")
            return

        self._busy = True
        try:
            # Determine target: only send target_index for AnyEnemy cards
            target_idx: int | None = None
            if card.get("target_type") == "AnyEnemy":
                enemies = extract_enemies(self.state)
                living = [e for e in enemies if not e.get("is_dead")]
                if living:
                    actual_target = min(self.selected_target, len(living) - 1)
                    target_idx = living[actual_target].get("index", 0)

            state = await self.controller.play_card(card["index"], target_idx)
            self.selected_card = -1

            if state.get("type") == "error":
                self.notify(state.get("message", "Cannot play that card."), severity="error")
                return

            await self._handle_response(state)
        finally:
            self._busy = False

    async def action_end_turn(self) -> None:
        if self._busy:
            return
        self._busy = True
        try:
            state = await self.controller.end_turn()
            self.selected_card = -1

            if state.get("type") == "error":
                self.notify(state.get("message", "Error ending turn."), severity="error")
                return

            await self._handle_response(state)
        finally:
            self._busy = False

    def action_use_potion(self) -> None:
        if self._busy:
            return
        player = extract_player(self.state)
        potions = player.get("potions", [])
        if not potions:
            self.notify(L("no_potions"), severity="warning")
            return

        # Prevent stacking overlays
        if any(isinstance(s, PotionMenuOverlay) for s in self.app.screen_stack):
            return

        enemies = extract_enemies(self.state)
        self.app.push_screen(PotionMenuOverlay(potions, enemies=enemies))

    async def _do_use_potion(self, potion_index: int, target_index: int | None) -> None:
        """Execute the potion use action and handle the response."""
        self._busy = True
        try:
            state = await self.controller.use_potion(potion_index, target_index)
            if state.get("type") == "error":
                self.notify(state.get("message", "Cannot use potion."), severity="error")
            else:
                await self._handle_response(state)
        finally:
            self._busy = False

    async def _do_discard_potion(self, potion_index: int) -> None:
        """Execute the potion discard action and handle the response."""
        self._busy = True
        try:
            state = await self.controller.discard_potion(potion_index)
            if state.get("type") == "error":
                self.notify(state.get("message", "Cannot discard potion."), severity="error")
            else:
                await self._handle_response(state)
        finally:
            self._busy = False

    def on_potion_use_request(self, message: PotionUseRequest) -> None:
        """Handle a use-potion request from the PotionMenuOverlay."""
        self.run_worker(
            self._do_use_potion(message.potion_index, message.target_index),
            exclusive=True,
        )

    def on_potion_discard_request(self, message: PotionDiscardRequest) -> None:
        """Handle a discard-potion request from the PotionMenuOverlay."""
        self.run_worker(
            self._do_discard_potion(message.potion_index),
            exclusive=True,
        )

    def action_show_help(self) -> None:
        if any(isinstance(s, GlobalHelpOverlay) for s in self.app.screen_stack):
            return
        self.app.push_screen(GlobalHelpOverlay("CombatScreen"))

    def _show_pile_overlay(self, pile_key: str, title: str) -> None:
        """Open a PileViewerOverlay for the given pile."""
        if any(isinstance(s, PileViewerOverlay) for s in self.app.screen_stack):
            return
        piles = extract_pile_contents(self.state)
        cards = piles.get(pile_key, [])
        self.app.push_screen(PileViewerOverlay(title, cards))

    def action_view_draw_pile(self) -> None:
        self._show_pile_overlay("draw", L("draw_pile"))

    def action_view_discard_pile(self) -> None:
        self._show_pile_overlay("discard", L("discard_pile"))

    def action_view_exhaust_pile(self) -> None:
        self._show_pile_overlay("exhaust", L("exhaust_pile"))
