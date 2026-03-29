#!/usr/bin/env python3
"""
Tuned heuristic bot for STS2 — real game knowledge for all 5 characters.

Strategies:
- Combat: powers first, block when needed, focus fire lowest HP, card value scoring
- Card rewards: skip if deck > 20, take powers/rares, match deck archetype
- Map: elites when healthy, rest/shop when low, treasure always
- Rest sites: heal < 50% HP, smith otherwise (upgrade best targets)
- Shop: buy powers, remove strikes, buy potions if rich
- Potions: damage potions on low HP enemies, block when incoming > 20, power early
"""

import json
import subprocess
import sys
import os
import time
import argparse
import select

# --- Path setup ---
SLS_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STS2_ROOT = os.path.join(os.path.dirname(SLS_ROOT), "sts2-cli")
PROJECT = os.path.join(STS2_ROOT, "src", "Sts2Headless", "Sts2Headless.csproj")

sys.path.insert(0, os.path.join(STS2_ROOT, "python"))
from game_log import GameLogger


def _find_dotnet():
    for p in ["dotnet", os.path.expanduser("~/.dotnet-arm64/dotnet"),
              os.path.expanduser("~/.dotnet/dotnet")]:
        try:
            r = subprocess.run([p, "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode == 0:
                return p
        except (FileNotFoundError, subprocess.TimeoutExpired):
            continue
    return "dotnet"


DOTNET = _find_dotnet()


# ==========================================================================
# Character-specific card priorities (lowercase names)
# ==========================================================================

IRONCLAD_WANT = {
    # Powers (scaling)
    "inflame", "demon form", "aggression", "barricade", "corruption",
    "feel no pain", "metallicize", "vicious", "juggernaut",
    # Key attacks
    "heavy blade", "whirlwind", "pommel strike", "reaper", "feed",
    "carnage", "uppercut", "bludgeon", "iron wave", "anger",
    # Key skills
    "shrug it off", "battle trance", "offering", "bloodletting",
    "impervious", "flame barrier", "true grit", "power through",
    "entrench", "disarm", "intimidate", "stone armor",
    "blood wall", "double tap", "limit break",
    # Setup
    "setup strike", "fight me", "brand", "taunt",
}

SILENT_WANT = {
    # Powers
    "noxious fumes", "envenom", "afterimage", "a thousand cuts",
    "abrasive", "accuracy", "accelerant",
    # Poison
    "deadly poison", "poisoned stab", "bouncing flask", "catalyst",
    "corpse explosion", "crippling cloud", "snakebite",
    # Defense
    "footwork", "backflip", "dodge and roll", "leg sweep",
    "blur", "haze", "bubble bubble",
    # Draw/utility
    "adrenaline", "well laid plans", "burst", "blade dance",
    "nightmare", "malaise", "acrobatics",
}

DEFECT_WANT = {
    # Powers
    "defragment", "biased cognition", "electrodynamics", "creative ai",
    "echo form", "buffer", "capacitor",
    # Orb generation
    "ball lightning", "doom and gloom", "glacier", "coolheaded",
    "cold snap", "darkness",
    # Utility
    "seek", "fission", "compile driver", "reboot",
    "thunder strike", "self repair", "consume", "multi cast",
    "focused strike", "hotfix",
}

REGENT_WANT = {
    "genesis", "child of the stars", "guiding star", "hidden cache",
    "seven stars", "falling star", "cloak of stars", "stardust",
    "astral pulse", "alignment", "judgment", "brilliance",
    "scrawl", "vault",
}

NECROBINDER_WANT = {
    "afterlife", "blight strike", "dark pact", "bone shield",
    "soul steal", "requiem", "necronomicon",
}

CHARACTER_WANTS = {
    "Ironclad": IRONCLAD_WANT,
    "Silent": SILENT_WANT,
    "Defect": DEFECT_WANT,
    "Regent": REGENT_WANT,
    "Necrobinder": NECROBINDER_WANT,
}

# Cards that are strong upgrade targets (per character)
GOOD_UPGRADES = {
    "Ironclad": {"bash", "inflame", "demon form", "heavy blade", "offering",
                 "impervious", "reaper", "whirlwind", "carnage", "feed",
                 "shrug it off", "battle trance", "blood wall"},
    "Silent": {"noxious fumes", "footwork", "catalyst", "leg sweep",
               "backflip", "bouncing flask", "deadly poison", "malaise",
               "blade dance", "adrenaline", "accuracy"},
    "Defect": {"defragment", "biased cognition", "glacier", "coolheaded",
               "ball lightning", "echo form", "electrodynamics", "buffer",
               "compile driver", "seek"},
    "Regent": {"genesis", "judgment", "brilliance", "seven stars",
               "guiding star", "vault"},
    "Necrobinder": {"afterlife", "dark pact", "soul steal", "requiem"},
}

# Keyword-based archetype detection for synergy scoring
ARCHETYPE_KEYWORDS = {
    "Ironclad": {
        "strength": ["inflame", "demon form", "heavy blade", "limit break",
                     "aggression", "fight me", "setup strike"],
        "block": ["barricade", "entrench", "body slam", "iron wave",
                  "shrug it off", "impervious", "stone armor"],
        "exhaust": ["corruption", "feel no pain", "true grit",
                    "power through", "ashen strike", "evil eye"],
    },
    "Silent": {
        "poison": ["noxious fumes", "deadly poison", "poisoned stab",
                   "bouncing flask", "catalyst", "corpse explosion",
                   "crippling cloud", "envenom", "snakebite"],
        "shiv": ["blade dance", "accuracy", "a thousand cuts",
                 "infinite blades", "cloak and dagger"],
        "defense": ["footwork", "backflip", "dodge and roll",
                    "leg sweep", "blur", "afterimage"],
    },
    "Defect": {
        "focus": ["defragment", "biased cognition", "consume",
                  "focused strike", "hotfix", "capacitor"],
        "orbs": ["ball lightning", "doom and gloom", "glacier",
                 "coolheaded", "cold snap", "darkness", "thunder strike"],
    },
}


# ==========================================================================
# Utility functions
# ==========================================================================

def get_card_name(card):
    """Extract string name from card, handling bilingual names."""
    name = card.get("name", "")
    if isinstance(name, dict):
        name = name.get("en", "") or name.get("zh", "") or str(name)
    return name


def calc_incoming_damage(enemies):
    """Estimate total incoming damage from enemy intents."""
    total = 0
    for e in enemies:
        for intent in (e.get("intents") or []):
            itype = intent.get("type", "")
            dmg = intent.get("damage", 0)
            hits = intent.get("hits", 1) or 1
            if itype in ("Attack", "DeathBlow") and dmg:
                total += dmg * hits
    return total


def find_lowest_hp_enemy(enemies):
    """Return the index of the enemy with the lowest HP."""
    if not enemies:
        return 0
    return min(enemies, key=lambda e: e.get("hp", 9999))["index"]


def find_highest_hp_enemy(enemies):
    """Return the index of the enemy with the highest HP."""
    if not enemies:
        return 0
    return max(enemies, key=lambda e: e.get("hp", 0))["index"]


def enemy_has_debuff(enemy, debuff_name):
    """Check if an enemy has a specific debuff/power."""
    for p in (enemy.get("powers") or []):
        if debuff_name.lower() in (p.get("name", "") or "").lower():
            return True
    return False


def player_has_power(state, power_name):
    """Check if the player has a specific power active."""
    player = state.get("player", {})
    for p in (player.get("powers") or []):
        if power_name.lower() in (p.get("name", "") or "").lower():
            return True
    return False


def detect_deck_archetype(state, character):
    """Detect which archetype the current deck leans towards."""
    if character not in ARCHETYPE_KEYWORDS:
        return None
    archetypes = ARCHETYPE_KEYWORDS[character]
    deck = state.get("player", {}).get("deck", [])
    deck_names = set()
    for card in deck:
        deck_names.add(get_card_name(card).lower())

    scores = {}
    for archetype, keywords in archetypes.items():
        scores[archetype] = sum(1 for kw in keywords if kw in deck_names)

    if not scores:
        return None
    best = max(scores, key=scores.get)
    if scores[best] >= 2:
        return best
    return None


# ==========================================================================
# Combat: Card value scoring
# ==========================================================================

def score_card(card, energy, enemies, state, is_boss):
    """Score a card based on the current combat situation. Higher = better."""
    ctype = card.get("type", "")
    name_lower = get_card_name(card).lower()
    cost = card.get("cost", 0)
    stats = card.get("stats") or {}
    player = state.get("player", {})
    hp = player.get("hp", 0)
    max_hp = player.get("max_hp", 1)
    block = player.get("block", 0)
    incoming = calc_incoming_damage(enemies)
    hp_ratio = hp / max(max_hp, 1)

    dmg = stats.get("damage", 0)
    blk = stats.get("block", 0)
    hp_loss = stats.get("hploss", 0)

    score = 0.0

    # --- Powers: always high priority (scaling wins runs) ---
    if ctype == "Power":
        score = 100.0
        # Specific power bonuses
        if "demon form" in name_lower:
            score = 150.0  # Best power in the game
        elif "inflame" in name_lower:
            score = 140.0
        elif "noxious fumes" in name_lower:
            score = 140.0
        elif "defragment" in name_lower:
            score = 140.0
        elif "biased cognition" in name_lower:
            score = 145.0
        elif "barricade" in name_lower:
            score = 130.0
        elif "feel no pain" in name_lower:
            score = 125.0
        elif "corruption" in name_lower:
            score = 120.0
        elif "afterimage" in name_lower:
            score = 135.0
        elif "echo form" in name_lower:
            score = 145.0
        elif "electrodynamics" in name_lower:
            score = 135.0
        elif "creative ai" in name_lower:
            score = 130.0
        # Reduce priority for expensive powers if not enough energy
        if cost > energy:
            score = -1  # Can't play
        return score

    # --- Block assessment ---
    need_block = incoming > hp * 0.3 or incoming > 15
    block_urgency = 0.0
    if incoming > 0:
        unblocked = max(0, incoming - block)
        if unblocked > hp * 0.4:
            block_urgency = 2.5  # Very urgent
        elif unblocked > hp * 0.25:
            block_urgency = 2.0
        elif unblocked > 10:
            block_urgency = 1.5
        else:
            block_urgency = 0.5

    # Special: if no incoming damage, block is nearly worthless
    if incoming == 0:
        block_urgency = 0.1

    # --- Attack scoring ---
    if ctype == "Attack" and dmg > 0:
        # Base damage value
        score = dmg * 1.0

        # Vulnerable multiplier — check if target has vulnerable
        target_idx = find_lowest_hp_enemy(enemies)
        target = next((e for e in enemies if e.get("index") == target_idx), None)
        if target and enemy_has_debuff(target, "vulnerable"):
            score *= 1.5

        # AoE multiplier (if targets all enemies)
        target_type = card.get("target_type", "")
        if target_type in ("AllEnemy", "AllEnemies") and len(enemies) > 1:
            score *= len(enemies) * 0.8

        # Can we kill an enemy? Huge bonus for removing a damage source
        if target:
            target_hp = target.get("hp", 999)
            target_block = target.get("block", 0)
            effective_hp = target_hp + target_block
            if dmg >= effective_hp:
                score += 20  # Kill bonus

        # Apply vulnerability scoring
        if "vulnerable" in str(stats).lower() or "vulnerablepower" in stats:
            score += 8  # Applying vulnerable is very valuable

        # Weak application
        if "weak" in str(stats).lower() or "weakpower" in stats:
            score += 6

        # If we need block badly and this is pure attack, reduce priority
        if need_block and block_urgency >= 2.0 and blk == 0:
            score *= 0.4

        # If we're about to die, still prioritize killing if we can kill everything
        total_enemy_hp = sum(e.get("hp", 0) + e.get("block", 0) for e in enemies)
        if incoming > hp + block and dmg >= total_enemy_hp:
            score += 50  # Kill or be killed

    # --- Skill scoring ---
    elif ctype == "Skill":
        if blk > 0:
            score = blk * block_urgency
            # Cards that give both block and damage/debuff
            if dmg > 0:
                score += dmg * 0.8
        elif dmg > 0:
            score = dmg * 0.8
        else:
            # Utility skills (draw, energy, etc.)
            score = 5.0
            # Draw cards
            if "cards" in stats and stats.get("cards", 0) > 0:
                score += stats["cards"] * 3
            # Energy generation
            if "energy" in stats and stats.get("energy", 0) > 0:
                score += stats["energy"] * 4

    # --- Mixed cards (block + damage) ---
    if blk > 0 and dmg > 0:
        score = max(score, blk * block_urgency + dmg * 0.8)

    # --- 0-cost bonus (free value) ---
    if cost == 0:
        score += 5

    # --- Exhaust bonus (deck thinning) ---
    deck_size = player.get("deck_size", 10)
    keywords = card.get("keywords") or []
    if isinstance(keywords, list) and "exhaust" in [k.lower() for k in keywords if isinstance(k, str)]:
        if deck_size > 15:
            score += 3

    # --- Value/cost ratio ---
    # Don't play expensive low-value cards
    if cost > 0:
        efficiency = score / cost
        # Penalize very inefficient cards slightly
        if efficiency < 3 and cost >= 2:
            score -= 2

    # --- Bloodletting special case ---
    if "bloodletting" in name_lower:
        if hp <= 10:
            score = -10  # Don't suicide
        elif hp > 20:
            score = 15  # Energy generation is good
        else:
            score = 5

    # --- Whirlwind at 0 energy ---
    if "whirlwind" in name_lower and energy == 0:
        score = -10

    # --- Skip HP-costly cards at low HP ---
    if hp_loss > 0 and hp <= hp_loss + 5:
        score = -10

    return score


def sort_hand_for_play(hand, energy, enemies, state, is_boss=False):
    """Sort playable cards by score. Returns ordered list of card dicts."""
    playable = [c for c in hand if c.get("can_play", False) and c.get("cost", 99) <= energy]

    for card in playable:
        card["_score"] = score_card(card, energy, enemies, state, is_boss)

    # Filter out negative-score cards (they're actively harmful)
    playable = [c for c in playable if c.get("_score", 0) > 0]

    # Sort by score descending
    playable.sort(key=lambda c: -c.get("_score", 0))
    return playable


# ==========================================================================
# Potion strategy
# ==========================================================================

def should_use_potion(state, enemies, is_boss):
    """Determine if we should use a potion this turn."""
    player = state.get("player", {})
    hp = player.get("hp", 0)
    max_hp = player.get("max_hp", 1)
    incoming = calc_incoming_damage(enemies)
    block = player.get("block", 0)

    # Always use potions in boss fights (they don't carry over acts)
    if is_boss:
        return True

    # Use if incoming will kill us
    if incoming > 0 and hp + block <= incoming:
        return True

    # Use if HP is very low
    if hp < max_hp * 0.2:
        return True

    # Use if incoming is very high
    if incoming > 20 and block < incoming * 0.5:
        return True

    return False


def pick_potion_to_use(state, enemies, is_boss):
    """Pick the best potion to use. Returns (potion_index, needs_target) or None."""
    player = state.get("player", {})
    potions = player.get("potions", [])
    hp = player.get("hp", 0)
    max_hp = player.get("max_hp", 1)
    incoming = calc_incoming_damage(enemies)

    best = None
    best_priority = -1

    for pot in potions:
        if not pot or pot.get("is_empty", True):
            continue

        idx = pot.get("index", 0)
        name_lower = (pot.get("name", "") or "").lower()
        target_type = pot.get("target_type", "")
        needs_target = target_type == "AnyEnemy"
        priority = 0

        # Power/buff potions: use early in boss fights
        if any(kw in name_lower for kw in ["strength", "dexterity", "focus", "attack",
                                            "speed", "energy", "blessing"]):
            if is_boss:
                priority = 10
            else:
                priority = 3

        # Block potions: use when incoming damage is high
        elif "block" in name_lower or "shield" in name_lower:
            if incoming > 20:
                priority = 8
            elif incoming > 10:
                priority = 5
            else:
                priority = 1

        # Damage potions: use on low HP enemies or in boss fights
        elif any(kw in name_lower for kw in ["fire", "explosive", "poison", "damage"]):
            if is_boss:
                priority = 7
            else:
                # Check if it can kill an enemy
                priority = 6

        # Healing potions: use when HP is low
        elif any(kw in name_lower for kw in ["blood", "heal", "fairy", "fruit"]):
            if hp < max_hp * 0.3:
                priority = 9
            elif hp < max_hp * 0.5:
                priority = 4
            else:
                priority = 1

        # Draw/utility potions
        elif any(kw in name_lower for kw in ["bottled", "colorless", "potion"]):
            if is_boss:
                priority = 5
            else:
                priority = 2

        # Default: use in boss fights
        else:
            if is_boss:
                priority = 4
            else:
                priority = 1

        if priority > best_priority:
            best_priority = priority
            best = (idx, needs_target)

    if best_priority <= 0:
        return None
    return best


# ==========================================================================
# Card reward strategy
# ==========================================================================

def pick_card_reward(cards, character, state):
    """Pick the best card reward or skip to avoid deck bloat."""
    player = state.get("player", {})
    deck_size = player.get("deck_size", 0)
    wants = CHARACTER_WANTS.get(character, set())
    archetype = detect_deck_archetype(state, character)

    # Never take curses
    non_curse = [c for c in cards if c.get("type", "").lower() != "curse"]
    if not non_curse:
        return None

    # Score each card
    best_idx = None
    best_score = -1

    for card in non_curse:
        name = get_card_name(card)
        name_lower = name.lower()
        ctype = card.get("type", "")
        rarity = card.get("rarity", "Common")
        stats = card.get("stats") or {}
        after_upgrade = card.get("after_upgrade") or {}
        card_cost = card.get("cost", card.get("card_cost", 1))

        score = 0.0

        # Power cards: almost always take them (they scale)
        if ctype == "Power":
            score = 50

        # Rare cards: almost always take them
        if rarity == "Rare":
            score += 30
        elif rarity == "Uncommon":
            score += 15

        # Character-specific wants
        if name_lower in wants:
            score += 25

        # Archetype synergy bonus
        if archetype and character in ARCHETYPE_KEYWORDS:
            for arch, keywords in ARCHETYPE_KEYWORDS[character].items():
                if arch == archetype and name_lower in keywords:
                    score += 15  # Matches our archetype
                    break

        # Card type scoring
        if ctype == "Attack":
            dmg = stats.get("damage", 0)
            score += min(dmg * 0.5, 15)
            # Vulnerability application
            if "vulnerablepower" in stats or "vulnerable" in str(stats).lower():
                score += 8
        elif ctype == "Skill":
            blk = stats.get("block", 0)
            score += min(blk * 0.4, 10)
            # Draw cards
            if "cards" in stats:
                score += stats["cards"] * 3

        # 0-cost cards are great
        if card_cost == 0:
            score += 8

        # Skip threshold: if deck > 20, only take really good cards
        if deck_size > 20 and score < 35:
            continue
        # Moderate threshold at 15-20
        if deck_size > 15 and score < 20:
            continue

        if score > best_score:
            best_score = score
            best_idx = card["index"]

    return best_idx


# ==========================================================================
# Map strategy
# ==========================================================================

def pick_map_node(choices, player, floor):
    """Pick the best map node based on HP and floor."""
    hp = player.get("hp", 0)
    max_hp = player.get("max_hp", 1)
    hp_ratio = hp / max(max_hp, 1)
    floor = floor or 0

    # Before boss (floor 13+): seek rest to heal up
    if floor >= 13:
        if hp_ratio < 0.8:
            type_prio = {"RestSite": 0, "Treasure": 1, "Shop": 2, "Event": 3,
                         "Unknown": 4, "Monster": 5, "Ancient": 8, "Elite": 9, "Boss": 10}
        else:
            type_prio = {"Monster": 0, "Treasure": 1, "RestSite": 2, "Event": 3,
                         "Shop": 4, "Unknown": 5, "Ancient": 8, "Elite": 9, "Boss": 10}
    elif hp_ratio < 0.4:
        # Low HP: prioritize healing and safety
        type_prio = {"RestSite": 0, "Event": 1, "Shop": 2, "Treasure": 3,
                     "Unknown": 4, "Monster": 5, "Ancient": 6, "Elite": 8, "Boss": 9}
    elif hp_ratio < 0.7:
        # Medium HP: fight but be cautious
        type_prio = {"Monster": 0, "Treasure": 1, "Event": 2, "Shop": 3,
                     "Unknown": 4, "RestSite": 5, "Ancient": 6, "Elite": 7, "Boss": 8}
    else:
        # Full HP: elites give relics, very powerful
        type_prio = {"Elite": 0, "Treasure": 1, "Monster": 2, "Event": 3,
                     "Unknown": 4, "Shop": 5, "RestSite": 6, "Ancient": 7, "Boss": 8}

    # Always take treasure rooms if available
    for c in choices:
        if c.get("type") == "Treasure":
            return c

    choices_sorted = sorted(choices, key=lambda c: type_prio.get(c.get("type", ""), 99))
    return choices_sorted[0]


# ==========================================================================
# Rest site strategy
# ==========================================================================

def pick_rest_option(state, character, floor):
    """Choose rest site action: heal or smith."""
    options = state.get("options", [])
    enabled = [o for o in options if o.get("is_enabled", True)]
    player = state.get("player", {})
    hp = player.get("hp", 0)
    max_hp = player.get("max_hp", 1)
    hp_ratio = hp / max(max_hp, 1)

    heal = next((o for o in enabled if o.get("option_id") == "HEAL"), None)
    smith = next((o for o in enabled if o.get("option_id") == "SMITH"), None)

    # Near boss: heal aggressively
    if floor and floor >= 13:
        if hp_ratio < 0.9 and heal:
            return heal
        elif smith:
            return smith
        return heal or (enabled[0] if enabled else None)

    # Normal: heal if below 50%, smith if above
    if hp_ratio < 0.5 and heal:
        return heal

    # Smith if we have good upgrade targets
    if smith and hp_ratio >= 0.5:
        deck = player.get("deck", [])
        good_targets = GOOD_UPGRADES.get(character, set())
        has_good_target = any(
            not c.get("upgraded", False) and get_card_name(c).lower() in good_targets
            for c in deck
        )
        if has_good_target:
            return smith

    # Default: heal if below 65%, otherwise smith
    if hp_ratio < 0.65 and heal:
        return heal
    if smith:
        return smith
    if heal:
        return heal
    return enabled[0] if enabled else None


# ==========================================================================
# Smith (card select for upgrade)
# ==========================================================================

def pick_card_to_upgrade(cards, character):
    """Pick the best card to upgrade from a selection."""
    good_targets = GOOD_UPGRADES.get(character, set())

    # First pass: known good upgrades
    for card in cards:
        name_lower = get_card_name(card).lower()
        if name_lower in good_targets:
            return card["index"]

    # Second pass: powers > attacks > skills, prefer higher rarity
    best = None
    best_score = -1
    for card in cards:
        ctype = card.get("type", "")
        rarity = card.get("rarity", "Common")
        score = 0

        if ctype == "Power":
            score = 30
        elif ctype == "Attack":
            score = 20
        elif ctype == "Skill":
            score = 10

        if rarity == "Rare":
            score += 20
        elif rarity == "Uncommon":
            score += 10

        # Don't upgrade basic strikes/defends (low value)
        name_lower = get_card_name(card).lower()
        if name_lower in ("strike", "defend"):
            score -= 15

        if score > best_score:
            best_score = score
            best = card["index"]

    return best if best is not None else 0


# ==========================================================================
# Shop strategy
# ==========================================================================

def handle_shop(state, character, send_fn):
    """Handle shop decisions: buy powers, remove strikes, buy potions.

    Conservative approach: buy power cards, buy wanted cards, then leave.
    Card removal is handled via the card_select decision handler if triggered.
    """
    player = state.get("player", {})
    gold = player.get("gold", 0)
    deck_size = player.get("deck_size", 0)
    wants = CHARACTER_WANTS.get(character, set())

    shop_cards = state.get("cards", [])
    removal_cost = state.get("card_removal_cost", 75)
    can_remove = state.get("card_removal_available", False)

    # Priority 1: Remove a Strike (deck thinning is the most powerful shop action)
    if can_remove and gold >= removal_cost and deck_size > 8:
        state = send_fn({
            "cmd": "action",
            "action": "remove_card",
            "args": {}
        })
        if state.get("type") != "error":
            gold -= removal_cost
        # remove_card triggers card_select — return to main loop to handle it
        if state.get("decision") != "shop":
            return state
        # Re-read shop state
        player = state.get("player", {})
        gold = player.get("gold", 0)
        shop_cards = state.get("cards", [])

    # Priority 2: Buy power cards if affordable
    for card in shop_cards:
        if not card.get("is_stocked", False):
            continue
        cost = card.get("cost", 999)
        ctype = card.get("type", "")

        if ctype == "Power" and cost <= gold:
            state = send_fn({
                "cmd": "action",
                "action": "buy_card",
                "args": {"card_index": card["index"]}
            })
            if state.get("type") != "error":
                gold -= cost
            if state.get("decision") != "shop":
                return state
            break  # Only buy one power to be safe

    # Priority 3: Buy wanted cards if affordable
    shop_cards = state.get("cards", []) if state.get("decision") == "shop" else shop_cards
    for card in shop_cards:
        if not card.get("is_stocked", False):
            continue
        cost = card.get("cost", 999)
        name_lower = (card.get("name", "") or "").lower()
        if name_lower in wants and cost <= gold and cost <= 100:
            state = send_fn({
                "cmd": "action",
                "action": "buy_card",
                "args": {"card_index": card["index"]}
            })
            if state.get("type") != "error":
                gold -= cost
            if state.get("decision") != "shop":
                return state
            break

    # Leave shop
    state = send_fn({"cmd": "action", "action": "leave_room"})
    return state


# ==========================================================================
# Event strategy
# ==========================================================================

def pick_event_option(state, character):
    """Pick the best event option."""
    options = state.get("options", [])
    unlocked = [o for o in options if not o.get("is_locked")]
    if not unlocked:
        return options[0] if options else None

    player = state.get("player", {})
    hp = player.get("hp", 0)
    max_hp = player.get("max_hp", 1)
    hp_ratio = hp / max(max_hp, 1)
    event_name = (state.get("event_name", "") or "").lower()

    # Neow event: prefer relic > rare card > other
    if "neow" in event_name:
        for o in unlocked:
            title = (o.get("title", "") or "").lower()
            desc = (o.get("description", "") or "").lower()
            # Prefer options that give relics
            if "relic" in title or "relic" in desc:
                return o
        for o in unlocked:
            title = (o.get("title", "") or "").lower()
            desc = (o.get("description", "") or "").lower()
            if "rare" in title or "rare" in desc:
                return o

    # For other events: prefer options that don't cost HP when low
    if hp_ratio < 0.5:
        safe = [o for o in unlocked if "hp" not in (o.get("description", "") or "").lower()
                or "gain" in (o.get("description", "") or "").lower()]
        if safe:
            return safe[0]

    return unlocked[0]


# ==========================================================================
# Neow (first event) strategy
# ==========================================================================

def pick_neow_option(state, character):
    """Pick the best Neow (starting) option."""
    options = state.get("options", [])
    unlocked = [o for o in options if not o.get("is_locked")]
    if not unlocked:
        return options[0] if options else None

    # Score each option
    best = None
    best_score = -1
    for o in unlocked:
        title = (o.get("title", "") or "").lower()
        desc = (o.get("description", "") or "").lower()
        score = 0

        # Relics are very strong
        if "relic" in title or "relic" in desc:
            score += 40
            # Multiple relics
            vars_data = o.get("vars") or {}
            if vars_data.get("Relics", 0) >= 2:
                score += 20

        # Rare cards
        if "rare" in desc and "card" in desc:
            score += 35

        # Max HP increase
        if "max hp" in desc or "maxhp" in title.lower():
            score += 20

        # Gold
        if "gold" in desc:
            score += 15

        # Healing
        if "heal" in desc:
            score += 10

        # Card removal
        if "remove" in desc:
            score += 25

        # Upgrade
        if "upgrade" in desc:
            score += 18

        # Penalty for options with downsides
        if "lose" in desc or "damage" in desc or "curse" in desc:
            score -= 15

        if score > best_score:
            best_score = score
            best = o

    return best or unlocked[0]


# ==========================================================================
# Main game loop
# ==========================================================================

def play_tuned_run(seed, character="Ironclad", verbose=False, log=True):
    """Play a complete run with tuned heuristics."""
    logger = GameLogger(character, seed, enabled=log)

    game_dir_candidates = [
        os.path.expanduser("~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_arm64"),
        os.path.expanduser("~/Library/Application Support/Steam/steamapps/common/Slay the Spire 2/SlayTheSpire2.app/Contents/Resources/data_sts2_macos_x86_64"),
    ]
    env = os.environ.copy()
    for gd in game_dir_candidates:
        if os.path.isdir(gd):
            env["STS2_GAME_DIR"] = gd
            break

    proc = subprocess.Popen(
        [DOTNET, "run", "--no-build", "--project", PROJECT],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,
        env=env,
    )

    def read_json_line(timeout_sec=10):
        deadline = time.time() + timeout_sec
        while True:
            remaining = deadline - time.time()
            if remaining <= 0:
                raise RuntimeError("No response from simulator (timeout)")
            ready, _, _ = select.select([proc.stdout], [], [], min(remaining, 5))
            if not ready:
                if proc.poll() is not None:
                    raise RuntimeError("No response from simulator (EOF)")
                continue
            resp_line = proc.stdout.readline().strip()
            if not resp_line:
                raise RuntimeError("No response from simulator (EOF)")
            if resp_line.startswith("{"):
                return json.loads(resp_line)

    def send(cmd):
        line = json.dumps(cmd)
        if verbose:
            print(f"  > {line[:200]}")
        logger.log_action(cmd)
        proc.stdin.write(line + "\n")
        proc.stdin.flush()
        resp = read_json_line()
        logger.log_state(resp)
        if verbose:
            rtype = resp.get("type", "?")
            decision = resp.get("decision", "")
            if rtype == "decision":
                p = resp.get("player", {})
                ctx = resp.get("context", {})
                print(f"  < {decision} act={ctx.get('act','?')} "
                      f"floor={ctx.get('floor','?')} "
                      f"hp={p.get('hp','?')}/{p.get('max_hp','?')} "
                      f"gold={p.get('gold','?')} deck={p.get('deck_size','?')}")
            else:
                print(f"  < {json.dumps(resp)[:200]}")
        return resp

    try:
        ready = read_json_line()
        if ready.get("type") != "ready":
            return {"victory": False, "seed": seed, "error": "bad_init"}

        state = send({"cmd": "start_run", "character": character, "seed": seed})

        step = 0
        max_steps = 800
        end_turn_count = 0
        last_known_floor = 0
        potion_used_this_combat = False
        neow_done = False
        failed_card_ids = set()  # Track card IDs that fail to play (simulator bugs)
        last_combat_state_key = None  # For detecting truly stuck states

        while step < max_steps:
            step += 1

            if state.get("type") == "error":
                state = send({"cmd": "action", "action": "proceed"})
                if state.get("type") == "error":
                    break
                continue

            decision = state.get("decision", "")
            context = state.get("context", {})
            floor = context.get("floor") or state.get("floor") or last_known_floor
            if floor:
                last_known_floor = floor

            # ============================================================
            # GAME OVER
            # ============================================================
            if decision == "game_over":
                victory = state.get("victory", False)
                player = state.get("player", {})
                return {
                    "victory": victory,
                    "seed": seed,
                    "steps": step,
                    "act": context.get("act") or state.get("act"),
                    "floor": floor,
                    "hp": player.get("hp"),
                    "max_hp": player.get("max_hp"),
                    "deck_size": player.get("deck_size"),
                    "character": character,
                }

            # ============================================================
            # MAP SELECT
            # ============================================================
            elif decision == "map_select":
                choices = state.get("choices", [])
                if not choices:
                    break
                player = state.get("player", {})
                pick = pick_map_node(choices, player, floor)
                state = send({
                    "cmd": "action",
                    "action": "select_map_node",
                    "args": {"col": pick["col"], "row": pick["row"]}
                })
                potion_used_this_combat = False
                end_turn_count = 0
                failed_card_ids = set()  # Reset per combat

            # ============================================================
            # COMBAT
            # ============================================================
            elif decision == "combat_play":
                hand = state.get("hand", [])
                energy = state.get("energy", 0)
                enemies = state.get("enemies", [])
                player = state.get("player", {})
                is_boss = floor is not None and floor >= 15

                # Potion usage
                if not potion_used_this_combat or is_boss:
                    if should_use_potion(state, enemies, is_boss):
                        pot_info = pick_potion_to_use(state, enemies, is_boss)
                        if pot_info:
                            pidx, needs_target = pot_info
                            args = {"potion_index": pidx}
                            if needs_target and enemies:
                                if is_boss:
                                    args["target_index"] = find_highest_hp_enemy(enemies)
                                else:
                                    args["target_index"] = find_lowest_hp_enemy(enemies)
                            state = send({
                                "cmd": "action",
                                "action": "use_potion",
                                "args": args
                            })
                            potion_used_this_combat = True
                            if state.get("decision") != "combat_play":
                                continue
                            enemies = state.get("enemies", [])
                            hand = state.get("hand", [])
                            energy = state.get("energy", 0)

                # Filter out cards that are known to fail in the simulator
                filtered_hand = [c for c in hand if c.get("id", "") not in failed_card_ids]

                # Play cards by score
                playable = sort_hand_for_play(filtered_hand, energy, enemies, state, is_boss)

                if playable:
                    end_turn_count = 0
                    card = playable[0]
                    args = {"card_index": card["index"]}

                    # Target selection
                    if card.get("target_type") == "AnyEnemy" and enemies:
                        if is_boss and len(enemies) > 1:
                            # In boss fights: kill minions first (lower HP), then boss
                            max_hp_enemy = max(e.get("hp", 0) for e in enemies)
                            minions = [e for e in enemies if e.get("hp", 0) < max_hp_enemy]
                            if minions:
                                args["target_index"] = min(minions, key=lambda e: e.get("hp", 9999))["index"]
                            else:
                                args["target_index"] = find_lowest_hp_enemy(enemies)
                        else:
                            # Focus fire: lowest HP enemy to reduce damage sources
                            args["target_index"] = find_lowest_hp_enemy(enemies)

                    state = send({
                        "cmd": "action",
                        "action": "play_card",
                        "args": args
                    })

                    # If the card failed to play, mark it and recover
                    if state.get("type") == "error":
                        card_id = card.get("id", "")
                        if card_id:
                            failed_card_ids.add(card_id)
                        state = send({"cmd": "action", "action": "proceed"})
                        continue
                else:
                    # No playable cards: end turn
                    state = send({"cmd": "action", "action": "end_turn"})
                    if state.get("type") == "error":
                        state = send({"cmd": "action", "action": "proceed"})

            # ============================================================
            # EVENT CHOICE
            # ============================================================
            elif decision == "event_choice":
                event_name = (state.get("event_name", "") or "").lower()

                if "neow" in event_name and not neow_done:
                    neow_done = True
                    choice = pick_neow_option(state, character)
                else:
                    choice = pick_event_option(state, character)

                if choice:
                    state = send({
                        "cmd": "action",
                        "action": "choose_option",
                        "args": {"option_index": choice["index"]}
                    })
                    if state and state.get("type") == "error":
                        state = send({"cmd": "action", "action": "leave_room"})
                else:
                    state = send({"cmd": "action", "action": "leave_room"})

            # ============================================================
            # REST SITE
            # ============================================================
            elif decision == "rest_site":
                choice = pick_rest_option(state, character, floor)
                if choice:
                    state = send({
                        "cmd": "action",
                        "action": "choose_option",
                        "args": {"option_index": choice["index"]}
                    })
                    if state and state.get("type") == "error":
                        state = send({"cmd": "action", "action": "leave_room"})
                else:
                    state = send({"cmd": "action", "action": "leave_room"})

            # ============================================================
            # CARD REWARD
            # ============================================================
            elif decision == "card_reward":
                cards = state.get("cards", [])
                pick_idx = pick_card_reward(cards, character, state) if cards else None

                if pick_idx is not None:
                    state = send({
                        "cmd": "action",
                        "action": "select_card_reward",
                        "args": {"card_index": pick_idx}
                    })
                    if state.get("type") == "error":
                        # Fallback: skip if select fails
                        state = send({"cmd": "action", "action": "skip_card_reward"})
                else:
                    state = send({"cmd": "action", "action": "skip_card_reward"})
                if state.get("type") == "error":
                    state = send({"cmd": "action", "action": "proceed"})

            # ============================================================
            # CARD SELECT (smith upgrade, event card pick, etc.)
            # ============================================================
            elif decision == "card_select":
                cards = state.get("cards", [])
                if cards:
                    # Check context: is this a smith upgrade or event?
                    room_type = context.get("room_type", "")
                    if room_type == "RestSite":
                        # Smith: pick best card to upgrade
                        idx = pick_card_to_upgrade(cards, character)
                        state = send({"cmd": "action", "action": "select_cards",
                                     "args": {"indices": str(idx)}})
                    elif room_type == "Shop":
                        # Shop card removal: pick worst card (strikes first)
                        worst = None
                        worst_score = 999
                        for card in cards:
                            name_lower = get_card_name(card).lower()
                            score = 50  # default
                            if name_lower == "strike":
                                score = 0  # Remove strikes first
                            elif name_lower == "defend":
                                score = 10
                            elif card.get("type", "") == "Curse":
                                score = -10  # Remove curses ASAP
                            elif "status" in (card.get("type", "") or "").lower():
                                score = -5
                            if score < worst_score:
                                worst_score = score
                                worst = card["index"]
                        state = send({"cmd": "action", "action": "select_cards",
                                     "args": {"indices": str(worst or 0)}})
                    else:
                        # Default: pick first card
                        state = send({"cmd": "action", "action": "select_cards",
                                     "args": {"indices": "0"}})
                else:
                    state = send({"cmd": "action", "action": "skip_select"})

            # ============================================================
            # SHOP
            # ============================================================
            elif decision == "shop":
                state = handle_shop(state, character, send)

            # ============================================================
            # BUNDLE SELECT
            # ============================================================
            elif decision == "bundle_select":
                state = send({"cmd": "action", "action": "select_bundle",
                             "args": {"bundle_index": 0}})

            # ============================================================
            # FALLBACK
            # ============================================================
            elif decision == "unknown":
                state = send({"cmd": "action", "action": "proceed"})
            else:
                state = send({"cmd": "action", "action": "proceed"})
                if state.get("type") == "error" or state.get("decision") == decision:
                    state = send({"cmd": "action", "action": "proceed"})

        return {"victory": False, "seed": seed, "steps": step, "timeout": True,
                "character": character, "floor": last_known_floor}

    except Exception as e:
        import traceback
        traceback.print_exc()
        return {"victory": False, "seed": seed,
                "steps": step if 'step' in dir() else 0,
                "error": str(e), "character": character,
                "floor": last_known_floor if 'last_known_floor' in dir() else 0}

    finally:
        logger.close()
        if logger.path and verbose:
            print(f"  [log] Saved to {logger.path}")
        try:
            proc.stdin.write(json.dumps({"cmd": "quit"}) + "\n")
            proc.stdin.flush()
        except:
            pass
        try:
            proc.terminate()
            proc.wait(timeout=5)
        except:
            proc.kill()


# ==========================================================================
# CLI entry point
# ==========================================================================

def main():
    parser = argparse.ArgumentParser(description="Tuned heuristic bot for STS2")
    parser.add_argument("--character", default="Ironclad",
                        choices=["Ironclad", "Silent", "Defect", "Regent", "Necrobinder"],
                        help="Character to play")
    parser.add_argument("--seed", default="42", help="Seed (single or start-end range)")
    parser.add_argument("--seeds", type=str, default=None,
                        help="Seed range, e.g. 60001-60020")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--no-log", action="store_true", help="Disable game logging")
    args = parser.parse_args()

    # Determine seeds
    if args.seeds:
        parts = args.seeds.split("-")
        seeds = list(range(int(parts[0]), int(parts[1]) + 1))
    else:
        seeds = [args.seed]

    character = args.character

    print("=" * 70)
    print(f"  TUNED BOT — {len(seeds)} game(s)")
    print(f"  Character: {character}")
    print(f"  Seeds: {seeds[0]}" + (f"-{seeds[-1]}" if len(seeds) > 1 else ""))
    print("=" * 70)

    results = []
    for i, seed in enumerate(seeds):
        t0 = time.time()
        result = play_tuned_run(str(seed), character=character,
                                verbose=args.verbose, log=not args.no_log)
        elapsed = time.time() - t0
        results.append(result)

        if result:
            status = "WIN" if result.get("victory") else "LOSS"
            if result.get("timeout"):
                status = "TIMEOUT"
            if result.get("error"):
                status = f"ERR({result['error'][:20]})"
            floor = result.get("floor", "?")
            act = result.get("act", "?")
            hp = result.get("hp", "?")
            max_hp = result.get("max_hp", "?")
            deck = result.get("deck_size", "?")
            print(f"  [{i+1:3d}/{len(seeds)}] seed={str(seed):>6} {status:12s} "
                  f"act={act} floor={str(floor):>3} "
                  f"hp={hp}/{max_hp} deck={deck} ({elapsed:.1f}s)")
        else:
            print(f"  [{i+1:3d}/{len(seeds)}] seed={seed} NO RESULT")

    # Summary
    print("\n" + "=" * 70)
    print("  SUMMARY")
    print("=" * 70)

    floors = [r.get("floor", 0) for r in results if r and isinstance(r.get("floor"), (int, float))]
    wins = sum(1 for r in results if r and r.get("victory"))
    errors = sum(1 for r in results if r and r.get("error"))
    timeouts = sum(1 for r in results if r and r.get("timeout"))

    if floors:
        avg_floor = sum(floors) / len(floors)
        max_floor = max(floors)
        min_floor = min(floors)
        floor15 = sum(1 for f in floors if f >= 15)
    else:
        avg_floor = max_floor = min_floor = 0
        floor15 = 0

    print(f"  Games: {len(results)}")
    print(f"  Wins: {wins}/{len(results)} ({100*wins/max(len(results),1):.0f}%)")
    print(f"  Errors: {errors}, Timeouts: {timeouts}")
    print(f"  Floor — avg: {avg_floor:.1f}, max: {max_floor}, min: {min_floor}")
    print(f"  Reached floor 15+: {floor15}/{len(results)}")
    print("=" * 70)

    return results


if __name__ == "__main__":
    main()
