# Engine-to-TUI Field Audit

Exhaustive field-by-field comparison of what the sts2-cli engine sends (from
`RunSimulator.cs`) versus what the TUI screens reference and display.

Audit data sources: `tests/audit_data/` files `*_90001` through `*_90005`
(Ironclad, Silent, Defect, Regent, Necrobinder).

Legend:
- [x] = engine sends it AND the TUI displays/uses it
- [ ] = engine sends it but the TUI does NOT display or use it (GAP)
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
- [ ] id — engine sends card ID (e.g., "CARD.STRIKE_IRONCLAD") but TUI never displays or uses it; controller.extract_hand() drops it entirely
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
- [ ] intends_attack — engine sends a boolean shortcut, TUI ignores it (uses parsed intents instead; not a real gap but redundant data ignored)
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
- [ ] room_type — engine sends it (e.g., "Monster", "Boss"), TUI NEVER displays it in combat
- [ ] act_name — engine sends localized act name, TUI NEVER displays it in combat (only in map screen)
- [ ] boss — engine sends boss name/id in context, TUI NEVER displays it in combat (only in map screen)

### Player summary fields (in `player{}`)
- [x] name — shown in TopBar
- [x] hp — shown in TopBar with HP bar
- [x] max_hp — shown in TopBar
- [x] block — NOT shown in TopBar (shown in PlayerStats instead)
- [x] gold — shown in TopBar
- [x] relics — shown in RelicBar with names, counters, and descriptions
- [x] potions — shown in TopBar (names only) and used for potion actions
- [x] deck_size — used for exhaust pile approximation
- [ ] deck — engine sends the full deck list in PlayerSummary; during combat, TUI uses the cached `player_deck` from controller for deck viewer, so it IS accessible but not re-fetched each combat state

### Player relic fields (per relic in `player.relics[]`)
- [x] id — extracted by controller, used for internal lookup
- [x] name — shown in RelicBar and RelicViewerOverlay
- [x] description — shown in RelicBar and RelicViewerOverlay
- [x] counter — shown when >= 0 in RelicBar and RelicViewerOverlay
- [ ] vars — engine sends dynamic vars dict for relics, controller drops it (only uses description after resolving)

### Player potion fields (per potion in `player.potions[]`)
- [x] index — used for use_potion command
- [x] name — shown in TopBar and RelicViewerOverlay
- [x] description — resolved and shown in RelicViewerOverlay
- [x] target_type — used to determine if potion needs targeting
- [ ] vars — engine sends dynamic vars dict, controller uses it for description resolution only

---

## card_reward

### Top-level fields
- [x] type — used for routing
- [x] decision — used for routing ("card_reward")
- [x] context — used by build_status_footer
- [x] cards — rendered as RewardCardWidget list
- [ ] can_skip — engine sends whether reward can be skipped; TUI ALWAYS shows skip option (Esc) regardless of this flag
- [x] gold_earned — shown on card_reward title as "+N gold"
- [x] player — used by build_status_footer (HP/gold/act/floor)

