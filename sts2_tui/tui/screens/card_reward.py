"""Card reward screen -- pick 1 of N cards after combat.

Now driven by raw dict state from sts2-cli (decision == "card_reward").
Supports potion rewards that the player can collect, skip, or swap.
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

from sts2_tui.bridge import BridgeError
from sts2_tui.tui.controller import GameController, _name_str, resolve_card_description, extract_reward_cards
from sts2_tui.tui.i18n import L
from sts2_tui.tui.shared import CARD_TYPE_COLORS, KEYWORD_ICONS, RARITY_COLORS, build_status_footer, build_upgrade_preview

log = logging.getLogger(__name__)


class RewardCardWidget(Static):
    """A single reward card option."""

    def __init__(self, card: dict, index: int, selected: bool = False) -> None:
        classes = "reward-card"
        if selected:
            classes += " --selected"
        super().__init__(classes=classes)
        self.card = card
        self.index = index

    def compose(self) -> ComposeResult:
        c = self.card
        ctype = c.get("type", "")
        color = CARD_TYPE_COLORS.get(ctype, "white")

        name = _name_str(c.get("name"))
        rarity = c.get("rarity", "")

        name_text = Text(justify="center")
        name_text.append(f"[{self.index + 1}] ", style="bold yellow")
        # Show "+" suffix for upgraded cards
        if c.get("upgraded"):
            name_text.append(f"{name}+", style=f"bold {color}")
        else:
            name_text.append(name, style=f"bold {color}")
        # Show keyword icons
        for kw in c.get("keywords") or []:
            if isinstance(kw, str):
                icon = KEYWORD_ICONS.get(kw.title(), "")
                if icon:
                    name_text.append(f" {icon}", style="bold red" if kw.title() == "Exhaust" else "bold cyan")
        yield Static(name_text, classes="reward-card-name")

        type_text = Text(justify="center")
        type_text.append(f"{ctype}", style=color)
        if rarity:
            rarity_label, rarity_color = RARITY_COLORS.get(
                rarity, (rarity, "dim")
            )
            type_text.append(" | ", style="dim")
            type_text.append(rarity_label, style=f"bold {rarity_color}")
        # Show card ID suffix to disambiguate duplicates with the same name
        card_id = c.get("id", "")
        if card_id:
            type_text.append(f" ({card_id})", style="dim")
        yield Static(type_text, classes="reward-card-type")

        cost = c.get("cost", 0)
        star_cost = c.get("star_cost")
        cost_str = str(cost) if cost >= 0 else "X"
        cost_text = Text(justify="center")
        if star_cost is not None:
            # Regent card: show both energy cost and star cost
            if cost > 0:
                cost_text.append(f"{L('cost')}: {cost_str}+\u2605{star_cost}", style="bold yellow")
            else:
                cost_text.append(f"{L('cost')}: \u2605{star_cost}", style="bold yellow")
        else:
            cost_text.append(f"{L('cost')}: {cost_str}", style="bold yellow")
        yield Static(cost_text, classes="reward-card-cost")

        # Description is already resolved by extract_reward_cards()
        desc_display = c.get("description", "")

        if desc_display:
            desc_text = Text(justify="center")
            desc_text.append(desc_display, style="white")
            yield Static(desc_text, classes="reward-card-desc")

        # Upgrade preview (skip if card is already upgraded -- it's at max level)
        if not c.get("upgraded"):
            after_upgrade = c.get("after_upgrade")
            if after_upgrade:
                upgrade_text = self._build_upgrade_text(c, after_upgrade)
                if upgrade_text:
                    yield Static(upgrade_text, classes="reward-card-upgrade")


    def _build_upgrade_text(self, card: dict, after_upgrade: dict) -> Text | None:
        """Build upgrade preview text showing stat changes."""
        preview = build_upgrade_preview(card, after_upgrade)
        if not preview:
            return None

        t = Text(justify="center")
        t.append(f"{L('upgrade')}: ", style="dim cyan")
        t.append(preview, style="dim cyan")
        return t


def _resolve_potion_reward_description(potion: dict) -> str:
    """Resolve template variables in a potion reward description.

    Potion rewards from the engine often have unresolved template vars
    like {Block}, {Damage}, {Cards} etc. because the engine does not send
    ``vars`` for potion rewards.  We reuse the shop screen's
    ``_enrich_potion_description`` which resolves templates using
    game_data and well-known fallback values.
    """
    try:
        from sts2_tui.tui.screens.shop import _enrich_potion_description
        resolved = _enrich_potion_description(potion)
        if resolved:
            return resolved
    except Exception:
        log.debug("Failed to enrich potion description via shop resolver", exc_info=True)
    # Fallback: try resolve_card_description with engine-sent vars
    raw_desc = potion.get("description", "")
    if not raw_desc:
        return ""
    pot_vars = potion.get("vars") or {}
    return resolve_card_description(raw_desc, pot_vars)


class PotionRewardWidget(Static):
    """A single potion reward option."""

    def __init__(self, potion: dict, index: int) -> None:
        super().__init__(classes="potion-reward")
        self.potion = potion
        self.index = index

    def compose(self) -> ComposeResult:
        p = self.potion
        name = _name_str(p.get("name", "?"))
        desc = _resolve_potion_reward_description(p)

        line = Text()
        line.append(f"  [P{self.index + 1}] ", style="bold cyan")
        line.append(name, style="bold cyan")
        if desc:
            line.append(f"  {desc}", style="dim")
        yield Static(line)


class CardRewardDoneMessage(Message):
    """Posted when the card reward screen is dismissed."""

    def __init__(self, next_state: dict) -> None:
        super().__init__()
        self.next_state = next_state


class CardRewardScreen(Screen):
    """Pick 1 of N cards after combat victory, and optionally collect potions."""

    BINDINGS = [
        Binding("1", "select_card(0)", "Card 1", show=False),
        Binding("2", "select_card(1)", "Card 2", show=False),
        Binding("3", "select_card(2)", "Card 3", show=False),
        Binding("4", "select_card(3)", "Card 4", show=False),
        Binding("5", "select_card(4)", "Card 5", show=False),
        Binding("enter", "confirm", "Confirm"),
        Binding("escape", "skip", "Skip"),
        Binding("p", "collect_first_potion", "Collect Potion", show=False),
        Binding("x", "skip_all_potions", "Skip Potions", show=False),
    ]

    selected: reactive[int] = reactive(-1, init=False)

    def __init__(self, state: dict, *, controller: GameController) -> None:
        super().__init__()
        self.state = state
        self.controller = controller
        self.cards: list[dict] = extract_reward_cards(state)
        self.potion_rewards: list[dict] = state.get("potion_rewards") or []
        self.potion_slots_full: bool = state.get("potion_slots_full", False)
        self.can_skip: bool = state.get("can_skip", True)
        self._is_composed = False
        self._busy = False
        self._refreshing = False
        self._needs_refresh = False

    def compose(self) -> ComposeResult:
        with Vertical(id="card-reward-screen"):
            yield Static(self._title_text(), id="reward-title")
            yield Horizontal(
                *[RewardCardWidget(c, i, selected=(i == self.selected)) for i, c in enumerate(self.cards)],
                id="reward-cards",
            )
            if self.potion_rewards:
                yield Static(self._potion_title_text(), id="potion-reward-title")
                yield Vertical(
                    *[PotionRewardWidget(p, i) for i, p in enumerate(self.potion_rewards)],
                    id="potion-rewards",
                )
            yield Static(self._footer_text(), id="reward-footer")

    def on_mount(self) -> None:
        self._is_composed = True

    async def _refresh_display(self) -> None:
        if not self._is_composed:
            return
        if self._refreshing:
            # Another refresh is in progress -- flag that we need a re-render
            # after it finishes so the update is not silently dropped.
            self._needs_refresh = True
            return
        self._refreshing = True
        self._needs_refresh = False
        try:
            for old in self.query("#card-reward-screen"):
                await old.remove()

            children = [
                Static(self._title_text(), id="reward-title"),
                Horizontal(
                    *[RewardCardWidget(c, i, selected=(i == self.selected)) for i, c in enumerate(self.cards)],
                    id="reward-cards",
                ),
            ]
            if self.potion_rewards:
                children.append(Static(self._potion_title_text(), id="potion-reward-title"))
                children.append(Vertical(
                    *[PotionRewardWidget(p, i) for i, p in enumerate(self.potion_rewards)],
                    id="potion-rewards",
                ))
            children.append(Static(self._footer_text(), id="reward-footer"))

            await self.mount(
                Vertical(*children, id="card-reward-screen")
            )
        finally:
            self._refreshing = False
            # If a refresh was requested while we were busy, re-trigger now.
            if self._needs_refresh:
                self._needs_refresh = False
                self.call_later(self._refresh_display)

    def _title_text(self) -> Text:
        title = Text(justify="center")
        title.append(f"  {L('card_reward')}  ", style="bold white on dark_green")
        # Show gold earned from combat if present
        gold_earned = self.state.get("gold_earned")
        if gold_earned is not None and gold_earned > 0:
            title.append(f"\n \u25c9 +{gold_earned} gold", style="bold yellow")
        title.append(f"\n {L('choose_card_add')}", style="dim")
        return title

    def _potion_title_text(self) -> Text:
        t = Text(justify="center")
        t.append(f"\n  {L('potion_rewards')}  ", style="bold white on dark_blue")
        if self.potion_slots_full:
            t.append(f"  {L('potion_slots_full')}", style="bold red")
        if self.potion_slots_full:
            t.append(f"\n  [P] {L('discard_for_potion')}  [X] {L('skip_potions')}", style="dim")
        else:
            t.append(f"\n  [P] {L('collect_potion')}  [X] {L('skip_potions')}", style="dim")
        return t

    def _footer_text(self) -> Text:
        max_idx = min(len(self.cards), 5)
        bindings = Text()
        if self.cards:
            bindings.append(f"[1-{max_idx}]", style="bold yellow")
            bindings.append(f" {L('select')}  ", style="dim")
            bindings.append("[Enter]", style="bold yellow")
            bindings.append(f" {L('confirm')}  ", style="dim")
        if self.can_skip:
            bindings.append("[Esc]", style="bold yellow")
            bindings.append(f" {L('skip')}", style="dim")
        if self.potion_rewards:
            bindings.append("  [P]", style="bold cyan")
            if self.potion_slots_full:
                bindings.append(f" {L('discard_for_potion')}  ", style="dim")
            else:
                bindings.append(f" {L('collect_potion')}  ", style="dim")
            bindings.append("[X]", style="bold cyan")
            bindings.append(f" {L('skip_potions')}", style="dim")
        return build_status_footer(bindings, self.state)

    async def watch_selected(self, value: int) -> None:
        await self._refresh_display()

    def action_select_card(self, index: int) -> None:
        if 0 <= index < len(self.cards):
            self.selected = index

    async def action_confirm(self) -> None:
        if self._busy:
            return
        if not self.cards:
            # No cards to select -- just skip
            await self.action_skip()
            return
        if self.selected < 0:
            self.notify(L("select_first"), severity="warning")
            return

        card = self.cards[self.selected]
        card_index = card.get("index", self.selected)

        self._busy = True
        try:
            state = await self.controller.select_card_reward(card_index)

            if state.get("type") == "error":
                self.notify(state.get("message", "Error selecting card."), severity="error")
                return

            self.app.post_message(CardRewardDoneMessage(state))
            self.app.pop_screen()
        finally:
            self._busy = False

    async def action_skip(self) -> None:
        if self._busy:
            return
        if not self.can_skip:
            self.notify(L("must_select_card"), severity="warning")
            return
        self._busy = True
        try:
            state = await self.controller.skip_card_reward()

            if state.get("type") == "error":
                self.notify(state.get("message", "Error skipping."), severity="error")
                return

            self.app.post_message(CardRewardDoneMessage(state))
            self.app.pop_screen()
        finally:
            self._busy = False

    async def action_collect_first_potion(self) -> None:
        """Collect the first available potion reward."""
        if self._busy or not self.potion_rewards:
            return
        self._busy = True
        try:
            pr = self.potion_rewards[0]
            state = await self.controller.bridge.collect_potion_reward(pr["index"])

            if state.get("type") == "error":
                self.notify(state.get("message", "Cannot collect potion."), severity="error")
                return

            # Update local state from the response
            self._update_from_state(state)
        except BridgeError as exc:
            self.notify(f"Bridge error: {exc}", severity="error")
        finally:
            self._busy = False

    async def action_skip_all_potions(self) -> None:
        """Skip all remaining potion rewards."""
        if self._busy or not self.potion_rewards:
            return
        self._busy = True
        try:
            state = await self.controller.bridge.skip_potion_reward()

            if state.get("type") == "error":
                self.notify(state.get("message", "Error skipping potions."), severity="error")
                return

            self._update_from_state(state)
        except BridgeError as exc:
            self.notify(f"Bridge error: {exc}", severity="error")
        finally:
            self._busy = False

    def _update_from_state(self, state: dict) -> None:
        """Update screen from a new state response (after potion action)."""
        self.state = state

        # If decision is still card_reward, update the display
        if state.get("decision") == "card_reward":
            self.cards = extract_reward_cards(state)
            self.potion_rewards = state.get("potion_rewards") or []
            self.potion_slots_full = state.get("potion_slots_full", False)
            # Reset selection if cards changed
            self.selected = -1
            self.call_later(self._refresh_display)
        else:
            # Decision changed (e.g., moved to map), dismiss this screen
            self.app.post_message(CardRewardDoneMessage(state))
            self.app.pop_screen()
