#!/usr/bin/env python3
"""
Audit data collector: play 5 games (one per character) with random actions,
saving complete raw JSON engine responses to tests/audit_data/{Character}_{seed}.jsonl.

Usage:
    python tests/run_audit.py [start_seed]

Default start_seed is 100001.  Characters cycle: Ironclad, Silent, Defect, Regent, Necrobinder.
"""

import asyncio
import json
import random
import sys
from pathlib import Path

# Ensure project root is importable
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from sts2_tui.bridge import EngineBridge, BridgeError

CHARACTERS = ["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"]
MAX_STEPS = 500
AUDIT_DIR = PROJECT_ROOT / "tests" / "audit_data"


def pick_random_action(state: dict) -> dict | None:
    """Given an engine state, return a random valid action command dict.

    Returns None if the game is over or we don't know what to do.
    """
    decision = state.get("decision", "")

    if decision == "game_over":
        return None

    if decision == "map_select":
        choices = state.get("choices", [])
        if not choices:
            return None
        choice = random.choice(choices)
        return {
            "cmd": "action",
            "action": "select_map_node",
            "args": {"col": choice["col"], "row": choice["row"]},
        }

    if decision == "combat_play":
        hand = state.get("hand", [])
        energy = state.get("energy", 0)
        enemies = state.get("enemies", [])
        playable = [c for c in hand if c.get("can_play") and c.get("cost", 0) <= energy]

        if playable:
            card = random.choice(playable)
            args = {"card_index": card["index"]}
            if card.get("target_type") == "AnyEnemy" and enemies:
                args["target_index"] = random.choice(enemies)["index"]
            return {"cmd": "action", "action": "play_card", "args": args}
        else:
            return {"cmd": "action", "action": "end_turn"}

    if decision == "event_choice":
        options = state.get("options", [])
        unlocked = [o for o in options if not o.get("is_locked")]
        if unlocked:
            choice = random.choice(unlocked)
            return {
                "cmd": "action",
                "action": "choose_option",
                "args": {"option_index": choice["index"]},
            }
        return {"cmd": "action", "action": "leave_room"}

    if decision == "rest_site":
        options = state.get("options", [])
        enabled = [o for o in options if o.get("is_enabled", True)]
        if enabled:
            choice = random.choice(enabled)
            return {
                "cmd": "action",
                "action": "choose_option",
                "args": {"option_index": choice["index"]},
            }
        return {"cmd": "action", "action": "leave_room"}

    if decision == "card_reward":
        # Handle potion rewards first
        potion_rewards = state.get("potion_rewards") or []
        slots_full = state.get("potion_slots_full", False)
        if potion_rewards:
            pr = potion_rewards[0]
            if not slots_full:
                return {
                    "cmd": "action",
                    "action": "collect_potion_reward",
                    "args": {"potion_index": pr["index"]},
                }
            else:
                return {
                    "cmd": "action",
                    "action": "skip_potion_reward",
                    "args": {"potion_index": pr["index"]},
                }
        # Pick a random card or skip
        cards = state.get("cards", [])
        if cards and random.random() < 0.7:
            idx = random.randint(0, len(cards) - 1)
            return {
                "cmd": "action",
                "action": "select_card_reward",
                "args": {"card_index": idx},
            }
        return {"cmd": "action", "action": "skip_card_reward"}

    if decision == "bundle_select":
        bundles = state.get("bundles", [])
        idx = random.randint(0, max(0, len(bundles) - 1)) if bundles else 0
        return {
            "cmd": "action",
            "action": "select_bundle",
            "args": {"bundle_index": idx},
        }

    if decision == "card_select":
        cards = state.get("cards", [])
        if cards:
            return {
                "cmd": "action",
                "action": "select_cards",
                "args": {"indices": "0"},
            }
        return {"cmd": "action", "action": "skip_select"}

    if decision == "shop":
        return {"cmd": "action", "action": "leave_room"}

    # Fallback: proceed
    return {"cmd": "action", "action": "proceed"}


