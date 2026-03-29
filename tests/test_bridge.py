"""Tests for the sts2-cli engine bridge and state adapter.

Tests are split into:
1. Unit tests for the state adapter (no subprocess needed, uses fixture data)
2. Integration tests for EngineBridge (require sts2-cli to be built and available)
"""

from __future__ import annotations

import pytest
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# State adapter unit tests — use fixture JSON, no subprocess needed
# ---------------------------------------------------------------------------

from sts2_tui.bridge_state import (
    parse_card,
    parse_combat_state,
    parse_hand,
    parse_map_choices,
    parse_monster,
    parse_player,
    parse_potion,
    parse_power,
    parse_powers,
    parse_relic,
    parse_response,
    parse_run_state,
)
from sts2_tui.engine.models.cards import CardKeyword, CardType, TargetType
from sts2_tui.engine.models.combat import TurnPhase
from sts2_tui.engine.models.map import MapNodeType
from sts2_tui.engine.models.powers import PowerType


# ---- Fixture data (extracted from actual sts2-cli responses) ----

COMBAT_STATE: dict[str, Any] = {
    "type": "decision",
    "decision": "combat_play",
    "context": {
        "act": 1,
        "act_name": "Overgrowth",
        "floor": 2,
        "room_type": "Monster",
    },
    "round": 1,
    "energy": 3,
    "max_energy": 3,
    "hand": [
        {
            "index": 0,
            "id": "CARD.DEFEND_IRONCLAD",
            "name": "Defend",
            "cost": 1,
            "type": "Skill",
            "can_play": True,
            "target_type": "Self",
            "stats": {"block": 5},
            "description": "Gain {Block:diff()} Block.",
        },
        {
            "index": 1,
            "id": "CARD.STRIKE_IRONCLAD",
            "name": "Strike",
            "cost": 1,
            "type": "Attack",
            "can_play": True,
            "target_type": "AnyEnemy",
            "stats": {"damage": 6},
            "description": "Deal {Damage:diff()} damage.",
        },
        {
            "index": 2,
            "id": "CARD.BASH",
            "name": "Bash",
            "cost": 2,
            "type": "Attack",
            "can_play": True,
            "target_type": "AnyEnemy",
            "stats": {"damage": 8, "vulnerablepower": 2},
            "description": "Deal {Damage:diff()} damage.\nApply {VulnerablePower:diff()} Vulnerable.",
        },
    ],
    "enemies": [
        {
            "index": 0,
            "name": "Nibbit",
            "hp": 43,
            "max_hp": 43,
            "block": 0,
            "intents": [{"type": "Attack", "damage": 12}],
            "intends_attack": True,
            "powers": None,
        }
    ],
    "player": {
        "name": "The Ironclad",
        "hp": 80,
        "max_hp": 80,
        "block": 0,
        "gold": 99,
        "relics": [
            {
                "name": "Burning Blood",
                "description": "At the end of combat, heal {Heal} HP.",
                "vars": {"Heal": 6},
            }
        ],
        "potions": [
            {
                "index": 0,
                "name": "Swift Potion",
                "description": "Draw {Cards} cards.",
                "vars": {"Cards": 3},
            }
        ],
        "deck_size": 11,
        "deck": [],
    },
    "player_powers": None,
    "draw_pile_count": 6,
    "discard_pile_count": 0,
    "exhaust_pile_count": 0,
}

MAP_SELECT_STATE: dict[str, Any] = {
    "type": "decision",
    "decision": "map_select",
    "context": {"act": 1, "floor": 1},
    "choices": [
        {"col": 0, "row": 1, "type": "Monster"},
        {"col": 3, "row": 1, "type": "Monster"},
        {"col": 5, "row": 1, "type": "Event"},
        {"col": 6, "row": 1, "type": "Elite"},
    ],
    "player": {
        "name": "The Ironclad",
        "hp": 80,
        "max_hp": 80,
        "block": 0,
        "gold": 99,
        "relics": [],
        "potions": [],
        "deck_size": 10,
        "deck": [],
    },
    "act": 1,
    "floor": 1,
}

EVENT_CHOICE_STATE: dict[str, Any] = {
    "type": "decision",
    "decision": "event_choice",
    "context": {"act": 1, "floor": 1},
    "event_name": "Neow",
    "options": [
        {"index": 0, "title": "Lost Coffer", "description": "Gain stuff.", "is_locked": False},
        {"index": 1, "title": "Booming Conch", "description": "Draw more.", "is_locked": False},
    ],
    "player": {
        "name": "The Ironclad",
        "hp": 80,
        "max_hp": 80,
        "block": 0,
        "gold": 99,
        "relics": [],
        "potions": [],
        "deck_size": 10,
        "deck": [],
    },
}

