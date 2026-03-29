#!/usr/bin/env python3
"""
Play Necrobinder and Regent games to verify character-specific TUI displays.

Tests:
1. Necrobinder: Osty companion display (name, HP, block, alive status)
2. Regent: Stars resource display + card star_cost in hand
"""

import asyncio
import json
import sys
import traceback

sys.path.insert(0, "/Users/yunjieke/Documents/Projects/sls-cli/src")

from sts2_tui.bridge import EngineBridge, BridgeError
from sts2_tui.tui.controller import extract_player, extract_hand


# Fields we already handle in the TUI
KNOWN_TOP_LEVEL = {
    "type", "decision", "context", "round", "energy", "max_energy",
    "hand", "enemies", "player", "player_powers",
    "draw_pile_count", "discard_pile_count", "exhaust_pile_count",
    "event_name", "description", "options", "cards", "choices",
    "bundles", "relics", "potions", "victory", "act", "floor",
    "orbs", "orb_slots",
    # Newly handled:
    "osty", "stars",
}

KNOWN_PLAYER = {
    "name", "hp", "max_hp", "block", "gold", "relics", "potions",
    "deck_size", "deck", "orbs", "orb_slots",
}


def collect_novel_fields(state: dict, novel: dict) -> None:
    """Find any fields in the combat state that we don't already handle."""
    decision = state.get("decision", "")
    for key in state:
        if key not in KNOWN_TOP_LEVEL:
            if key not in novel:
                novel[key] = {"first_decision": decision, "sample_value": repr(state[key])[:200]}
    player = state.get("player", {})
    for key in player:
        pkey = f"player.{key}"
        if key not in KNOWN_PLAYER:
            if pkey not in novel:
                novel[pkey] = {"first_decision": decision, "sample_value": repr(player[key])[:200]}


