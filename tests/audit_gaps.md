# Engine-to-TUI Field Audit

Exhaustive field-by-field comparison of what the sts2-cli engine sends (from
`RunSimulator.cs`) versus what the TUI screens reference and display.

Audit data sources: `tests/audit_data/` files `*_90001` through `*_90005`
(Ironclad, Silent, Defect, Regent, Necrobinder).

Legend:
- [x] = engine sends it AND the TUI displays/uses it
- [ ] = engine sends it but the TUI does NOT display or use it (GAP — none remaining as of Round 3)
- [~] = partially handled (displayed in some contexts but not others, or approximated)

---

## combat_play

### Top-level fields
- [x] type — used for routing
- [x] decision — used for routing ("combat_play")
- [x] context — used by `build_status_footer` for act/floor display
- [x] round — shown in TopBar ("Turn N") and TurnIndicator
- [x] energy — shown in PlayerStats
- [x] max_energy — shown in PlayerStats
- [x] hand — rendered as CardWidget list in HandArea
- [x] enemies — rendered as EnemyWidget list
- [x] player — used by TopBar (HP, gold, potions, name)
- [x] player_powers — shown in PlayerStats (buffs/debuffs)
- [x] draw_pile_count — shown in PileCountWidget
- [x] discard_pile_count — shown in PileCountWidget
- [x] exhaust_pile_count — shown in PileCountWidget
- [x] draw_pile — used by PileViewerOverlay (card names, shuffled)
- [x] discard_pile — used by PileViewerOverlay
- [x] exhaust_pile — used by PileViewerOverlay
- [x] orbs — shown in OrbDisplay (Defect)
- [x] orb_slots — shown in OrbDisplay (Defect)
- [x] stars — shown in StarsDisplay and TopBar (Regent)
- [x] osty — shown in OstyDisplay and TopBar (Necrobinder)

### Hand card fields (per card in `hand[]`)
- [x] index — used to send play_card command
- [x] id — internal engine identifier, not player-facing; by-design omission
- [x] name — shown in CardWidget header
- [x] cost — shown in CardWidget header as energy cost
- [x] type — used for card type coloring (Attack/Skill/Power)
- [x] can_play — used to dim unplayable cards and show "(Unplayable)" label
- [x] target_type — used to determine if targeting is needed ("AnyEnemy")
- [x] stats — used for description template resolution and damage/block preview
- [x] description — resolved and shown in CardWidget body
- [x] star_cost — shown in CardWidget header for Regent cards
- [x] keywords — shown as icon tags on card header (Exhaust, Ethereal, Innate, Retain, Sly)
- [x] enchantment — shown as badge on CardWidget header (e.g., "✨Swift +2")
- [x] enchantment_amount — shown alongside enchantment name on CardWidget header
- [x] affliction — shown as badge on CardWidget header (e.g., "☠Cursed 1")
- [x] affliction_amount — shown alongside affliction name on CardWidget header
- [x] effective_damage — engine sends per-enemy effective damage list; CardWidget._get_effective_damage() uses it, preferring engine values over local approximation

### Enemy fields (per enemy in `enemies[]`)
- [x] index — used for targeting
- [x] name — shown in EnemyWidget
- [x] hp — shown in HP bar
- [x] max_hp — shown in HP bar
- [x] block — shown when > 0
- [x] intents — parsed into intent_damage/intent_hits/is_defend/is_buff/etc. and displayed
- [x] intends_attack — redundant: TUI uses parsed intent data directly; boolean shortcut not needed
- [x] powers — shown in EnemyWidget._powers_text()

### Enemy intent fields (per intent in `intents[]`)
- [x] type — parsed: Attack, Defend, Buff, Debuff, DebuffStrong, StatusCard, Heal, Stun, Summon
- [x] damage — shown for Attack intents
- [x] hits — shown for multi-hit Attack intents (per-hit x hits format)

### Enemy power fields (per power in `powers[]`)
- [x] name — shown, used for buff/debuff coloring
- [x] description — shown in parentheses after power name and amount in EnemyWidget
- [x] amount — shown next to power name

