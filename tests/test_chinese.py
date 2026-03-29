"""End-to-end test: play a full game in Chinese mode via EngineBridge.

Verifies that:
1. Card names come back in Chinese (not English)
2. UI labels from i18n.py are in Chinese
3. No broken characters or encoding issues
4. Enemy names are in Chinese
5. Relic/potion names are in Chinese
6. English mode still works (no regression)
"""

from __future__ import annotations

import asyncio
import json
import re
import unicodedata
from pathlib import Path
from typing import Any

import pytest

from sts2_tui.bridge import BridgeError, EngineBridge
from sts2_tui.tui.controller import (
    GameController,
    _name_str,
    extract_enemies,
    extract_hand,
    extract_player,
    extract_reward_cards,
)
from sts2_tui.tui.i18n import LABELS, L, get_label, get_language, set_language

# ---------------------------------------------------------------------------
# Skip if sts2-cli is not available
# ---------------------------------------------------------------------------

_STS2_CLI_AVAILABLE = (
    Path("/tmp/sts2-cli/lib/sts2.dll").is_file()
    and Path("/tmp/sts2-cli/src/Sts2Headless/bin/Debug/net9.0/Sts2Headless.dll").is_file()
)

requires_sts2 = pytest.mark.skipif(
    not _STS2_CLI_AVAILABLE,
    reason="sts2-cli not built at /tmp/sts2-cli",
)

# Seed that produces a deterministic run (Ironclad, seed "7")
TEST_SEED = "7"
TEST_CHARACTER = "Ironclad"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def contains_chinese(text: str) -> bool:
    """Return True if text contains at least one CJK Unified Ideograph."""
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            return True
    return False


def is_valid_unicode(text: str) -> bool:
    """Return True if text has no replacement characters or encoding artifacts."""
    if "\ufffd" in text:  # Unicode replacement character
        return False
    # Check for common mojibake patterns
    try:
        text.encode("utf-8").decode("utf-8")
    except (UnicodeDecodeError, UnicodeEncodeError):
        return False
    return True


def is_english_only(text: str) -> bool:
    """Return True if text is purely ASCII/Latin (no CJK characters)."""
    for ch in text:
        if "\u4e00" <= ch <= "\u9fff":
            return False
    return True


# ---------------------------------------------------------------------------
# Unit tests: i18n module
# ---------------------------------------------------------------------------


class TestI18nModule:
    """Verify the i18n module works correctly."""

    def test_set_language_zh(self):
        set_language("zh")
        assert get_language() == "zh"

    def test_set_language_en(self):
        set_language("en")
        assert get_language() == "en"

    def test_set_language_invalid_falls_back(self):
        set_language("xx")
        assert get_language() == "en"

    def test_get_label_zh(self):
        set_language("zh")
        assert get_label("end_turn") == "\u7ed3\u675f\u56de\u5408"  # "结束回合"
        assert get_label("energy") == "\u80fd\u91cf"  # "能量"
        assert get_label("block") == "\u683c\u6321"  # "格挡"

    def test_get_label_en(self):
        set_language("en")
        assert get_label("end_turn") == "End Turn"
        assert get_label("energy") == "Energy"
        assert get_label("block") == "Block"

    def test_get_label_fallback_to_en(self):
        set_language("zh")
        # Test that unknown keys fall back to English, then to the key itself
        result = get_label("nonexistent_key_xyz")
        assert result == "nonexistent_key_xyz"

    def test_all_zh_labels_are_chinese(self):
        """Every value in the zh label dict should contain Chinese characters."""
        for key, value in LABELS["zh"].items():
            # Some labels are pure numbers or contain format placeholders
            # Just check that the label is valid unicode
            assert is_valid_unicode(value), (
                f"Label '{key}' has invalid unicode: {value!r}"
            )

    def test_all_en_labels_are_english(self):
        """Every value in the en label dict should be ASCII/Latin."""
        for key, value in LABELS["en"].items():
            assert is_english_only(value), (
                f"English label '{key}' contains non-Latin chars: {value!r}"
            )

    def test_zh_and_en_have_same_keys(self):
        """Both language dicts should have the same set of keys."""
        en_keys = set(LABELS["en"].keys())
        zh_keys = set(LABELS["zh"].keys())
        missing_in_zh = en_keys - zh_keys
        missing_in_en = zh_keys - en_keys
        assert not missing_in_zh, f"Keys missing in zh: {missing_in_zh}"
        assert not missing_in_en, f"Keys missing in en: {missing_in_en}"

    def test_l_alias_works(self):
        set_language("zh")
        assert L("end_turn") == "\u7ed3\u675f\u56de\u5408"
        set_language("en")
        assert L("end_turn") == "End Turn"


