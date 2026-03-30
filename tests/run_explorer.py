#!/usr/bin/env python3
"""
EXPLORER: Play god-mode games using the sts2-agent strategy to explore deep content.

Uses god_mode=True with the real strategy from sts2-agent (not a toy inline bot).
Wraps the strategy's play_game to also log every JSON state for the Challenger.
"""

import asyncio
import json
import random
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AGENT_ROOT = PROJECT_ROOT.parent / "sts2-agent"
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(AGENT_ROOT))

from sts2_tui.bridge import EngineBridge, BridgeError

ALL_CHARACTERS = ["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"]
AUDIT_DIR = PROJECT_ROOT / "tests" / "audit_data"


async def play_one_game(character: str, seed: int, outpath: Path) -> dict:
    """Play a full god-mode game, logging every state to JSONL.

    Uses sts2-agent's strategy for decision-making but intercepts every
    bridge response to write it to disk for the Challenger to review.
    """
    # Import strategy from sts2-agent
    from sts2_agent.strategy import (
        pick_card_to_play, pick_map_node, pick_card_reward,
        pick_event_option, pick_rest_option, handle_shop,
        pick_neow_option, pick_upgrade_target,
        should_use_potion, pick_potion_to_use,
        find_lowest_hp_enemy, find_highest_hp_enemy, is_boss_fight,
        get_text, get_card_name, CARD_WANTS, UPGRADE_TARGETS,
    )

    bridge = EngineBridge()
    lines_written = 0
    stats = {
        "character": character, "seed": seed,
        "max_act": 0, "max_floor": 0,
        "decisions_seen": set(), "victory": False, "crash": None,
    }

    def log_state(state: dict, fout):
        nonlocal lines_written
        fout.write(json.dumps(state) + "\n")
        lines_written += 1

    try:
        with open(outpath, "w") as fout:
            ready = await bridge.start()
            log_state(ready, fout)

            state = await bridge.start_run(character, seed=str(seed), god_mode=True)
            log_state(state, fout)

            max_steps = 2000  # god-mode full runs need more than 800
            stuck_key = ""
            stuck_count = 0
            potion_used_this_combat = False
            failed_card_ids: set[str] = set()

            for step in range(max_steps):
                decision = state.get("decision", "")
                ctx = state.get("context", {})
                player = state.get("player", {})

                # Track stats
                stats["decisions_seen"].add(decision)
                act = ctx.get("act", 0)
                floor_num = ctx.get("floor", 0)
                if act: stats["max_act"] = max(stats["max_act"], act)
                if floor_num: stats["max_floor"] = max(stats["max_floor"], floor_num)

                if state.get("type") == "error":
                    state = await bridge.send({"cmd": "action", "action": "proceed"})
                    log_state(state, fout)
                    continue

                # Stuck detection (non-combat only)
                if decision != "combat_play":
                    key = f"{decision}:{floor_num}"
                    if key == stuck_key:
                        stuck_count += 1
                    else:
                        stuck_key = key
                        stuck_count = 1
                else:
                    stuck_count = 0

                if stuck_count > 10:
                    # Try escaping
                    for escape in ["proceed", "leave_room", "skip_card_reward",
                                   "skip_select", "skip_potion_reward"]:
                        state = await bridge.send({"cmd": "action", "action": escape})
                        log_state(state, fout)
                        if state.get("decision") != decision:
                            stuck_count = 0
                            break
                    else:
                        stats["crash"] = f"stuck at step {step}"
                        break
                    continue

                # Progress
                if step % 100 == 0:
                    print(f"  [{character}] step={step} act={act} floor={floor_num} decision={decision}")

                if decision == "game_over":
                    stats["victory"] = state.get("victory", False)
                    label = "VICTORY" if stats["victory"] else "DEFEAT"
                    print(f"  [{character}] {label} at step {step}, act={act} floor={floor_num}")
                    return stats

                # Use sts2-agent strategy for decisions
                try:
                    if decision == "map_select":
                        pick = pick_map_node(state, character)
                        state = await bridge.send({"cmd": "action", "action": "select_map_node",
                                                   "args": {"col": pick["col"], "row": pick["row"]}})
                        potion_used_this_combat = False
                        failed_card_ids.clear()

                    elif decision == "combat_play":
                        # Try potion first
                        if not potion_used_this_combat or is_boss_fight(state):
                            if should_use_potion(state):
                                pot = pick_potion_to_use(state)
                                if pot:
                                    pidx, needs_target = pot
                                    enemies = state.get("enemies", [])
                                    args = {"potion_index": pidx}
                                    if needs_target and enemies:
                                        if is_boss_fight(state):
                                            args["target_index"] = find_highest_hp_enemy(enemies)
                                        else:
                                            args["target_index"] = find_lowest_hp_enemy(enemies)
                                    state = await bridge.send({"cmd": "action", "action": "use_potion", "args": args})
                                    log_state(state, fout)
                                    potion_used_this_combat = True
                                    continue

                        result = pick_card_to_play(state)
                        if result:
                            card_idx, target_idx = result
                            card = next((c for c in state.get("hand", []) if c.get("index") == card_idx), None)
                            card_id = card.get("id", "") if card else ""

                            # Skip known-broken cards
                            if card_id in failed_card_ids:
                                state = await bridge.send({"cmd": "action", "action": "end_turn"})
                                log_state(state, fout)
                                continue

                            args = {"card_index": card_idx}
                            if target_idx is not None:
                                args["target_index"] = target_idx
                            result_state = await bridge.send({"cmd": "action", "action": "play_card", "args": args})
                            if result_state.get("type") == "error":
                                if card_id:
                                    failed_card_ids.add(card_id)
                                state = await bridge.send({"cmd": "action", "action": "proceed"})
                            else:
                                state = result_state
                        else:
                            state = await bridge.send({"cmd": "action", "action": "end_turn"})

                    elif decision == "card_reward":
                        # Handle potions first
                        potion_rewards = state.get("potion_rewards") or []
                        if potion_rewards:
                            if not state.get("potion_slots_full", False):
                                try:
                                    state = await bridge.send({"cmd": "action", "action": "collect_potion_reward",
                                                               "args": {"potion_index": 0}})
                                except BridgeError:
                                    state = await bridge.send({"cmd": "action", "action": "skip_potion_reward"})
                            else:
                                state = await bridge.send({"cmd": "action", "action": "skip_potion_reward"})
                            log_state(state, fout)
                            continue
                        cards = state.get("cards", [])
                        if cards:
                            pick = pick_card_reward(state, character)
                            if pick is not None:
                                state = await bridge.send({"cmd": "action", "action": "select_card_reward",
                                                           "args": {"card_index": pick}})
                            else:
                                state = await bridge.send({"cmd": "action", "action": "skip_card_reward"})
                        else:
                            state = await bridge.send({"cmd": "action", "action": "skip_card_reward"})

                    elif decision == "event_choice":
                        event_name = get_text(state.get("event_name", "")).lower()
                        if "neow" in event_name:
                            pick = pick_neow_option(state, character)
                        else:
                            pick = pick_event_option(state, character)
                        if pick:
                            state = await bridge.send({"cmd": "action", "action": "choose_option",
                                                       "args": {"option_index": pick["index"]}})
                        else:
                            state = await bridge.send({"cmd": "action", "action": "leave_room"})

                    elif decision == "rest_site":
                        pick = pick_rest_option(state, character)
                        if pick:
                            state = await bridge.send({"cmd": "action", "action": "choose_option",
                                                       "args": {"option_index": pick["index"]}})
                        else:
                            state = await bridge.send({"cmd": "action", "action": "leave_room"})

                    elif decision == "card_select":
                        cards = state.get("cards", [])
                        if cards:
                            room = ctx.get("room_type", "")
                            if room == "RestSite":
                                idx = pick_upgrade_target(cards, character)
                                state = await bridge.send({"cmd": "action", "action": "select_cards",
                                                           "args": {"indices": str(idx)}})
                            elif room in ("Shop", "Merchant", "MerchantRoom"):
                                # Remove worst card (strikes/curses first)
                                worst_idx = 0
                                worst_score = 999
                                for card in cards:
                                    nl = get_card_name(card).lower()
                                    s = 50
                                    if card.get("type", "") == "Curse":
                                        s = -10
                                    elif "status" in (card.get("type", "") or "").lower():
                                        s = -5
                                    elif nl == "strike":
                                        s = 0
                                    elif nl == "defend":
                                        s = 10
                                    if s < worst_score:
                                        worst_score = s
                                        worst_idx = card.get("index", 0)
                                state = await bridge.send({"cmd": "action", "action": "select_cards",
                                                           "args": {"indices": str(worst_idx)}})
                            else:
                                state = await bridge.send({"cmd": "action", "action": "select_cards",
                                                           "args": {"indices": "0"}})
                        else:
                            state = await bridge.send({"cmd": "action", "action": "skip_select"})

                    elif decision == "shop":
                        # Async shop logic (mirrors sts2-agent's handle_shop)
                        player_info = state.get("player", {})
                        gold = player_info.get("gold", 0)
                        deck_size = player_info.get("deck_size", 0)
                        wants = CARD_WANTS.get(character, set())
                        # Try card removal
                        if state.get("card_removal_available") and gold >= state.get("card_removal_cost", 75) and deck_size > 8:
                            result = await bridge.send({"cmd": "action", "action": "remove_card", "args": {}})
                            log_state(result, fout)
                            if result.get("decision") != "shop":
                                state = result
                                continue
                            state = result
                            gold = state.get("player", {}).get("gold", 0)
                        # Buy power cards or wanted cards
                        bought = False
                        for card in state.get("cards", []):
                            if not card.get("is_stocked"):
                                continue
                            cost = card.get("cost", 999)
                            ctype = card.get("type", "")
                            name_lower = get_text(card.get("name", "")).lower()
                            if (ctype == "Power" or name_lower in wants) and cost <= gold:
                                result = await bridge.send({"cmd": "action", "action": "buy_card",
                                                            "args": {"card_index": card["index"]}})
                                log_state(result, fout)
                                if result.get("decision") != "shop":
                                    state = result
                                    bought = True
                                    break
                                state = result
                                gold = state.get("player", {}).get("gold", 0)
                                bought = True
                                break
                        if not bought or state.get("decision") == "shop":
                            state = await bridge.send({"cmd": "action", "action": "leave_room"})

                    elif decision == "bundle_select":
                        state = await bridge.send({"cmd": "action", "action": "select_bundle",
                                                   "args": {"bundle_index": 0}})

                    else:
                        state = await bridge.send({"cmd": "action", "action": "proceed"})

                    log_state(state, fout)

                except BridgeError as e:
                    # Engine error (invalid action etc) — try to recover
                    err_msg = str(e)
                    log_state({"type": "error_recovery", "step": step, "error": err_msg}, fout)
                    try:
                        # Try proceed to move past the error
                        state = await bridge.send({"cmd": "action", "action": "proceed"})
                        log_state(state, fout)
                    except BridgeError:
                        try:
                            state = await bridge.send({"cmd": "action", "action": "skip_potion_reward"})
                            log_state(state, fout)
                        except BridgeError:
                            try:
                                state = await bridge.send({"cmd": "action", "action": "leave_room"})
                                log_state(state, fout)
                            except BridgeError:
                                stats["crash"] = err_msg
                                break
                except Exception as e:
                    # Strategy function failed — fallback to proceed
                    try:
                        state = await bridge.send({"cmd": "action", "action": "proceed"})
                        log_state(state, fout)
                    except BridgeError:
                        stats["crash"] = str(e)
                        break

            if step >= max_steps - 1:
                stats["crash"] = f"max steps ({max_steps})"
            return stats

    except Exception as e:
        stats["crash"] = str(e)
        return stats
    finally:
        try:
            await bridge.quit()
        except Exception:
            pass
        print(f"  [{character}] {lines_written} lines → {outpath.name}")


async def main():
    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    characters = list(ALL_CHARACTERS)
    seeds = [random.randint(1, 999999) for _ in range(5)]

    print(f"EXPLORER: 5 god-mode games (all characters, random seeds)")
    print(f"Seeds: {seeds}")

    # Run games sequentially to avoid OOM from 5 .NET processes
    all_stats = []
    for char, seed in zip(characters, seeds):
        outpath = AUDIT_DIR / f"{char}_{seed}.jsonl"
        result = await play_one_game(char, seed, outpath)
        all_stats.append(result)

    print(f"\n{'='*60}")
    print("SUMMARY")
    for s in all_stats:
        label = "VICTORY" if s["victory"] else ("CRASH" if s["crash"] else "ENDED")
        s["decisions_seen"] = sorted(s["decisions_seen"])
        print(f"  {s['character']} seed={s['seed']}: {label} act={s['max_act']} floor={s['max_floor']}")
        if s["crash"]:
            print(f"    → {s['crash'][:80]}")


if __name__ == "__main__":
    asyncio.run(main())
