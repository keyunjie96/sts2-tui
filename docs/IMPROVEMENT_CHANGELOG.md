# Self-Improvement Changelog

Tracks what the Auditor → Reviewer → Fixer pipeline changes each round.

---

## Round 5 — 2026-03-29

**Auditor:** Used 110k data from Round 4 (all 5 characters, no crashes).
**Reviewer:** Found 2 new gaps — engine now sends `star_cost` for shop and card_select (previously engine-side gap, now TUI-side).
**Fixer:** Fixed both gaps.

### TUI code fixes (2 changes)
- [x] `star_cost` in shop — `_ShopItem` gains star_cost slot, `_render_card_line()` shows `(cost+★star_cost)` for Regent cards (`shop.py`)
- [x] `star_cost` in card_select — GenericScreen shows `+★{star_cost}` after energy cost (`generic.py`)

### Observations
- Silent 110002 clean — no LegSweep crash (was in 100k)
- Innate keyword encountered for first time (Backstab), already handled
- 7 new enemy names, 6 new event names — all standard schemas
- Pipeline converging: only 2 new gaps this round (vs 11 in Round 4)

---

## Round 4 — 2026-03-29

**Auditor:** Played 5 games (seeds 110001-110005, all completed).
**Reviewer:** Cross-referenced 100k data against TUI screens. Found 11 new gaps from new engine fields.
**Fixer:** Resolved all 11 new gaps.

### New engine fields discovered (100k vs 90k data)
- `potion_rewards` and `potion_slots_full` on card_reward (TUI already handled)
- `rarity`, `upgraded`, `after_upgrade` on combat hand cards (NEW — passed through)
- `rarity` on shop cards (engine-side gap now FIXED)
- `rarity` on card_select cards (NEW)
- `from_event` on card_reward (informational, by-design)
- New "Sleep" intent type on enemies

### TUI code fixes (6 changes)
- [x] Potion reward descriptions resolved — template vars `{Block}`, `{Damage}` etc. now use shop's `_enrich_potion_description()` (`card_reward.py`)
- [x] Upgraded "+" suffix on combat hand cards — `extract_hand()` passes `upgraded`, CardWidget shows "+" (`controller.py`, `combat.py`)
- [x] Rarity and after_upgrade passed through in `extract_hand()` (`controller.py`)
- [x] Rarity badges shown on card_select options in GenericScreen (`generic.py`)
- [x] Sleep intent handler — dedicated icon and cyan color (`controller.py`, `combat.py`, `bridge_state.py`)
- [x] Rarity display consistency — now shown on card_reward, shop, and card_select

### Engine-side gaps (annotated)
- LegSweep crash (Silent seed 100002) — engine marks `can_play: true` but fails to execute
- bundle_select cards lack rarity/keywords/after_upgrade (engine doesn't send them)
- bundle_select has no bundle-level name (engine-side)

---

## Round 3 — 2026-03-29

**Auditor:** Played 5 games (seeds 100001-100005). Silent crashed on LegSweep (engine bug).
**Fixer:** Resolved all 33 unchecked items (0 remaining).

### TUI code fixes (3 changes)
- [x] `can_skip` respected in card_reward — skip button hidden and action blocked when `can_skip: false` (`card_reward.py`)
- [x] `room_type` displayed in combat TopBar with color coding: Boss=red, Elite=magenta, Monster=dim (`combat.py`)
- [x] Upgraded cards show "+" suffix and keyword icons (Exhaust, Ethereal, Innate, Retain, Sly) in generic screen for card_select/smith (`generic.py`)

### Already fixed (confirmed working)
- [x] Keywords in card_reward — `extract_reward_cards()` already passes keywords, `RewardCardWidget` already renders icons

### Engine-side gaps (annotated, TUI cannot fix)
- star_cost not sent for shop cards (Regent impact)
- rarity not sent for shop cards
- effective_block not sent (TUI approximates via Dexterity + Frail)
- heal amount not sent (TUI uses ~30% estimate)
- smith upgradeable card list not sent
- enchantment/affliction not sent for reward cards (by design — combat-context properties)

### Redundancies closed (by-design omissions)
- 3x card `id` fields (internal, not player-facing)
- `intends_attack` (redundant with parsed intents)
- `text_key` (internal localization key)
- Top-level `act`, `act_name`, `floor` (duplicate context fields)
- Per-node `current` (duplicate of `current_coord`)
- `deck` in combat (cached from controller)
- `vars` dicts (used internally for description resolution)
- `boss` in combat (already visible as enemy widget)

### Bugs discovered
- Silent (seed 100002) crashed: "Card could not be played: LegSweep" — engine-side card playability bug

---

## Round 2 — 2026-03-29

**Auditor:** Played 5 games (seeds 90001-90005, all characters)
**Reviewer:** Cross-referenced engine JSON against TUI screens
**Result:** `tests/audit_gaps.md` — 199 checked, 33 unchecked, 9 partial

---

## Round 1 — 2026-03-29

**Auditor:** Played 5 games (seeds 80001-80005, all characters)
**Reviewer:** Initial audit pass
**Result:** First version of `tests/audit_gaps.md`