### Card fields (per card in `cards[]`)
- [x] index — used to send select_card_reward command
- [ ] id — engine sends card ID, TUI drops it in extract_reward_cards()
- [x] name — shown in RewardCardWidget
- [x] cost — shown in RewardCardWidget
- [x] type — used for card type coloring
- [x] rarity — shown in RewardCardWidget (Common/Uncommon/Rare badge)
- [x] description — resolved and shown
- [x] stats — used for description template resolution
- [x] after_upgrade — shown as upgrade preview text
- [x] star_cost — **FIXED in sts2-cli**: engine now sends star_cost for card_reward cards (confirmed in 90004 data: Guiding Star star_cost=2, Cloak of Stars star_cost=1). RewardCardWidget correctly displays it. Previously the engine did NOT send this field for card_reward (confirmed absent in 80004 data).
- [ ] keywords — **GAP**: engine sends keywords for card_reward cards (e.g., Know Thy Place has `keywords: ["Exhaust"]` in 90004 data), but `extract_reward_cards()` does NOT pass keywords through, and RewardCardWidget does NOT display them. Players cannot see Exhaust, Ethereal, Innate, Retain, Sly tags when choosing reward cards.

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
- [ ] star_cost — **engine does NOT send star_cost for shop cards** (not present in any shop card in 90001-90005 data); Regent players cannot see star costs when buying cards

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
- [ ] **rarity NOT shown in shop** — engine does NOT send rarity for shop cards, and the shop only shows rarity if it can look it up from game_data. The card_reward screen always shows rarity because the engine sends it there.
- [x] **upgrade preview now shown in shop** — shop card lines display upgrade preview below description, consistent with card_reward and deck_viewer
- [x] **keywords now shown in shop** — shop card lines display keyword tags (Exhaust, Ethereal, etc.) when the engine sends them
- [ ] **star_cost NOT shown in shop** — engine does NOT send it for shop cards; Regent players are blind to star costs when buying

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
- [ ] **Heal amount is approximated** — the TUI hardcodes `_REST_HEAL_FRACTION = 0.3` and shows "~30% heal". The engine does NOT send the actual heal amount. Relics like Regal Pillow modify heal amount, but the TUI cannot know the real value. Comment in code acknowledges this with "~" prefix.
- [ ] **Smith card list not shown** — when SMITH is available, the player doesn't see which cards are upgradeable. They must open the deck viewer separately to check. The engine only sends option availability, not what the smith would upgrade.

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
- [ ] text_key — engine sends the internal text key (e.g., "NEOW.pages.INITIAL.options.STONE_HUMIDIFIER"); TUI NEVER displays or uses it
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
- [ ] act — engine sends act number at top level (redundant with context.act); TUI ignores top-level act
- [ ] act_name — engine sends at top level; TUI ignores top-level, uses context.act_name from full map data instead
- [ ] floor — engine sends at top level (redundant with context.floor); TUI ignores top-level floor

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
- [ ] current — engine sends per-node `current` boolean; TUI ignores it and uses `current_coord` from top-level instead (equivalent but redundant)

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
- [ ] id — engine sends card ID; TUI does not display it
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
- [ ] act — engine sends final act number; TUI game-over overlays do NOT show it
- [ ] floor — engine sends final floor; TUI game-over overlays do NOT show it

---

## Cross-cutting gaps and decision quality issues

### Enchantments and Afflictions (Regent mechanic)
- [x] **Enchantments shown in combat** — CardWidget header displays enchantment name and amount as a green badge (e.g., "✨Swift +2")
- [x] **Afflictions shown in combat** — CardWidget header displays affliction name and amount as a red badge (e.g., "☠Cursed 1")
- [ ] **Enchantments/afflictions NOT in card_reward** — engine does NOT send enchantment/affliction fields on card_reward cards (confirmed in 90004 data). This is an engine-side gap; cards in the reward screen cannot show their enchantment/affliction because the data is absent. However, for reward cards these are typically card properties that are only applied when the card is in a combat context, so this may be by design.

### Keywords consistency across screens
- [x] **Keywords shown in combat hand** — CardWidget shows keyword icons (Exhaust, Ethereal, Innate, Retain, Sly, Unplayable)
- [ ] **Keywords NOT shown in card_reward** — engine sends keywords for reward cards but `extract_reward_cards()` drops them and RewardCardWidget does not display them. **This is a TUI-side gap** — the data is available but not passed through or rendered.
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
- [ ] **can_skip ignored** — the TUI always shows "Skip" on card_reward regardless of `can_skip`. If the engine ever sends `can_skip: false`, the TUI would still allow attempting to skip.

### Star cost consistency
- [x] **star_cost now shown in card_reward** — FIXED in sts2-cli. Engine now sends star_cost for card_reward cards (confirmed present in 90004, absent in 80004). RewardCardWidget correctly renders it with star icons.
- [x] **star_cost shown in combat** — CardWidget correctly shows star_cost in card header for Regent cards.
- [ ] **star_cost NOT shown in shop** — engine does NOT send star_cost for shop cards; Regent players are blind to star costs when buying cards. TUI could potentially look this up from game_data.

