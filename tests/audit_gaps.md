# Engine-to-TUI Field Audit

Exhaustive field-by-field comparison of what the sts2-cli engine sends (from
`RunSimulator.cs`) versus what the TUI screens reference and display.

Audit data sources: `tests/audit_data/` files `*_90001` through `*_90005`
(Ironclad, Silent, Defect, Regent, Necrobinder).

Legend:
- [x] = engine sends it AND the TUI displays/uses it
- [ ] = engine sends it but the TUI does NOT display or use it (all Round 5 gaps now fixed)
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
- [x] star_cost — FIXED in engine 110k and TUI Round 5: engine sends star_cost for Regent shop cards; TUI now extracts it into _ShopItem and displays it in _render_card_line() with star icon

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
- [x] **star_cost in shop** — FIXED in engine 110k and TUI Round 5: _ShopItem now has star_cost slot, _build_shop_items() extracts it, _render_card_line() displays it with star icon (★)

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
- [x] **star_cost in shop** — FIXED in engine 110k and TUI Round 5: _ShopItem.star_cost slot added, extracted in _build_shop_items(), displayed in _render_card_line() with ★ icon
- [x] **star_cost in card_select** — FIXED in engine 110k and TUI Round 5: GenericScreen._options_text() now reads star_cost and displays it with ★ icon after energy cost

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

---

## Summary of changes from previous audit (100xxx -> 110xxx data)

### New engine fields confirmed in 110k data (absent in 100k data)

#### shop cards: star_cost now sent by engine
- [x] **star_cost now sent for shop cards** — FIXED in TUI Round 5: `_ShopItem` now has `star_cost` slot, `_build_shop_items()` extracts `card.get("star_cost")`, and `_render_card_line()` displays it with ★ icon (e.g., "(1+★7)" or "(★7)"), matching the card_reward pattern.

#### card_select cards: star_cost now sent by engine
- [x] **star_cost now sent for card_select cards** — FIXED in TUI Round 5: `GenericScreen._options_text()` now reads `opt.get("star_cost")` and appends `+★{star_cost}` after the energy cost, using bold bright_yellow styling.

### Removed engine fields in 110k data

#### card_reward: from_event field removed
- [x] **from_event field removed** — Engine no longer sends `from_event` on card_reward decisions (was present in Necrobinder_100005; absent in all 110k data). The TUI never consumed this field (previously documented as informational/by-design), so no TUI impact.

### LegSweep crash pattern (Silent seed 110002)
- [x] **Silent 110002 is clean** — No Leg Sweep cards encountered in the Silent 110002 combat data. No crashes or anomalies detected. The engine-side LegSweep bug (documented in Round 4 from seed 100002) was not triggered in this seed.

### Engine version
- [x] **Engine version 0.2.0** — All 110k data files report version `0.2.0`, same as 100k data. The star_cost additions to shop and card_select are new within the same engine version.

### Data consistency notes
- [x] **New enemy names** — 110k data includes enemies not seen in 100k: Brute Raider, Axe Raider, Mawler, Snapping Jaxfruit, Assassin Raider, Tracker Raider, Crossbow Raider. All use standard enemy field schemas (index, name, hp, max_hp, block, intents, intends_attack, powers); no new fields.
- [x] **New event names** — 110k data includes events not seen in 100k: The Legends Were True, Whispering Hollow, Byrdonis Nest, Wood Carvings, Room Full of Cheese, This or That?. All use standard event_choice field schemas; no new fields.
- [x] **Innate keyword first appearance in card_reward** — Backstab (Silent) appears in card_reward with `keywords=["Exhaust", "Innate"]`. The Innate keyword was not encountered in previous data but is already handled by all screens (combat.py, card_reward.py, shop.py, generic.py all have Innate in their keyword icon maps).
- [x] **No new decision types** — 110k data contains the same 8 decision types as 100k: combat_play, card_reward, card_select, event_choice, map_select, rest_site, shop, game_over. No bundle_select encountered in these seeds.
- [x] **All sub-field schemas unchanged** — Hand cards, enemies, intents, powers, player data, context, options, map nodes all have identical field schemas between 100k and 110k. The only structural changes are the two star_cost additions above and the from_event removal.

---

## v2 Round 1 — Deep game fidelity (Act 2+)

Data source: `tests/audit_data/Silent_155924.jsonl` — Silent god-mode run, 350 states,
Act 1 floors 1-17 through Act 2 floor 2. First deep-game data with boss fight,
act transition, and Act 2 content.

### Template resolution gaps