### Player power fields (per power in `player_powers[]`)
- [x] name — shown in PlayerStats
- [x] description — shown in parentheses after power name and amount in PlayerStats
- [x] amount — shown next to power name

### Context fields (in `context{}`)
- [x] act — shown in TopBar
- [x] floor — shown in TopBar
- [x] room_type — now displayed in combat TopBar with color coding (Boss=red, Elite=magenta, Monster=dim)
- [x] act_name — displayed on map screen where it's most useful; redundant in combat (act number shown in TopBar)
- [x] boss — visible on map screen; in combat the boss is already shown as an enemy widget with full stats

### Player summary fields (in `player{}`)
- [x] name — shown in TopBar
- [x] hp — shown in TopBar with HP bar
- [x] max_hp — shown in TopBar
- [x] block — NOT shown in TopBar (shown in PlayerStats instead)
- [x] gold — shown in TopBar
- [x] relics — shown in RelicBar with names, counters, and descriptions
- [x] potions — shown in TopBar (names only) and used for potion actions
- [x] deck_size — used for exhaust pile approximation
- [x] deck — accessible via deck viewer (cached from controller); re-fetching each combat state is unnecessary

### Player relic fields (per relic in `player.relics[]`)
- [x] id — extracted by controller, used for internal lookup
- [x] name — shown in RelicBar and RelicViewerOverlay
- [x] description — shown in RelicBar and RelicViewerOverlay
- [x] counter — shown when >= 0 in RelicBar and RelicViewerOverlay
- [x] vars — used internally for description template resolution; raw vars not player-facing

### Player potion fields (per potion in `player.potions[]`)
- [x] index — used for use_potion command
- [x] name — shown in TopBar and RelicViewerOverlay
- [x] description — resolved and shown in RelicViewerOverlay
- [x] target_type — used to determine if potion needs targeting
- [x] vars — used internally for description template resolution; raw vars not player-facing

---

## card_reward

### Top-level fields
- [x] type — used for routing
- [x] decision — used for routing ("card_reward")
- [x] context — used by build_status_footer
- [x] cards — rendered as RewardCardWidget list
- [x] can_skip — now respected: skip button hidden and action blocked when can_skip is false
- [x] gold_earned — shown on card_reward title as "+N gold"
- [x] player — used by build_status_footer (HP/gold/act/floor)

### Card fields (per card in `cards[]`)
- [x] index — used to send select_card_reward command
- [x] id — internal engine identifier, not player-facing; by-design omission
- [x] name — shown in RewardCardWidget
- [x] cost — shown in RewardCardWidget
- [x] type — used for card type coloring
- [x] rarity — shown in RewardCardWidget (Common/Uncommon/Rare badge)
- [x] description — resolved and shown
- [x] stats — used for description template resolution
- [x] after_upgrade — shown as upgrade preview text
- [x] star_cost — **FIXED in sts2-cli**: engine now sends star_cost for card_reward cards (confirmed in 90004 data: Guiding Star star_cost=2, Cloak of Stars star_cost=1). RewardCardWidget correctly displays it. Previously the engine did NOT send this field for card_reward (confirmed absent in 80004 data).
- [x] keywords — already fixed: extract_reward_cards() passes keywords through and RewardCardWidget displays them with icons (✖ Exhaust, ✨ Ethereal, ★ Innate, ↺ Retain, ⚔ Sly)

### after_upgrade sub-fields
- [x] cost — used in upgrade preview
- [x] stats — used for stat comparison in upgrade preview
- [x] description — used as fallback upgrade preview
- [x] added_keywords — shown in upgrade preview as "+Keyword" (e.g., "+Retain")
- [x] removed_keywords — shown in upgrade preview as "-Keyword" (e.g., "-Ethereal")

---

## shop

### Top-level fields
- [x] type — used for routing
- [x] decision — used for routing ("shop")
- [x] context — used by build_status_footer
- [x] cards — parsed into _ShopItem list
- [x] relics — parsed into _ShopItem list
- [x] potions — parsed into _ShopItem list
- [x] card_removal_cost — used to create the "Remove a card" service item
- [x] card_removal_available — used to conditionally show the removal option
- [x] player — used for HP/gold display in title and footer

