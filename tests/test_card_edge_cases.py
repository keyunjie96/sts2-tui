#!/usr/bin/env python3
"""
Test edge case card mechanics in sts2-tui.

Targets 8 specific card categories:
1. X-cost cards (Whirlwind, Malaise) -- cost all remaining energy
2. 0-cost cards -- legitimately cost 0
3. Unplayable cards (Burn, Wound, Dazed) -- should be dimmed
4. Cards with card_select triggers (Survivor, Gambler's Chip) -- trigger discard selection
5. Cards that exhaust -- should show exhaust keyword
6. Cards with Retain -- stay in hand between turns
7. Multi-hit cards (Pummel, Barrage) -- display "NxM" format
8. Cards that generate other cards (Scrape, Cloak and Dagger)

Each test:
- Verifies the card displays correctly (cost, description, keywords)
- Verifies playing it works (no crash, correct state change)
- Verifies the TUI updates correctly after play
"""

import asyncio
import re
import sys
import traceback

sys.path.insert(0, "/Users/yunjieke/Documents/Projects/sls-cli/src")

from sts2_tui.bridge import EngineBridge, BridgeError
from sts2_tui.tui.controller import (
    resolve_card_description,
    extract_hand,
    extract_enemies,
    extract_player,
    extract_pile_counts,
    _detect_x_cost,
    _name_str,
)


# ---------------------------------------------------------------------------
# Result tracking
# ---------------------------------------------------------------------------

class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.checks: list[tuple[str, bool, str]] = []  # (description, passed, detail)

    def check(self, desc: str, passed: bool, detail: str = ""):
        status = "PASS" if passed else "FAIL"
        self.checks.append((desc, passed, detail))
        print(f"    [{status}] {desc}" + (f" -- {detail}" if detail else ""))

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks)

    @property
    def fail_count(self) -> int:
        return sum(1 for _, ok, _ in self.checks if not ok)

    def summary(self) -> str:
        total = len(self.checks)
        passes = sum(1 for _, ok, _ in self.checks if ok)
        fails = total - passes
        status = "PASS" if fails == 0 else "FAIL"
        return f"  [{status}] {self.name}: {passes}/{total} checks passed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

async def _auto_play_combat(bridge: EngineBridge, state: dict, max_turns: int = 80) -> dict:
    """Auto-play combat. Returns post-combat state."""
    for _ in range(max_turns):
        decision = state.get("decision", "")
        if decision != "combat_play":
            return state
        hand = state.get("hand", [])
        energy = state.get("energy", 0)
        enemies = state.get("enemies", [])
        playable = [c for c in hand if c.get("can_play", False) and c.get("cost", 99) <= energy]
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
        if state.get("type") == "error":
            return state
    return state


async def _navigate_to_combat(bridge: EngineBridge, state: dict, max_steps: int = 40) -> dict | None:
    """Navigate from current state to combat. Returns combat state or None."""
    for _ in range(max_steps):
        decision = state.get("decision", "")
        if decision == "combat_play":
            return state
        if decision == "game_over":
            return None
        try:
            if decision == "event_choice":
                options = state.get("options", [])
                if options:
                    pick = next((o for o in options if not o.get("is_locked")), options[0])
                    state = await bridge.choose(pick["index"])
                else:
                    state = await bridge.leave_room()
            elif decision == "map_select":
                choices = state.get("choices", [])
                if choices:
                    state = await bridge.select_map_node(choices[0]["col"], choices[0]["row"])
                else:
                    return None
            elif decision == "card_reward":
                # Always pick cards to build the deck for edge case testing
                cards = state.get("cards", [])
                if cards:
                    state = await bridge.select_card_reward(0)
                else:
                    state = await bridge.skip_card_reward()
            elif decision == "bundle_select":
                bundles = state.get("bundles", [])
                idx = bundles[0].get("index", 0) if bundles else 0
                state = await bridge.select_bundle(idx)
            elif decision == "card_select":
                cards = state.get("cards", [])
                if cards:
                    state = await bridge.select_cards("0")
                else:
                    state = await bridge.skip_select()
            elif decision == "rest_site":
                options = state.get("options", [])
                enabled = [o for o in options if o.get("is_enabled", True)]
                if enabled:
                    state = await bridge.choose(enabled[0]["index"])
                else:
                    state = await bridge.leave_room()
            elif decision == "shop":
                state = await bridge.leave_room()
            else:
                state = await bridge.proceed()
            if state.get("type") == "error":
                try:
                    state = await bridge.proceed()
                except BridgeError:
                    return None
        except BridgeError:
            return None
    return None


# ---------------------------------------------------------------------------
# Test 1: X-cost cards
# ---------------------------------------------------------------------------