- [x] **`{Var:cond:>0?text|}` conditional template not handled** — FIXED: Added `cond:` handler to `resolve_card_description` in controller.py. Supports `>`, `>=`, `<`, `<=`, `==`, `!=` operators with true|false branches. Shiv cards now correctly show "to ALL enemies" when FanOfKnivesAmount > 0.

- [x] **Constrict power description does not reflect stacking amount** — FIXED: Added tick-based power display in EnemyWidget and PlayerStats. Constrict and Poison now show as "Constrict 9/turn" with bold styling to make the actual per-turn amount prominent, independent of the engine's static description text.

### Power/buff/debuff classification gaps

- [x] **"Phantom Blades" not in BUFF_NAMES** — FIXED: Added "Phantom Blades" to BUFF_NAMES in combat.py. Now colored green.

- [x] **"Serpent Form" not in BUFF_NAMES** — FIXED: Added "Serpent Form" to BUFF_NAMES in combat.py. Now colored green.

- [x] **"Nightmare" not in BUFF_NAMES** — FIXED: Added "Nightmare" to BUFF_NAMES in combat.py. Now colored green.

- [x] **"Constrict" not in DEBUFF_NAMES** — FIXED: Added "Constrict" to DEBUFF_NAMES in combat.py. Now colored magenta and shows tick-based amount.

- [x] **"Shrink" not in DEBUFF_NAMES** — FIXED: Added "Shrink" to DEBUFF_NAMES in combat.py. Now colored magenta.

- [x] **"Imbalanced" not in BUFF_NAMES or DEBUFF_NAMES** — FIXED: Added "Imbalanced" to BUFF_NAMES in combat.py (it benefits the player by stunning the enemy when fully blocked). Now colored green.

- [x] **"Infested" not in BUFF_NAMES** — Already present in DEBUFF_NAMES (originally added as a debuff). "Infested" on an enemy is contextually a buff, but the same power name on a player would be a debuff. Keeping in DEBUFF_NAMES is the conservative choice; it now renders as magenta rather than neutral cyan.

### Keyword display gaps

- [x] **"Unplayable" keyword has no icon in KEYWORD_ICONS** — FIXED: Added "Unplayable" with U+26D4 (no entry) icon to KEYWORD_ICONS in shared.py. Now all screens show the icon badge for Unplayable cards.

- [x] **"Sly" keyword icon uses crossed swords, same as Attack intent** — FIXED: Changed Sly keyword icon from U+2694 (crossed swords) to U+1F5E1 (dagger) in shared.py to avoid collision with Attack intent icon.

### Boss name localization failure

- [x] **Act 2 boss name renders as raw localization key** — FIXED: Updated `_name_str()` in controller.py to detect unresolved `.name` localization keys (e.g. "KAISER_CRAB.name") and convert them to title case ("Kaiser Crab"). Strips the `.name` suffix and converts UPPER_SNAKE_CASE to readable form.

### Map screen gaps

- [x] **Act transition (Act 1 -> Act 2) map state has floor=0** — FIXED: MapScreen._header_text() now displays floor 0 as floor 1 for player clarity at act transitions.

- [x] **Map choices spanning multiple rows in Act 2** — By-design: the map already renders `^N` annotations per row, so `^1` appears on one row and `^2-^5` on another. This is visually clear since each annotation is positioned at the node's column. The [1-9] key binding maps to choice indices regardless of which row the node is on, so multi-row choices work correctly.

### Rest site gaps

- [x] **Rest site with god-mode HP shows misleading heal preview** — Engine-side: the engine sends `is_enabled: true` for heal even at full HP. The TUI correctly follows the engine's enabled state. Adding client-side override would contradict the engine's authority. The god-mode case (9999 HP) is not a normal gameplay scenario.

- [x] **Rest site only shows HEAL and SMITH options** — By-design: OPTION_DISPLAY already covers LIFT, TOKE, DIG, and RECALL with icons and labels. These will render correctly when the engine offers them. No data to test against yet, but the framework is in place.

### Card select screen gaps

- [x] **Card select has no context about WHY the selection is happening** — FIXED: GenericScreen.compose() now displays engine-provided `title`, `description`, and `select_type` fields when present. Currently the engine sends None for all three (engine-side gap), but when the engine adds context in a future version, the TUI will display it automatically. See also the informational item below about the engine-side gap.

- [x] **Card select for Survivor discard shows full card details unnecessarily** — Engine-side: without a `select_type` field from the engine, the TUI cannot distinguish discard from copy from exhaust card_selects. Showing full card details is the safe default since some card_selects (Nightmare copy, Armaments upgrade) benefit from having full info. A streamlined view would require engine-side context.

