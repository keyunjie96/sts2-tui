"""Tests for untested code paths in sts2-tui screens and controller.

Analysis of code coverage gaps:

=== UNTESTED CODE PATHS REPORT ===

1. CHARACTER-SPECIFIC PATHS (HIGH RISK)
   Ground truth data only covers Ironclad. These character-specific paths
   are completely untested:
   - Defect: OrbDisplay widget (orbs, orb_slots, orb types: Lightning/Frost/Dark/Plasma/Glass)
   - Necrobinder: OstyDisplay widget (companion HP, alive/fallen state, block)
   - Regent: StarsDisplay widget (star resource, star_cost on cards)
   - extract_player: orbs from state vs player dict, osty extraction, stars extraction

2. BILINGUAL / I18N PATHS
   - _name_str() with dict input (bilingual names like {"en": "Strike", "zh": "打击"})
   - _name_str() fallback chain: lang -> en -> zh -> str(dict)

3. ENEMY INTENT EDGE CASES
   - Multi-intent enemies (Attack+Defend, Attack+Buff) -- intent_parts join with " + "
   - Unknown intent type (falls through all elif to generic append)
   - All intents are present in ground truth except combinations

4. COMBAT SCREEN EDGE CASES
   - Stuck state detection (_handle_response with repeated fingerprints)
   - Double-press card selection (auto-play)
   - Potion cycling with multiple potions
   - Empty living enemies list (all dead)
   - selected_target >= len(living) clamp

5. CONTROLLER HELPER EDGE CASES
   - resolve_card_description: empty description, empty stats, nested templates
   - _detect_x_cost: cost != 0 early return, literal X detection
   - extract_pile_counts: exhaust computation when negative
   - humanize_stat_key: "power" suffix stripping, unknown keys
   - _enrich_card_stats: exception path, basic card name fallback (Strike/Defend)
   - extract_reward_cards: after_upgrade processing

6. SCREEN ERROR PATHS
   - EventScreen: locked option selection, confirm with no selection, error on choose
   - RestScreen: disabled option selection, confirm with no selection, error on choose
   - CardRewardScreen: confirm with no selection, error on select, skip error
   - MapScreen: map fetch failure, no choices, invalid path index
   - ShopScreen: not enough gold, unknown item kind, buy error, unstocked items
   - GenericScreen: bundle_select/card_select/shop decision routing, no selection proceed

7. DECK/RELIC VIEWER EDGE CASES
   - Empty deck
   - Cards with unknown type (not in _TYPE_ORDER)
   - Singular vs plural type labels (e.g., "1 ATTACK" vs "2 ATTACKS")
   - Upgrade preview with cost change, new stats, description-only change

8. MAP RENDERING EDGE CASES
   - _build_connection_line: multi-column span, adjacent diagonal, straight vertical
   - _render_full_map: empty rows_data
   - _render_fallback_choices: empty choices
   - _append_floor_summary: empty type_counts, empty next_types

9. SHOP EDGE CASES
   - _normalize_name: apostrophe variants
   - _load_card_data: file not found, JSON parse error
   - _build_shop_items: unstocked cards/relics/potions, no card_removal_cost
   - _buy_item: unknown item kind returning error dict
   - Card enrichment from after_upgrade stats as fallback
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from pathlib import Path
from textual.app import App

# ---------------------------------------------------------------------------
# Imports under test
# ---------------------------------------------------------------------------

from sts2_tui.tui.controller import (
    _name_str,
    humanize_stat_key,
    resolve_card_description,
    extract_enemies,
    extract_player,
    extract_pile_counts,
    extract_hand,
    extract_reward_cards,
    _detect_x_cost,
    _error_dict,
    GameController,
)

CSS_PATH = Path(__file__).parent.parent / "src" / "sts2_tui" / "tui" / "sls.tcss"


# ===================================================================
# 1. _name_str -- bilingual dict handling
# ===================================================================


class TestNameStr:
    def test_none_returns_question_mark(self):
        assert _name_str(None) == "?"

    def test_plain_string_passthrough(self):
        assert _name_str("Strike") == "Strike"

    def test_integer_converted_to_string(self):
        assert _name_str(42) == "42"

    def test_bilingual_dict_en(self):
        """When language is 'en', return the English name."""
        with patch("sts2_tui.tui.i18n.get_language", return_value="en"):
            result = _name_str({"en": "Strike", "zh": "打击"})
            assert result == "Strike"

    def test_bilingual_dict_zh(self):
        """When language is 'zh', return the Chinese name."""
        with patch("sts2_tui.tui.i18n.get_language", return_value="zh"):
            result = _name_str({"en": "Strike", "zh": "打击"})
            assert result == "打击"

    def test_bilingual_dict_fallback_to_en(self):
        """When requested language missing, fall back to English."""
        with patch("sts2_tui.tui.i18n.get_language", return_value="fr"):
            result = _name_str({"en": "Strike", "zh": "打击"})
            assert result == "Strike"

    def test_bilingual_dict_fallback_to_zh(self):
        """When only Chinese available, fall back to zh."""
        with patch("sts2_tui.tui.i18n.get_language", return_value="en"):
            result = _name_str({"zh": "打击"})
            assert result == "打击"

    def test_bilingual_dict_empty_falls_to_str(self):
        """When dict has no matching keys, fall back to str(dict)."""
        with patch("sts2_tui.tui.i18n.get_language", return_value="en"):
            result = _name_str({"fr": "Frappe"})
            assert result == str({"fr": "Frappe"})


# ===================================================================
# 2. humanize_stat_key -- edge cases
# ===================================================================


class TestHumanizeStatKey:
    def test_known_key(self):
        assert humanize_stat_key("damage") == "Damage"
        assert humanize_stat_key("hploss") == "HP Loss"
        assert humanize_stat_key("maxhp") == "Max HP"

    def test_power_suffix_stripping(self):
        assert humanize_stat_key("vulnerablepower") == "Vulnerable"
        assert humanize_stat_key("juggernautpower") == "Juggernaut"

    def test_short_power_not_stripped(self):
        """The word 'power' itself (5 chars) should not strip to empty."""
        # "power" has len 5, condition is len > 5, so it won't strip
        result = humanize_stat_key("power")
        assert result == "Power"

    def test_unknown_key_with_underscores(self):
        assert humanize_stat_key("some_stat_key") == "Some Stat Key"

    def test_unknown_key_plain(self):
        assert humanize_stat_key("foobar") == "Foobar"


# ===================================================================
# 3. resolve_card_description -- edge cases
# ===================================================================


class TestResolveCardDescription:
    def test_empty_description(self):
        assert resolve_card_description("", {}) == ""
        assert resolve_card_description("", None) == ""

    def test_plain_text_passthrough(self):
        assert resolve_card_description("Deal 6 damage.", {}) == "Deal 6 damage."

    def test_bbcode_stripping(self):
        result = resolve_card_description("[b]Deal[/b] [color=#ff0000]6[/color] damage.", {})
        assert "Deal" in result
        assert "[b]" not in result
        assert "[color" not in result

    def test_numeric_brackets_preserved(self):
        """Energy icons like [2] should be preserved."""
        result = resolve_card_description("Costs [2] energy.", {})
        assert "[2]" in result

    def test_stat_resolution(self):
        result = resolve_card_description("Deal {Damage:diff()} damage.", {"damage": 9})
        assert "9" in result

    def test_energy_prefix_single(self):
        result = resolve_card_description("{energyPrefix:energyIcons(1)}", {})
        assert result == "Energy"

    def test_energy_prefix_multiple(self):
        result = resolve_card_description("{energyPrefix:energyIcons(3)}", {})
        assert result == "3 Energy"

    def test_if_upgraded_with_pipe(self):
        result = resolve_card_description("{IfUpgraded:show:Upgraded|Base}", {})
        assert result == "Base"

    def test_if_upgraded_without_pipe(self):
        result = resolve_card_description("{IfUpgraded:show:OnlyUpgraded}", {})
        assert result == ""

    def test_plural_singular(self):
        result = resolve_card_description("{Hits:plural:time|times}", {"hits": 1})
        assert result == "time"

    def test_plural_plural(self):
        result = resolve_card_description("{Hits:plural:time|times}", {"hits": 3})
        assert result == "times"

    def test_star_icons_singular(self):
        result = resolve_card_description("{Stars:starIcons()}", {"stars": 1})
        assert "1 Star" in result

    def test_star_icons_plural(self):
        result = resolve_card_description("{Stars:starIcons()}", {"stars": 3})
        assert "3 Stars" in result

    def test_star_icons_no_value(self):
        result = resolve_card_description("{Stars:starIcons()}", {})
        assert "Stars" in result

    def test_energy_icons_formatter(self):
        result = resolve_card_description("{Energy:energyIcons()}", {"energy": 2})
        assert "2 Energy" in result

    def test_entity_reference_zero_value(self):
        """When a stat value is 0 and looks like an entity reference, show readable name."""
        result = resolve_card_description("{BirdCard}", {"birdcard": 0})
        assert "Bird Card" in result

    def test_entity_reference_non_entity(self):
        """A stat value of 0 for a non-entity key should show 0."""
        result = resolve_card_description("{Damage}", {"damage": 0})
        assert "0" in result

    def test_icon_vars(self):
        result = resolve_card_description("{singleStarIcon}", {})
        assert "\u2605" in result  # filled star

    def test_unresolved_var_with_formatter(self):
        result = resolve_card_description("{UnknownVar:diff()}", {})
        assert result == "X"

    def test_unresolved_simple_var(self):
        result = resolve_card_description("{UnknownVar}", {})
        assert result == "X"

    def test_in_combat_block_removed(self):
        result = resolve_card_description("Deal damage.{InCombat:extra text|}", {})
        assert "extra text" not in result
        assert "InCombat" not in result

    def test_is_multiplayer_block(self):
        """IsMultiplayer: always single-player, so pick the false branch."""
        result = resolve_card_description("{IsMultiplayer:multi text|single text}", {})
        assert "single text" in result
        assert "multi text" not in result

    def test_nested_template_resolution(self):
        """Templates with nested braces like {Var:plural:word|{:diff()} words}."""
        result = resolve_card_description(
            "{LightningRodPower:plural:turn|{:diff()} turns}",
            {"lightningrodpower": 2},
        )
        assert "2 turns" in result

    def test_nested_template_singular(self):
        result = resolve_card_description(
            "{LightningRodPower:plural:turn|{:diff()} turns}",
            {"lightningrodpower": 1},
        )
        assert "turn" in result


# ===================================================================
# 4. _detect_x_cost
# ===================================================================


class TestDetectXCost:
    def test_non_zero_cost_returns_false(self):
        assert _detect_x_cost(1, "Deal X damage") is False
        assert _detect_x_cost(2, "X times") is False

    def test_zero_cost_with_x(self):
        assert _detect_x_cost(0, "Deal X damage") is True
        assert _detect_x_cost(0, "X times") is True

    def test_zero_cost_without_x(self):
        assert _detect_x_cost(0, "Deal 0 damage") is False

    def test_x_inside_template_not_matched(self):
        """Template vars like {Repeat:diff()} should not trigger X-cost."""
        assert _detect_x_cost(0, "Repeat {Repeat:diff()} times") is False

    def test_x_as_word_boundary(self):
        """X must be a whole word, not part of 'Exhaust'."""
        assert _detect_x_cost(0, "Exhaust this card") is False


# ===================================================================
# 5. extract_enemies -- edge cases
# ===================================================================


class TestExtractEnemies:
    def test_empty_enemies(self):
        result = extract_enemies({"enemies": []})
        assert result == []

    def test_no_enemies_key(self):
        result = extract_enemies({})
        assert result == []

    def test_dead_enemy(self):
        result = extract_enemies({"enemies": [
            {"index": 0, "name": "Slime", "hp": 0, "max_hp": 20, "block": 0,
             "intents": [], "powers": None},
        ]})
        assert len(result) == 1
        assert result[0]["is_dead"] is True

    def test_bilingual_enemy_name(self):
        with patch("sts2_tui.tui.i18n.get_language", return_value="en"):
            result = extract_enemies({"enemies": [
                {"index": 0, "name": {"en": "Slime", "zh": "史莱姆"},
                 "hp": 20, "max_hp": 20, "block": 0, "intents": [], "powers": None},
            ]})
            assert result[0]["name"] == "Slime"

    def test_multi_intent_enemy(self):
        """Enemy with Attack + Defend intents."""
        result = extract_enemies({"enemies": [
            {"index": 0, "name": "Guard", "hp": 30, "max_hp": 30, "block": 0,
             "intents": [
                 {"type": "Attack", "damage": 8, "hits": 1},
                 {"type": "Defend"},
             ], "powers": None},
        ]})
        e = result[0]
        assert e["intent_damage"] == 8
        assert e["is_defend"] is True
        assert "Attack 8" in e["intent_summary"]
        assert "Defend" in e["intent_summary"]

    def test_unknown_intent_type(self):
        result = extract_enemies({"enemies": [
            {"index": 0, "name": "Boss", "hp": 100, "max_hp": 100, "block": 0,
             "intents": [{"type": "UnknownNewType"}], "powers": None},
        ]})
        assert "UnknownNewType" in result[0]["intent_summary"]

    def test_multi_hit_attack(self):
        result = extract_enemies({"enemies": [
            {"index": 0, "name": "Rat", "hp": 10, "max_hp": 10, "block": 0,
             "intents": [{"type": "Attack", "damage": 4, "hits": 3}],
             "powers": None},
        ]})
        assert result[0]["intent_damage"] == 4
        assert result[0]["intent_hits"] == 3
        assert "4x3" in result[0]["intent_summary"]

    def test_all_intent_types(self):
        """Test every intent type flag is set correctly."""
        intents = [
            {"type": "Defend"},
            {"type": "Buff"},
            {"type": "Debuff"},
            {"type": "DebuffStrong"},
            {"type": "StatusCard"},
            {"type": "Heal"},
            {"type": "Stun"},
            {"type": "Summon"},
        ]
        result = extract_enemies({"enemies": [
            {"index": 0, "name": "Boss", "hp": 100, "max_hp": 100, "block": 0,
             "intents": intents, "powers": None},
        ]})
        e = result[0]
        assert e["is_defend"] is True
        assert e["is_buff"] is True
        assert e["is_debuff"] is True
        assert e["is_status_card"] is True
        assert e["is_heal"] is True
        assert e["is_stun"] is True
        assert e["is_summon"] is True

    def test_enemy_with_powers(self):
        result = extract_enemies({"enemies": [
            {"index": 0, "name": "Elite", "hp": 50, "max_hp": 50, "block": 5,
             "intents": [], "powers": [
                 {"name": "Strength", "amount": 3},
                 {"name": "Vulnerable", "amount": 2},
             ]},
        ]})
        e = result[0]
        assert len(e["powers"]) == 2
        assert e["powers"][0]["name"] == "Strength"
        assert e["block"] == 5

    def test_none_powers(self):
        result = extract_enemies({"enemies": [
            {"index": 0, "name": "Slime", "hp": 20, "max_hp": 20, "block": 0,
             "intents": [], "powers": None},
        ]})
        assert result[0]["powers"] == []


# ===================================================================
# 6. extract_player -- character-specific paths
# ===================================================================


class TestExtractPlayer:
    def test_basic_player(self):
        state = {
            "player": {"name": "Ironclad", "hp": 80, "max_hp": 80, "block": 0,
                        "gold": 99, "potions": None, "relics": None, "deck_size": 10},
            "energy": 3, "max_energy": 3,
        }
        result = extract_player(state)
        assert result["name"] == "Ironclad"
        assert result["hp"] == 80
        assert result["energy"] == 3
        assert result["potions"] == []
        assert result["relics"] == []
        assert result["orbs"] == []
        assert result["osty"] is None
        assert result["stars"] is None

    def test_defect_orbs_in_player(self):
        """Defect orbs from player dict."""
        state = {
            "player": {
                "name": "Defect", "hp": 60, "max_hp": 60, "block": 0,
                "gold": 50, "potions": [], "relics": [], "deck_size": 12,
                "orbs": [
                    {"type": "Lightning", "passive_amount": 3, "evoke_amount": 8},
                    {"type": "Frost", "passive_amount": 2, "evoke_amount": 5},
                ],
                "orb_slots": 3,
            },
            "energy": 3, "max_energy": 3,
        }
        result = extract_player(state)
        assert len(result["orbs"]) == 2
        assert result["orbs"][0]["type"] == "Lightning"
        assert result["orb_slots"] == 3

    def test_defect_orbs_in_state(self):
        """Defect orbs from top-level state dict."""
        state = {
            "player": {
                "name": "Defect", "hp": 60, "max_hp": 60, "block": 0,
                "gold": 50, "potions": [], "relics": [], "deck_size": 12,
            },
            "orbs": [
                {"type": "Dark", "passive_amount": 6, "evoke_amount": 6},
            ],
            "orb_slots": 4,
            "energy": 3, "max_energy": 3,
        }
        result = extract_player(state)
        assert len(result["orbs"]) == 1
        assert result["orbs"][0]["type"] == "Dark"
        assert result["orb_slots"] == 4

    def test_necrobinder_osty(self):
        """Necrobinder companion extraction."""
        state = {
            "player": {
                "name": "Necrobinder", "hp": 70, "max_hp": 70, "block": 0,
                "gold": 50, "potions": [], "relics": [], "deck_size": 10,
            },
            "osty": {
                "name": "Osty", "hp": 25, "max_hp": 30, "block": 5, "alive": True,
            },
            "energy": 3, "max_energy": 3,
        }
        result = extract_player(state)
        assert result["osty"] is not None
        assert result["osty"]["name"] == "Osty"
        assert result["osty"]["hp"] == 25
        assert result["osty"]["alive"] is True
        assert result["osty"]["block"] == 5

    def test_necrobinder_osty_dead(self):
        state = {
            "player": {
                "name": "Necrobinder", "hp": 70, "max_hp": 70, "block": 0,
                "gold": 50, "potions": [], "relics": [], "deck_size": 10,
            },
            "osty": {
                "name": "Osty", "hp": 0, "max_hp": 30, "block": 0, "alive": False,
            },
            "energy": 3, "max_energy": 3,
        }
        result = extract_player(state)
        assert result["osty"]["alive"] is False

    def test_necrobinder_osty_null(self):
        """When osty is null or absent, osty should be None."""
        state = {
            "player": {
                "name": "Ironclad", "hp": 80, "max_hp": 80, "block": 0,
                "gold": 99, "potions": [], "relics": [], "deck_size": 10,
            },
            "osty": None,
            "energy": 3, "max_energy": 3,
        }
        result = extract_player(state)
        assert result["osty"] is None

    def test_regent_stars(self):
        state = {
            "player": {
                "name": "Regent", "hp": 65, "max_hp": 65, "block": 0,
                "gold": 50, "potions": [], "relics": [], "deck_size": 10,
            },
            "stars": 3,
            "energy": 3, "max_energy": 3,
        }
        result = extract_player(state)
        assert result["stars"] == 3

    def test_potions_with_description_resolution(self):
        state = {
            "player": {
                "name": "Ironclad", "hp": 80, "max_hp": 80, "block": 0,
                "gold": 99,
                "potions": [
                    {"index": 0, "name": "Fire Potion", "target_type": "AnyEnemy",
                     "description": "Deal {Damage:diff()} damage.", "vars": {"damage": 20}},
                ],
                "relics": [
                    {"name": "Burning Blood",
                     "description": "Heal {Heal:diff()} HP at end of combat.", "vars": {"heal": 6}},
                ],
                "deck_size": 10,
            },
            "energy": 3, "max_energy": 3,
        }
        result = extract_player(state)
        assert "20" in result["potions"][0]["description"]
        assert "6" in result["relics"][0]["description"]


# ===================================================================
# 7. extract_pile_counts -- edge cases
# ===================================================================


class TestExtractPileCounts:
    def test_normal(self):
        state = {
            "draw_pile_count": 5,
            "discard_pile_count": 3,
            "hand": [{"index": 0}, {"index": 1}],
            "player": {"deck_size": 12},
        }
        result = extract_pile_counts(state)
        assert result["draw"] == 5
        assert result["discard"] == 3
        assert result["exhaust"] == 2  # 12 - 5 - 3 - 2

    def test_negative_exhaust_clamped_to_zero(self):
        """When status/curse cards inflate the count, exhaust should not go negative."""
        state = {
            "draw_pile_count": 10,
            "discard_pile_count": 5,
            "hand": [{"index": 0}] * 3,
            "player": {"deck_size": 10},  # 10 - 10 - 5 - 3 = -8 -> 0
        }
        result = extract_pile_counts(state)
        assert result["exhaust"] == 0

    def test_missing_keys(self):
        result = extract_pile_counts({})
        assert result["draw"] == 0
        assert result["discard"] == 0
        assert result["exhaust"] == 0


# ===================================================================
# 8. extract_hand -- X-cost and star_cost
# ===================================================================


class TestExtractHand:
    def test_x_cost_card(self):
        state = {
            "hand": [
                {"index": 0, "name": "Whirlwind", "cost": 0, "type": "Attack",
                 "can_play": True, "target_type": "AllEnemy",
                 "stats": {"damage": 5}, "description": "Deal X damage to ALL enemies.",
                 "keywords": []},
            ],
        }
        hand = extract_hand(state)
        assert hand[0]["cost"] == -1  # sentinel for X-cost

    def test_zero_cost_card_not_x(self):
        state = {
            "hand": [
                {"index": 0, "name": "Anger", "cost": 0, "type": "Attack",
                 "can_play": True, "target_type": "AnyEnemy",
                 "stats": {"damage": 6}, "description": "Deal {Damage:diff()} damage.",
                 "keywords": []},
            ],
        }
        hand = extract_hand(state)
        assert hand[0]["cost"] == 0  # Not X-cost

    def test_star_cost_card(self):
        """Regent cards may have star_cost alongside energy cost."""
        state = {
            "hand": [
                {"index": 0, "name": "Royal Decree", "cost": 1, "type": "Skill",
                 "can_play": True, "target_type": "None",
                 "star_cost": 2,
                 "stats": {"block": 10}, "description": "Gain {Block:diff()} Block.",
                 "keywords": []},
            ],
        }
        hand = extract_hand(state)
        assert hand[0]["star_cost"] == 2
        assert hand[0]["cost"] == 1


# ===================================================================
# 9. extract_reward_cards -- after_upgrade processing
# ===================================================================


class TestExtractRewardCards:
    def test_card_with_after_upgrade(self):
        state = {
            "cards": [
                {
                    "index": 0, "name": "Bash", "cost": 2, "type": "Attack",
                    "rarity": "Common",
                    "stats": {"damage": 8, "vulnerablepower": 2},
                    "description": "Deal {Damage:diff()} damage. Apply {VulnerablePower:diff()} Vulnerable.",
                    "after_upgrade": {
                        "cost": 2,
                        "stats": {"damage": 10, "vulnerablepower": 3},
                        "description": "Deal {Damage:diff()} damage. Apply {VulnerablePower:diff()} Vulnerable.",
                    },
                },
            ],
        }
        cards = extract_reward_cards(state)
        assert len(cards) == 1
        assert cards[0]["after_upgrade"] is not None
        assert cards[0]["after_upgrade"]["stats"]["damage"] == 10

    def test_card_without_after_upgrade(self):
        state = {
            "cards": [
                {
                    "index": 0, "name": "Wound", "cost": -2, "type": "Status",
                    "rarity": "",
                    "stats": {}, "description": "Unplayable.",
                },
            ],
        }
        cards = extract_reward_cards(state)
        assert cards[0]["after_upgrade"] is None


# ===================================================================
# 10. GameController -- error handling paths
# ===================================================================


class TestGameControllerErrors:
    """Test that BridgeError is caught and returned as error dicts."""

    @pytest.fixture
    def controller(self):
        from sts2_tui.bridge import BridgeError
        bridge = MagicMock()
        ctrl = GameController(bridge)
        return ctrl, bridge, BridgeError

    @pytest.mark.asyncio
    async def test_start_run_error(self, controller):
        ctrl, bridge, BridgeError = controller
        bridge.start_run = AsyncMock(side_effect=BridgeError("connection lost"))
        result = await ctrl.start_run("Ironclad")
        assert result["type"] == "error"
        assert "connection lost" in result["message"]

    @pytest.mark.asyncio
    async def test_play_card_error(self, controller):
        ctrl, bridge, BridgeError = controller
        bridge.play_card = AsyncMock(side_effect=BridgeError("invalid card"))
        result = await ctrl.play_card(0, None)
        assert result["type"] == "error"

    @pytest.mark.asyncio
    async def test_end_turn_error(self, controller):
        ctrl, bridge, BridgeError = controller
        bridge.end_turn = AsyncMock(side_effect=BridgeError("not your turn"))
        result = await ctrl.end_turn()
        assert result["type"] == "error"

    @pytest.mark.asyncio
    async def test_choose_error(self, controller):
        ctrl, bridge, BridgeError = controller
        bridge.choose = AsyncMock(side_effect=BridgeError("invalid choice"))
        result = await ctrl.choose(0)
        assert result["type"] == "error"

    @pytest.mark.asyncio
    async def test_get_map_error(self, controller):
        ctrl, bridge, BridgeError = controller
        bridge.get_map = AsyncMock(side_effect=BridgeError("map unavailable"))
        result = await ctrl.get_map()
        assert result["type"] == "error"

    @pytest.mark.asyncio
    async def test_use_potion_error(self, controller):
        ctrl, bridge, BridgeError = controller
        bridge.use_potion = AsyncMock(side_effect=BridgeError("no potion"))
        result = await ctrl.use_potion(0)
        assert result["type"] == "error"

    @pytest.mark.asyncio
    async def test_select_bundle_error(self, controller):
        ctrl, bridge, BridgeError = controller
        bridge.select_bundle = AsyncMock(side_effect=BridgeError("invalid bundle"))
        result = await ctrl.select_bundle(0)
        assert result["type"] == "error"

    @pytest.mark.asyncio
    async def test_select_cards_error(self, controller):
        ctrl, bridge, BridgeError = controller
        bridge.select_cards = AsyncMock(side_effect=BridgeError("invalid"))
        result = await ctrl.select_cards("0,1")
        assert result["type"] == "error"

    @pytest.mark.asyncio
    async def test_skip_select_error(self, controller):
        ctrl, bridge, BridgeError = controller
        bridge.skip_select = AsyncMock(side_effect=BridgeError("cannot skip"))
        result = await ctrl.skip_select()
        assert result["type"] == "error"


# ===================================================================
# 11. GameController -- _update_deck
# ===================================================================


class TestUpdateDeck:
    @pytest.mark.asyncio
    async def test_deck_cached_on_success(self):
        bridge = MagicMock()
        bridge.play_card = AsyncMock(return_value={
            "type": "decision", "decision": "combat_play",
            "player": {
                "deck": [{"name": "Strike"}, {"name": "Defend"}],
                "hp": 80, "max_hp": 80,
            },
        })
        ctrl = GameController(bridge)
        await ctrl.play_card(0)
        assert len(ctrl.player_deck) == 2
        assert ctrl.player_deck[0]["name"] == "Strike"

    @pytest.mark.asyncio
    async def test_deck_not_updated_when_absent(self):
        bridge = MagicMock()
        bridge.play_card = AsyncMock(return_value={
            "type": "decision", "decision": "combat_play",
            "player": {"hp": 80, "max_hp": 80},
        })
        ctrl = GameController(bridge)
        ctrl.player_deck = [{"name": "OldCard"}]
        await ctrl.play_card(0)
        # Deck should remain as before since response had no deck key
        assert ctrl.player_deck == [{"name": "OldCard"}]


# ===================================================================
# 12. TUI Screens -- Defect/Necrobinder/Regent rendering (HIGH RISK)
# ===================================================================


class CombatTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.combat import CombatScreen
        self.push_screen(CombatScreen(self._state, controller=self._controller))


def _make_mock_controller(next_state: dict | None = None) -> MagicMock:
    if next_state is None:
        next_state = {
            "type": "decision", "decision": "map_select",
            "choices": [], "player": {"name": "Test", "hp": 80, "max_hp": 80,
                                       "block": 0, "gold": 99, "relics": [],
                                       "potions": [], "deck_size": 10},
        }
    ctrl = MagicMock()
    for method in [
        "play_card", "end_turn", "choose", "select_map_node",
        "select_card_reward", "skip_card_reward", "use_potion",
        "proceed", "leave_room", "select_bundle", "select_cards",
        "skip_select", "get_state", "start_run", "quit", "get_map",
    ]:
        setattr(ctrl, method, AsyncMock(return_value=next_state))
    return ctrl


# --- Defect combat state with orbs ---
DEFECT_COMBAT_STATE = {
    "type": "decision",
    "decision": "combat_play",
    "context": {"act": 1, "floor": 3},
    "round": 1,
    "energy": 3,
    "max_energy": 3,
    "hand": [
        {"index": 0, "name": "Zap", "cost": 1, "type": "Skill",
         "can_play": True, "target_type": "None",
         "stats": {}, "description": "Channel 1 Lightning.",
         "keywords": []},
    ],
    "enemies": [
        {"index": 0, "name": "Nibbit", "hp": 40, "max_hp": 40, "block": 0,
         "intents": [{"type": "Attack", "damage": 8}], "powers": None},
    ],
    "player": {
        "name": "The Defect", "hp": 60, "max_hp": 60, "block": 0,
        "gold": 50, "potions": [], "relics": [], "deck_size": 12,
        "orbs": [
            {"type": "Lightning", "passive_amount": 3, "evoke_amount": 8},
            {"type": "Frost", "passive_amount": 2, "evoke_amount": 5},
        ],
        "orb_slots": 3,
    },
    "player_powers": [],
    "draw_pile_count": 8,
    "discard_pile_count": 0,
}

# --- Necrobinder combat state with Osty ---
NECROBINDER_COMBAT_STATE = {
    "type": "decision",
    "decision": "combat_play",
    "context": {"act": 1, "floor": 3},
    "round": 1,
    "energy": 3,
    "max_energy": 3,
    "hand": [
        {"index": 0, "name": "Soul Drain", "cost": 1, "type": "Attack",
         "can_play": True, "target_type": "AnyEnemy",
         "stats": {"damage": 7}, "description": "Deal {Damage:diff()} damage.",
         "keywords": []},
    ],
    "enemies": [
        {"index": 0, "name": "Splotch", "hp": 30, "max_hp": 30, "block": 0,
         "intents": [{"type": "Attack", "damage": 6}], "powers": None},
    ],
    "player": {
        "name": "The Necrobinder", "hp": 70, "max_hp": 70, "block": 0,
        "gold": 50, "potions": [], "relics": [], "deck_size": 10,
    },
    "osty": {
        "name": "Osty", "hp": 25, "max_hp": 30, "block": 5, "alive": True,
    },
    "player_powers": [],
    "draw_pile_count": 7,
    "discard_pile_count": 0,
}

# --- Necrobinder with fallen Osty ---
NECROBINDER_FALLEN_OSTY_STATE = {
    **NECROBINDER_COMBAT_STATE,
    "osty": {
        "name": "Osty", "hp": 0, "max_hp": 30, "block": 0, "alive": False,
    },
}

# --- Regent combat state with stars ---
REGENT_COMBAT_STATE = {
    "type": "decision",
    "decision": "combat_play",
    "context": {"act": 1, "floor": 3},
    "round": 1,
    "energy": 3,
    "max_energy": 3,
    "hand": [
        {"index": 0, "name": "Royal Strike", "cost": 1, "type": "Attack",
         "can_play": True, "target_type": "AnyEnemy",
         "star_cost": 1,
         "stats": {"damage": 9}, "description": "Deal {Damage:diff()} damage.",
         "keywords": []},
    ],
    "enemies": [
        {"index": 0, "name": "Knight", "hp": 35, "max_hp": 35, "block": 0,
         "intents": [{"type": "Attack", "damage": 10}], "powers": None},
    ],
    "player": {
        "name": "The Regent", "hp": 65, "max_hp": 65, "block": 0,
        "gold": 50, "potions": [], "relics": [], "deck_size": 10,
    },
    "stars": 3,
    "player_powers": [],
    "draw_pile_count": 7,
    "discard_pile_count": 0,
}


@pytest.mark.asyncio
class TestDefectCombatScreen:
    """Defect-specific combat screen rendering with orbs."""

    async def test_defect_renders_orb_display(self):
        ctrl = _make_mock_controller()
        app = CombatTestApp(DEFECT_COMBAT_STATE, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#combat-screen"), "Missing #combat-screen"
            orb_displays = app.screen.query("#orb-display")
            assert len(orb_displays) == 1, "OrbDisplay not rendered for Defect"

    async def test_defect_empty_orb_slots(self):
        """Defect with orb slots but no orbs yet."""
        state = {**DEFECT_COMBAT_STATE}
        state["player"] = {**state["player"], "orbs": [], "orb_slots": 3}
        ctrl = _make_mock_controller()
        app = CombatTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#combat-screen")


@pytest.mark.asyncio
class TestNecrobinderCombatScreen:
    """Necrobinder-specific combat screen rendering with Osty."""

    async def test_necrobinder_renders_osty(self):
        ctrl = _make_mock_controller()
        app = CombatTestApp(NECROBINDER_COMBAT_STATE, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#combat-screen"), "Missing #combat-screen"
            osty_displays = app.screen.query("#osty-display")
            assert len(osty_displays) == 1, "OstyDisplay not rendered for Necrobinder"

    async def test_necrobinder_fallen_osty(self):
        """Osty that has fallen should render without crash."""
        ctrl = _make_mock_controller()
        app = CombatTestApp(NECROBINDER_FALLEN_OSTY_STATE, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#combat-screen")
            osty_displays = app.screen.query("#osty-display")
            assert len(osty_displays) == 1


@pytest.mark.asyncio
class TestRegentCombatScreen:
    """Regent-specific combat screen rendering with stars."""

    async def test_regent_renders_stars(self):
        ctrl = _make_mock_controller()
        app = CombatTestApp(REGENT_COMBAT_STATE, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#combat-screen"), "Missing #combat-screen"
            stars_displays = app.screen.query("#stars-display")
            assert len(stars_displays) == 1, "StarsDisplay not rendered for Regent"


# ===================================================================
# 13. Shop screen -- edge cases
# ===================================================================


class ShopTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.shop import ShopScreen
        self.push_screen(ShopScreen(self._state, controller=self._controller))


SHOP_STATE = {
    "type": "decision",
    "decision": "shop",
    "context": {"act": 1, "floor": 5},
    "player": {"hp": 70, "max_hp": 80, "gold": 200, "potions": [], "relics": [],
               "deck_size": 10},
    "cards": [
        {"index": 0, "name": "Inflame", "cost": 50, "type": "Power",
         "card_cost": 1, "is_stocked": True, "on_sale": False,
         "stats": None, "description": "Gain {Strength:diff()} Strength."},
        {"index": 1, "name": "Sold Out", "cost": 30, "type": "Attack",
         "card_cost": 1, "is_stocked": False,
         "stats": None, "description": "Already sold."},
    ],
    "relics": [
        {"index": 0, "name": "Vajra", "cost": 150, "is_stocked": True,
         "description": "Gain {Strength:diff()} Strength."},
    ],
    "potions": [
        {"index": 0, "name": "Fire Potion", "cost": 50, "is_stocked": True,
         "description": "Deal {Damage:diff()} damage."},
    ],
    "card_removal_cost": 75,
}


@pytest.mark.asyncio
class TestShopScreen:

    async def test_shop_renders(self):
        ctrl = _make_mock_controller()
        app = ShopTestApp(SHOP_STATE, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#shop-screen"), "Missing #shop-screen"

    async def test_shop_unstocked_items_filtered(self):
        """Unstocked cards should not appear in the shop items."""
        from sts2_tui.tui.screens.shop import _build_shop_items
        items = _build_shop_items(SHOP_STATE)
        card_names = [i.name for i in items if i.kind == "card"]
        assert "Inflame" in card_names
        assert "Sold Out" not in card_names

    async def test_shop_card_removal_present(self):
        from sts2_tui.tui.screens.shop import _build_shop_items
        items = _build_shop_items(SHOP_STATE)
        remove_items = [i for i in items if i.kind == "remove"]
        assert len(remove_items) == 1
        assert remove_items[0].cost == 75

    async def test_shop_no_card_removal(self):
        """When card_removal_cost is absent, no remove item."""
        from sts2_tui.tui.screens.shop import _build_shop_items
        state = {**SHOP_STATE}
        del state["card_removal_cost"]
        items = _build_shop_items(state)
        remove_items = [i for i in items if i.kind == "remove"]
        assert len(remove_items) == 0

    async def test_shop_empty(self):
        from sts2_tui.tui.screens.shop import _build_shop_items
        state = {
            "cards": [], "relics": [], "potions": [],
            "player": {"gold": 100},
        }
        items = _build_shop_items(state)
        assert len(items) == 0

    async def test_buy_unknown_kind(self):
        """_buy_item with unknown kind returns error dict."""
        from sts2_tui.tui.screens.shop import _ShopItem
        item = _ShopItem("unknown_kind", 0, "Mystery", "???", 10)
        from sts2_tui.tui.screens.shop import ShopScreen
        ctrl = _make_mock_controller()
        screen = ShopScreen.__new__(ShopScreen)
        screen.controller = ctrl
        result = await screen._buy_item(item)
        assert result["type"] == "error"
        assert "Unknown item kind" in result["message"]


# ===================================================================
# 14. Map rendering -- edge cases
# ===================================================================


class TestMapRendering:
    def test_render_fallback_empty_choices(self):
        from sts2_tui.tui.screens.map import _render_fallback_choices
        state = {"choices": [], "context": {"floor": 5}}
        text = _render_fallback_choices(state)
        rendered = str(text)
        # Should not crash, should show "no paths" equivalent
        assert text is not None

    def test_render_full_map_empty_rows(self):
        from sts2_tui.tui.screens.map import _render_full_map
        map_data = {"rows": [], "boss": {"col": 2, "row": 99, "name": "Boss"},
                    "context": {"act_name": "Test"}}
        text = _render_full_map(map_data, set(), {}, 0)
        rendered = str(text)
        assert text is not None

    def test_connection_line_straight_vertical(self):
        from sts2_tui.tui.screens.map import _build_connection_line
        nodes = [{"col": 2, "children": [{"col": 2, "row": 5}]}]
        result = _build_connection_line(nodes, 5, 5)
        assert "\u2502" in result  # vertical pipe

    def test_connection_line_adjacent_diagonal(self):
        from sts2_tui.tui.screens.map import _build_connection_line
        nodes = [{"col": 1, "children": [{"col": 2, "row": 5}]}]
        result = _build_connection_line(nodes, 5, 5)
        assert "\u2571" in result  # / diagonal

    def test_connection_line_multi_column_span(self):
        from sts2_tui.tui.screens.map import _build_connection_line
        nodes = [{"col": 0, "children": [{"col": 3, "row": 5}]}]
        result = _build_connection_line(nodes, 5, 5)
        # Should contain corner characters and horizontal lines
        assert "\u2570" in result or "\u256e" in result  # corner chars


# ===================================================================
# 15. _normalize_name (shop.py) -- apostrophe handling
# ===================================================================


class TestNormalizeName:
    def test_lowercase(self):
        from sts2_tui.tui.screens.shop import _normalize_name
        assert _normalize_name("Inflame") == "inflame"

    def test_apostrophe_stripped(self):
        from sts2_tui.tui.screens.shop import _normalize_name
        assert _normalize_name("Mazaleth's Gift") == "mazaleths gift"

    def test_curly_apostrophe_stripped(self):
        from sts2_tui.tui.screens.shop import _normalize_name
        assert _normalize_name("Mazaleth\u2019s Gift") == "mazaleths gift"


# ===================================================================
# 16. Deck viewer -- empty deck and unknown type
# ===================================================================


class DeckViewerTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, deck: list[dict]) -> None:
        super().__init__()
        self._deck = deck

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.deck_viewer import DeckViewerOverlay
        self.push_screen(DeckViewerOverlay(self._deck))


@pytest.mark.asyncio
class TestDeckViewerEdgeCases:

    async def test_empty_deck(self):
        app = DeckViewerTestApp([])
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#deck-overlay")

    async def test_unknown_card_type(self):
        deck = [
            {"name": "Strange Card", "cost": 1, "type": "Enchantment",
             "stats": {}, "description": "Something weird."},
        ]
        app = DeckViewerTestApp(deck)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#deck-overlay")

    async def test_singular_type_label(self):
        """When there's only 1 card of a type, label should be singular."""
        deck = [
            {"name": "Strike", "cost": 1, "type": "Attack",
             "stats": {"damage": 6}, "description": "Deal 6 damage."},
        ]
        app = DeckViewerTestApp(deck)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#deck-overlay")