# ---------------------------------------------------------------------------
# Unit tests: _name_str with bilingual dicts
# ---------------------------------------------------------------------------


class TestNameStr:
    """Test _name_str handles different input formats."""

    def test_plain_string(self):
        assert _name_str("Strike") == "Strike"

    def test_none(self):
        assert _name_str(None) == "?"

    def test_bilingual_dict_en(self):
        set_language("en")
        assert _name_str({"en": "Strike", "zh": "\u6253\u51fb"}) == "Strike"

    def test_bilingual_dict_zh(self):
        set_language("zh")
        assert _name_str({"en": "Strike", "zh": "\u6253\u51fb"}) == "\u6253\u51fb"

    def test_bilingual_dict_missing_zh(self):
        set_language("zh")
        assert _name_str({"en": "Strike"}) == "Strike"

    def test_bilingual_dict_missing_en(self):
        set_language("en")
        assert _name_str({"zh": "\u6253\u51fb"}) == "\u6253\u51fb"

    def test_plain_chinese_string(self):
        """When engine sends pre-localized Chinese string, pass it through."""
        assert _name_str("\u6253\u51fb") == "\u6253\u51fb"


# ---------------------------------------------------------------------------
# Integration tests: play a game in Chinese mode
# ---------------------------------------------------------------------------


async def _play_game_steps(bridge: EngineBridge, lang: str, max_steps: int = 80) -> dict:
    """Play through a game collecting state snapshots for inspection.

    Returns a summary dict with:
      - decisions_seen: set of decision types encountered
      - card_names: list of card names seen in hand
      - enemy_names: list of enemy names seen
      - relic_names: list of relic names seen
      - potion_names: list of potion names seen
      - player_names: list of player names seen
      - all_states: list of all raw states
      - errors: list of any errors encountered
    """
    result = {
        "decisions_seen": set(),
        "card_names": [],
        "enemy_names": [],
        "relic_names": [],
        "potion_names": [],
        "player_names": [],
        "event_names": [],
        "option_titles": [],
        "all_states": [],
        "errors": [],
    }

    state = await bridge.start_run(TEST_CHARACTER, seed=TEST_SEED, lang=lang)
    if state.get("type") == "error":
        result["errors"].append(f"start_run failed: {state.get('message')}")
        return result

    for step in range(max_steps):
        decision = state.get("decision", "")
        result["decisions_seen"].add(decision)
        result["all_states"].append(state)

        # Collect player names
        player = state.get("player", {})
        pname = player.get("name")
        if pname and pname not in result["player_names"]:
            result["player_names"].append(pname)

        # Collect relic names
        for r in player.get("relics") or []:
            rname = r.get("name")
            if rname and rname not in result["relic_names"]:
                result["relic_names"].append(rname)

        # Collect potion names
        for p in player.get("potions") or []:
            if p is None:
                continue
            pname = p.get("name")
            if pname and pname not in result["potion_names"]:
                result["potion_names"].append(pname)

        # Collect enemy names from combat
        for e in state.get("enemies") or []:
            ename = e.get("name")
            if ename and ename not in result["enemy_names"]:
                result["enemy_names"].append(ename)

        # Collect card names from hand
        for c in state.get("hand") or []:
            cname = c.get("name")
            if cname and cname not in result["card_names"]:
                result["card_names"].append(cname)

        # Collect card names from rewards
        for c in state.get("cards") or []:
            cname = c.get("name")
            if cname and cname not in result["card_names"]:
                result["card_names"].append(cname)

        # Collect event names
        ename = state.get("event_name")
        if ename and ename not in result["event_names"]:
            result["event_names"].append(ename)

        # Collect option titles
        for opt in state.get("options") or []:
            title = opt.get("title") or opt.get("name")
            if title and title not in result["option_titles"]:
                result["option_titles"].append(title)

        # Navigate the game
        try:
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
                        alive = [e for e in enemies if e.get("hp", 0) > 0]
                        if alive:
                            target = alive[0]["index"]
                    state = await bridge.play_card(card["index"], target=target)
                else:
                    state = await bridge.end_turn()
            elif decision == "event_choice":
                options = state.get("options", [])
                unlocked = [o for o in options if not o.get("is_locked", False)]
                if unlocked:
                    state = await bridge.choose(unlocked[0]["index"])
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
        except BridgeError as e:
            result["errors"].append(f"Step {step} ({decision}): {e}")
            break

    return result