REST_SITE_STATE: dict[str, Any] = {
    "type": "decision",
    "decision": "rest_site",
    "context": {"act": 1, "floor": 6},
    "options": [
        {"index": 0, "option_id": "HEAL", "name": "HealRestSiteOption", "is_enabled": True},
        {"index": 1, "option_id": "SMITH", "name": "SmithRestSiteOption", "is_enabled": True},
    ],
    "player": {
        "name": "The Ironclad",
        "hp": 50,
        "max_hp": 80,
        "block": 0,
        "gold": 120,
        "relics": [],
        "potions": [],
        "deck_size": 12,
        "deck": [],
    },
}

CARD_REWARD_STATE: dict[str, Any] = {
    "type": "decision",
    "decision": "card_reward",
    "context": {"act": 1, "floor": 2},
    "cards": [
        {
            "index": 0,
            "id": "CARD.BLOOD_WALL",
            "name": "Blood Wall",
            "cost": 2,
            "type": "Skill",
            "rarity": "Common",
            "description": "Lose {HpLoss:diff()} HP.\nGain {Block:diff()} Block.",
            "stats": {"hploss": 2, "block": 16},
        },
        {
            "index": 1,
            "id": "CARD.MOLTEN_FIST",
            "name": "Molten Fist",
            "cost": 1,
            "type": "Attack",
            "rarity": "Common",
            "stats": {"damage": 10},
        },
    ],
    "can_skip": True,
    "player": {
        "name": "The Ironclad",
        "hp": 80,
        "max_hp": 80,
        "block": 0,
        "gold": 99,
        "relics": [],
        "potions": [],
        "deck_size": 10,
        "deck": [],
    },
}

GAME_OVER_STATE: dict[str, Any] = {
    "type": "decision",
    "decision": "game_over",
    "victory": False,
    "context": {"act": 1, "floor": 8},
    "player": {
        "name": "The Ironclad",
        "hp": 0,
        "max_hp": 80,
        "block": 0,
        "gold": 55,
        "relics": [],
        "potions": [],
        "deck_size": 14,
        "deck": [],
    },
}


# ---------------------------------------------------------------------------
# Card parsing
# ---------------------------------------------------------------------------

class TestParseCard:
    def test_basic_attack(self):
        card = parse_card(COMBAT_STATE["hand"][1])
        assert card.id == "CARD.STRIKE_IRONCLAD"
        assert card.name == "Strike"
        assert card.type == CardType.ATTACK
        assert card.energy_cost == 1
        assert card.target_type == TargetType.SINGLE_ENEMY
        assert card.base_damage == 6
        assert card.character == "ironclad"

    def test_basic_skill(self):
        card = parse_card(COMBAT_STATE["hand"][0])
        assert card.id == "CARD.DEFEND_IRONCLAD"
        assert card.name == "Defend"
        assert card.type == CardType.SKILL
        assert card.target_type == TargetType.SELF
        assert card.base_block == 5

    def test_card_with_multiple_stats(self):
        card = parse_card(COMBAT_STATE["hand"][2])
        assert card.name == "Bash"
        assert card.base_damage == 8
        assert "vulnerablepower" in card.vars
        assert card.vars["vulnerablepower"] == 2

    def test_card_description_resolved(self):
        card = parse_card(COMBAT_STATE["hand"][1])
        assert "6" in card.description  # damage value resolved

    def test_card_with_keywords(self):
        card = parse_card({
            "id": "CARD.TEST",
            "name": "Test",
            "cost": 0,
            "type": "Skill",
            "keywords": ["Exhaust", "Innate"],
            "stats": {},
        })
        assert CardKeyword.EXHAUST in card.keywords
        assert CardKeyword.INNATE in card.keywords

    def test_upgraded_card(self):
        card = parse_card({
            "id": "CARD.STRIKE_IRONCLAD",
            "name": "Strike+",
            "cost": 1,
            "type": "Attack",
            "upgraded": True,
            "stats": {"damage": 9},
        })
        assert card.upgrade_level == 1
        assert card.is_upgraded