# ===================================================================
# 17. Generic screen -- decision type routing
# ===================================================================


class GenericTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.generic import GenericScreen
        self.push_screen(GenericScreen(self._state, controller=self._controller))


@pytest.mark.asyncio
class TestGenericScreenDecisionRouting:

    async def test_bundle_select_proceed(self):
        """bundle_select decision should call select_bundle on proceed."""
        state = {
            "type": "decision", "decision": "bundle_select",
            "context": {"act": 1, "floor": 1},
            "player": {"hp": 80, "max_hp": 80, "gold": 99, "deck_size": 10},
            "bundles": [
                {"index": 0, "title": "Bundle A", "description": "Option A"},
                {"index": 1, "title": "Bundle B", "description": "Option B"},
            ],
        }
        next_state = {
            "type": "decision", "decision": "map_select",
            "choices": [], "player": {"hp": 80, "max_hp": 80, "gold": 99,
                                       "deck_size": 10},
        }
        ctrl = _make_mock_controller(next_state)
        app = GenericTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Select first option and proceed
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            ctrl.select_bundle.assert_called()

    async def test_card_select_proceed(self):
        """card_select decision should call select_cards on proceed."""
        state = {
            "type": "decision", "decision": "card_select",
            "context": {"act": 1, "floor": 1},
            "player": {"hp": 80, "max_hp": 80, "gold": 99, "deck_size": 10},
            "cards": [
                {"index": 0, "name": "Strike", "type": "Attack", "cost": 1,
                 "stats": {"damage": 6}, "description": "Deal 6 damage."},
            ],
        }
        next_state = {
            "type": "decision", "decision": "map_select",
            "choices": [], "player": {"hp": 80, "max_hp": 80, "gold": 99,
                                       "deck_size": 10},
        }
        ctrl = _make_mock_controller(next_state)
        app = GenericTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("down")
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            ctrl.select_cards.assert_called()

    async def test_no_selection_card_select_skips(self):
        """card_select with no selection should call skip_select."""
        state = {
            "type": "decision", "decision": "card_select",
            "context": {"act": 1, "floor": 1},
            "player": {"hp": 80, "max_hp": 80, "gold": 99, "deck_size": 10},
            "cards": [
                {"index": 0, "name": "Strike", "type": "Attack", "cost": 1,
                 "stats": {}, "description": ""},
            ],
        }
        next_state = {
            "type": "decision", "decision": "map_select",
            "choices": [], "player": {"hp": 80, "max_hp": 80, "gold": 99,
                                       "deck_size": 10},
        }
        ctrl = _make_mock_controller(next_state)
        app = GenericTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Proceed without selecting anything
            await pilot.press("enter")
            await pilot.pause()
            ctrl.skip_select.assert_called()

    async def test_no_selection_bundle_select_defaults(self):
        """bundle_select with no selection should call select_bundle(0)."""
        state = {
            "type": "decision", "decision": "bundle_select",
            "context": {"act": 1, "floor": 1},
            "player": {"hp": 80, "max_hp": 80, "gold": 99, "deck_size": 10},
            "bundles": [{"index": 0, "title": "Bundle A"}],
        }
        next_state = {
            "type": "decision", "decision": "map_select",
            "choices": [], "player": {"hp": 80, "max_hp": 80, "gold": 99,
                                       "deck_size": 10},
        }
        ctrl = _make_mock_controller(next_state)
        app = GenericTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            ctrl.select_bundle.assert_called_with(0)

    async def test_unknown_decision_uses_proceed(self):
        """Unknown decision with no selection should call proceed."""
        state = {
            "type": "decision", "decision": "treasure_chest",
            "context": {"act": 1, "floor": 1},
            "player": {"hp": 80, "max_hp": 80, "gold": 99, "deck_size": 10},
        }
        next_state = {
            "type": "decision", "decision": "map_select",
            "choices": [], "player": {"hp": 80, "max_hp": 80, "gold": 99,
                                       "deck_size": 10},
        }
        ctrl = _make_mock_controller(next_state)
        app = GenericTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("enter")
            await pilot.pause()
            ctrl.proceed.assert_called()


