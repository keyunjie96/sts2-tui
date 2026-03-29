#!/usr/bin/env python3
"""
RL Data Collector — plays parallel sts2-cli games and saves training data.

Runs games using the smart bot strategy for action selection, encodes each
(state, action, reward, next_state) transition as numeric arrays, and saves
them as .npy files for RL training.

Usage:
    python tools/rl_data_collector.py                # 10 sequential games (test)
    python tools/rl_data_collector.py --games 100 --workers 4  # parallel
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import numpy as np

# --- Path setup ---
SLS_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SLS_ROOT / "src"))

from sts2_tui.bridge import EngineBridge, BridgeError

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Card vocabulary — build a hash map for card_id encoding
# ---------------------------------------------------------------------------

_CARD_DATA: list[dict] = []
_CARD_ID_TO_IDX: dict[str, int] = {}


def _load_card_vocab() -> None:
    global _CARD_DATA, _CARD_ID_TO_IDX
    cards_path = SLS_ROOT / "game_data" / "cards.json"
    if cards_path.is_file():
        _CARD_DATA = json.loads(cards_path.read_text())
        for i, card in enumerate(_CARD_DATA):
            _CARD_ID_TO_IDX[card["id"]] = i
    else:
        log.warning("cards.json not found at %s", cards_path)


_load_card_vocab()
CARD_VOCAB_SIZE = max(len(_CARD_DATA), 1)

# Top 16 power/buff IDs we track (same order for player and enemy)
TRACKED_POWERS = [
    "strength", "dexterity", "vulnerable", "weak", "frail",
    "vigor", "metallicize", "plated_armor", "thorns", "barricade",
    "demon_form", "feel_no_pain", "corruption", "juggernaut",
    "poison", "regen",
]

# Top 10 relics to track as one-hot
TRACKED_RELICS = [
    "burning_blood", "vajra", "bag_of_preparation", "ring_of_the_snake",
    "cracked_core", "anchor", "lantern", "horn_cleat",
    "blood_vial", "happy_flower",
]

# Decision type to one-hot index
DECISION_TYPES = [
    "combat_play", "map_select", "card_reward", "rest_site",
    "shop", "event_choice", "card_select", "bundle_select",
]

# Character name to one-hot index
CHARACTERS = ["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"]


# ============================================================================
# State Encoder  (state dict -> 512-float numpy vector)
# ============================================================================

def _clip01(val: float) -> float:
    return max(0.0, min(1.0, val))


def _clip11(val: float) -> float:
    return max(-1.0, min(1.0, val))


def _get_power_amount(powers: list[dict] | None, power_id: str) -> float:
    """Find a power by id in a powers list and return its amount."""
    if not powers:
        return 0.0
    for p in powers:
        pid = (p.get("id") or p.get("power_id") or "").lower().replace(" ", "_")
        if pid == power_id:
            return float(p.get("amount", 0))
    return 0.0


def _card_name_to_id(card: dict) -> str:
    """Extract a usable card identifier from a card dict."""
    # Try various fields the engine may use
    for key in ("id", "card_id", "cardId"):
        if key in card:
            return str(card[key]).lower()
    name = card.get("name", "")
    if isinstance(name, dict):
        name = name.get("en", "") or name.get("zh", "") or str(name)
    return name.lower().replace(" ", "_")


def _hash_card_id(card_id: str) -> float:
    """Map card_id to [0, 1] deterministically."""
    idx = _CARD_ID_TO_IDX.get(card_id, -1)
    if idx >= 0:
        return idx / CARD_VOCAB_SIZE
    # Fallback: hash
    h = int(hashlib.md5(card_id.encode()).hexdigest()[:8], 16)
    return (h % CARD_VOCAB_SIZE) / CARD_VOCAB_SIZE


def encode_state(state: dict) -> np.ndarray:
    """Convert sts2-cli game state to 512-float feature vector.

    Layout:
        [0..63]    Player features (64 floats)
        [64..223]  Hand features   (160 floats = 10 cards x 16)
        [224..415] Enemy features  (192 floats = 4 enemies x 48)
        [416..463] Context features (48 floats)
        [464..511] Global features  (48 floats)
    """
    features = np.zeros(512, dtype=np.float32)

    player = state.get("player") or {}
    hand = state.get("hand") or []
    enemies = state.get("enemies") or []
    decision = state.get("decision", "")

    # === Player features (64 floats) [0..63] ===
    hp = float(player.get("hp", 0))
    max_hp = float(player.get("max_hp", 1))
    features[0] = _clip01(hp / max(max_hp, 1))
    features[1] = _clip01(hp / 100.0)
    features[2] = _clip01(max_hp / 100.0)
    features[3] = _clip01(float(player.get("block", 0)) / 50.0)
    features[4] = _clip01(float(state.get("energy", 0)) / 5.0)
    features[5] = _clip01(float(state.get("max_energy", 3)) / 5.0)
    features[6] = _clip01(float(player.get("gold", 0)) / 500.0)
    features[7] = _clip01(float(player.get("deck_size", 0)) / 40.0)
    features[8] = _clip01(float(state.get("draw_pile_count", 0)) / 30.0)
    features[9] = _clip01(float(state.get("discard_pile_count", 0)) / 30.0)
    features[10] = _clip01(float(state.get("exhaust_pile_count", 0)) / 20.0)
    features[11] = _clip01(float(state.get("round", 0)) / 20.0)
    features[12] = _clip01(float(state.get("act", 1)) / 3.0)
    features[13] = _clip01(float(state.get("floor", 0)) / 20.0)

    # Player powers [14..29]
    player_powers = player.get("powers") or []
    for i, pid in enumerate(TRACKED_POWERS):
        features[14 + i] = _clip11(_get_power_amount(player_powers, pid) / 10.0)

    # Deck composition [30..39] — requires deck info which may not always be present
    # We fill what we can; zeros are fine for missing data
    deck_size = float(player.get("deck_size", 0))
    if deck_size > 0:
        features[30] = 0.5  # placeholder for % attack (not always in state)
        features[31] = 0.5  # placeholder for % skill
    # features[32..39] remain zero (reserved/unavailable in live state)

    # Relic presence [40..49]
    relic_names = set()
    for r in (player.get("relics") or []):
        rid = (r.get("id") or r.get("relic_id") or "").lower().replace(" ", "_")
        relic_names.add(rid)
    for i, rid in enumerate(TRACKED_RELICS):
        features[40 + i] = 1.0 if rid in relic_names else 0.0

    # Potion slots [50..53]
    potions = player.get("potions") or []
    for i in range(min(4, len(potions))):
        pot = potions[i]
        if pot and not pot.get("is_empty", True):
            # Simple encoding: non-empty = 0.5 (we don't have a full potion vocab)
            features[50 + i] = 0.5
    # [54..63] reserved, stay zero

    # === Hand features (160 floats = 10 cards x 16) [64..223] ===
    for i in range(min(10, len(hand))):
        card = hand[i]
        base = 64 + i * 16
        card_id = _card_name_to_id(card)
        stats = card.get("stats") or {}

        features[base + 0] = _hash_card_id(card_id)
        features[base + 1] = _clip01(float(card.get("cost", 0)) / 5.0)
        ctype = (card.get("type") or "").lower()
        features[base + 2] = 1.0 if ctype == "attack" else 0.0
        features[base + 3] = 1.0 if ctype == "skill" else 0.0
        features[base + 4] = 1.0 if ctype == "power" else 0.0
        features[base + 5] = 1.0 if ctype in ("curse", "status") else 0.0
        features[base + 6] = 1.0 if card.get("can_play", False) else 0.0
        features[base + 7] = _clip01(float(stats.get("damage", 0)) / 30.0)
        features[base + 8] = _clip01(float(stats.get("block", 0)) / 30.0)
        features[base + 9] = 1.0 if card.get("target_type") == "AnyEnemy" else 0.0
        features[base + 10] = 1.0 if card.get("cost", 0) == -1 else 0.0  # X-cost
        # [base+11..base+15] reserved, stay zero

    # === Enemy features (192 floats = 4 enemies x 48) [224..415] ===
    for i in range(min(4, len(enemies))):
        enemy = enemies[i]
        base = 224 + i * 48

        e_hp = float(enemy.get("hp", 0))
        e_max = float(enemy.get("max_hp", 1))
        features[base + 0] = 1.0  # is_alive (enemy is in list, so alive)
        features[base + 1] = _clip01(e_hp / max(e_max, 1))
        features[base + 2] = _clip01(e_hp / 300.0)
        features[base + 3] = _clip01(e_max / 300.0)
        features[base + 4] = _clip01(float(enemy.get("block", 0)) / 50.0)

        # Intent parsing
        intents = enemy.get("intents") or []
        total_intent_dmg = 0.0
        for intent in intents:
            itype = intent.get("type", "")
            dmg = float(intent.get("damage", 0))
            hits = float(intent.get("hits", 1) or 1)
            if itype in ("Attack", "DeathBlow"):
                features[base + 5] = 1.0  # intent_is_attack
                features[base + 6] = _clip01(dmg / 50.0)
                features[base + 7] = _clip01(hits / 5.0)
                total_intent_dmg += dmg * hits
            elif itype in ("Defend", "Block"):
                features[base + 8] = 1.0  # intent_is_defend
            elif itype in ("Buff", "Strategic"):
                features[base + 9] = 1.0  # intent_is_buff
            elif itype in ("Debuff",):
                features[base + 10] = 1.0  # intent_is_debuff
        features[base + 11] = _clip01(total_intent_dmg / 80.0)

        # Enemy powers [base+12..base+27]
        enemy_powers = enemy.get("powers") or []
        for j, pid in enumerate(TRACKED_POWERS):
            features[base + 12 + j] = _clip11(
                _get_power_amount(enemy_powers, pid) / 10.0
            )
        # [base+28..base+47] reserved

    # === Decision context features (48 floats) [416..463] ===
    # One-hot decision type [416..423]
    for i, dt in enumerate(DECISION_TYPES):
        if decision == dt:
            features[416 + i] = 1.0

    # Map choice types [424..430]
    if decision == "map_select":
        MAP_TYPES = ["Monster", "Elite", "RestSite", "Shop", "Event", "Treasure", "Boss"]
        for choice in state.get("choices", [])[:7]:
            ctype = choice.get("type", "")
            if ctype in MAP_TYPES:
                features[424 + MAP_TYPES.index(ctype)] = 1.0

    # Card reward rarities [431..433]
    if decision == "card_reward":
        for i, card in enumerate(state.get("cards", [])[:3]):
            rarity = (card.get("rarity", "Common") or "Common").lower()
            if rarity == "common":
                features[431] = 1.0
            elif rarity == "uncommon":
                features[432] = 1.0
            elif rarity == "rare":
                features[433] = 1.0

    # Rest options [434..435]
    if decision == "rest_site":
        for opt in state.get("options", []):
            oid = opt.get("option_id", "")
            if oid == "HEAL":
                features[434] = 1.0
            elif oid == "SMITH":
                features[435] = 1.0
    # [436..463] reserved

    # === Global features (48 floats) [464..511] ===
    # Character one-hot [464..468]
    char_name = state.get("character", "") or ""
    for i, c in enumerate(CHARACTERS):
        if char_name.lower() == c.lower():
            features[464 + i] = 1.0

    # Ascension [469]
    features[469] = _clip01(float(state.get("ascension", 0)) / 20.0)

    # Room type encoded [470]
    room_type = state.get("room_type", "")
    room_map = {"Monster": 0.2, "Elite": 0.4, "Boss": 0.6, "Event": 0.8}
    features[470] = room_map.get(room_type, 0.0)
    # [471..511] reserved

    return features


# ============================================================================
# Action Encoder / Decoder
# ============================================================================

def encode_action(action: dict, state: dict) -> int:
    """Convert a bridge action command to a discrete action index (0-63).

    Action space:
        0-9:   play_card(i) no target
        10-19: play_card(i, target=0)
        20-29: play_card(i, target=1)
        30-39: play_card(i, target=2)
        40-43: play_card(i, target=3) (cards 0-3 only)
        44:    end_turn
        45-48: use_potion(i)
        49:    reserved
        50-56: select_map_node(choice 0-6)
        57-59: select_card_reward(0-2)
        60:    skip_card_reward
        61:    rest_heal
        62:    rest_smith
        63:    leave_room / proceed
    """
    act_name = action.get("action", "")
    args = action.get("args", {})

    if act_name == "play_card":
        card_idx = args.get("card_index", 0)
        target_idx = args.get("target_index", None)
        if target_idx is not None:
            # targeted card
            if target_idx <= 2:
                return 10 + target_idx * 10 + min(card_idx, 9)
            elif target_idx == 3:
                return 40 + min(card_idx, 3)
        else:
            return min(card_idx, 9)

    elif act_name == "end_turn":
        return 44

    elif act_name == "use_potion":
        pidx = args.get("potion_index", 0)
        return 45 + min(pidx, 3)

    elif act_name == "select_map_node":
        # Map node selection — find the choice index by matching col/row
        col = args.get("col")
        row = args.get("row")
        choices = state.get("choices", [])
        for i, choice in enumerate(choices[:7]):
            if choice.get("col") == col and choice.get("row") == row:
                return 50 + i
        return 50  # default to first choice

    elif act_name == "select_card_reward":
        cidx = args.get("card_index", 0)
        return 57 + min(cidx, 2)

    elif act_name == "skip_card_reward":
        return 60

    elif act_name == "choose_option":
        # Could be rest site or event
        opt_idx = args.get("option_index", 0)
        decision = state.get("decision", "")
        if decision == "rest_site":
            options = state.get("options", [])
            if opt_idx < len(options):
                oid = options[opt_idx].get("option_id", "")
                if oid == "HEAL":
                    return 61
                elif oid == "SMITH":
                    return 62
            return 61  # default to heal
        # Event or other — treat as proceed
        return 63

    elif act_name in ("leave_room", "proceed"):
        return 63

    elif act_name == "select_bundle":
        return 63  # treat as proceed

    elif act_name in ("select_cards", "skip_select"):
        return 63

    return 63  # fallback


def decode_action(action_idx: int, state: dict) -> dict:
    """Convert action index back to a bridge command dict."""
    if action_idx <= 9:
        # play_card(i) no target
        return {
            "cmd": "action", "action": "play_card",
            "args": {"card_index": action_idx}
        }
    elif action_idx <= 39:
        # play_card(i, target=t)
        target = (action_idx - 10) // 10
        card = (action_idx - 10) % 10
        return {
            "cmd": "action", "action": "play_card",
            "args": {"card_index": card, "target_index": target}
        }
    elif action_idx <= 43:
        # play_card(i, target=3) for cards 0-3
        card = action_idx - 40
        return {
            "cmd": "action", "action": "play_card",
            "args": {"card_index": card, "target_index": 3}
        }
    elif action_idx == 44:
        return {"cmd": "action", "action": "end_turn"}
    elif action_idx <= 48:
        pidx = action_idx - 45
        return {
            "cmd": "action", "action": "use_potion",
            "args": {"potion_index": pidx}
        }
    elif action_idx <= 56:
        choice_i = action_idx - 50
        choices = state.get("choices", [])
        if choice_i < len(choices):
            c = choices[choice_i]
            return {
                "cmd": "action", "action": "select_map_node",
                "args": {"col": c["col"], "row": c["row"]}
            }
        # Fallback to first choice
        if choices:
            c = choices[0]
            return {
                "cmd": "action", "action": "select_map_node",
                "args": {"col": c["col"], "row": c["row"]}
            }
        return {"cmd": "action", "action": "proceed"}
    elif action_idx <= 59:
        cidx = action_idx - 57
        return {
            "cmd": "action", "action": "select_card_reward",
            "args": {"card_index": cidx}
        }
    elif action_idx == 60:
        return {"cmd": "action", "action": "skip_card_reward"}
    elif action_idx == 61:
        # rest_heal — find HEAL option index
        for opt in state.get("options", []):
            if opt.get("option_id") == "HEAL":
                return {
                    "cmd": "action", "action": "choose_option",
                    "args": {"option_index": opt["index"]}
                }
        # Fallback: first enabled option
        for opt in state.get("options", []):
            if opt.get("is_enabled", True):
                return {
                    "cmd": "action", "action": "choose_option",
                    "args": {"option_index": opt["index"]}
                }
        return {"cmd": "action", "action": "proceed"}
    elif action_idx == 62:
        # rest_smith
        for opt in state.get("options", []):
            if opt.get("option_id") == "SMITH":
                return {
                    "cmd": "action", "action": "choose_option",
                    "args": {"option_index": opt["index"]}
                }
        for opt in state.get("options", []):
            if opt.get("is_enabled", True):
                return {
                    "cmd": "action", "action": "choose_option",
                    "args": {"option_index": opt["index"]}
                }
        return {"cmd": "action", "action": "proceed"}
    else:  # 63
        return {"cmd": "action", "action": "proceed"}


def get_valid_actions(state: dict) -> list[int]:
    """Return list of valid action indices for the current state."""
    decision = state.get("decision", "")
    valid = []

    if decision == "combat_play":
        hand = state.get("hand", [])
        enemies = state.get("enemies", [])
        energy = state.get("energy", 0)
        alive_enemies = [e for e in enemies if e.get("hp", 0) > 0]
        alive_indices = {e.get("index", i) for i, e in enumerate(alive_enemies)}

        for i, card in enumerate(hand[:10]):
            if not card.get("can_play", False):
                continue
            cost = card.get("cost", 99)
            if cost > energy and cost != -1:  # -1 = X-cost (always playable)
                continue

            needs_target = card.get("target_type") == "AnyEnemy"
            if needs_target:
                # Add targeted actions for each alive enemy
                for ei in range(min(4, len(enemies))):
                    if ei in alive_indices:
                        if ei <= 2:
                            valid.append(10 + ei * 10 + i)
                        elif ei == 3 and i <= 3:
                            valid.append(40 + i)
            else:
                # Self-target / AoE
                valid.append(i)

        # end_turn is always valid in combat
        valid.append(44)

        # Potions
        player = state.get("player") or {}
        potions = player.get("potions") or []
        for pot in potions:
            if pot and not pot.get("is_empty", True):
                pidx = pot.get("index", 0)
                if pidx <= 3:
                    valid.append(45 + pidx)

    elif decision == "map_select":
        choices = state.get("choices", [])
        for i in range(min(7, len(choices))):
            valid.append(50 + i)

    elif decision == "card_reward":
        cards = state.get("cards", [])
        for i in range(min(3, len(cards))):
            valid.append(57 + i)
        valid.append(60)  # skip

    elif decision == "rest_site":
        for opt in state.get("options", []):
            if opt.get("is_enabled", True):
                oid = opt.get("option_id", "")
                if oid == "HEAL":
                    valid.append(61)
                elif oid == "SMITH":
                    valid.append(62)
        if not valid:
            valid.append(63)  # proceed/leave

    elif decision == "shop":
        valid.append(63)  # leave_room

    elif decision == "event_choice":
        valid.append(63)  # simplified: proceed

    elif decision in ("bundle_select", "card_select", "unknown"):
        valid.append(63)

    else:
        valid.append(63)

    return valid if valid else [63]


# ============================================================================
# Reward computation
# ============================================================================

def compute_reward(prev_state: dict, action: dict, next_state: dict) -> float:
    """Compute per-step reward based on state transition.

    Reward shaping from RL_PLAN.md Section 6:
        HP gained:    +0.5 per HP
        HP lost:      -0.2 per HP
        Enemy killed: +2.0
        Floor advance: +0.5
        Victory:      +100
        Defeat:        floor_reached * 3
        Stuck/error:  -5.0
    """
    reward = 0.0

    # Terminal rewards
    if next_state.get("decision") == "game_over":
        if next_state.get("victory", False):
            reward += 100.0
        else:
            floor = next_state.get("floor", 0) or 0
            reward += float(floor) * 3.0
        return reward

    # Error penalty
    if next_state.get("type") == "error":
        return -5.0

    prev_player = prev_state.get("player", {})
    next_player = next_state.get("player", {})
    prev_hp = float(prev_player.get("hp", 0))
    next_hp = float(next_player.get("hp", 0))

    # HP change
    hp_diff = next_hp - prev_hp
    if hp_diff > 0:
        reward += 0.5 * hp_diff  # healing
    elif hp_diff < 0:
        reward += 0.2 * hp_diff  # damage taken (negative)

    # Enemy killed
    prev_enemies = prev_state.get("enemies", [])
    next_enemies = next_state.get("enemies", [])
    prev_alive = sum(1 for e in prev_enemies if e.get("hp", 0) > 0)
    next_alive = sum(1 for e in next_enemies if e.get("hp", 0) > 0)
    killed = prev_alive - next_alive
    if killed > 0:
        reward += 2.0 * killed

    # Floor advance
    prev_floor = prev_state.get("floor", 0) or 0
    next_floor = next_state.get("floor", 0) or 0
    if next_floor > prev_floor:
        reward += 0.5

    return reward


# ============================================================================
# Smart bot strategy (adapted from smart_bot.py for action selection)
# ============================================================================

# Import the character want lists from smart_bot module
# We inline the key helpers to avoid import issues

def _calc_incoming_damage(enemies: list[dict]) -> float:
    total = 0.0
    for e in enemies:
        for intent in (e.get("intents") or []):
            itype = intent.get("type", "")
            dmg = intent.get("damage", 0)
            hits = intent.get("hits", 1) or 1
            if itype in ("Attack", "DeathBlow") and dmg:
                total += float(dmg) * float(hits)
    return total


def _find_lowest_hp_enemy_idx(enemies: list[dict]) -> int:
    if not enemies:
        return 0
    alive = [e for e in enemies if e.get("hp", 0) > 0]
    if not alive:
        return 0
    return min(alive, key=lambda e: e.get("hp", 9999)).get("index", 0)


def smart_bot_choose_action(state: dict, character: str = "Ironclad") -> dict:
    """Choose an action using the smart bot heuristics, returning a command dict."""
    decision = state.get("decision", "")

    if decision == "combat_play":
        return _smart_combat_action(state, character)
    elif decision == "map_select":
        return _smart_map_action(state)
    elif decision == "card_reward":
        return _smart_card_reward_action(state, character)
    elif decision == "rest_site":
        return _smart_rest_action(state)
    elif decision == "event_choice":
        return _smart_event_action(state)
    elif decision == "shop":
        return {"cmd": "action", "action": "leave_room"}
    elif decision == "bundle_select":
        return {"cmd": "action", "action": "select_bundle",
                "args": {"bundle_index": 0}}
    elif decision == "card_select":
        cards = state.get("cards", [])
        if cards:
            return {"cmd": "action", "action": "select_cards",
                    "args": {"indices": "0"}}
        return {"cmd": "action", "action": "skip_select"}
    else:
        return {"cmd": "action", "action": "proceed"}


def _smart_combat_action(state: dict, character: str) -> dict:
    hand = state.get("hand", [])
    energy = state.get("energy", 0)
    enemies = state.get("enemies", [])
    player = state.get("player", {})
    incoming = _calc_incoming_damage(enemies)
    hp = player.get("hp", 0)
    max_hp = player.get("max_hp", 1)
    hp_ratio = hp / max(max_hp, 1)

    # Check potions
    if hp_ratio < 0.25:
        potions = player.get("potions") or []
        for pot in potions:
            if pot and not pot.get("is_empty", True):
                pidx = pot.get("index", 0)
                target_type = pot.get("target_type", "")
                args = {"potion_index": pidx}
                if target_type == "AnyEnemy" and enemies:
                    args["target_index"] = _find_lowest_hp_enemy_idx(enemies)
                return {"cmd": "action", "action": "use_potion", "args": args}

    # Sort playable cards by priority
    playable = []
    for c in hand:
        if c.get("can_play", False) and c.get("cost", 99) <= energy:
            playable.append(c)

    if playable:
        need_block = incoming > 15 or (incoming > 8 and hp_ratio < 0.5)

        def priority(card):
            ctype = card.get("type", "")
            stats = card.get("stats") or {}
            cost = card.get("cost", 0)
            name = card.get("name", "")
            if isinstance(name, dict):
                name = name.get("en", "") or ""
            if ctype == "Power":
                return (0, cost)
            if need_block and stats.get("block", 0) > 0:
                return (1, -stats.get("block", 0))
            if ctype == "Attack" and stats.get("damage", 0) > 0:
                return (2, -stats.get("damage", 0))
            if stats.get("block", 0) > 0:
                return (3, -stats.get("block", 0))
            return (4, cost)

        playable.sort(key=priority)
        card = playable[0]
        args = {"card_index": card["index"]}
        if card.get("target_type") == "AnyEnemy" and enemies:
            args["target_index"] = _find_lowest_hp_enemy_idx(enemies)
        return {"cmd": "action", "action": "play_card", "args": args}
    else:
        return {"cmd": "action", "action": "end_turn"}


def _smart_map_action(state: dict) -> dict:
    choices = state.get("choices", [])
    if not choices:
        return {"cmd": "action", "action": "proceed"}
    player = state.get("player", {})
    hp = player.get("hp", 0)
    max_hp = player.get("max_hp", 1)
    hp_ratio = hp / max(max_hp, 1)

    if hp_ratio < 0.4:
        type_prio = {"RestSite": 0, "Event": 1, "Shop": 2, "Unknown": 3,
                     "Treasure": 4, "Monster": 5, "Ancient": 6, "Elite": 7, "Boss": 8}
    elif hp_ratio < 0.7:
        type_prio = {"Monster": 0, "Event": 1, "Shop": 2, "Unknown": 3,
                     "Treasure": 4, "RestSite": 5, "Ancient": 6, "Elite": 7, "Boss": 8}
    else:
        type_prio = {"Elite": 0, "Monster": 1, "Event": 2, "Unknown": 3,
                     "Shop": 4, "Treasure": 5, "RestSite": 6, "Ancient": 7, "Boss": 8}

    pick = sorted(choices, key=lambda c: type_prio.get(c.get("type", ""), 99))[0]
    return {
        "cmd": "action", "action": "select_map_node",
        "args": {"col": pick["col"], "row": pick["row"]}
    }


def _smart_card_reward_action(state: dict, character: str) -> dict:
    cards = state.get("cards", [])
    player = state.get("player", {})
    deck_size = player.get("deck_size", 0)

    # Character want lists (subset — matches smart_bot.py)
    CHARACTER_WANTS = {
        "Ironclad": {"inflame", "demon form", "setup strike", "fight me", "brand",
                     "heavy blade", "whirlwind", "pommel strike", "shrug it off",
                     "battle trance", "offering", "bloodletting", "feel no pain",
                     "corruption", "barricade", "impervious", "limit break",
                     "reaper", "feed", "aggression", "stone armor"},
        "Silent": {"noxious fumes", "deadly poison", "poisoned stab", "bouncing flask",
                   "catalyst", "corpse explosion", "footwork", "backflip",
                   "blade dance", "adrenaline", "well laid plans", "burst"},
        "Defect": {"defragment", "biased cognition", "focused strike", "hotfix",
                   "glacier", "coolheaded", "ball lightning", "creative ai",
                   "buffer", "seek", "fission", "compile driver"},
    }
    wants = CHARACTER_WANTS.get(character, set())

    if deck_size > 20:
        # Only pick if it's a wanted card
        for card in cards:
            name = card.get("name", "")
            if isinstance(name, dict):
                name = name.get("en", "") or ""
            if name.lower() in wants:
                return {
                    "cmd": "action", "action": "select_card_reward",
                    "args": {"card_index": card["index"]}
                }
        return {"cmd": "action", "action": "skip_card_reward"}

    # Pick wanted card or best by heuristic
    for card in cards:
        name = card.get("name", "")
        if isinstance(name, dict):
            name = name.get("en", "") or ""
        if name.lower() in wants:
            return {
                "cmd": "action", "action": "select_card_reward",
                "args": {"card_index": card["index"]}
            }

    # Pick first card if any
    if cards:
        return {
            "cmd": "action", "action": "select_card_reward",
            "args": {"card_index": cards[0]["index"]}
        }
    return {"cmd": "action", "action": "skip_card_reward"}


def _smart_rest_action(state: dict) -> dict:
    player = state.get("player", {})
    hp = player.get("hp", 0)
    max_hp = player.get("max_hp", 1)
    hp_ratio = hp / max(max_hp, 1)
    options = state.get("options", [])
    enabled = [o for o in options if o.get("is_enabled", True)]

    heal = next((o for o in enabled if o.get("option_id") == "HEAL"), None)
    smith = next((o for o in enabled if o.get("option_id") == "SMITH"), None)

    if hp_ratio < 0.5 and heal:
        choice = heal
    elif smith:
        choice = smith
    elif heal:
        choice = heal
    elif enabled:
        choice = enabled[0]
    else:
        return {"cmd": "action", "action": "leave_room"}

    return {
        "cmd": "action", "action": "choose_option",
        "args": {"option_index": choice["index"]}
    }


def _smart_event_action(state: dict) -> dict:
    options = state.get("options", [])
    if options:
        unlocked = [o for o in options if not o.get("is_locked")]
        choice = unlocked[0] if unlocked else options[0]
        return {
            "cmd": "action", "action": "choose_option",
            "args": {"option_index": choice["index"]}
        }
    return {"cmd": "action", "action": "leave_room"}


# ============================================================================
# Game runner
# ============================================================================

async def _bridge_send_safe(
    bridge: EngineBridge, cmd: dict, timeout: float = 10.0
) -> dict:
    """Send a command, returning the response even on engine errors.

    EngineBridge.send() raises BridgeError on error responses.
    This helper catches that and tries recovery commands.
    If the bridge process has died, returns a synthetic error immediately.
    Uses a shorter timeout than the bridge's default 30s.
    """
    if not bridge.is_running():
        return {"type": "error", "decision": "", "message": "recovery_failed"}
    try:
        return await asyncio.wait_for(bridge.send(cmd), timeout=timeout)
    except (BridgeError, asyncio.TimeoutError):
        # The engine returned an error or timed out.
        # Try one recovery with proceed.
        if not bridge.is_running():
            return {"type": "error", "decision": "", "message": "recovery_failed"}
        try:
            return await asyncio.wait_for(
                bridge.send({"cmd": "action", "action": "proceed"}),
                timeout=5.0,
            )
        except (BridgeError, asyncio.TimeoutError):
            pass
        # If recovery fails, return a synthetic error state
        return {"type": "error", "decision": "", "message": "recovery_failed"}


async def collect_game(
    seed: int,
    character: str = "Ironclad",
    verbose: bool = False,
) -> tuple[list[tuple], dict]:
    """Play one full game and return (transitions, result).

    Each transition is (state_vec, action_idx, reward, next_state_vec, done).
    """
    bridge = EngineBridge()
    transitions: list[tuple] = []
    result = {"seed": seed, "character": character, "victory": False}

    try:
        await bridge.start()
        state = await bridge.start_run(character, seed=str(seed))

        step = 0
        max_steps = 500
        stuck_count = 0
        last_state_key = None
        consecutive_errors = 0

        while step < max_steps:
            step += 1
            decision = state.get("decision", "")

            # Game over
            if decision == "game_over":
                victory = state.get("victory", False)
                player = state.get("player") or {}
                result.update({
                    "victory": victory,
                    "steps": step,
                    "act": state.get("act"),
                    "floor": state.get("floor"),
                    "hp": player.get("hp"),
                    "max_hp": player.get("max_hp"),
                })

                # Mark last transition as done with terminal reward
                if transitions:
                    s, a, r, ns, d = transitions[-1]
                    terminal_r = compute_reward(
                        {"floor": state.get("floor")},
                        {},
                        state,
                    )
                    done_state = encode_state(state)
                    transitions[-1] = (s, a, r + terminal_r, done_state, True)

                break

            # Bail immediately if bridge process has died
            if not bridge.is_running():
                if verbose:
                    print(f"  [seed={seed}] Bridge process died at step {step}")
                break

            # Error / synthetic error handling
            if state.get("type") == "error" or decision == "":
                consecutive_errors += 1
                if consecutive_errors > 3:
                    if verbose:
                        print(f"  [seed={seed}] Too many errors, aborting")
                    break
                state = await _bridge_send_safe(
                    bridge, {"cmd": "action", "action": "proceed"}
                )
                continue
            else:
                consecutive_errors = 0

            # Stuck detection
            hand_len = len(state.get("hand") or [])
            enemy_hp = sum(e.get("hp", 0) for e in (state.get("enemies") or []))
            energy = state.get("energy", 0)
            state_key = (
                f"{decision}:{state.get('round')}:"
                f"{(state.get('player') or {}).get('hp')}:"
                f"{hand_len}:{enemy_hp}:{energy}"
            )
            if state_key == last_state_key:
                stuck_count += 1
                if stuck_count > 20:
                    if verbose:
                        print(f"  [seed={seed}] STUCK after {step} steps")
                    result["stuck"] = True
                    break
            else:
                stuck_count = 0
                last_state_key = state_key

            # Encode current state
            state_vec = encode_state(state)

            # Choose action using smart bot
            action_cmd = smart_bot_choose_action(state, character)
            action_idx = encode_action(action_cmd, state)

            # Execute action (safe — handles engine errors with recovery)
            next_state = await _bridge_send_safe(bridge, action_cmd)

            # If recovery completely failed, bail
            if next_state.get("message") == "recovery_failed":
                break

            # Compute reward
            reward = compute_reward(state, action_cmd, next_state)

            # Encode next state
            next_state_vec = encode_state(next_state)
            done = next_state.get("decision") == "game_over"

            transitions.append((state_vec, action_idx, reward, next_state_vec, done))

            state = next_state

        if "steps" not in result:
            result["steps"] = step

    except Exception as e:
        result["error"] = str(e)
        if verbose:
            import traceback
            traceback.print_exc()

    finally:
        # ALWAYS clean up the bridge
        try:
            await bridge.quit()
        except Exception:
            pass

    return transitions, result


async def collect_sequential(
    n_games: int,
    character: str = "Ironclad",
    start_seed: int = 5000,
    verbose: bool = True,
) -> tuple[list[tuple], list[dict]]:
    """Run n_games sequentially. Returns (all_transitions, all_results)."""
    all_transitions: list[tuple] = []
    all_results: list[dict] = []

    for i in range(n_games):
        seed = start_seed + i
        if verbose:
            print(f"Game {i + 1}/{n_games} (seed={seed}, char={character}) ...", end=" ")
        t0 = time.time()

        transitions, result = await collect_game(seed, character, verbose=False)
        elapsed = time.time() - t0

        all_transitions.extend(transitions)
        all_results.append(result)

        if verbose:
            victory = "WIN" if result.get("victory") else "LOSS"
            floor = result.get("floor", "?")
            hp = result.get("hp", "?")
            steps = result.get("steps", "?")
            err = f" ERROR={result.get('error')}" if result.get("error") else ""
            stuck = " STUCK" if result.get("stuck") else ""
            print(
                f"{victory} floor={floor} hp={hp} "
                f"steps={steps} transitions={len(transitions)} "
                f"time={elapsed:.1f}s{err}{stuck}"
            )

    return all_transitions, all_results


async def collect_parallel(
    n_games: int,
    n_workers: int = 4,
    character: str = "Ironclad",
    start_seed: int = 5000,
    verbose: bool = True,
) -> tuple[list[tuple], list[dict]]:
    """Run n_games using n_workers concurrent tasks.

    Uses asyncio semaphore to limit concurrency. Each game gets its own
    EngineBridge (its own .NET subprocess).
    """
    semaphore = asyncio.Semaphore(n_workers)
    all_transitions: list[tuple] = []
    all_results: list[dict] = []
    lock = asyncio.Lock()
    completed = 0

    async def run_one(game_idx: int, seed: int):
        nonlocal completed
        async with semaphore:
            t0 = time.time()
            transitions, result = await collect_game(seed, character, verbose=False)
            elapsed = time.time() - t0

            async with lock:
                all_transitions.extend(transitions)
                all_results.append(result)
                completed += 1

            if verbose:
                victory = "WIN" if result.get("victory") else "LOSS"
                floor = result.get("floor", "?")
                steps = result.get("steps", "?")
                err = f" ERR" if result.get("error") else ""
                print(
                    f"  [{completed}/{n_games}] seed={seed} {victory} "
                    f"floor={floor} steps={steps} "
                    f"trans={len(transitions)} time={elapsed:.1f}s{err}"
                )

    # Launch all tasks
    tasks = []
    for i in range(n_games):
        seed = start_seed + i
        tasks.append(run_one(i, seed))

    await asyncio.gather(*tasks)
    return all_transitions, all_results


# ============================================================================
# Save to numpy
# ============================================================================

def save_training_data(
    transitions: list[tuple],
    output_dir: str | Path,
) -> dict[str, Path]:
    """Save transitions as numpy arrays.

    Files:
        states.npy   — shape (N, 512)
        actions.npy  — shape (N,)
        rewards.npy  — shape (N,)
        dones.npy    — shape (N,)

    Returns dict of file paths.
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    if not transitions:
        print("WARNING: No transitions to save!")
        return {}

    N = len(transitions)
    states = np.zeros((N, 512), dtype=np.float32)
    actions = np.zeros(N, dtype=np.int32)
    rewards = np.zeros(N, dtype=np.float32)
    dones = np.zeros(N, dtype=np.bool_)

    for i, (s, a, r, ns, d) in enumerate(transitions):
        states[i] = s
        actions[i] = a
        rewards[i] = r
        dones[i] = d

    paths = {}
    for name, arr in [("states", states), ("actions", actions),
                      ("rewards", rewards), ("dones", dones)]:
        p = output_dir / f"{name}.npy"
        np.save(str(p), arr)
        paths[name] = p

    # Also save next_states for completeness
    next_states = np.zeros((N, 512), dtype=np.float32)
    for i, (s, a, r, ns, d) in enumerate(transitions):
        next_states[i] = ns
    p = output_dir / "next_states.npy"
    np.save(str(p), next_states)
    paths["next_states"] = p

    return paths