class TestParseHand:
    def test_parses_all_cards(self):
        hand = parse_hand(COMBAT_STATE["hand"])
        assert len(hand) == 3
        assert hand[0].name == "Defend"
        assert hand[1].name == "Strike"
        assert hand[2].name == "Bash"


# ---------------------------------------------------------------------------
# Power parsing
# ---------------------------------------------------------------------------

class TestParsePower:
    def test_buff(self):
        power = parse_power({"name": "Strength", "amount": 3})
        assert power.name == "Strength"
        assert power.amount == 3
        assert power.type == PowerType.BUFF

    def test_debuff(self):
        power = parse_power({"name": "Vulnerable", "amount": -2})
        assert power.type == PowerType.DEBUFF
        assert power.amount == -2

    def test_none_amount(self):
        power = parse_power({"name": "No Damage", "amount": None})
        assert power.amount == 0

    def test_empty_list(self):
        assert parse_powers(None) == []
        assert parse_powers([]) == []


# ---------------------------------------------------------------------------
# Monster parsing
# ---------------------------------------------------------------------------

class TestParseMonster:
    def test_basic_monster(self):
        m = parse_monster(COMBAT_STATE["enemies"][0])
        assert m.name == "Nibbit"
        assert m.current_hp == 43
        assert m.max_hp == 43
        assert m.block == 0
        assert not m.is_dead

    def test_intent_attack(self):
        m = parse_monster(COMBAT_STATE["enemies"][0])
        assert m.intent is not None
        assert m.intent.damage == 12
        assert "Attack" in m.intent.name

    def test_dead_monster(self):
        m = parse_monster({"index": 0, "name": "Dead", "hp": 0, "max_hp": 10, "block": 0})
        assert m.is_dead

    def test_multi_intent(self):
        m = parse_monster({
            "index": 0,
            "name": "Multi",
            "hp": 20,
            "max_hp": 20,
            "block": 0,
            "intents": [
                {"type": "Attack", "damage": 5, "hits": 3},
                {"type": "Buff"},
            ],
        })
        assert m.intent is not None
        assert m.intent.damage == 5
        assert m.intent.hits == 3
        assert m.intent.is_buff


# ---------------------------------------------------------------------------
# Player parsing
# ---------------------------------------------------------------------------

class TestParsePlayer:
    def test_basic_player(self):
        p = parse_player(COMBAT_STATE["player"], COMBAT_STATE)
        assert p.name == "The Ironclad"
        assert p.current_hp == 80
        assert p.max_hp == 80
        assert p.gold == 99
        assert p.energy == 3
        assert p.max_energy == 3

    def test_relics(self):
        p = parse_player(COMBAT_STATE["player"], COMBAT_STATE)
        assert len(p.relics) == 1
        assert p.relics[0].name == "Burning Blood"

    def test_potions(self):
        p = parse_player(COMBAT_STATE["player"], COMBAT_STATE)
        assert len(p.potions) == 1
        assert p.potions[0] is not None
        assert p.potions[0].name == "Swift Potion"

    def test_player_with_powers(self):
        state = {
            **COMBAT_STATE,
            "player_powers": [
                {"name": "Strength", "amount": 2},
                {"name": "Dexterity", "amount": -1},
            ],
        }
        p = parse_player(COMBAT_STATE["player"], state)
        assert len(p.powers) == 2


# ---------------------------------------------------------------------------
# Relic parsing
# ---------------------------------------------------------------------------

class TestParseRelic:
    def test_basic(self):
        r = parse_relic(COMBAT_STATE["player"]["relics"][0])
        assert r.name == "Burning Blood"
        assert "6" in r.description  # Heal var resolved


# ---------------------------------------------------------------------------
# Potion parsing
# ---------------------------------------------------------------------------

class TestParsePotion:
    def test_basic(self):
        p = parse_potion(COMBAT_STATE["player"]["potions"][0])
        assert p.name == "Swift Potion"


# ---------------------------------------------------------------------------
# Combat state parsing
# ---------------------------------------------------------------------------

class TestParseCombatState:
    def test_full_combat(self):
        cs = parse_combat_state(COMBAT_STATE)
        assert cs.turn == 1
        assert cs.phase == TurnPhase.PLAYER_TURN
        assert len(cs.hand) == 3
        assert len(cs.monsters) == 1
        assert cs.player.energy == 3
        assert cs.player.current_hp == 80

    def test_monsters_in_combat(self):
        cs = parse_combat_state(COMBAT_STATE)
        m = cs.monsters[0]
        assert m.name == "Nibbit"
        assert m.intent is not None
        assert m.intent.damage == 12