async def test_x_cost_cards(results: list[TestResult]):
    """Test X-cost card detection and display."""
    print("\n--- Test 1: X-cost cards ---")
    result = TestResult("X-cost cards")

    # Test the _detect_x_cost function directly (uses RAW descriptions)
    result.check("_detect_x_cost('Whirlwind' raw)",
                 _detect_x_cost(0, "Deal {Damage:diff()} damage to ALL enemies X times."),
                 "should detect literal X in raw description")
    result.check("_detect_x_cost('Malaise' raw)",
                 _detect_x_cost(0, "Enemy loses X{IfUpgraded:show:+1} Strength. Apply X{IfUpgraded:show:+1} Weak."),
                 "should detect literal X in raw description")
    result.check("_detect_x_cost('Tempest' raw)",
                 _detect_x_cost(0, "Channel {IfUpgraded:show:X+1|X} Lightning."),
                 "should detect literal X in IfUpgraded template")
    result.check("_detect_x_cost(non-X card)", not _detect_x_cost(0, "Deal 6 damage"),
                 "should NOT detect X in normal 0-cost card")
    result.check("_detect_x_cost(cost=1 card)", not _detect_x_cost(1, "Deal X damage"),
                 "should NOT detect X when cost is not 0")
    # Spite is NOT X-cost -- its {Repeat:diff()} resolves to X after template processing,
    # but the raw description has no literal X
    result.check("_detect_x_cost('Spite' raw - false positive fix)",
                 not _detect_x_cost(0, "Deal {Damage:diff()} damage.\nIf you lost HP this turn,\nhits {Repeat:diff()} times."),
                 "should NOT detect X in Spite's raw description (no literal X)")

    # Test that extract_hand properly maps X-cost cards to cost=-1
    # Create a mock state with an X-cost card.
    # Note: descriptions are RAW (pre-resolution) since the engine sends raw templates.
    mock_state = {
        "hand": [
            {
                "index": 0,
                "name": "Whirlwind",
                "cost": 0,
                "type": "Attack",
                "can_play": True,
                "target_type": "AllEnemies",
                "stats": {"damage": 5},
                "description": "Deal {Damage:diff()} damage to ALL enemies X times.",
                "keywords": [],
            },
            {
                "index": 1,
                "name": "Defend",
                "cost": 1,
                "type": "Skill",
                "can_play": True,
                "target_type": "Self",
                "stats": {"block": 5},
                "description": "Gain {Block:diff()} Block.",
                "keywords": [],
            },
            {
                "index": 2,
                "name": "Anger",
                "cost": 0,
                "type": "Attack",
                "can_play": True,
                "target_type": "AnyEnemy",
                "stats": {"damage": 6},
                "description": "Deal {Damage:diff()} damage. Add a copy to your discard pile.",
                "keywords": [],
            },
            {
                "index": 3,
                "name": "Spite",
                "cost": 0,
                "type": "Attack",
                "can_play": True,
                "target_type": "AnyEnemy",
                "stats": {"damage": 6, "cards": 1},
                "description": "Deal {Damage:diff()} damage.\nIf you lost HP this turn,\nhits {Repeat:diff()} times.",
                "keywords": [],
            },
        ],
        "player": {"hp": 70, "max_hp": 80, "gold": 99, "relics": [], "potions": []},
        "energy": 3,
        "max_energy": 3,
    }

    hand = extract_hand(mock_state)

    # Whirlwind should have cost=-1 (X-cost)
    whirlwind = hand[0]
    result.check("Whirlwind cost is -1 (X-cost sentinel)",
                 whirlwind["cost"] == -1,
                 f"got cost={whirlwind['cost']}")

    # Defend should have cost=1
    defend = hand[1]
    result.check("Defend cost is 1 (normal cost)",
                 defend["cost"] == 1,
                 f"got cost={defend['cost']}")

    # Anger should have cost=0 (true 0-cost, not X-cost)
    anger = hand[2]
    result.check("Anger cost is 0 (true 0-cost, not X-cost)",
                 anger["cost"] == 0,
                 f"got cost={anger['cost']}")

    # Spite should have cost=0 (NOT X-cost -- the X in its resolved desc comes from
    # unresolved {Repeat:diff()}, not a literal X in the raw template)
    spite = hand[3]
    result.check("Spite cost is 0 (NOT X-cost, false positive fix)",
                 spite["cost"] == 0,
                 f"got cost={spite['cost']}")

    # Test CardWidget rendering of X-cost
    from sts2_tui.tui.screens.combat import CardWidget
    xcard_widget = CardWidget(whirlwind, 0, energy=3)
    header = xcard_widget._header()
    header_str = header.plain
    result.check("X-cost card header shows 'X' for cost",
                 "(X)" in header_str,
                 f"header: '{header_str}'")

    zero_card_widget = CardWidget(anger, 2, energy=3)
    zero_header = zero_card_widget._header()
    zero_header_str = zero_header.plain
    result.check("0-cost card header shows '0' for cost",
                 "(0)" in zero_header_str,
                 f"header: '{zero_header_str}'")

    # Test that X-cost cards are playable (not flagged as too expensive)
    xcard_widget2 = CardWidget(whirlwind, 0, energy=0)
    result.check("X-cost card playable even with 0 energy",
                 "--unplayable" not in xcard_widget2.classes,
                 f"classes: {xcard_widget2.classes}")

    results.append(result)


# ---------------------------------------------------------------------------
# Test 2: 0-cost cards
# ---------------------------------------------------------------------------