async def play_one_game(character: str, seed: str, outpath: Path) -> dict:
    """Play a full game, writing every engine state to outpath as JSONL."""
    bridge = EngineBridge()
    lines_written = 0

    try:
        with open(outpath, "w") as fout:
            # Start the bridge
            ready = await bridge.start()
            fout.write(json.dumps(ready) + "\n")
            lines_written += 1
            print(f"  Engine ready: {ready.get('version', '?')}")

            # Start the run
            state = await bridge.start_run(character, seed=seed)
            fout.write(json.dumps(state) + "\n")
            lines_written += 1

            step = 0
            stuck_count = 0
            last_state_key = None

            while step < MAX_STEPS:
                step += 1
                decision = state.get("decision", "")

                # Report progress occasionally
                if step % 25 == 0:
                    ctx = state.get("context", {})
                    player = state.get("player", {})
                    print(
                        f"    step={step} decision={decision} "
                        f"act={ctx.get('act','?')} floor={ctx.get('floor','?')} "
                        f"hp={player.get('hp','?')}/{player.get('max_hp','?')}"
                    )

                # Check game over
                if decision == "game_over":
                    victory = state.get("victory", False)
                    player = state.get("player", {})
                    print(
                        f"  {'VICTORY' if victory else 'DEFEAT'} at step {step}, "
                        f"act={state.get('act','?')} floor={state.get('floor','?')} "
                        f"hp={player.get('hp','?')}/{player.get('max_hp','?')}"
                    )
                    return {"victory": victory, "steps": step, "lines": lines_written}

                # Stuck detection
                hand_len = len(state.get("hand", []))
                enemy_hp = sum(e.get("hp", 0) for e in state.get("enemies", []))
                energy = state.get("energy", 0)
                state_key = (
                    f"{decision}:{state.get('round')}:"
                    f"{state.get('player',{}).get('hp')}:{hand_len}:{enemy_hp}:{energy}"
                )
                if state_key == last_state_key:
                    stuck_count += 1
                    if stuck_count > 20:
                        print(f"  STUCK after {step} steps, aborting")
                        return {"stuck": True, "steps": step, "lines": lines_written}
                else:
                    stuck_count = 0
                    last_state_key = state_key

                # Pick and send action
                action = pick_random_action(state)
                if action is None:
                    print(f"  No valid action at step {step}, decision={decision}")
                    break

                try:
                    state = await bridge.send(action)
                    fout.write(json.dumps(state) + "\n")
                    lines_written += 1

                    # If error, try to recover
                    if state.get("type") == "error":
                        err_msg = state.get("message", "unknown")
                        print(f"    engine error at step {step}: {err_msg}")
                        # Try proceed as recovery
                        try:
                            state = await bridge.send(
                                {"cmd": "action", "action": "proceed"}
                            )
                            fout.write(json.dumps(state) + "\n")
                            lines_written += 1
                        except BridgeError:
                            break

                except BridgeError as e:
                    print(f"  BridgeError at step {step}: {e}")
                    fout.write(
                        json.dumps({"type": "crash", "step": step, "error": str(e)})
                        + "\n"
                    )
                    lines_written += 1
                    break

            print(f"  Reached max steps ({MAX_STEPS})")
            return {"timeout": True, "steps": step, "lines": lines_written}

    except BridgeError as e:
        print(f"  Bridge startup error: {e}")
        return {"error": str(e), "lines": lines_written}
    except Exception as e:
        print(f"  Unexpected error: {e}")
        return {"error": str(e), "lines": lines_written}
    finally:
        try:
            await bridge.quit()
        except Exception:
            pass
        print(f"  Wrote {lines_written} lines to {outpath.name}")


async def main():
    start_seed = int(sys.argv[1]) if len(sys.argv) > 1 else 100001

    AUDIT_DIR.mkdir(parents=True, exist_ok=True)

    results = {}
    for i, character in enumerate(CHARACTERS):
        seed = str(start_seed + i)
        outpath = AUDIT_DIR / f"{character}_{seed}.jsonl"
        print(f"\n{'='*60}")
        print(f"Game {i+1}/5: {character} (seed {seed})")
        print(f"{'='*60}")
        result = await play_one_game(character, seed, outpath)
        results[f"{character}_{seed}"] = result

    print(f"\n{'='*60}")
    print("AUDIT SUMMARY")
    print(f"{'='*60}")
    for key, r in results.items():
        status = "ERROR"
        if r.get("victory"):
            status = "VICTORY"
        elif r.get("stuck"):
            status = "STUCK"
        elif r.get("timeout"):
            status = "TIMEOUT"
        elif r.get("error"):
            status = f"ERROR: {r['error'][:60]}"
        elif "steps" in r:
            status = "DEFEAT"
        print(f"  {key}: {status} (steps={r.get('steps','?')}, lines={r.get('lines','?')})")


if __name__ == "__main__":
    asyncio.run(main())