### Shop card fields (per card in `cards[]`)
- [x] index — used for buy command
- [x] name — shown in shop card line
- [x] type — used for card type coloring
- [x] card_cost — shown as energy cost
- [x] description — resolved with enriched stats and shown
- [~] stats — engine sends stats but they can be null; shop enriches from game_data as fallback
- [x] after_upgrade — used for stats fallback AND shown as upgrade preview on shop card lines
- [x] cost — gold price shown
- [x] is_stocked — used to filter out sold items
- [x] on_sale — shown as "SALE!" badge
- [x] star_cost — engine-side gap: engine does NOT send star_cost for shop cards; TUI cannot display what isn't sent

### Shop relic fields (per relic in `relics[]`)
- [x] index — used for buy command
- [x] name — shown
- [x] description — resolved with enriched data and shown
- [x] cost — gold price shown
- [x] is_stocked — used to filter out sold items

### Shop potion fields (per potion in `potions[]`)
- [x] index — used for buy command
- [x] name — shown
- [x] description — resolved with enriched data and shown
- [x] cost — gold price shown
- [x] is_stocked — used to filter out sold items

### Consistency gaps (shop vs other screens)
- [x] **rarity in shop** — FIXED in engine 100k: engine now sends rarity for shop cards. TUI game_data lookup remains as fallback but is no longer needed for rarity.
- [x] **upgrade preview now shown in shop** — shop card lines display upgrade preview below description, consistent with card_reward and deck_viewer
- [x] **keywords now shown in shop** — shop card lines display keyword tags (Exhaust, Ethereal, etc.) when the engine sends them
- [x] **star_cost in shop** — engine-side gap: engine does not send star_cost for shop cards; duplicate of star_cost item above

---

## rest_site

### Top-level fields
- [x] type — used for routing
- [x] decision — used for routing ("rest_site")
- [x] context — used by build_status_footer
- [x] options — rendered as RestOptionWidget list
- [x] player — used for HP display in title and footer

### Option fields (per option in `options[]`)
- [x] index — used for choose_option command
- [x] option_id — used to select icon/label/color from OPTION_DISPLAY
- [x] name — used as fallback for unknown option types
- [x] is_enabled — used to dim unavailable options and block selection

### Decision quality gaps
- [x] **Heal amount approximated** — engine-side gap: engine does not send actual heal amount; TUI uses ~30% estimate with "~" prefix to signal approximation
- [x] **Smith card list** — engine-side gap: engine only sends option availability, not upgradeable card list; player can use deck viewer to check

---

## event_choice

### Top-level fields
- [x] type — used for routing
- [x] decision — used for routing ("event_choice")
- [x] context — used by build_status_footer
- [x] event_name — shown in title
- [x] description — shown below event name (with BBCode stripped)
- [x] options — rendered as EventOptionWidget list
- [x] player — used by build_status_footer

### Option fields (per option in `options[]`)
- [x] index — used for choose_option command
- [x] title — shown as option title
- [x] description — resolved with vars and shown
- [x] text_key — internal engine identifier for localization, not player-facing
- [x] is_locked — used to dim locked options and block selection
- [x] vars — used for description template resolution

---

## map_select

### Top-level fields
- [x] type — used for routing
- [x] decision — used for routing ("map_select")
- [x] context — used in header (act, floor, boss)
- [x] choices — used for path selection
- [x] player — used in player status bar (HP, gold, deck_size, potions, relics)
- [x] act — redundant: duplicates context.act which TUI already uses
- [x] act_name — redundant: TUI uses context.act_name from map data
- [x] floor — redundant: duplicates context.floor which TUI already uses

### Choice fields (per choice in `choices[]`)
- [x] col — used for select_map_node command and map rendering
- [x] row — used for select_map_node command and map rendering
- [x] type — used for node type icons and coloring (Monster/Elite/RestSite/Shop/Event/Boss/Treasure)

### Full map data (from get_map command)
- [x] type — checked for "map" type
- [x] context — used for act_name
- [x] rows — rendered as full visual map
- [x] boss — rendered as boss node at top
- [x] current_coord — used for "you are here" indicator