# ============================================================================
# Main
# ============================================================================

async def main():
    parser = argparse.ArgumentParser(
        description="RL Data Collector — play sts2-cli games and save training data"
    )
    parser.add_argument("--games", type=int, default=10,
                        help="Number of games to play (default: 10)")
    parser.add_argument("--workers", type=int, default=1,
                        help="Parallel workers (default: 1 = sequential)")
    parser.add_argument("--character", type=str, default="Ironclad",
                        help="Character to play (default: Ironclad)")
    parser.add_argument("--seed", type=int, default=5000,
                        help="Starting seed (default: 5000)")
    parser.add_argument("--output", type=str, default=None,
                        help="Output directory (default: data/training/<character>)")
    parser.add_argument("--verbose", action="store_true", default=True)
    parser.add_argument("--quiet", action="store_true")
    args = parser.parse_args()

    verbose = args.verbose and not args.quiet
    output_dir = args.output or str(
        SLS_ROOT / "data" / "training" / args.character.lower()
    )

    print("=" * 60)
    print(f"  RL Data Collector")
    print(f"  Games: {args.games}  Workers: {args.workers}")
    print(f"  Character: {args.character}  Start seed: {args.seed}")
    print(f"  Output: {output_dir}")
    print("=" * 60)

    t0 = time.time()

    if args.workers <= 1:
        transitions, results = await collect_sequential(
            args.games, args.character, args.seed, verbose
        )
    else:
        transitions, results = await collect_parallel(
            args.games, args.workers, args.character, args.seed, verbose
        )

    elapsed = time.time() - t0

    # Save data
    paths = save_training_data(transitions, output_dir)

    # Print summary
    print()
    print("=" * 60)
    print("  SUMMARY")
    print("=" * 60)
    wins = sum(1 for r in results if r.get("victory"))
    floors = [r.get("floor", 0) or 0 for r in results]
    errors = sum(1 for r in results if r.get("error"))
    stuck = sum(1 for r in results if r.get("stuck"))
    avg_floor = sum(floors) / max(len(floors), 1)
    max_floor = max(floors) if floors else 0

    print(f"  Games played:  {len(results)}")
    print(f"  Wins:          {wins}/{len(results)}")
    print(f"  Avg floor:     {avg_floor:.1f}")
    print(f"  Max floor:     {max_floor}")
    print(f"  Errors:        {errors}")
    print(f"  Stuck:         {stuck}")
    print(f"  Transitions:   {len(transitions)}")
    print(f"  Time:          {elapsed:.1f}s ({elapsed / max(len(results), 1):.1f}s/game)")
    print()

    if paths:
        for name, p in paths.items():
            arr = np.load(str(p))
            print(f"  {name}.npy: shape={arr.shape} dtype={arr.dtype}")
        print(f"\n  Saved to: {output_dir}")

    # Quick sanity check on the encoded data
    if transitions:
        states_arr = np.load(str(paths["states"]))
        actions_arr = np.load(str(paths["actions"]))
        rewards_arr = np.load(str(paths["rewards"]))
        print(f"\n  Sanity checks:")
        print(f"    States range: [{states_arr.min():.3f}, {states_arr.max():.3f}]")
        print(f"    Actions range: [{actions_arr.min()}, {actions_arr.max()}]")
        print(f"    Rewards range: [{rewards_arr.min():.2f}, {rewards_arr.max():.2f}]")
        print(f"    Non-zero features per state (avg): "
              f"{(states_arr != 0).sum(axis=1).mean():.1f} / 512")
        action_counts = np.bincount(actions_arr, minlength=64)
        top5 = np.argsort(action_counts)[::-1][:5]
        print(f"    Top 5 actions: {[(int(a), int(action_counts[a])) for a in top5]}")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