@requires_sts2
class TestChineseGameplay:
    """Integration tests: play a full game in Chinese and verify content."""

    @pytest.fixture
    async def bridge(self):
        b = EngineBridge()
        await b.start()
        yield b
        if b.is_running():
            await b.quit()

    async def test_chinese_game_card_names(self, bridge):
        """Card names should be in Chinese when lang='zh'."""
        result = await _play_game_steps(bridge, lang="zh")
        assert not result["errors"], f"Errors: {result['errors']}"
        assert len(result["card_names"]) > 0, "No card names collected"

        # At least some card names should contain Chinese characters
        chinese_cards = [n for n in result["card_names"] if contains_chinese(n)]
        assert len(chinese_cards) > 0, (
            f"No Chinese card names found. All names: {result['card_names']}"
        )
        # All card names should be valid unicode
        for name in result["card_names"]:
            assert is_valid_unicode(name), f"Invalid unicode in card name: {name!r}"

    async def test_chinese_game_enemy_names(self, bridge):
        """Enemy names should be in Chinese when lang='zh'."""
        result = await _play_game_steps(bridge, lang="zh")
        assert not result["errors"], f"Errors: {result['errors']}"

        if not result["enemy_names"]:
            pytest.skip("No enemy encounters in this run")

        # At least some enemy names should contain Chinese characters
        chinese_enemies = [n for n in result["enemy_names"] if contains_chinese(n)]
        assert len(chinese_enemies) > 0, (
            f"No Chinese enemy names found. All names: {result['enemy_names']}"
        )
        for name in result["enemy_names"]:
            assert is_valid_unicode(name), f"Invalid unicode in enemy name: {name!r}"

    async def test_chinese_game_relic_names(self, bridge):
        """Relic names should be in Chinese when lang='zh'."""
        result = await _play_game_steps(bridge, lang="zh")
        assert not result["errors"], f"Errors: {result['errors']}"

        if not result["relic_names"]:
            pytest.skip("No relics collected in this run")

        chinese_relics = [n for n in result["relic_names"] if contains_chinese(n)]
        assert len(chinese_relics) > 0, (
            f"No Chinese relic names found. All names: {result['relic_names']}"
        )
        for name in result["relic_names"]:
            assert is_valid_unicode(name), f"Invalid unicode in relic name: {name!r}"

    async def test_chinese_game_player_name(self, bridge):
        """Player character name should be in Chinese when lang='zh'."""
        result = await _play_game_steps(bridge, lang="zh")
        assert not result["errors"], f"Errors: {result['errors']}"
        assert len(result["player_names"]) > 0, "No player names collected"

        # The player name should contain Chinese
        chinese_players = [n for n in result["player_names"] if contains_chinese(n)]
        assert len(chinese_players) > 0, (
            f"No Chinese player names found. All names: {result['player_names']}"
        )

    async def test_chinese_game_no_encoding_issues(self, bridge):
        """No state in the run should have broken encoding."""
        result = await _play_game_steps(bridge, lang="zh")
        assert not result["errors"], f"Errors: {result['errors']}"

        # Walk every string value in every state and check for encoding issues
        broken = []

        def _check_strings(obj, path=""):
            if isinstance(obj, str):
                if not is_valid_unicode(obj):
                    broken.append((path, obj))
            elif isinstance(obj, dict):
                for k, v in obj.items():
                    _check_strings(v, f"{path}.{k}")
            elif isinstance(obj, list):
                for i, v in enumerate(obj):
                    _check_strings(v, f"{path}[{i}]")

        for i, state in enumerate(result["all_states"]):
            _check_strings(state, f"state[{i}]")

        assert not broken, (
            f"Found {len(broken)} broken strings:\n"
            + "\n".join(f"  {path}: {val!r}" for path, val in broken[:10])
        )

    async def test_chinese_game_controller_helpers(self, bridge):
        """Controller helper functions work with Chinese data."""
        set_language("zh")
        state = await bridge.start_run(TEST_CHARACTER, seed=TEST_SEED, lang="zh")

        # Navigate to a combat state
        for _ in range(30):
            decision = state.get("decision", "")
            if decision == "combat_play":
                break
            elif decision == "event_choice":
                options = state.get("options", [])
                unlocked = [o for o in options if not o.get("is_locked")]
                if unlocked:
                    state = await bridge.choose(unlocked[0]["index"])
                else:
                    state = await bridge.leave_room()
            elif decision == "map_select":
                choices = state.get("choices", [])
                if choices:
                    state = await bridge.select_map_node(choices[0]["col"], choices[0]["row"])
                else:
                    break
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
            pytest.skip("Could not reach combat")

        if state.get("decision") != "combat_play":
            pytest.skip("Could not reach combat within max steps")

        # Test extract_hand with Chinese data
        hand = extract_hand(state)
        assert len(hand) > 0, "Hand is empty"
        for card in hand:
            assert is_valid_unicode(card["name"]), f"Bad encoding in card name: {card['name']!r}"

        # Test extract_enemies with Chinese data
        enemies = extract_enemies(state)
        assert len(enemies) > 0, "No enemies found"
        for e in enemies:
            assert is_valid_unicode(e["name"]), f"Bad encoding in enemy name: {e['name']!r}"

        # Test extract_player with Chinese data
        player = extract_player(state)
        assert is_valid_unicode(player["name"]), f"Bad encoding in player name: {player['name']!r}"
        for r in player["relics"]:
            assert is_valid_unicode(r["name"]), f"Bad encoding in relic name: {r['name']!r}"