### Rarity consistency
- [~] **rarity shown in card_reward but NOT reliably in shop** — card_reward always gets rarity from engine. Shop must look it up from game_data as a fallback since the engine omits it for shop cards.

### Upgrade preview consistency
- [x] **upgrade preview shown in card_reward, deck_viewer, AND shop** — all three screens now display upgrade previews using `build_upgrade_preview()`. Shop card lines show "Upgrade: ..." below the description.

### Damage approximation vs engine calculation
- [~] **effective_damage preferred but local calc is fallback** — the TUI correctly prefers engine-calculated `effective_damage` when available, but falls back to a local approximation (`calculate_display_damage`) that only accounts for Strength, Weak, and Vulnerable. The local calc misses other modifiers (e.g., Pen Nib, Paper Krane, multi-hit multipliers). This is noted in code as "DISPLAY ONLY" but could mislead players when the engine value is unavailable.

### Block calculation approximation
- [ ] **No engine-provided effective_block** — unlike damage, the engine does NOT send an `effective_block` field. The TUI uses `calculate_display_block` which only accounts for Dexterity and Frail. Other block modifiers (e.g., Metallicize, Plated Armor on block gain) are not reflected in the displayed block value.

### Multi-hit damage values
- [x] **Multi-hit damage correctly displayed** — engine sends TOTAL damage in `intent.damage` for multi-hit attacks (confirmed: Cubex Construct damage=22 hits=2 means 11x2; Inklet damage=6 hits=3 means 2x3). Both `extract_enemies()` in controller.py and `IncomingSummary`/`EnemyWidget` in combat.py correctly compute `per_hit = dmg // hits` and display as "per_hit x hits (total)". The total incoming summary also correctly sums the engine-provided totals.

### "Spoils of Battle" description and Forge mechanic
- [~] **Forge keyword is engine template text, not TUI-fabricated** — "Spoils of Battle" is a Regent Skill card. The engine localization template is `[gold]Forge[/gold] {Forge:diff()}.` (from `localization_eng/cards.json`). When resolved with the card's Forge stat value, this produces text like "Forge 15." The `[gold]...[/gold]` BBCode is stripped by the TUI's description resolver. The game_data/cards.json has NO vars or description for this card (both are null), so the TUI relies entirely on the engine sending stats and the raw description template. If the engine sends stats with the Forge value, the description resolves correctly. If stats are null (as in shop context where stats can be missing), the Forge value would show as "X" instead of the actual number. This is the standard shop stats-enrichment gap, not specific to this card.

### Room type not shown
- [ ] **room_type from context not displayed** — the engine sends room type (Monster, Boss, etc.) in context but the TUI never displays it. Players in combat don't see whether they're fighting a Boss, Elite, or regular Monster (though they can often infer from enemy names).

---

## Summary of changes from previous audit (80xxx -> 90xxx data)

### Fixed items (now [x])
- [x] **star_cost in card_reward** — engine now sends star_cost for Regent cards in card_reward (was absent in 80004, present in 90004 for Guiding Star=2, Cloak of Stars=1)
- [x] **keywords in card_reward data** — engine now sends keywords field for card_reward cards (e.g., Know Thy Place has `["Exhaust"]` in 90004 but not in 80004). NOTE: the TUI does not yet consume this data (see gap below).
- [x] **upgrade preview in shop** — shop now displays upgrade previews, previously noted as missing

### Newly identified gaps
- [ ] **keywords not rendered in card_reward** — despite the engine now sending keywords for card_reward cards, `extract_reward_cards()` does not include keywords in its output dict, and RewardCardWidget has no code to display them. This is a TUI-side gap introduced by the data now being available but not consumed.
- [ ] **enchantment/affliction not available in card_reward** — engine does not send these fields for reward cards. For Regent, this means players cannot see enchantment or affliction information when choosing reward cards. However, these are combat-context properties that may not apply to unplayed cards.
- [~] **card_select upgraded indicator** — GenericScreen has the `upgraded` boolean available for card_select cards but does not display it (no "+" suffix on upgraded card names).