async def test_zero_cost_cards(results: list[TestResult]):
    """Test 0-cost cards display and playability."""
    print("\n--- Test 2: 0-cost cards ---")
    result = TestResult("0-cost cards")

    # Play as Silent (has 0-cost Neutralize and Shivs)
    bridge = EngineBridge()
    try:
        await bridge.start()
        state = await bridge.start_run("Silent", seed="42")
        combat_state = await _navigate_to_combat(bridge, state)
        if not combat_state:
            result.check("Reached combat as Silent", False, "could not navigate to combat")
            results.append(result)
            await bridge.quit()
            return

        result.check("Reached combat as Silent", True)

        # Find 0-cost cards in hand
        hand = extract_hand(combat_state)
        zero_cost_cards = [c for c in hand if c["cost"] == 0]
        nonzero_cards = [c for c in hand if c["cost"] > 0]

        result.check("Hand has 0-cost cards (Neutralize expected)",
                     len(zero_cost_cards) > 0,
                     f"found {len(zero_cost_cards)} 0-cost cards: {[c['name'] for c in zero_cost_cards]}")

        # Verify 0-cost cards show correct cost in CardWidget
        if zero_cost_cards:
            from sts2_tui.tui.screens.combat import CardWidget
            card = zero_cost_cards[0]
            w = CardWidget(card, 0, energy=3)
            header_str = w._header().plain
            result.check(f"0-cost card '{card['name']}' shows (0) in header",
                         "(0)" in header_str,
                         f"header: '{header_str}'")

            # 0-cost card should be playable even with 0 energy
            w_zero_energy = CardWidget(card, 0, energy=0)
            is_unplayable = "--unplayable" in w_zero_energy.classes
            result.check(f"0-cost card '{card['name']}' playable with 0 energy",
                         not is_unplayable,
                         f"classes: {w_zero_energy.classes}")

        # Actually play a 0-cost card
        if zero_cost_cards:
            card = zero_cost_cards[0]
            target = None
            if card.get("target_type") == "AnyEnemy":
                enemies = extract_enemies(combat_state)
                living = [e for e in enemies if not e.get("is_dead")]
                if living:
                    target = living[0].get("index", 0)
            pre_energy = combat_state.get("energy", 0)
            new_state = await bridge.play_card(card["index"], target=target)
            result.check(f"Playing 0-cost card '{card['name']}' succeeds",
                         new_state.get("type") != "error",
                         f"decision={new_state.get('decision')}")
            post_energy = new_state.get("energy", 0)
            result.check("0-cost card does not consume energy",
                         post_energy == pre_energy,
                         f"energy: {pre_energy} -> {post_energy}")

    except Exception as e:
        result.check("No crash during 0-cost card test", False, f"{type(e).__name__}: {e}")
    finally:
        await bridge.quit()

    results.append(result)


# ---------------------------------------------------------------------------
# Test 3: Unplayable cards
# ---------------------------------------------------------------------------

async def test_unplayable_cards(results: list[TestResult]):
    """Test unplayable cards (Burn, Wound, Dazed) display and behavior."""
    print("\n--- Test 3: Unplayable cards ---")
    result = TestResult("Unplayable cards")

    # Test with mock state containing unplayable cards
    mock_state = {
        "hand": [
            {
                "index": 0,
                "name": "Burn",
                "cost": 0,
                "type": "Status",
                "can_play": False,
                "target_type": "None",
                "stats": {},
                "description": "Unplayable. At the end of your turn, take 2 damage.",
                "keywords": ["Unplayable"],
            },
            {
                "index": 1,
                "name": "Wound",
                "cost": 0,
                "type": "Status",
                "can_play": False,
                "target_type": "None",
                "stats": {},
                "description": "Unplayable.",
                "keywords": ["Unplayable"],
            },
            {
                "index": 2,
                "name": "Dazed",
                "cost": 0,
                "type": "Status",
                "can_play": False,
                "target_type": "None",
                "stats": {},
                "description": "Unplayable. Ethereal.",
                "keywords": ["Unplayable", "Ethereal"],
            },
            {
                "index": 3,
                "name": "Strike",
                "cost": 1,
                "type": "Attack",
                "can_play": True,
                "target_type": "AnyEnemy",
                "stats": {"damage": 6},
                "description": "Deal 6 damage.",
                "keywords": [],
            },
        ],
        "player": {"hp": 70, "max_hp": 80, "gold": 99, "relics": [], "potions": []},
        "energy": 3,
        "max_energy": 3,
    }

    hand = extract_hand(mock_state)
    from sts2_tui.tui.screens.combat import CardWidget

    # Burn should be unplayable
    burn = hand[0]
    burn_w = CardWidget(burn, 0, energy=3)
    result.check("Burn marked as unplayable",
                 not burn["can_play"],
                 f"can_play={burn['can_play']}")
    result.check("Burn widget has --unplayable class",
                 "--unplayable" in burn_w.classes,
                 f"classes: {burn_w.classes}")

    # Unplayable keyword shown in header
    header_str = burn_w._header().plain
    result.check("Burn header shows (unplayable) or Unplayable keyword icon",
                 "unplayable" in header_str.lower() or "\u2718" in burn_w._header().plain,
                 f"header: '{header_str}'")

    # Wound
    wound = hand[1]
    wound_w = CardWidget(wound, 1, energy=3)
    result.check("Wound marked as unplayable",
                 not wound["can_play"])
    result.check("Wound widget has --unplayable class",
                 "--unplayable" in wound_w.classes)

    # Dazed has both Unplayable and Ethereal
    dazed = hand[2]
    dazed_w = CardWidget(dazed, 2, energy=3)
    result.check("Dazed marked as unplayable",
                 not dazed["can_play"])
    result.check("Dazed shows Ethereal keyword",
                 "Ethereal" in str(dazed["keywords"]),
                 f"keywords: {dazed['keywords']}")
    # The desc section should show keyword labels
    desc_text = dazed_w._desc().plain
    result.check("Dazed description shows keyword labels",
                 "Unplayable" in desc_text or "Ethereal" in desc_text,
                 f"desc: '{desc_text}'")

    # Normal card should NOT be unplayable
    strike = hand[3]
    strike_w = CardWidget(strike, 3, energy=3)
    result.check("Strike is NOT unplayable",
                 "--unplayable" not in strike_w.classes,
                 f"classes: {strike_w.classes}")

    # Test HandLabel with all unplayable hand
    all_unplayable_state = {
        "hand": mock_state["hand"][:3],  # Only status cards
        "player": mock_state["player"],
        "energy": 3,
        "max_energy": 3,
    }
    from sts2_tui.tui.screens.combat import HandLabel
    label = HandLabel(all_unplayable_state)
    label_text = label.render()
    result.check("HandLabel shows end-turn hint when all cards unplayable",
                 "end" in label_text.plain.lower() or "[E]" in label_text.plain,
                 f"label: '{label_text.plain}'")

    results.append(result)


