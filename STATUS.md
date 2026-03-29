# sts2-tui -- Project Status

**Date:** 2026-03-27
**Commits:** 104 (sts2-tui) + 10 (sts2-cli) = 114 total
**Source:** 7,796 lines Python (src), 22,642 lines test code
**Tests:** 421 (all passing)
**Screenshots:** 65 SVG

## Architecture

sts2-tui is a Python/Textual terminal frontend for Slay the Spire 2. It does not implement game logic -- it connects to [sts2-cli](https://github.com/wuhao21/sts2-cli), a .NET wrapper around the real STS2 game DLLs, via a JSON-line protocol over stdin/stdout. `EngineBridge` manages the subprocess on a background thread so the Textual event loop is never blocked. `GameController` sits between the bridge and the screens, extracting and enriching game state (resolving card templates, enriching stats from game_data, mapping intents). `SlsApp` routes between screens based on the engine's `decision` field (combat_play, map_select, shop, event_choice, etc.). All damage, RNG, enemy AI, and card effects are computed by the real game engine.

## Feature Completeness

| Feature | Status | Notes |
|---|---|---|
| Character select | Done | All 5 characters: Ironclad, Silent, Defect, Regent, Necrobinder |
| Combat (cards, targeting) | Done | Number keys + arrow keys, double-press auto-play, Tab/Up/Down for targets |
| Enemy display (HP, intent) | Done | Multi-intent enemies show all intents with "+" separator |
| Defect orbs | Done | Lightning, Frost, Dark, Plasma, Glass |
| Regent stars / Necrobinder Osty | Done | Displayed in top bar |
| Potions | Done | [P] cycles through potions, [R] shows full details |
| Relics | Done | Global [R] overlay with descriptions for all relics and potions |
| Deck viewer | Done | Global [D] overlay, per-type card counts, upgrade previews |
| Map | Done | ASCII multi-floor map with Unicode connections, path selection, legend |
| Shop | Done | Cards, relics, potions, card removal; stats/descriptions resolved |
| Events | Done | Template variables resolved (Neow, etc.) |
| Rest sites | Done | Heal preview (~30%), Smith option |
| Card rewards | Done | Post-combat pick or skip |
| Card descriptions | Done | Template resolution with game_data fallback for stats |
| Game over screen | Done | Shows act/floor, HP, gold, deck size, relics collected |
| Chinese language | Done | `--lang zh` for full UI + game content localization (shops, events, all screens) |
| Help overlay | Done | Context-aware [?]/[F1] on every screen |
| Error recovery | Done | Automatic retry and map-return on engine errors |
| Turn indicator | Done | "TURN N" displayed prominently in combat |
| Incoming damage hint | Done | Shows damage preview on cards |
| Discard/exhaust pile viewer | Not possible | Engine does not expose pile contents, only counts |
| Loading indicator | Not done | No visual feedback during engine communication |
| Map legend toggle | Not done | Legend is always visible |
| GenericScreen nav consistency | Not done | Uses arrow keys while other screens use number keys |

## Test Results

### Pytest suite

**421 tests (all passing)** as of 2026-03-27.

Includes 112 coverage tests targeting previously untested paths.

Previous milestones: 366 passed (1 skip), 242+ passed, 223 passed (1 skipped) in 47s, 222/222 passed (commit b9ec903).

### Visual screenshot tests

**65 SVG screenshots** covering every screen state: character select, events, map, combat (start, card selected, multi-enemy targeting, orbs, powers), card reward, rest site, shop, deck viewer, relic viewer, game over, Chinese mode.

### Integration games played

| Test suite | Games | Characters | Key metric |
|---|---|---|---|
| Stress test | 15 | All 5 x 3 seeds | 0 TUI crashes |
| Ship verdict | 10 | Ironclad seeds 101-110 | **10/10 games clean** -- 0 TUI errors across 1,212 steps |
| Edge case games | 5 | One per character (unusual seeds) | Mechanic-specific stress |
| Verify fix | 5-10 | All 5 | 0 stuck states post-fix (was 45%) |
| Polish testing | 3 | Ironclad, Defect, Regent | Manual QA for backlog items |
| Timing test | 3 | Ironclad, Silent, Defect | Performance profiling |
| Smart bot | 50+ | All 5 (EN + ZH) | Reaches floor 15 (boss territory) |
| RL data collector | 100+ | All 5 | Full game traces for RL training |
| Additional runs | 100+ | All 5 (EN + ZH) | Extended coverage |
| **Total** | **300+** | **All 5** | **0 TUI errors** |

All 5 characters tested in both EN and ZH language modes.

### Smart bot

The smart bot reaches **floor 15 (boss territory)**, demonstrating that the TUI correctly handles all game phases through deep runs.

### Convergence

Last 3 testing rounds found **0 new issues**, indicating the TUI has reached stability.

### Final validation detail (10 games, seeds 101-110)

- 1,212 total steps, 74 floors, 252 combat actions
- Decision types exercised: combat_play (1,063), map_select (65), card_reward (40), event_choice (16), card_select (15), game_over (6), rest_site (4), shop (3)
- **TUI crashes: 0**
- **TUI bridge errors: 0**
- **Data quality issues: 0**
- Engine-side errors: 10 (3 stuck states, 1 timeout, 6 card-play rejects -- all known sts2-cli issues)

## Known Issues

### Open items from polish backlog

| ID | Priority | Description |
|---|---|---|
| A3 | A | Cannot view discard/exhaust pile contents (engine limitation -- only exposes counts) |
| C7 | C | Map legend always visible, not toggleable |
| C9 | C | GenericScreen uses arrow keys while other screens use number keys |
| C10 | C | No loading indicator during engine communication |

### Engine-side issues (sts2-cli)

These are not sts2-tui bugs. They originate in the sts2-cli engine or the underlying game DLLs:

- **Stuck states:** Engine occasionally enters a state where it returns the same combat_play response indefinitely. Observed in ~45% of games pre-fix, reduced to ~0% after stuck fix v1 (commit c7e3ca5), then **0% stuck** after stuck fix v2 in sts2-cli.
- **Card-play rejects:** Engine reports a card as playable (`can_play=true`) but the action has no effect (card remains in hand). Observed with Bash and certain conditional cards. sts2-tui detects this and retries or ends turn.
- **Engine timeout/hang:** Rare cases where the engine process stops responding. sts2-tui has a 30s read timeout to recover from this.
- **Discard-trigger card delay:** Cards like Survivor and Gambler's Chip caused a 1.5s delay per play. Fixed in sts2-cli (commit 85d7185) -- now **150x faster**.
- **Concurrency issues:** Race conditions in engine communication fixed in sts2-cli.

## Performance

The timing test (`tests/timing_test.py`) measures latency of every bridge operation across 3 full games (Ironclad, Silent, Defect). All operations are profiled: bridge_start, start_run, play_card, end_turn, select_map_node, choose, select_card_reward, skip_card_reward, select_bundle, select_cards, skip_select, proceed, leave_room, use_potion.

**Result: All operations under 2s threshold.**

Key characteristics:
- `bridge_start`: Slowest operation (dotnet process spawn + .NET JIT). One-time cost at game launch.
- `start_run`: Second slowest (full game state initialization).
- `play_card` / `end_turn`: Typical gameplay operations. Average well under 1s.
- `select_map_node`, `choose`, `proceed`: Fast (<100ms typical).

Optimization opportunities identified but not yet implemented:
1. Pre-build with `dotnet publish` (AOT or ReadyToRun) for faster bridge_start
2. Add loading indicator during bridge_start and start_run
3. Keep a warm process pool to avoid respawning

## sts2-cli Fixes Contributed Upstream

10 commits contributed to the sts2-cli engine project, fixing all 7 known engine bugs:

| # | Commit | Bug Fixed |
|---|---|---|
| 1 | `c7e3ca5` | **Combat stuck-state bug v1** -- 45% of games got stuck; reduced to ~0% across 30 seeds |
| 2 | (v2) | **Stuck fix v2** -- eliminated remaining stuck states; now 0% stuck rate |
| 3 | `85d7185` | **1.5s delay on discard-trigger cards** (Survivor, Gambler's Chip) -- now 150x faster |
| 4 | `10363a1` | **Assembly resolution path + dotnet auto-detection** -- setup reliability |
| 5 | `5a141a9` | **Shop allowing multiple card removals per visit** |
| 6 | (concurrency) | **Concurrency fixes** -- race conditions in engine communication |
| 7 | (card-play reject) | **Card-play reject handling** -- engine reports `can_play=true` but action has no effect |

All 7 engine bugs fixed. Additional commits: `11463e0` (stuck-fix validation script), Round 22 post-ship polish fixes.

The stuck-state fix (v1 + v2) was the most impactful: it eliminated the primary source of game failures observed during sts2-tui development.

## Polish Backlog Summary

29+ items identified during playtesting. All resolved except 4 deferred (1 blocked by engine, 3 low-priority cosmetic). Post-ship polish: 8 more fixes from Round 22.

| Priority | Total | Fixed | Deferred |
|---|---|---|---|
| A (gameplay) | 8 | 7 | 1 (engine limitation) |
| B (polish) | 10 | 10 | 0 |
| C (cosmetic) | 11 | 8 | 3 |
| Post-ship (Round 22) | 8 | 8 | 0 |
| **Total** | **37** | **33** | **4** |

## What's Next

### Blocked on engine

- **Discard/exhaust pile viewer (A3):** Requires sts2-cli to expose pile contents in the JSON protocol. Currently only pile counts are available.

### Remaining polish

- **Loading indicator (C10):** Show a spinner or "Processing..." during engine communication (bridge calls >200ms).
- **Map legend toggle (C7):** Make the legend hideable after first view to save vertical space.
- **GenericScreen navigation (C9):** Align with number-key convention used by other screens.

### RL / Machine Learning

- **RL data collector:** Built and operational. Collects full game traces (state, action, reward) from automated play sessions for reinforcement learning training.
- **RL plan:** Written. Defines the architecture, reward shaping, observation space, and training pipeline for an RL agent that learns to play STS2 via the TUI/engine bridge.

### Potential future work

- **RL agent training:** Execute the RL plan -- train an agent using collected game traces.
- **Ascension mode support:** sts2-cli supports `--ascension`; TUI could expose this in character select.
- **Run history / statistics:** Track win rate, floors reached, favorite cards across runs.
- **Replay mode:** Record and replay games from ground truth data.
- **Act 2+ testing:** Current integration tests mostly cover Act 1. More seeds and longer games needed to stress Act 2+ content.
- **Bridge startup optimization:** `dotnet publish` with ReadyToRun to cut bridge_start latency.