async def play_character(character: str, seed: str, verbose: bool = True) -> dict:
    """Play a game, verifying TUI extraction for character-specific features."""
    bridge = EngineBridge()
    novel_fields: dict = {}
    osty_seen = False
    stars_seen = False
    star_cost_cards_seen = 0
    combat_states = 0
    errors = []

    try:
        ready = await bridge.start()
        if verbose:
            print(f"  Engine ready: {ready}")
    except Exception as e:
        print(f"  FATAL: Could not start engine: {e}")
        return {"character": character, "error": str(e)}

    try:
        state = await bridge.start_run(character, seed=seed)
        if verbose:
            decision = state.get("decision", "?")
            player = state.get("player", {})
            print(f"  Started run: decision={decision} hp={player.get('hp')}/{player.get('max_hp')}")
    except Exception as e:
        print(f"  FATAL: Could not start run: {e}")
        await bridge.quit()
        return {"character": character, "error": str(e)}

    step = 0
    max_steps = 400
    stuck_count = 0
    last_state_key = None

    while step < max_steps:
        step += 1
        decision = state.get("decision", "")

        if state.get("type") == "error":
            try:
                state = await bridge.proceed()
                continue
            except Exception:
                break

        collect_novel_fields(state, novel_fields)

        # Test TUI extraction on combat states
        if decision == "combat_play":
            combat_states += 1
            try:
                player = extract_player(state)
                hand = extract_hand(state)

                # Check Necrobinder Osty
                osty = player.get("osty")
                if osty is not None:
                    if not osty_seen:
                        osty_seen = True
                        print(f"  [step {step}] OSTY found: name={osty['name']} hp={osty['hp']}/{osty['max_hp']} block={osty['block']} alive={osty['alive']}")

                # Check Regent Stars
                stars = player.get("stars")
                if stars is not None:
                    if not stars_seen:
                        stars_seen = True
                        print(f"  [step {step}] STARS found: {stars}")

                # Check for star_cost cards
                for card in hand:
                    sc = card.get("star_cost")
                    if sc is not None:
                        star_cost_cards_seen += 1
                        if star_cost_cards_seen <= 3:
                            print(f"  [step {step}] Star-cost card: '{card['name']}' star_cost={sc} energy_cost={card['cost']}")

            except Exception as e:
                errors.append(f"step {step}: TUI extraction error: {e}")
                traceback.print_exc()

        # Stuck detection
        hand_len = len(state.get("hand", []))
        enemy_hp = sum(e.get("hp", 0) for e in state.get("enemies", []))
        energy = state.get("energy", 0)
        round_ = state.get("round")
        player_hp = state.get("player", {}).get("hp")
        state_key = f"{decision}:{round_}:{player_hp}:{hand_len}:{enemy_hp}:{energy}"
        if state_key == last_state_key:
            stuck_count += 1
            if stuck_count > 5:
                print(f"  [step {step}] Engine stuck at {decision}")
                break
        else:
            stuck_count = 0
            last_state_key = state_key

        try:
            if decision == "game_over":
                print(f"  Game over at step {step} (victory={state.get('victory')})")
                break
            elif decision == "combat_play":
                hand_raw = state.get("hand", [])
                energy = state.get("energy", 0)
                enemies = state.get("enemies", [])
                playable = [c for c in hand_raw if c.get("can_play", False) and c.get("cost", 99) <= energy]
                if playable:
                    card = playable[0]
                    target = None
                    if card.get("target_type") == "AnyEnemy" and enemies:
                        living = [e for e in enemies if e.get("hp", 0) > 0]
                        if living:
                            target = living[0].get("index", 0)
                    state = await bridge.play_card(card["index"], target=target)
                else:
                    state = await bridge.end_turn()
            elif decision == "event_choice":
                options = state.get("options", [])
                if options:
                    pick = next((o for o in options if not o.get("is_locked")), options[0])
                    state = await bridge.choose(pick["index"])
                    if state.get("type") == "error":
                        state = await bridge.leave_room()
                else:
                    state = await bridge.leave_room()
            elif decision == "rest_site":
                options = state.get("options", [])
                enabled = [o for o in options if o.get("is_enabled", True)]
                heal = next((o for o in enabled if o.get("option_id") == "HEAL"), None)
                choice = heal or (enabled[0] if enabled else None)
                if choice:
                    state = await bridge.choose(choice["index"])
                    if state.get("type") == "error":
                        state = await bridge.leave_room()
                else:
                    state = await bridge.leave_room()
            elif decision == "map_select":
                choices = state.get("choices", [])
                if choices:
                    choice = choices[0]
                    state = await bridge.select_map_node(choice["col"], choice["row"])
                else:
                    break
            elif decision == "card_reward":
                cards = state.get("cards", [])
                if cards:
                    state = await bridge.select_card_reward(0)
                else:
                    state = await bridge.skip_card_reward()
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
            elif decision == "boss_reward":
                options = state.get("options", [])
                relics = state.get("relics", [])
                if relics:
                    state = await bridge.choose(0)
                elif options:
                    state = await bridge.choose(options[0].get("index", 0))
                else:
                    state = await bridge.proceed()
            else:
                state = await bridge.proceed()
                if state.get("type") == "error" or state.get("decision") == decision:
                    try:
                        state = await bridge.leave_room()
                    except BridgeError:
                        state = await bridge.proceed()

        except BridgeError as e:
            errors.append(f"step {step}: BridgeError: {e}")
            try:
                state = await bridge.proceed()
            except Exception:
                try:
                    state = await bridge.leave_room()
                except Exception:
                    break
        except Exception as e:
            errors.append(f"step {step}: {type(e).__name__}: {e}")
            try:
                state = await bridge.proceed()
            except Exception:
                break

    await bridge.quit()

    print(f"\n  === {character} RESULTS ===")
    print(f"  Steps: {step}, Combat states tested: {combat_states}")
    print(f"  Osty seen: {osty_seen}")
    print(f"  Stars seen: {stars_seen}")
    print(f"  Star-cost cards seen: {star_cost_cards_seen}")
    if novel_fields:
        remaining = {k: v for k, v in novel_fields.items()
                     if not k.startswith("enemy.") and k not in ("act_name", "can_skip", "gold_earned", "max_select", "min_select")}
        if remaining:
            print(f"  Unhandled novel fields: {sorted(remaining.keys())}")
    if errors:
        print(f"  Errors ({len(errors)}):")
        for e in errors[:5]:
            print(f"    {e}")
    else:
        print(f"  Errors: 0")

    return {
        "character": character,
        "osty_seen": osty_seen,
        "stars_seen": stars_seen,
        "star_cost_cards": star_cost_cards_seen,
        "combat_states": combat_states,
        "errors": errors,
        "novel_fields": novel_fields,
    }


async def main():
    print("=" * 70)
    print("  TESTING NECROBINDER CHARACTER-SPECIFIC MECHANICS")
    print("=" * 70)
    necro_result = await play_character("Necrobinder", seed="42")

    print("\n\n")
    print("=" * 70)
    print("  TESTING REGENT CHARACTER-SPECIFIC MECHANICS")
    print("=" * 70)
    regent_result = await play_character("Regent", seed="42")

    # Summary
    print("\n\n" + "=" * 70)
    print("TEST RESULTS SUMMARY")
    print("=" * 70)

    all_pass = True

    # Necrobinder checks
    print("\n  Necrobinder:")
    if necro_result.get("osty_seen"):
        print("    [PASS] Osty companion detected and extracted")
    else:
        print("    [FAIL] Osty companion NOT detected")
        all_pass = False

    # Regent checks
    print("\n  Regent:")
    if regent_result.get("stars_seen"):
        print("    [PASS] Stars resource detected and extracted")
    else:
        print("    [FAIL] Stars resource NOT detected")
        all_pass = False

    if regent_result.get("star_cost_cards", 0) > 0:
        print(f"    [PASS] Star-cost cards detected ({regent_result['star_cost_cards']} instances)")
    else:
        print("    [FAIL] No star-cost cards detected")
        all_pass = False

    total_errors = len(necro_result.get("errors", [])) + len(regent_result.get("errors", []))
    print(f"\n  Total extraction errors: {total_errors}")

    if all_pass and total_errors == 0:
        print("\n  ALL TESTS PASSED!")
    elif all_pass:
        print(f"\n  Character mechanics detected, but {total_errors} errors occurred")
    else:
        print("\n  SOME TESTS FAILED")

    return 0 if all_pass else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