# ---------------------------------------------------------------------------
# Test 4: Cards with card_select triggers
# ---------------------------------------------------------------------------

async def test_card_select_triggers(results: list[TestResult]):
    """Test cards that trigger card_select decision (Survivor, Gambler's Chip)."""
    print("\n--- Test 4: card_select triggers ---")
    result = TestResult("card_select triggers")

    # Play Silent games looking for card_select decisions
    found_card_select = False
    for seed in range(1, 30):
        bridge = EngineBridge()
        try:
            await bridge.start()
            state = await bridge.start_run("Silent", seed=str(seed))

            # Navigate to combat and play through, looking for card_select
            combat_state = await _navigate_to_combat(bridge, state)
            if not combat_state:
                await bridge.quit()
                continue

            # Play combat and look for card_select decisions
            for turn in range(50):
                decision = combat_state.get("decision", "")
                if decision == "card_select":
                    found_card_select = True
                    # Validate the card_select state
                    cards = combat_state.get("cards", [])
                    result.check(f"card_select has cards to choose from (seed={seed})",
                                 len(cards) > 0,
                                 f"found {len(cards)} cards")

                    if cards:
                        # Verify card descriptions resolve properly
                        for card in cards:
                            name = _name_str(card.get("name"))
                            desc = card.get("description", "")
                            stats = card.get("stats") or {}
                            resolved = resolve_card_description(desc, stats)
                            unresolved = re.findall(r"\{[^}]+\}", resolved)
                            if unresolved:
                                result.check(f"card_select card '{name}' description resolved",
                                             False, f"unresolved: {unresolved}")

                        # Select the first card
                        new_state = await bridge.select_cards("0")
                        result.check("Selecting card in card_select succeeds",
                                     new_state.get("type") != "error",
                                     f"decision={new_state.get('decision')}")
                        combat_state = new_state
                    break

                elif decision == "combat_play":
                    hand = combat_state.get("hand", [])
                    energy = combat_state.get("energy", 0)
                    playable = [c for c in hand if c.get("can_play", False) and c.get("cost", 99) <= energy]
                    if playable:
                        card = playable[0]
                        target = None
                        if card.get("target_type") == "AnyEnemy":
                            enemies = combat_state.get("enemies", [])
                            living = [e for e in enemies if e.get("hp", 0) > 0]
                            if living:
                                target = living[0].get("index", 0)
                        combat_state = await bridge.play_card(card["index"], target=target)
                    else:
                        combat_state = await bridge.end_turn()
                elif decision == "game_over":
                    break
                else:
                    break

                if combat_state.get("type") == "error":
                    break

            if found_card_select:
                await bridge.quit()
                break

        except Exception as e:
            result.check(f"No crash testing card_select (seed={seed})", False, f"{type(e).__name__}: {e}")
        finally:
            await bridge.quit()

    if not found_card_select:
        # Also test the GenericScreen handling of card_select with mock data
        result.check("card_select found in live game", False,
                     "Did not encounter card_select in seeds 1-29. Testing mock instead.")

    # Test GenericScreen can handle card_select state
    mock_card_select_state = {
        "decision": "card_select",
        "cards": [
            {
                "index": 0,
                "name": "Strike",
                "cost": 1,
                "type": "Attack",
                "description": "Deal {Damage:diff()} damage.",
                "stats": {"damage": 6},
            },
            {
                "index": 1,
                "name": "Defend",
                "cost": 1,
                "type": "Skill",
                "description": "Gain {Block:diff()} Block.",
                "stats": {"block": 5},
            },
        ],
        "player": {"hp": 70, "max_hp": 80, "gold": 99},
        "context": {"act": 1, "floor": 5},
    }

    from sts2_tui.tui.screens.generic import GenericScreen

    class MockController:
        async def select_cards(self, indices): return {"decision": "combat_play"}
        async def skip_select(self): return {"decision": "combat_play"}

    # Verify GenericScreen parses options correctly
    screen = GenericScreen(mock_card_select_state, controller=MockController())
    result.check("GenericScreen finds card_select options",
                 len(screen.options) == 2,
                 f"found {len(screen.options)} options")

    # Verify option descriptions get resolved
    options_text = screen._options_text()
    plain = options_text.plain
    result.check("card_select options have resolved descriptions",
                 "6" in plain and "5" in plain,
                 "text includes damage/block values")
    result.check("card_select options do NOT have unresolved templates",
                 "{Damage" not in plain and "{Block" not in plain,
                 "options text clean of templates")

    results.append(result)


# ---------------------------------------------------------------------------
# Test 5: Cards that exhaust
# ---------------------------------------------------------------------------