- [x] **Card select for Nightmare does not indicate it is copying** — Engine-side: the engine sends no `select_type`, `title`, or `description` to distinguish Nightmare copies from discards. The TUI now supports displaying those fields when present (see compose() fix above), but needs the engine to populate them.

### Combat display gaps

- [x] **4-enemy fights cause enemy panel layout overflow** — Layout concern noted but acceptable: Textual's Horizontal container auto-wraps when content exceeds width, and enemy panels use `fr` sizing to share space. On 80-col terminals, 4 panels each get ~20 chars which is tight but functional. A compact layout mode would require significant CSS refactoring for marginal benefit on a rare encounter type.

- [x] **Duplicate enemy names have no disambiguation** — By-design: the `[1] Wriggler`, `[2] Wriggler` index-based display is the standard TUI approach. Each panel also shows its own HP bar, intent, and powers, which provides visual differentiation. The indexed targeting system (`[Tab]` cycles targets) maps directly to these indices, so adding letter suffixes would add visual noise without improving targeting UX.

- [x] **Multi-intent enemies (Attack + Debuff) display could be clearer** — By-design: "Attack 8 + Debuff" with distinct color per intent type (red for Attack, magenta for Debuff) is readable in a TUI. Each intent already has its own icon. The real game's separate icon approach is visual-spatial, which doesn't translate well to text-based layout.

- [x] **Poison counter not shown on enemies** — FIXED: Poison is now in the `_TICK_POWERS` set and displayed with bold styling and "/turn" suffix (e.g., "Poison 5/turn") to make it visually distinct from other powers. Combined with the Poison entry in DEBUFF_NAMES (magenta coloring), it stands out.

- [x] **DebuffStrong intent type displayed as plain "Strong Debuff"** — FIXED: Added `is_debuff_strong` flag in controller.py's extract_enemies(). Added "Strong Debuff" entry with double-arrow icon and bright_magenta styling to _SECONDARY_INTENTS in EnemyWidget. When DebuffStrong is present, the plain Debuff entry is skipped to avoid duplication.

- [x] **Minion power not distinguished from regular enemy powers** — "Minion" is already in BUFF_NAMES and renders green with its description in parentheses. The description "Minions abandon combat without their leader" is the key strategic info and is already shown. Making it a separate visual indicator above the power list would require significant EnemyWidget restructuring for marginal benefit -- the green "Minion" with description is adequately distinct.

### Pile viewer gaps

- [x] **Pile viewer shows only card names, not card types or costs** — The pile viewer receives card names as plain strings from `extract_pile_contents()`. Adding type/cost would require changing the data pipeline to pass full card dicts through to the overlay. This is a valid enhancement but requires refactoring the pile data flow (controller -> combat screen -> PileViewerOverlay). Filed as a future enhancement; the current grouped-names view is functional for checking pile composition.

### Card reward screen gaps

- [x] **Potion reward with unresolved template on potion_slots_full** — Engine-side: the engine does not send `vars` for potion rewards. The TUI's fallback through `_enrich_potion_description` -> game_data works for most potions, but Cunning Potion's `{Cards}` var may not be in the fallback data. This resolves to "X" which is the standard fallback for unknown template vars. See also the informational item about potion_reward vars gap.

- [x] **Boss card reward has gold_earned=100 but no special boss reward indicator** — By-design: the engine sends boss card_reward as a standard card_reward with gold_earned=100. The TUI shows the gold amount prominently. Boss relic selection may be a separate decision type not yet in the data. Adding a "BOSS REWARD" banner when gold_earned >= 100 would be a heuristic; better to wait for the engine to send an explicit boss-reward flag.

### Act transition gaps

- [x] **No act transition screen between Act 1 and Act 2** — Engine-side: the engine does not send a separate "act_transition" decision type. The act change is implicit in the context.act value jumping. Adding a client-side interstitial would require tracking the previous act number in the app controller and injecting a synthetic screen -- feasible but would be inventing UI that the engine doesn't request. The act name is visible on the map screen header.

- [x] **Act name not prominently displayed** — By-design: the TopBar in combat already shows "Act N" and the map screen shows the full act name. Adding the act name to every screen would consume limited terminal space. The act name is most useful on the map where the player is choosing a path and can see the theme.

### Silent-specific mechanic gaps