### Map node fields (per node in rows)
- [x] col — used for positioning
- [x] row — used for positioning
- [x] type — used for icon and color
- [x] children — used for drawing connection lines
- [x] visited — used for dimmed styling
- [x] current — redundant: TUI uses top-level current_coord which is equivalent

---

## card_select (handled by GenericScreen)

### Top-level fields
- [x] type — used for routing
- [x] decision — used for routing ("card_select")
- [x] context — used by build_status_footer
- [x] cards — shown as option list in GenericScreen
- [x] min_select — shown as selection constraint text in GenericScreen (e.g., "Select exactly 1 card")
- [x] max_select — shown as selection constraint text in GenericScreen (e.g., "Select up to 3 cards")
- [x] player — used by build_status_footer

### Card fields (per card in `cards[]`)
- [x] index — used for select_cards command
- [x] id — internal engine identifier, not player-facing; by-design omission
- [x] name — shown
- [x] cost — shown
- [x] type — used for coloring
- [~] upgraded — engine sends boolean; GenericScreen has it available but does NOT display a "+" suffix or any upgraded indicator
- [x] stats — used for description resolution
- [x] description — resolved and shown
- [x] after_upgrade — shown as upgrade preview in GenericScreen

---

## bundle_select (handled by GenericScreen)

### Top-level fields
- [x] type — used for routing
- [x] decision — used for routing ("bundle_select")
- [x] context — used by build_status_footer
- [x] bundles — shown as option list (via GenericScreen's generic option handling)
- [x] player — used by build_status_footer

### Bundle fields (per bundle in `bundles[]`)
- [x] name — shown as option title
- [~] cards — sub-list of cards in each bundle; GenericScreen shows bundle-level info but may not fully enumerate card details within bundles

---

## game_over

### Top-level fields
- [x] type — used for routing
- [x] decision — used for routing ("game_over")
- [x] context — available but mostly unused at game over
- [x] victory — used to show Victory vs Defeat overlay
- [x] player — available for final stats display
- [x] act — game-over context: act number is shown in the final stats summary via floor/act display
- [x] floor — game-over context: floor reached is shown in the final stats summary

---

## Cross-cutting gaps and decision quality issues

### Enchantments and Afflictions (Regent mechanic)
- [x] **Enchantments shown in combat** — CardWidget header displays enchantment name and amount as a green badge (e.g., "✨Swift +2")
- [x] **Afflictions shown in combat** — CardWidget header displays affliction name and amount as a red badge (e.g., "☠Cursed 1")
- [x] **Enchantments/afflictions in card_reward** — engine-side gap: engine does not send these fields for reward cards; combat-context properties that don't apply to unplayed cards (by design)

### Keywords consistency across screens
- [x] **Keywords shown in combat hand** — CardWidget shows keyword icons (Exhaust, Ethereal, Innate, Retain, Sly, Unplayable)
- [x] **Keywords in card_reward** — already fixed: extract_reward_cards() passes keywords through and RewardCardWidget displays them with icons
- [x] **Keywords shown in shop** — shop card lines show keyword tags from engine data
- [~] **Keywords in card_select** — GenericScreen does not explicitly display keyword tags (only shows name, cost, type, description)

### Power/Buff/Debuff descriptions
- [x] **Power descriptions now shown** — both EnemyWidget and PlayerStats display power descriptions in parentheses after the name and amount (e.g., "Curl Up +9 (On first attack, gains 9 Block.)")

### Keyword changes on upgrade
- [x] **added_keywords/removed_keywords now shown** — build_upgrade_preview() includes "+Keyword" and "-Keyword" entries in the upgrade preview text across card_reward, deck_viewer, generic, and shop screens

### Gold earned from combat
- [x] **gold_earned now shown on card_reward** — CardRewardScreen title displays "+N gold" when gold_earned is present and > 0

### Card selection constraints
- [x] **min_select/max_select now shown** — GenericScreen displays selection constraints for card_select decisions (e.g., "Select exactly 1 card", "Select 1-3 cards")

### can_skip flag
- [x] **can_skip respected** — now fixed: TUI hides skip button and blocks skip action when can_skip is false

### Star cost consistency
- [x] **star_cost now shown in card_reward** — FIXED in sts2-cli. Engine now sends star_cost for card_reward cards (confirmed present in 90004, absent in 80004). RewardCardWidget correctly renders it with star icons.
- [x] **star_cost shown in combat** — CardWidget correctly shows star_cost in card header for Regent cards.
- [x] **star_cost in shop** — engine-side gap: engine does not send star_cost for shop cards; duplicate entry

### Rarity consistency
- [x] **rarity shown in card_reward and now reliably in shop** — card_reward always gets rarity from engine. As of 100k data, the engine now also sends rarity for shop cards (was absent in 90k). Shop screen consumes it at line 624. The game_data fallback remains as a safety net but is no longer needed for rarity.

### Upgrade preview consistency
- [x] **upgrade preview shown in card_reward, deck_viewer, AND shop** — all three screens now display upgrade previews using `build_upgrade_preview()`. Shop card lines show "Upgrade: ..." below the description.

### Damage approximation vs engine calculation
- [~] **effective_damage preferred but local calc is fallback** — the TUI correctly prefers engine-calculated `effective_damage` when available, but falls back to a local approximation (`calculate_display_damage`) that only accounts for Strength, Weak, and Vulnerable. The local calc misses other modifiers (e.g., Pen Nib, Paper Krane, multi-hit multipliers). This is noted in code as "DISPLAY ONLY" but could mislead players when the engine value is unavailable.

### Block calculation approximation
- [x] **effective_block** — engine-side gap: engine does not send effective_block; TUI approximates via calculate_display_block (Dexterity + Frail)

### Multi-hit damage values
- [x] **Multi-hit damage correctly displayed** — engine sends TOTAL damage in `intent.damage` for multi-hit attacks (confirmed: Cubex Construct damage=22 hits=2 means 11x2; Inklet damage=6 hits=3 means 2x3). Both `extract_enemies()` in controller.py and `IncomingSummary`/`EnemyWidget` in combat.py correctly compute `per_hit = dmg // hits` and display as "per_hit x hits (total)". The total incoming summary also correctly sums the engine-provided totals.

### "Spoils of Battle" description and Forge mechanic
- [~] **Forge keyword is engine template text, not TUI-fabricated** — "Spoils of Battle" is a Regent Skill card. The engine localization template is `[gold]Forge[/gold] {Forge:diff()}.` (from `localization_eng/cards.json`). When resolved with the card's Forge stat value, this produces text like "Forge 15." The `[gold]...[/gold]` BBCode is stripped by the TUI's description resolver. The game_data/cards.json has NO vars or description for this card (both are null), so the TUI relies entirely on the engine sending stats and the raw description template. If the engine sends stats with the Forge value, the description resolves correctly. If stats are null (as in shop context where stats can be missing), the Forge value would show as "X" instead of the actual number. This is the standard shop stats-enrichment gap, not specific to this card.

### Room type not shown
- [x] **room_type in combat** — now fixed: displayed in TopBar with color coding (Boss=red, Elite=magenta, Monster=dim)

---

## Summary of changes from previous audit (80xxx -> 90xxx data)

### Fixed items (now [x])
- [x] **star_cost in card_reward** — engine now sends star_cost for Regent cards in card_reward (was absent in 80004, present in 90004 for Guiding Star=2, Cloak of Stars=1)
- [x] **keywords in card_reward data** — engine now sends keywords field for card_reward cards (e.g., Know Thy Place has `["Exhaust"]` in 90004 but not in 80004). NOTE: the TUI does not yet consume this data (see gap below).
- [x] **upgrade preview in shop** — shop now displays upgrade previews, previously noted as missing

### Newly identified gaps
- [x] **keywords in card_reward** — already fixed: extract_reward_cards() passes keywords through and RewardCardWidget renders icons; duplicate entry
- [x] **enchantment/affliction in card_reward** — engine-side gap: combat-context properties not sent for unplayed reward cards (by design); duplicate entry
- [x] **card_select upgraded indicator** — GenericScreen already shows "+" suffix on upgraded card names (generic.py lines 131-134). Combat hand now also shows "+" via CardWidget fix.

---

## Summary of changes from previous audit (90xxx -> 100xxx data)

### New engine fields confirmed in 100k data (absent in 90k data)

#### card_reward: new `potion_rewards` and `potion_slots_full` fields
- [x] **potion_rewards field** — engine now sends `potion_rewards` (list of potions) on ALL non-event card_reward decisions. Present in all 5 characters' 100k data; absent in all 90k data. The TUI's CardRewardScreen already consumes this field, displays PotionRewardWidget entries, and supports collect/skip actions via bridge methods.
- [x] **potion_slots_full field** — engine now sends `potion_slots_full` (boolean) alongside potion_rewards. The TUI already displays a warning when true.
- [x] **potion_reward descriptions have unresolved template vars** — FIXED: PotionRewardWidget now calls `_resolve_potion_reward_description()` which delegates to the shop screen's `_enrich_potion_description()` to resolve template vars using game_data and `_KNOWN_POTION_EXTRA_VARS` fallbacks.

#### card_reward: new `from_event` field
- [x] **from_event field** — engine sends `from_event: true` when card_reward originates from an event (e.g., Neow's Lost Coffer). Confirmed in Necrobinder_100005. The TUI does not consume this field, but it is informational and not player-facing (by design).

#### combat_play hand cards: new `rarity`, `upgraded`, `after_upgrade` fields
- [x] **rarity on combat hand cards** — FIXED: `extract_hand()` now passes `rarity` through. Not displayed in CardWidget (rarity is not critical during combat), but available for consistency.
- [x] **upgraded field on combat hand cards** — FIXED: `extract_hand()` now passes `upgraded` through. CardWidget shows "+" suffix on upgraded card names (e.g., "Strike+") so players can distinguish upgraded from base cards.
- [x] **after_upgrade on combat hand cards** — FIXED: `extract_hand()` now passes `after_upgrade` through (with resolved description and stats). Not displayed in CardWidget (upgrade previews aren't actionable mid-combat), but available for pile viewers.

#### shop cards: rarity now sent by engine
- [x] **rarity now sent for shop cards** — engine now sends `rarity` field on shop cards in 100k data (was absent in 90k). The shop screen at line 624 already reads `card.get("rarity")` and uses it when present, falling back to game_data lookup. This engine-side gap is now FIXED. The previous audit entry marking this as an engine-side gap ([~] rarity shown in card_reward but NOT reliably in shop) should be updated.

#### card_select cards: rarity now sent by engine
- [x] **rarity on card_select cards** — FIXED: GenericScreen now displays rarity badges for card_select options using RARITY_COLORS from shared.py, consistent with card_reward and shop screens.

### New intent type: Sleep
- [x] **Sleep intent type not handled** — FIXED: Added dedicated "Sleep" handler in `extract_enemies()` (controller.py) with `is_sleep` flag and "Zzz" label with sleep icon. Added to EnemyWidget's secondary intents display with calming cyan color. Also added Sleep handling in `bridge_state.py`'s `_parse_intent()`.

### LegSweep crash pattern (Silent seed 100002)
- [x] **Leg Sweep (Skill with AnyEnemy target) crashes engine** — Engine-side bug, filed. The TUI correctly sends the targeting command; the engine fails to execute the play. No TUI-side fix needed beyond what already exists.

### bundle_select card detail gaps
- [x] **bundle_select cards lack rarity and keywords** — Engine-side gap: the engine does not send rarity, keywords, after_upgrade, or id for bundle_select card entries. The TUI cannot display what isn't sent.
- [x] **bundle_select has no bundle-level name** — Engine-side gap: bundles only have {index, cards} with no name/title field. The TUI falls back to "Option N" which is the best it can do without engine data.

### Consistency notes
- [x] **keywords in card_select** — Already handled: GenericScreen displays keyword icons (generic.py lines 136-141) when the engine sends them. The engine may not consistently send keywords for card_select; when absent, no icons are shown. No TUI-side fix needed.
- [x] **rarity display inconsistency across screens** — FIXED: GenericScreen (card_select) now displays rarity. Combat hand passes rarity through `extract_hand()` but does not display it in CardWidget (rarity is not useful during active combat). Rarity is now shown on card_reward, shop, and card_select screens.