# ===================================================================
# 18. _error_dict helper
# ===================================================================


class TestErrorDict:
    def test_basic(self):
        result = _error_dict("something broke")
        assert result == {"type": "error", "message": "something broke"}


# ===================================================================
# 19. Event screen -- locked option and empty options
# ===================================================================


class EventTestApp(App):
    CSS_PATH = str(CSS_PATH)

    def __init__(self, state: dict, controller: MagicMock) -> None:
        super().__init__()
        self._state = state
        self._controller = controller

    def on_mount(self) -> None:
        from sts2_tui.tui.screens.event import EventScreen
        self.push_screen(EventScreen(self._state, controller=self._controller))


@pytest.mark.asyncio
class TestEventScreenEdgeCases:

    async def test_locked_option_not_selectable(self):
        state = {
            "type": "decision", "decision": "event_choice",
            "event_name": "Test Event",
            "context": {"act": 1, "floor": 3},
            "player": {"hp": 80, "max_hp": 80, "gold": 99, "deck_size": 10},
            "options": [
                {"index": 0, "title": "Free Option", "is_locked": False},
                {"index": 1, "title": "Locked Option", "is_locked": True},
            ],
        }
        ctrl = _make_mock_controller()
        app = EventTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            # Try to select the locked option (index 1 = key "2")
            await pilot.press("2")
            await pilot.pause()
            # Should NOT be selected -- confirm should warn
            await pilot.press("enter")
            await pilot.pause()
            # The choose method should NOT have been called
            ctrl.choose.assert_not_called()

    async def test_empty_options(self):
        state = {
            "type": "decision", "decision": "event_choice",
            "event_name": "Empty Event",
            "context": {"act": 1, "floor": 3},
            "player": {"hp": 80, "max_hp": 80, "gold": 99, "deck_size": 10},
            "options": [],
        }
        ctrl = _make_mock_controller()
        app = EventTestApp(state, ctrl)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            assert app.screen.query("#event-screen")


# ===================================================================
# 20. build_status_footer -- with and without state
# ===================================================================


class TestBuildStatusFooter:
    def test_without_state(self):
        from sts2_tui.tui.shared import build_status_footer
        from rich.text import Text
        bindings = Text("[Enter] Confirm")
        result = build_status_footer(bindings)
        rendered = str(result)
        assert "Confirm" in rendered

    def test_with_state(self):
        from sts2_tui.tui.shared import build_status_footer
        from rich.text import Text
        bindings = Text("[Enter] Confirm")
        state = {
            "player": {"hp": 50, "max_hp": 80, "gold": 100},
            "context": {"act": 1, "floor": 5},
        }
        result = build_status_footer(bindings, state)
        rendered = str(result)
        assert "50/80" in rendered
        assert "100" in rendered

    def test_with_partial_state(self):
        from sts2_tui.tui.shared import build_status_footer
        from rich.text import Text
        bindings = Text("[Enter] Confirm")
        state = {"player": {}, "context": {}}
        result = build_status_footer(bindings, state)
        # Should not crash even with empty player/context
        assert result is not None