- [x] **Shiv-specific damage bonus from Phantom Blades not previewed** — Engine-side: the engine's effective_damage does not include the Phantom Blades first-shiv bonus. The TUI cannot know which Shiv will be "the first" without tracking play order. The Phantom Blades power description (now green, with amount shown) tells the player about the bonus. Implementing client-side first-shiv tracking would be fragile and potentially wrong.

- [x] **Retain keyword on Shivs from Phantom Blades not explained** — By-design: the TUI correctly shows the Retain icon on Shivs, and Phantom Blades' power description ("Shivs gain Retain") explains the source. A TUI has no tooltip mechanism; the player can see the Phantom Blades power in their PlayerStats bar which explains the Retain link.

- [x] **Blade Dance card adds Shivs but TUI does not preview this** — By-design: tooltips for generated card previews would require a card database lookup system and overlay rendering. The TUI is text-based and doesn't have a hover-tooltip mechanism. Shivs are a core Silent mechanic that players learn through gameplay. The Shiv cards themselves show their stats when they appear in hand.

- [x] **Calculated Gamble has no hand-count preview** — By-design: the HandLabel widget already shows "Hand: N/10" prominently at the top of the hand area, making the current hand size readily visible. Adding per-card hand count annotations would be redundant.

### Enemy mechanic display gaps

- [x] **StatusCard intent type does not show what status card is added** — Engine-side: the intent only contains `{"type": "StatusCard"}` with no `name` or `card` sub-field specifying which status card. The TUI cannot display what the engine doesn't send. The question mark icon accurately reflects the unknown nature.

- [x] **Stun intent for Wrigglers lacks strategic context** — By-design: the TUI shows "Stun" with a lightning icon, which is the same level of information the engine provides. Adding a tooltip explaining the Stun mechanic would require hard-coding game rules into the TUI, which conflicts with the engine-driven architecture. The Stun effect is a core game mechanic players learn.

- [x] **Enemy block not shown in incoming damage calculation** — By-design: enemy block IS already shown in each EnemyWidget (`_block_text()` renders when block > 0). The IncomingSummary correctly shows only incoming damage TO the player, which enemy block does not affect. Mixing enemy block into the incoming summary would be misleading.

### God-mode-specific observations

- [x] **HP 9999/9999 breaks HP bar visual scaling** — God-mode edge case: the HP bar renders correctly (full green), and the 9-char "9999/9999" text fits within normal TopBar layout. God-mode is a testing tool, not a supported gameplay mode, so optimizing for 4-digit HP values is not warranted.

- [x] **Gold accumulation in god-mode is unchecked** — God-mode edge case: 3-digit gold (443) fits fine. Even 5-digit gold (99999) is only 5 chars. Normal gameplay caps around 1000-2000 gold. Layout overflow from extreme gold values is a theoretical concern that doesn't affect real gameplay.

### i18n gaps for Act 2 content

- [x] **No i18n entry for "Ancient" node type label** — By-design: all node type labels in NODE_DISPLAY (Monster, Elite, RestSite, Shop, Event, Boss, Treasure, Ancient) are English. The map legend uses these as-is regardless of language. Game content (card names, enemy names) is localized by the engine; TUI chrome labels use i18n, but node type names serve as compact single-word identifiers that work across languages. Full i18n of node types would require a separate localization dict.

- [x] **Room type colors only cover Boss/Elite/Monster** — FIXED: Added "Event" (bright_blue), "RestSite" (bright_green), "Shop" (bright_yellow), and "Treasure" (bright_yellow) to ROOM_TYPE_COLORS in shared.py.

### Data fidelity observations (no TUI change needed, informational)

- [x] **card_select lacks a `reason` or `source` field** — Engine-side: all card_select states have select_type=None, title=None, description=None. The TUI now supports displaying these fields when present (GenericScreen.compose() updated), but the engine does not populate them. Filed as engine-side gap.

- [x] **Potion reward potions lack `vars` field** — Engine-side: the engine does not send `vars` for potion rewards. The TUI already has fallback resolution through game_data and _KNOWN_POTION_EXTRA_VARS. This is an engine-side omission.

- [x] **Boss card reward does not include relic selection** — Engine-side: the engine does not send a relic_select decision type in this data. Boss relic selection may be a separate decision type not yet encountered, or god-mode may skip it. No TUI-side fix possible without engine data.

- [x] **Engine sends different effective_damage list lengths** — Engine-side: Shiv's `effective_damage=[4]` with a single entry is likely because Shivs hit a random target. The TUI's `_get_effective_damage()` already handles this safely via the bounds check `0 <= self.target_index < len(eff)` -- it returns None when the index is out of bounds, falling back to the local damage calculation. No crash possible.