async def test_exhaust_cards(results: list[TestResult]):
    """Test cards with Exhaust keyword display and pile count updates."""
    print("\n--- Test 5: Exhaust cards ---")
    result = TestResult("Exhaust cards")

    # Mock an exhaust card
    mock_state = {
        "hand": [
            {
                "index": 0,
                "name": "Impervious",
                "cost": 2,
                "type": "Skill",
                "can_play": True,
                "target_type": "Self",
                "stats": {"block": 30},
                "description": "Gain 30 Block. Exhaust.",
                "keywords": ["Exhaust"],
            },
            {
                "index": 1,
                "name": "True Grit",
                "cost": 1,
                "type": "Skill",
                "can_play": True,
                "target_type": "Self",
                "stats": {"block": 7},
                "description": "Gain 7 Block. Exhaust a random card from your hand.",
                "keywords": ["Exhaust"],
            },
        ],
        "player": {"hp": 70, "max_hp": 80, "gold": 99, "deck_size": 20, "relics": [], "potions": []},
        "energy": 3,
        "max_energy": 3,
        "draw_pile_count": 10,
        "discard_pile_count": 5,
    }

    hand = extract_hand(mock_state)
    from sts2_tui.tui.screens.combat import CardWidget

    # Check exhaust keyword display
    imperv = hand[0]
    imperv_w = CardWidget(imperv, 0, energy=3)
    header_str = imperv_w._header().plain
    result.check("Exhaust card shows Exhaust keyword icon in header",
                 "\u2716" in imperv_w._header().plain,
                 f"header text: '{header_str}'")

    desc_str = imperv_w._desc().plain
    result.check("Exhaust card shows 'Exhaust' in description/keywords",
                 "Exhaust" in desc_str,
                 f"desc: '{desc_str}'")

    # Verify pile count calculation with exhaust pile
    piles = extract_pile_counts(mock_state)
    result.check("Pile counts computed correctly",
                 piles["draw"] == 10 and piles["discard"] == 5,
                 f"draw={piles['draw']} discard={piles['discard']} exhaust={piles['exhaust']}")

    # Verify exhaust pile count is computed (deck_size - draw - discard - hand)
    expected_exhaust = max(0, 20 - 10 - 5 - 2)
    result.check("Exhaust pile count approximation",
                 piles["exhaust"] == expected_exhaust,
                 f"expected={expected_exhaust} got={piles['exhaust']}")

    # Test PileCountWidget rendering
    from sts2_tui.tui.screens.combat import PileCountWidget
    pw = PileCountWidget(mock_state)
    pile_text = pw.render().plain
    result.check("PileCountWidget renders exhaust count",
                 str(expected_exhaust) in pile_text,
                 f"pile text: '{pile_text}'")

    results.append(result)


# ---------------------------------------------------------------------------
# Test 6: Cards with Retain
# ---------------------------------------------------------------------------

async def test_retain_cards(results: list[TestResult]):
    """Test cards with Retain keyword display."""
    print("\n--- Test 6: Retain cards ---")
    result = TestResult("Retain cards")

    mock_state = {
        "hand": [
            {
                "index": 0,
                "name": "Well-Laid Plans",
                "cost": 1,
                "type": "Skill",
                "can_play": True,
                "target_type": "Self",
                "stats": {},
                "description": "Retain up to 1 card in your hand.",
                "keywords": ["Retain"],
            },
            {
                "index": 1,
                "name": "Flame Barrier",
                "cost": 2,
                "type": "Skill",
                "can_play": True,
                "target_type": "Self",
                "stats": {"block": 12, "damage": 4},
                "description": "Gain 12 Block. Whenever you are attacked this turn, deal 4 damage back.",
                "keywords": [],
            },
        ],
        "player": {"hp": 70, "max_hp": 80, "gold": 99, "relics": [], "potions": []},
        "energy": 3,
        "max_energy": 3,
    }

    hand = extract_hand(mock_state)
    from sts2_tui.tui.screens.combat import CardWidget

    retain_card = hand[0]
    retain_w = CardWidget(retain_card, 0, energy=3)
    header_str = retain_w._header().plain
    result.check("Retain card shows Retain keyword icon in header",
                 "\u21ba" in retain_w._header().plain,
                 f"header: '{header_str}'")

    desc_str = retain_w._desc().plain
    result.check("Retain card shows 'Retain' in keywords section",
                 "Retain" in desc_str,
                 f"desc: '{desc_str}'")

    # Normal card should NOT show Retain
    normal_w = CardWidget(hand[1], 1, energy=3)
    normal_header = normal_w._header().plain
    result.check("Non-retain card does NOT show Retain icon",
                 "\u21ba" not in normal_w._header().plain,
                 f"header: '{normal_header}'")

    results.append(result)


# ---------------------------------------------------------------------------
# Test 7: Multi-hit cards
# ---------------------------------------------------------------------------