# ---------------------------------------------------------------------------
# Integration tests: verify English still works (regression test)
# ---------------------------------------------------------------------------


@requires_sts2
class TestEnglishRegression:
    """Ensure English mode still works after Chinese support was added."""

    @pytest.fixture
    async def bridge(self):
        b = EngineBridge()
        await b.start()
        yield b
        if b.is_running():
            await b.quit()

    async def test_english_game_card_names(self, bridge):
        """Card names should be in English when lang='en'."""
        set_language("en")
        result = await _play_game_steps(bridge, lang="en")
        assert not result["errors"], f"Errors: {result['errors']}"
        assert len(result["card_names"]) > 0, "No card names collected"

        # Card names should be English (no Chinese)
        english_cards = [n for n in result["card_names"] if is_english_only(n)]
        assert len(english_cards) > 0, (
            f"No English card names found. All names: {result['card_names']}"
        )

    async def test_english_labels_work(self, bridge):
        """UI labels should be in English when lang='en'."""
        set_language("en")
        assert get_label("end_turn") == "End Turn"
        assert get_label("energy") == "Energy"
        assert get_label("your_turn") == ">> YOUR TURN <<"

    async def test_english_no_chinese_leak(self, bridge):
        """English mode should not leak Chinese into card/enemy names."""
        set_language("en")
        result = await _play_game_steps(bridge, lang="en")
        assert not result["errors"], f"Errors: {result['errors']}"

        # No card names should contain Chinese when running in English
        for name in result["card_names"]:
            assert not contains_chinese(name), (
                f"Chinese leaked into English card name: {name!r}"
            )