# ---------------------------------------------------------------------------
# Map parsing
# ---------------------------------------------------------------------------

class TestParseMap:
    def test_map_choices(self):
        gmap = parse_map_choices(MAP_SELECT_STATE)
        assert len(gmap.nodes) == 4
        assert gmap.nodes[0].type == MapNodeType.MONSTER
        assert gmap.nodes[2].type == MapNodeType.EVENT
        assert gmap.nodes[3].type == MapNodeType.ELITE

    def test_map_node_coords(self):
        gmap = parse_map_choices(MAP_SELECT_STATE)
        assert gmap.nodes[0].x == 0
        assert gmap.nodes[0].y == 1
        assert gmap.nodes[1].x == 3


# ---------------------------------------------------------------------------
# Run state
# ---------------------------------------------------------------------------

class TestParseRunState:
    def test_from_combat(self):
        rs = parse_run_state(COMBAT_STATE)
        assert rs.act == 1
        assert rs.floor == 2
        assert rs.player.current_hp == 80


# ---------------------------------------------------------------------------
# Top-level dispatcher
# ---------------------------------------------------------------------------

class TestParseResponse:
    def test_combat(self):
        result = parse_response(COMBAT_STATE)
        assert result["decision"] == "combat_play"
        assert "combat" in result
        assert result["combat"].turn == 1

    def test_map_select(self):
        result = parse_response(MAP_SELECT_STATE)
        assert result["decision"] == "map_select"
        assert "map" in result
        assert len(result["map"].nodes) == 4

    def test_event_choice(self):
        result = parse_response(EVENT_CHOICE_STATE)
        assert result["decision"] == "event_choice"
        assert len(result["options"]) == 2

    def test_rest_site(self):
        result = parse_response(REST_SITE_STATE)
        assert result["decision"] == "rest_site"
        assert len(result["options"]) == 2

    def test_card_reward(self):
        result = parse_response(CARD_REWARD_STATE)
        assert result["decision"] == "card_reward"
        assert len(result["cards"]) == 2
        assert result["cards"][0].name == "Blood Wall"

    def test_game_over(self):
        result = parse_response(GAME_OVER_STATE)
        assert result["decision"] == "game_over"
        assert result["victory"] is False


# ---------------------------------------------------------------------------
# Integration tests — require sts2-cli process
# ---------------------------------------------------------------------------

# Skip integration tests if sts2-cli is not available.
_STS2_CLI_AVAILABLE = (
    Path("/tmp/sts2-cli/lib/sts2.dll").is_file()
    and Path("/tmp/sts2-cli/src/Sts2Headless/bin/Debug/net9.0/Sts2Headless.dll").is_file()
)

requires_sts2 = pytest.mark.skipif(
    not _STS2_CLI_AVAILABLE,
    reason="sts2-cli not built at /tmp/sts2-cli",
)