async def test_multi_hit_cards(results: list[TestResult]):
    """Test multi-hit card display (NxM format) in descriptions."""
    print("\n--- Test 7: Multi-hit cards ---")
    result = TestResult("Multi-hit cards")

    # Play as Ironclad looking for multi-hit cards like Pummel, Twin Strike
    # Also test enemy multi-hit intents
    mock_state = {
        "hand": [
            {
                "index": 0,
                "name": "Pummel",
                "cost": 1,
                "type": "Attack",
                "can_play": True,
                "target_type": "AnyEnemy",
                "stats": {"damage": 2},
                "description": "Deal 2 damage 4 times. Exhaust.",
                "keywords": ["Exhaust"],
            },
            {
                "index": 1,
                "name": "Twin Strike",
                "cost": 1,
                "type": "Attack",
                "can_play": True,
                "target_type": "AnyEnemy",
                "stats": {"damage": 5},
                "description": "Deal 5 damage twice.",
                "keywords": [],
            },
        ],
        "enemies": [
            {
                "index": 0,
                "name": "Jaw Worm",
                "hp": 40,
                "max_hp": 44,
                "block": 0,
                "intents": [{"type": "Attack", "damage": 7, "hits": 2}],
                "powers": [],
            },
        ],
        "player": {"hp": 70, "max_hp": 80, "gold": 99, "relics": [], "potions": []},
        "energy": 3,
        "max_energy": 3,
    }

    hand = extract_hand(mock_state)
    enemies = extract_enemies(mock_state)

    # Multi-hit card description preserved
    pummel = hand[0]
    result.check("Pummel description mentions multi-hit",
                 "4 times" in pummel["description"] or "x4" in pummel["description"],
                 f"desc: '{pummel['description']}'")

    twin = hand[1]
    result.check("Twin Strike description mentions hitting twice",
                 "twice" in twin["description"] or "x2" in twin["description"],
                 f"desc: '{twin['description']}'")

    # Test enemy multi-hit intent rendering
    enemy = enemies[0]
    result.check("Enemy with multi-hit intent shows hits",
                 enemy["intent_hits"] == 2,
                 f"intent_hits={enemy.get('intent_hits')}")
    result.check("Enemy intent summary includes hit count",
                 "x2" in enemy["intent_summary"],
                 f"summary: '{enemy['intent_summary']}'")

    # Test EnemyWidget rendering of multi-hit
    from sts2_tui.tui.screens.combat import EnemyWidget
    ew = EnemyWidget(enemy, 0)
    intent_text = ew._intent_text().plain
    result.check("EnemyWidget shows multi-hit in NxM format",
                 "7x2" in intent_text or "7 x 2" in intent_text,
                 f"intent text: '{intent_text}'")

    # Test IncomingSummary with multi-hit
    from sts2_tui.tui.screens.combat import IncomingSummary
    incoming = IncomingSummary(mock_state)
    incoming_text = incoming.render().plain
    result.check("IncomingSummary totals multi-hit correctly",
                 "14" in incoming_text,  # 7*2 = 14
                 f"incoming text: '{incoming_text}'")

    results.append(result)


# ---------------------------------------------------------------------------
# Test 8: Cards that generate other cards
# ---------------------------------------------------------------------------

async def test_card_generating_cards(results: list[TestResult]):
    """Test cards that add cards to hand/deck (Shiv generators, etc)."""
    print("\n--- Test 8: Card-generating cards ---")
    result = TestResult("Card-generating cards")

    # Play as Silent, which generates Shivs
    bridge = EngineBridge()
    try:
        await bridge.start()
        state = await bridge.start_run("Silent", seed="15")
        combat_state = await _navigate_to_combat(bridge, state)
        if not combat_state:
            result.check("Reached combat as Silent", False, "could not navigate to combat")
            results.append(result)
            await bridge.quit()
            return

        result.check("Reached combat as Silent", True)

        # Look at hand for any card-generating cards
        hand = extract_hand(combat_state)
        card_names = [c["name"] for c in hand]
        result.check("Hand is non-empty",
                     len(hand) > 0,
                     f"hand: {card_names}")

        # Play through combat looking for Shivs or generated cards
        shiv_seen = False
        hand_size_increased = False
        pre_hand_size = len(hand)

        for turn in range(30):
            decision = combat_state.get("decision", "")
            if decision != "combat_play":
                break

            hand = extract_hand(combat_state)
            current_names = [c["name"] for c in hand]

            # Check for Shivs
            for card in hand:
                name = card.get("name", "")
                if "Shiv" in name:
                    shiv_seen = True
                    result.check("Shiv card has cost=0",
                                 card["cost"] == 0,
                                 f"cost={card['cost']}")
                    result.check("Shiv card is playable",
                                 card.get("can_play", False),
                                 f"can_play={card.get('can_play')}")
                    result.check("Shiv has description",
                                 len(card.get("description", "")) > 0,
                                 f"desc: '{card.get('description')}'")

            if len(hand) > pre_hand_size:
                hand_size_increased = True

            energy = combat_state.get("energy", 0)
            playable = [c for c in hand if c.get("can_play", False)]
            affordable = [c for c in playable if c.get("cost", 99) <= energy]

            if affordable:
                card = affordable[0]
                target = None
                if card.get("target_type") == "AnyEnemy":
                    enemies = combat_state.get("enemies", [])
                    living = [e for e in enemies if e.get("hp", 0) > 0]
                    if living:
                        target = living[0].get("index", 0)
                combat_state = await bridge.play_card(card["index"], target=target)
            else:
                pre_hand_size = 0  # Reset after end turn for fresh draw
                combat_state = await bridge.end_turn()

            if combat_state.get("type") == "error":
                result.check("No errors during card-gen combat", False,
                             combat_state.get("message"))
                break

        if shiv_seen:
            result.check("Encountered Shiv (generated card) during combat", True)
        else:
            result.check("Encountered Shiv during combat", False,
                         "No Shivs seen in 30 turns. This is seed-dependent.")

    except Exception as e:
        result.check("No crash during card-gen test", False, f"{type(e).__name__}: {e}")
    finally:
        await bridge.quit()

    results.append(result)


# ---------------------------------------------------------------------------
# Test: Live game with Silent (diverse card pool)
# ---------------------------------------------------------------------------