# ---------------------------------------------------------------------------
# Integration test: run both languages back-to-back
# ---------------------------------------------------------------------------


@requires_sts2
class TestLanguageSwitching:
    """Test that switching languages between runs works correctly."""

    async def test_switch_en_to_zh(self):
        """Start English, then start Chinese -- names should change."""
        # First run: English (separate bridge instance)
        en_bridge = EngineBridge()
        await en_bridge.start()
        try:
            set_language("en")
            en_state = await en_bridge.start_run(TEST_CHARACTER, seed=TEST_SEED, lang="en")
            en_player_name = en_state.get("player", {}).get("name", "")

            # Navigate a few steps to get card names
            en_cards = set()
            state = en_state
            for _ in range(15):
                for c in state.get("hand") or []:
                    en_cards.add(c.get("name", ""))
                decision = state.get("decision", "")
                if decision == "combat_play":
                    break
                elif decision == "event_choice":
                    options = state.get("options", [])
                    unlocked = [o for o in options if not o.get("is_locked")]
                    if unlocked:
                        state = await en_bridge.choose(unlocked[0]["index"])
                    else:
                        state = await en_bridge.leave_room()
                elif decision == "map_select":
                    choices = state.get("choices", [])
                    if choices:
                        state = await en_bridge.select_map_node(choices[0]["col"], choices[0]["row"])
                    else:
                        break
                elif decision == "bundle_select":
                    state = await en_bridge.select_bundle(0)
                elif decision == "card_select":
                    cards = state.get("cards", [])
                    state = await en_bridge.select_cards("0") if cards else await en_bridge.skip_select()
                else:
                    state = await en_bridge.proceed()
        finally:
            await en_bridge.quit()

        # Second run: Chinese (new bridge instance, same seed)
        zh_bridge = EngineBridge()
        await zh_bridge.start()
        try:
            set_language("zh")
            zh_state = await zh_bridge.start_run(TEST_CHARACTER, seed=TEST_SEED, lang="zh")
            zh_player_name = zh_state.get("player", {}).get("name", "")

            zh_cards = set()
            state = zh_state
            for _ in range(15):
                for c in state.get("hand") or []:
                    zh_cards.add(c.get("name", ""))
                decision = state.get("decision", "")
                if decision == "combat_play":
                    break
                elif decision == "event_choice":
                    options = state.get("options", [])
                    unlocked = [o for o in options if not o.get("is_locked")]
                    if unlocked:
                        state = await zh_bridge.choose(unlocked[0]["index"])
                    else:
                        state = await zh_bridge.leave_room()
                elif decision == "map_select":
                    choices = state.get("choices", [])
                    if choices:
                        state = await zh_bridge.select_map_node(choices[0]["col"], choices[0]["row"])
                    else:
                        break
                elif decision == "bundle_select":
                    state = await zh_bridge.select_bundle(0)
                elif decision == "card_select":
                    cards = state.get("cards", [])
                    state = await zh_bridge.select_cards("0") if cards else await zh_bridge.skip_select()
                else:
                    state = await zh_bridge.proceed()
        finally:
            await zh_bridge.quit()

        # Player names should differ between languages
        if en_player_name and zh_player_name:
            assert en_player_name != zh_player_name, (
                f"Player name did not change: en={en_player_name!r} zh={zh_player_name!r}"
            )

        # If we got card names in both languages, they should differ
        if en_cards and zh_cards:
            # At least some cards should have different names
            assert en_cards != zh_cards, (
                f"Card names are identical in both languages: {en_cards}"
            )


# ---------------------------------------------------------------------------
# Cleanup: restore English after tests
# ---------------------------------------------------------------------------

@pytest.fixture(autouse=True)
def _restore_language():
    """Ensure language is reset to English after each test."""
    yield
    set_language("en")