@requires_sts2
class TestEngineBridgeIntegration:
    """Integration tests that start a real sts2-cli process."""

    @pytest.fixture
    async def bridge(self):
        from sts2_tui.bridge import EngineBridge

        b = EngineBridge()
        yield b
        # Cleanup
        if b.is_running():
            await b.quit()

    async def test_start_and_ready(self, bridge):
        ready = await bridge.start()
        assert ready["type"] == "ready"
        assert "version" in ready
        assert bridge.is_running()

    async def test_start_run(self, bridge):
        await bridge.start()
        state = await bridge.start_run("Ironclad", seed="test_bridge_42")
        assert state["type"] == "decision"
        assert "player" in state
        assert state["player"]["hp"] > 0

    async def test_play_first_combat(self, bridge):
        """Start a run, navigate to combat, play a card, and end turn."""
        await bridge.start()
        state = await bridge.start_run("Ironclad", seed="test_bridge_42")

        # Navigate through Neow event
        max_steps = 20
        for _ in range(max_steps):
            decision = state.get("decision", "")
            if decision == "combat_play":
                break
            elif decision == "event_choice":
                options = state.get("options", [])
                if options:
                    idx = options[0]["index"]
                    state = await bridge.choose(idx)
                else:
                    state = await bridge.leave_room()
            elif decision == "map_select":
                choices = state.get("choices", [])
                if choices:
                    state = await bridge.select_map_node(
                        choices[0]["col"], choices[0]["row"]
                    )
            elif decision == "card_reward":
                state = await bridge.skip_card_reward()
            elif decision == "bundle_select":
                state = await bridge.select_bundle(0)
            elif decision == "card_select":
                cards = state.get("cards", [])
                if cards:
                    state = await bridge.select_cards("0")
                else:
                    state = await bridge.skip_select()
            else:
                state = await bridge.proceed()
        else:
            pytest.skip("Could not reach combat in max_steps")

        assert state["decision"] == "combat_play"

        # Parse combat state via adapter
        combat = parse_combat_state(state)
        assert combat.player.energy > 0
        assert len(combat.hand) > 0
        assert len(combat.monsters) > 0

        # Play a card
        hand = state.get("hand", [])
        playable = [c for c in hand if c.get("can_play")]
        if playable:
            card = playable[0]
            target = None
            if card.get("target_type") == "AnyEnemy":
                enemies = state.get("enemies", [])
                if enemies:
                    target = enemies[0]["index"]
            new_state = await bridge.play_card(card["index"], target=target)
            assert new_state["type"] == "decision"

        # End turn
        # Keep playing/ending until we get back to combat_play or combat ends
        state = new_state if playable else state
        if state.get("decision") == "combat_play":
            end_state = await bridge.end_turn()
            assert end_state["type"] == "decision"

    async def test_quit(self, bridge):
        await bridge.start()
        assert bridge.is_running()
        await bridge.quit()
        assert not bridge.is_running()

    async def test_context_manager(self):
        from sts2_tui.bridge import EngineBridge

        async with EngineBridge() as bridge:
            assert bridge.is_running()
            state = await bridge.start_run("Ironclad", seed="ctx_mgr_test")
            assert state["type"] == "decision"
        assert not bridge.is_running()

    async def test_state_adapter_round_trip(self, bridge):
        """Verify that every decision type we encounter can be parsed."""
        await bridge.start()
        state = await bridge.start_run("Ironclad", seed="adapter_test_42")

        decisions_seen: set[str] = set()
        max_steps = 50

        for _ in range(max_steps):
            decision = state.get("decision", "")
            decisions_seen.add(decision)

            # Parse through the adapter -- should not raise
            parsed = parse_response(state)
            assert parsed["decision"] == decision

            if decision == "game_over":
                break
            elif decision == "combat_play":
                hand = state.get("hand", [])
                energy = state.get("energy", 0)
                playable = [
                    c for c in hand
                    if c.get("can_play") and (c.get("cost", 99) <= energy)
                ]
                if playable:
                    card = playable[0]
                    target = None
                    if card.get("target_type") == "AnyEnemy":
                        enemies = state.get("enemies", [])
                        if enemies:
                            target = enemies[0]["index"]
                    state = await bridge.play_card(card["index"], target=target)
                else:
                    state = await bridge.end_turn()
            elif decision == "event_choice":
                options = state.get("options", [])
                if options:
                    pick = next(
                        (o for o in options if not o.get("is_locked")),
                        options[0],
                    )
                    state = await bridge.choose(pick["index"])
                else:
                    state = await bridge.leave_room()
            elif decision == "map_select":
                choices = state.get("choices", [])
                if choices:
                    state = await bridge.select_map_node(
                        choices[0]["col"], choices[0]["row"]
                    )
                else:
                    break
            elif decision == "card_reward":
                state = await bridge.skip_card_reward()
            elif decision == "rest_site":
                options = state.get("options", [])
                enabled = [o for o in options if o.get("is_enabled", True)]
                if enabled:
                    state = await bridge.choose(enabled[0]["index"])
                else:
                    state = await bridge.leave_room()
            elif decision == "bundle_select":
                state = await bridge.select_bundle(0)
            elif decision == "card_select":
                cards = state.get("cards", [])
                if cards:
                    state = await bridge.select_cards("0")
                else:
                    state = await bridge.skip_select()
            elif decision == "shop":
                state = await bridge.leave_room()
            else:
                state = await bridge.proceed()

        # We should have seen at least some meaningful decisions.
        assert "combat_play" in decisions_seen or "map_select" in decisions_seen

    async def test_bridge_error_on_invalid_command(self, bridge):
        """Sending a bad action should raise BridgeError."""
        from sts2_tui.bridge import BridgeError

        await bridge.start()
        await bridge.start_run("Ironclad", seed="error_test")

        with pytest.raises(BridgeError):
            # play_card before we're in combat should error
            await bridge.play_card(99)