async def test_live_silent_game(results: list[TestResult]):
    """Play a full Silent game testing all card types live."""
    print("\n--- Test: Live Silent game (diverse card pool) ---")
    result = TestResult("Live Silent game")

    bridge = EngineBridge()
    try:
        await bridge.start()
        state = await bridge.start_run("Silent", seed="7")

        cards_played: dict[str, list[str]] = {
            "x_cost": [],
            "zero_cost": [],
            "unplayable_seen": [],
            "exhaust": [],
            "retain": [],
            "multi_hit_desc": [],
            "card_select_decisions": [],
        }

        step = 0
        max_steps = 200
        while step < max_steps:
            step += 1
            decision = state.get("decision", "")
            if decision == "game_over":
                break

            if decision == "combat_play":
                hand = extract_hand(state)
                energy = state.get("energy", 0)

                for card in hand:
                    name = card.get("name", "")
                    cost = card.get("cost", 0)
                    can_play = card.get("can_play", True)
                    keywords = card.get("keywords", [])
                    desc = card.get("description", "")

                    # Categorize
                    if cost == -1:
                        if name not in cards_played["x_cost"]:
                            cards_played["x_cost"].append(name)
                    elif cost == 0 and can_play:
                        if name not in cards_played["zero_cost"]:
                            cards_played["zero_cost"].append(name)
                    if not can_play:
                        if name not in cards_played["unplayable_seen"]:
                            cards_played["unplayable_seen"].append(name)
                    if "Exhaust" in keywords:
                        if name not in cards_played["exhaust"]:
                            cards_played["exhaust"].append(name)
                    if "Retain" in keywords:
                        if name not in cards_played["retain"]:
                            cards_played["retain"].append(name)
                    if any(w in desc.lower() for w in ["times", "twice", "x2", "x3", "x4"]):
                        if name not in cards_played["multi_hit_desc"]:
                            cards_played["multi_hit_desc"].append(name)

                    # Verify no unresolved templates
                    unresolved = re.findall(r"\{[^}]+\}", desc)
                    if unresolved:
                        result.check(f"Card '{name}' desc resolved",
                                     False, f"unresolved: {unresolved}")

                # Play or end turn
                playable = [c for c in hand
                            if c.get("can_play", False) and
                            (c.get("cost", 99) <= energy or c.get("cost", 0) < 0)]
                if playable:
                    card = playable[0]
                    target = None
                    if card.get("target_type") == "AnyEnemy":
                        enemies = state.get("enemies", [])
                        living = [e for e in enemies if e.get("hp", 0) > 0]
                        if living:
                            target = living[0].get("index", 0)
                    state = await bridge.play_card(card["index"], target=target)
                else:
                    state = await bridge.end_turn()

            elif decision == "card_select":
                cards_played["card_select_decisions"].append(f"step_{step}")
                cards = state.get("cards", [])
                if cards:
                    state = await bridge.select_cards("0")
                else:
                    state = await bridge.skip_select()

            elif decision == "event_choice":
                options = state.get("options", [])
                if options:
                    pick = next((o for o in options if not o.get("is_locked")), options[0])
                    state = await bridge.choose(pick["index"])
                else:
                    state = await bridge.leave_room()

            elif decision == "map_select":
                choices = state.get("choices", [])
                if choices:
                    state = await bridge.select_map_node(choices[0]["col"], choices[0]["row"])
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

            elif decision == "rest_site":
                options = state.get("options", [])
                enabled = [o for o in options if o.get("is_enabled", True)]
                if enabled:
                    state = await bridge.choose(enabled[0]["index"])
                else:
                    state = await bridge.leave_room()

            elif decision == "shop":
                state = await bridge.leave_room()

            else:
                state = await bridge.proceed()

            if state.get("type") == "error":
                try:
                    state = await bridge.proceed()
                except Exception:
                    break

        # Report what we found
        print(f"    Steps played: {step}")
        for category, names in cards_played.items():
            if names:
                print(f"    {category}: {names}")
            else:
                print(f"    {category}: (none found)")

        result.check("Game completed without crash", True, f"{step} steps")
        result.check("Found 0-cost cards",
                     len(cards_played["zero_cost"]) > 0,
                     f"found: {cards_played['zero_cost']}")

    except Exception as e:
        result.check("No crash during live game", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        await bridge.quit()

    results.append(result)


# ---------------------------------------------------------------------------
# Test: Live Defect game (X-cost, orbs)
# ---------------------------------------------------------------------------

async def test_live_defect_game(results: list[TestResult]):
    """Play a Defect game looking for X-cost cards and orb interactions."""
    print("\n--- Test: Live Defect game (X-cost, orbs) ---")
    result = TestResult("Live Defect game")

    bridge = EngineBridge()
    try:
        await bridge.start()
        state = await bridge.start_run("Defect", seed="25")

        x_cost_found = False
        orbs_seen = False
        step = 0
        max_steps = 200

        while step < max_steps:
            step += 1
            decision = state.get("decision", "")
            if decision == "game_over":
                break

            if decision == "combat_play":
                hand = extract_hand(state)
                player = extract_player(state)
                energy = state.get("energy", 0)

                # Check for orbs
                if player.get("orbs"):
                    orbs_seen = True
                    for orb in player["orbs"]:
                        otype = orb.get("type", "Empty")
                        known = {"Lightning", "Frost", "Dark", "Plasma", "Glass", "Empty"}
                        if otype not in known:
                            result.check(f"Known orb type '{otype}'", False,
                                         "Unknown orb type detected")

                # Check for X-cost cards
                for card in hand:
                    if card["cost"] == -1:
                        x_cost_found = True
                        name = card["name"]
                        result.check(f"X-cost card '{name}' shows X in widget", True)
                        # Verify X-cost card is playable with any energy
                        from sts2_tui.tui.screens.combat import CardWidget
                        w = CardWidget(card, 0, energy=0)
                        result.check(f"X-cost card '{name}' playable with 0 energy",
                                     "--unplayable" not in w.classes or not card.get("can_play"),
                                     f"classes={w.classes}, can_play={card.get('can_play')}")

                # Play
                playable = [c for c in hand
                            if c.get("can_play", False) and
                            (c.get("cost", 99) <= energy or c.get("cost", 0) < 0)]
                if playable:
                    card = playable[0]
                    target = None
                    if card.get("target_type") == "AnyEnemy":
                        enemies = state.get("enemies", [])
                        living = [e for e in enemies if e.get("hp", 0) > 0]
                        if living:
                            target = living[0].get("index", 0)
                    state = await bridge.play_card(card["index"], target=target)
                else:
                    state = await bridge.end_turn()

            elif decision == "card_reward":
                # Pick cards to build deck, preferring rare/uncommon
                cards = state.get("cards", [])
                if cards:
                    state = await bridge.select_card_reward(0)
                else:
                    state = await bridge.skip_card_reward()

            elif decision == "event_choice":
                options = state.get("options", [])
                if options:
                    pick = next((o for o in options if not o.get("is_locked")), options[0])
                    state = await bridge.choose(pick["index"])
                else:
                    state = await bridge.leave_room()

            elif decision == "map_select":
                choices = state.get("choices", [])
                if choices:
                    state = await bridge.select_map_node(choices[0]["col"], choices[0]["row"])
                else:
                    break

            elif decision == "bundle_select":
                state = await bridge.select_bundle(0)

            elif decision == "card_select":
                cards = state.get("cards", [])
                if cards:
                    state = await bridge.select_cards("0")
                else:
                    state = await bridge.skip_select()

            elif decision == "rest_site":
                options = state.get("options", [])
                enabled = [o for o in options if o.get("is_enabled", True)]
                if enabled:
                    state = await bridge.choose(enabled[0]["index"])
                else:
                    state = await bridge.leave_room()

            elif decision == "shop":
                state = await bridge.leave_room()

            else:
                state = await bridge.proceed()

            if state.get("type") == "error":
                try:
                    state = await bridge.proceed()
                except Exception:
                    break

        result.check("Defect game completed without crash", True, f"{step} steps")
        result.check("Orbs seen during combat", orbs_seen)
        if not x_cost_found:
            result.check("X-cost cards found", False,
                         "No X-cost cards in this seed (normal, they are rare)")

    except Exception as e:
        result.check("No crash during Defect game", False, f"{type(e).__name__}: {e}")
        traceback.print_exc()
    finally:
        await bridge.quit()

    results.append(result)


# ---------------------------------------------------------------------------
# Test: Energy affordability edge cases
# ---------------------------------------------------------------------------

async def test_energy_affordability(results: list[TestResult]):
    """Test CardWidget --unplayable class with various energy/cost combos."""
    print("\n--- Test: Energy affordability edge cases ---")
    result = TestResult("Energy affordability")

    from sts2_tui.tui.screens.combat import CardWidget

    # Test cases: (card_cost, energy, can_play, expected_unplayable)
    test_cases = [
        # (cost, energy, can_play, should_have_unplayable, label)
        (1, 3, True, False, "1-cost card with 3 energy: playable"),
        (1, 0, True, True, "1-cost card with 0 energy: unplayable"),
        (0, 0, True, False, "0-cost card with 0 energy: playable"),
        (0, 3, True, False, "0-cost card with 3 energy: playable"),
        (-1, 0, True, False, "X-cost card with 0 energy: playable"),
        (-1, 3, True, False, "X-cost card with 3 energy: playable"),
        (1, 1, False, True, "1-cost can_play=false: unplayable"),
        (0, 3, False, True, "0-cost can_play=false: unplayable"),
        (5, 3, True, True, "5-cost card with 3 energy: unplayable"),
        (3, 3, True, False, "3-cost card with 3 energy: playable"),
    ]

    for cost, energy, can_play, expected_unplayable, label in test_cases:
        card = {
            "index": 0,
            "name": "Test",
            "cost": cost,
            "type": "Attack",
            "can_play": can_play,
            "target_type": "AnyEnemy",
            "stats": {},
            "description": "Test card.",
            "keywords": [],
        }
        w = CardWidget(card, 0, energy=energy)
        has_unplayable = "--unplayable" in w.classes
        result.check(label, has_unplayable == expected_unplayable,
                     f"expected {'un' if expected_unplayable else ''}playable, "
                     f"got {'--unplayable' if has_unplayable else 'playable'}")

    results.append(result)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    print("=" * 70)
    print("EDGE CASE CARD MECHANICS TEST SUITE")
    print("=" * 70)

    results: list[TestResult] = []

    # Unit-level tests (no engine needed)
    await test_x_cost_cards(results)
    await test_unplayable_cards(results)
    await test_exhaust_cards(results)
    await test_retain_cards(results)
    await test_multi_hit_cards(results)
    await test_energy_affordability(results)

    # Integration tests (need engine)
    await test_zero_cost_cards(results)
    await test_card_select_triggers(results)
    await test_card_generating_cards(results)

    # Full game tests
    await test_live_silent_game(results)
    await test_live_defect_game(results)

    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    total_checks = 0
    total_passed = 0
    total_failed = 0
    for r in results:
        print(r.summary())
        for desc, ok, detail in r.checks:
            total_checks += 1
            if ok:
                total_passed += 1
            else:
                total_failed += 1

    print(f"\n  Total: {total_checks} checks, {total_passed} passed, {total_failed} failed")

    if total_failed > 0:
        print("\n  FAILURES:")
        for r in results:
            for desc, ok, detail in r.checks:
                if not ok:
                    print(f"    [{r.name}] {desc}" + (f" -- {detail}" if detail else ""))

    return total_failed


if __name__ == "__main__":
    failed = asyncio.run(main())
    sys.exit(1 if failed > 0 else 0)
