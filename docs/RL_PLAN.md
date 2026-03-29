# RL Training Plan for STS2 AI Agent

**Date:** 2026-03-27
**Scope:** Train an RL agent to play Slay the Spire 2 via sts2-cli, starting with Ironclad Act 1.
**Timeline:** 1 week (5 working days)

---

## 1. Data Collection

### What to record

Every decision point produces a `(state, action, reward, next_state)` tuple. The sts2-cli engine already emits full JSON state at each decision point via its JSON-line protocol. We record:

- **State**: The full JSON blob from the engine at each decision point. Fields vary by decision type:
  - `combat_play`: player HP/block/energy, hand (card IDs, costs, can_play, target_type, stats), enemies (HP, max_hp, block, intents with type/damage/hits), player_powers, draw_pile_count, discard_pile_count, round number, potions, relics, orbs (Defect), stars (Regent), osty (Necrobinder).
  - `map_select`: choices (col, row, type), player (HP, gold, deck, relics).
  - `card_reward`: cards (name, cost, type, rarity, stats), player deck_size.
  - `rest_site`: options (HEAL, SMITH), player HP/max_hp.
  - `shop`: cards/relics/potions for sale, gold, card_removal_cost.
  - `event_choice`: options with vars (HP loss, gold gain, etc.).
- **Action**: The exact JSON command sent to the engine (action name + args).
- **Reward**: Computed post-hoc from the recorded trajectory (see Section 6).

### Recording infrastructure

The `GameLogger` class in `sts2-cli/python/game_log.py` already writes JSONL files with alternating `state` and `action` entries, timestamped and step-numbered. Each game produces one `.jsonl` file in `sts2-cli/logs/`.

**Collection script**: Extend `tools/smart_bot.py` (or `sts2-cli/python/play_full_run.py`) to run batch games with logging enabled. The bot already logs every step. We add a wrapper that:
1. Runs N games sequentially (one sts2-cli process per game, ~120 steps per game).
2. Saves logs to `data/training/raw/{character}_{seed}.jsonl`.
3. Post-processes logs into training-ready format.

### How many games

- **Phase 1 (bootstrap)**: 500 games with the heuristic smart bot (Ironclad only).
- **Phase 2 (self-play)**: 2,000 games with the RL agent exploring.
- **Phase 3 (refinement)**: 1,000 games with the best policy.
- **Total**: 3,500 games for initial Ironclad training.

### Storage format

**Raw**: JSONL (one file per game, as `GameLogger` already produces). Avg 270 lines x ~3.3 KB per line = ~900 KB per game.

**Training-ready**: Apache Parquet, one file per batch of 100 games. Each row is one decision step with columns:
- `game_id` (string)
- `step` (int)
- `decision_type` (string: combat_play, map_select, card_reward, rest_site, shop, event_choice)
- `state_features` (float array, fixed-size 512)
- `action_id` (int, index into the action space for that decision type)
- `reward` (float)
- `done` (bool, True at game_over)
- `value_target` (float, discounted return computed post-hoc)

### Estimated time and storage

| Metric | Value |
|---|---|
| Time per game (sts2-cli) | ~45 seconds (measured: 1,212 steps / 10 games = ~120 steps/game, ~350ms avg per step) |
| 500 bootstrap games | 6.25 hours (single-threaded) or 1.5 hours (4 parallel processes) |
| Raw JSONL per game | ~900 KB |
| 500 games raw | ~450 MB |
| Parquet (compressed) per game | ~30 KB (features only, no raw JSON) |
| 3,500 games parquet | ~105 MB |

---

## 2. Fast Simulator

### Why we need it

sts2-cli runs the real .NET game engine at ~2.2 games/minute single-threaded. RL training needs 10,000+ games/hour. We need a Python-native simulator that runs 100x faster for the combat phase (where 80% of decisions happen).

### What to build

A **combat-only** Python simulator. Non-combat decisions (map, card reward, rest, shop, event) are simple enough to handle with lookup tables -- they don't need physics simulation.

### What to restore from git history

There is no prior Python engine in the git history. We build from scratch using:
1. Card data from `game_data/cards.json` (576 cards, all stats pre-extracted).
2. Monster data from `game_data/monsters.json` (123 monsters).
3. Power/buff effects from `game_data/powers.json` (250 powers).
4. Relic effects from `game_data/relics.json` (289 relics).

### What to implement

A minimal combat loop covering the 20 most common Ironclad cards:
- **Strike** (deal 6 damage), **Defend** (gain 5 block), **Bash** (deal 8 + apply 2 Vulnerable)
- **Pommel Strike**, **Heavy Blade**, **Shrug It Off**, **Battle Trance**, **Inflame**, **Offering**
- **Whirlwind**, **Corruption**, **Feel No Pain**, **Barricade**, **Impervious**
- **Bloodletting**, **Aggression**, **Reaper**, **Feed**, **Brand**, **Stone Armor**

Plus the 8 most common Act 1 enemy groups (from monster data):
- Jaw Worm, 2x Louse, Cultist, 3x Slimes, Gremlin Gang, Looter, Fungi, Nob (elite), Lagavulin (elite), Hexaghost/Slime Boss/Guardian (bosses -- Act 1 bosses from STS2).

### Calibration against sts2-cli

Run 100 identical combats in both engines (same seed, same card plays, same order) and compare:
- Final player HP after combat
- Number of turns to win
- Damage dealt per card play

**Accuracy target**: Within 5% of sts2-cli HP outcomes on the 100-combat calibration set. Specifically: average HP difference <= 3 HP across all 100 combats.

**Speed target**: 10,000 simulated combats per hour on a single CPU core (M1 Mac). This means ~360ms per combat (10 turns x 5 cards/turn = 50 card plays at <7ms each).

### Implementation plan (Day 1-2)

```
src/sts2_tui/sim/
  __init__.py
  combat.py       # CombatState, apply_card(), enemy_turn()
  cards.py         # Card effects registry (loaded from game_data/cards.json)
  enemies.py       # Enemy intent patterns + AI
  powers.py        # Buff/debuff application
  calibrate.py     # Compare sim vs sts2-cli on 100 combats
```

### What we skip

- Relic triggered effects (too many edge cases; model can learn around inaccuracy)
- Potion effects (rare, handle in sts2-cli validation only)
- Card draw manipulation (Scrying, Well-Laid Plans)
- Orbs, Stars, Osty (character-specific; Ironclad-only in v1)

---

## 3. State Representation

### Fixed-size feature vector: 512 floats

All features normalized to [0, 1] or [-1, 1] range.

#### Player features (64 floats)

| Index | Feature | Normalization |
|---|---|---|
| 0 | HP / max_hp | [0, 1] |
| 1 | HP (raw) | / 100 |
| 2 | max_hp | / 100 |
| 3 | block | / 50 |
| 4 | energy | / 5 |
| 5 | max_energy | / 5 |
| 6 | gold | / 500 |
| 7 | deck_size | / 40 |
| 8 | draw_pile_count | / 30 |
| 9 | discard_pile_count | / 30 |
| 10 | exhaust_pile_count | / 20 |
| 11 | turn_number (round) | / 20 |
| 12 | act | / 3 |
| 13 | floor | / 20 |
| 14-29 | Top 16 buffs/debuffs (amount / 10): Strength, Dexterity, Vulnerable, Weak, Frail, Vigor, Metallicize, Plated Armor, Thorns, Barricade, Demon Form, Feel No Pain, Corruption, Juggernaut, Poison, Regen | [-1, 1] |
| 30-39 | Deck composition: % Attack, % Skill, % Power, % Curse, % Status, avg cost, # upgrades / deck_size, # rare / deck_size, # uncommon / deck_size, # common / deck_size | [0, 1] |
| 40-49 | Relic presence: one-hot for top 10 impactful relics (Burning Blood, Vajra, Bag of Preparation, etc.) | {0, 1} |
| 50-53 | Potion slots: 4 potion type IDs (0 = empty, mapped to 1-64) / 64 | [0, 1] |
| 54-63 | Reserved (zero-padded) | 0 |

#### Hand features (160 floats = 10 cards x 16 features)

For each of up to 10 cards in hand (zero-padded if fewer):

| Offset | Feature | Normalization |
|---|---|---|
| +0 | card_id (hashed to [0,1] from 576-card vocabulary) | [0, 1] |
| +1 | energy cost | / 5 |
| +2 | is_attack | {0, 1} |
| +3 | is_skill | {0, 1} |
| +4 | is_power | {0, 1} |
| +5 | is_curse_or_status | {0, 1} |
| +6 | can_play | {0, 1} |
| +7 | base_damage / 30 | [0, 1] clip |
| +8 | base_block / 30 | [0, 1] clip |
| +9 | needs_target (target_type == "AnyEnemy") | {0, 1} |
| +10 | is_x_cost | {0, 1} |
| +11-15 | Reserved | 0 |

#### Enemy features (192 floats = 4 enemies x 48 features)

For each of up to 4 enemies (zero-padded if fewer):

| Offset | Feature | Normalization |
|---|---|---|
| +0 | is_alive | {0, 1} |
| +1 | HP / max_hp | [0, 1] |
| +2 | HP raw | / 300 |
| +3 | max_hp | / 300 |
| +4 | block | / 50 |
| +5 | intent_is_attack | {0, 1} |
| +6 | intent_damage / 50 | [0, 1] clip |
| +7 | intent_hits | / 5 |
| +8 | intent_is_defend | {0, 1} |
| +9 | intent_is_buff | {0, 1} |
| +10 | intent_is_debuff | {0, 1} |
| +11 | intent_total_damage / 80 | [0, 1] clip |
| +12-27 | Top 16 enemy buffs/debuffs (same order as player) / 10 | [-1, 1] |
| +28-47 | Reserved | 0 |

#### Decision context features (48 floats)

| Index | Feature | Normalization |
|---|---|---|
| 0-7 | One-hot decision type: combat_play, map_select, card_reward, rest_site, shop, event_choice, card_select, bundle_select | {0, 1} |
| 8-14 | Map choice types (up to 7): one-hot Monster/Elite/RestSite/Shop/Event/Treasure/Boss | {0, 1} |
| 15-17 | Card reward: 3 card rarity indicators (Common/Uncommon/Rare) | {0, 1} |
| 18-19 | Rest options: can_heal, can_smith | {0, 1} |
| 20-47 | Reserved | 0 |

#### Global features (48 floats)

| Index | Feature | Normalization |
|---|---|---|
| 0-4 | One-hot character: Ironclad, Silent, Defect, Regent, Necrobinder | {0, 1} |
| 5 | Ascension level | / 20 |
| 6 | Room type encoded (Monster=0.2, Elite=0.4, Boss=0.6, Event=0.8, other=0) | [0, 1] |
| 7-47 | Reserved | 0 |

**Total**: 64 + 160 + 192 + 48 + 48 = **512 floats**

---

## 4. Action Space

The action space is decision-type-dependent. We use a **flat action space of 64 discrete actions** with masking (invalid actions masked to -inf before softmax).

### Combat actions (indices 0-49)

| Index | Action | Description |
|---|---|---|
| 0-9 | `play_card(i)` no target | Play card at hand index i (for self-targeting cards) |
| 10-19 | `play_card(i, target=0)` | Play card i targeting enemy 0 |
| 20-29 | `play_card(i, target=1)` | Play card i targeting enemy 1 |
| 30-39 | `play_card(i, target=2)` | Play card i targeting enemy 2 |
| 40-43 | `play_card(i, target=3)` | Play card i targeting enemy 3 (indices 40-43 only, cards 0-3) |
| 44 | `end_turn` | End the current turn |
| 45-48 | `use_potion(i)` | Use potion at slot i (0-3) |
| 49 | Reserved | |

### Non-combat actions (indices 50-63)

| Index | Action | Description |
|---|---|---|
| 50-56 | `select_map_node(choice_i)` | Pick map path i (up to 7 choices) |
| 57-59 | `select_card_reward(i)` | Pick card reward i (3 options) |
| 60 | `skip_card_reward` | Skip the reward |
| 61 | `rest_heal` | Rest site: heal |
| 62 | `rest_smith` | Rest site: smith/upgrade |
| 63 | `leave_room` / `proceed` | Leave shop, proceed past event, etc. |

### Action masking

At each step, compute a boolean mask of length 64. For combat:
- Card i is valid only if `hand[i].can_play == True` and `hand[i].cost <= energy`.
- Target-specific actions valid only if the card requires targeting (`target_type == "AnyEnemy"`) and that enemy index exists and is alive.
- Self-target card actions (0-9) valid only if card does NOT require enemy targeting.
- `end_turn` (44) is always valid during combat.
- Potion actions valid only if the potion slot is filled.

For non-combat, mask everything except the relevant decision-type actions.

---

## 5. Model Architecture

### Recommended: MLP with 3 hidden layers

For the initial week-1 prototype, an MLP is the right choice. StS is a card game with a moderate state space -- not a spatial/visual problem (no CNN needed) and not a long-sequence problem (no transformer needed). The fixed-size 512-feature vector is a natural MLP input.

```
Input:      512 floats (state features)
Hidden 1:   512 -> 256 (ReLU)
Hidden 2:   256 -> 256 (ReLU)
Hidden 3:   256 -> 128 (ReLU)
Policy head: 128 -> 64 (action logits, masked softmax)
Value head:  128 -> 1 (scalar state value)
```

### Parameter count

- Layer 1: 512 x 256 + 256 = 131,328
- Layer 2: 256 x 256 + 256 = 65,792
- Layer 3: 256 x 128 + 128 = 32,896
- Policy: 128 x 64 + 64 = 8,256
- Value: 128 x 1 + 1 = 129
- **Total: ~238,000 parameters**

This is small enough to train on CPU in hours. No GPU required for week 1.

### Framework

PyTorch. Model definition in `src/sts2_tui/rl/model.py`, ~80 lines.

### Future upgrades (beyond week 1)

- **Card embedding layer**: Replace hashed card_id floats with learned 16-dim embeddings (576-card vocabulary). This helps the model generalize across similar cards.
- **Attention over hand**: Replace fixed 10-slot hand encoding with a small transformer that attends over variable-length hand. Enables better multi-card planning.
- **Separate sub-networks per decision type**: Instead of one network with action masking, use separate policy heads for combat vs map vs reward. Reduces interference.

---

## 6. Training Loop

### Algorithm: PPO (Proximal Policy Optimization)

PPO is the standard choice for discrete action spaces with moderate complexity. It is stable, sample-efficient, and easy to debug.

### Reward shaping

**Terminal reward** (at game_over):
- Victory: +100
- Defeat: floor_reached * 3 (e.g., floor 17 = +51)

**Per-step reward** (after each action):
- HP gained (healing): +0.5 per HP
- HP lost (damage taken at end of turn): -0.2 per HP lost
- Enemy killed: +2.0
- Card reward picked (good card for character): +1.0
- Card reward skipped (deck > 20): +0.5
- Rest site heal (HP < 50%): +1.0
- Rest site smith (HP > 50%): +1.0
- Floor advanced: +0.5
- Turn ended with unspent energy > 0 and playable cards in hand: -0.3 (teach efficiency)
- Stuck / error: -5.0

**Discount factor** (gamma): 0.99 (games are long, ~120 steps, so near-1 gamma is needed to propagate terminal reward).

### Episode structure

One episode = one full game run (start_run to game_over). Typical length: 120 steps.

### Training phases

**Phase 1: Imitation learning warm-start (Day 3)**
- Convert 500 heuristic bot games to (state, action) pairs.
- Train the policy network via supervised cross-entropy loss to imitate the bot.
- Target: loss < 2.0 (bot actions are predictable).
- This gives the RL agent a reasonable starting policy instead of random.

**Phase 2: PPO training (Day 3-4)**
- Run 32 parallel game instances against sts2-cli (each a separate subprocess).
- Collect 4,096 steps per batch (128 steps x 32 environments).
- PPO update every batch.
- Total: 500 PPO updates = 2,048,000 steps = ~17,000 games.
- At 32 parallel processes on M1 Mac: 32 x 2.2 games/min = ~70 games/min = 17,000 games in ~4 hours.

**Phase 3: Fine-tune with fast sim (Day 4-5)**
- Once the Python combat simulator is calibrated, use it for combat-phase training.
- Run 10,000+ combat episodes per hour (100x faster than sts2-cli).
- Keep using sts2-cli for non-combat decisions (they're infrequent and fast).
- Total: 50,000 additional combat episodes over 5 hours.

### Hyperparameters

| Parameter | Value |
|---|---|
| Learning rate | 3e-4 |
| Batch size | 4,096 steps |
| Mini-batch size | 512 |
| PPO epochs per batch | 4 |
| PPO clip ratio (epsilon) | 0.2 |
| Value loss coefficient | 0.5 |
| Entropy bonus coefficient | 0.01 |
| GAE lambda | 0.95 |
| Gamma (discount) | 0.99 |
| Max gradient norm | 0.5 |
| Number of parallel envs | 32 |
| Total training steps | 2,048,000 (sts2-cli) + 5,000,000 (fast sim) |

### Implementation

```
src/sts2_tui/rl/
  __init__.py
  model.py          # ActorCritic MLP (Section 5)
  features.py       # state_to_features() -> np.array(512)
  actions.py         # action_id_to_command(), compute_action_mask()
  env.py             # STS2Env(gym.Env) wrapping sts2-cli subprocess
  train_ppo.py       # PPO training loop
  imitate.py         # Phase 1 imitation learning
  evaluate.py        # Run N games, report win rate
```

---

## 7. Validation

### Test against sts2-cli (real engine)

The trained model is always validated against the real sts2-cli engine, never the fast sim alone. This ensures no simulation inaccuracies affect the final evaluation.

**Validation script**: `tools/evaluate_rl.py` runs 100 games on sts2-cli with the trained policy (greedy action selection, no exploration). Reports:

| Metric | Target (Week 1) | Heuristic Bot Baseline | Human-like |
|---|---|---|---|
| Act 1 win rate (reach floor 17) | >10% | ~25% (estimated from smart_bot reaching floor 15) | ~50% |
| Average floor reached | >12 | ~13 | 17 |
| Average HP at death | >15 | ~10 | N/A (they win) |
| Games without stuck/crash | >95% | 100% | 100% |

### Comparison against the heuristic bot

Run 100 games each for the RL agent and `tools/smart_bot.py` on the same 100 seeds. Compare:
1. Win rate
2. Floor reached distribution
3. Average HP remaining at each floor
4. Average deck size at death (indicator of card selection quality)

### Regression testing

After each training run, re-run the 100-seed evaluation. Track metrics over time in `data/eval_results.csv`:
```
timestamp, training_step, win_rate, avg_floor, avg_hp_at_death, games_stuck
```

### Sanity checks

- **Action distribution**: Log the frequency of each action during evaluation. Check that the agent plays a variety of cards (not just spamming Strike) and doesn't end turn with unspent energy >50% of turns.
- **Combat efficiency**: Average number of turns per combat should be <8 (the heuristic bot averages ~6). If >10, the agent is playing suboptimally.
- **Card reward behavior**: Track pick vs skip rate. Good agents skip when deck is large and pick synergistic cards when small.

---

## 8. Integration -- Plug into the TUI as Advisor

### Architecture

The RL model runs as an in-process Python module within sts2-tui. No separate server needed -- the model is 238K parameters (~1 MB on disk), loads in <100ms, and inference takes <1ms per call.

### Loading

At TUI startup, if the model checkpoint exists at `data/model/policy.pt`, load it:

```python
# In src/sts2_tui/tui/app.py, during SlsApp.on_mount()
from sts2_tui.rl.advisor import Advisor
self.advisor = Advisor("data/model/policy.pt")  # Returns None if file missing
```

### Scoring

When `GameController` receives a new state from the bridge, the advisor scores all valid actions:

1. `features.state_to_features(state)` converts the raw JSON state to a 512-float vector.
2. `actions.compute_action_mask(state)` produces a 64-bool mask.
3. `model.forward(features)` returns 64 action logits + 1 state value.
4. Apply mask, softmax, and return top-3 actions with probabilities.

### Display in the TUI

Add a **1-line suggestion bar** at the bottom of each screen (above the status bar), showing the advisor's top recommendation:

```
[AI] Play Bash -> Enemy 0 (73%)  |  2nd: Defend (18%)  |  Value: +4.2
```

Implementation:
- Add an `AdvisorBar` widget to `src/sts2_tui/tui/shared.py`.
- The bar is hidden if no model is loaded (`self.advisor is None`).
- The bar updates whenever the screen receives a new state.
- Toggle visibility with `[A]` hotkey.

### User experience

- The advisor is **optional** -- it only appears if `data/model/policy.pt` exists.
- It is **display-only** -- it never sends commands to the engine.
- It shows a confidence percentage so the user can judge whether to trust it.
- The state value estimate ("+4.2") gives the user a sense of how well the run is going.
- Works on all decision screens: combat, map, card reward, rest, shop, event.

---

## Schedule

| Day | Task | Deliverable |
|---|---|---|
| 1 | Feature extraction + action space + batch data collection script | `rl/features.py`, `rl/actions.py`, 500 bot games logged |
| 2 | Python combat simulator (20 Ironclad cards, 8 enemy types) | `sim/combat.py`, calibrated within 5% of sts2-cli |
| 3 | Imitation learning + PPO training loop | `rl/train_ppo.py`, `rl/imitate.py`, initial model checkpoint |
| 4 | PPO training on sts2-cli (32 parallel envs, 4 hours) | Model achieving >5% Act 1 win rate |
| 5 | Fine-tune with fast sim + TUI advisor integration + evaluation | `data/model/policy.pt`, `AdvisorBar` widget, 100-game eval report |

---

## Dependencies

| Package | Version | Purpose |
|---|---|---|
| torch | >=2.0 | Model + training |
| numpy | >=1.24 | Feature vectors |
| pyarrow | >=14.0 | Parquet I/O |
| gymnasium | >=0.29 | Env wrapper standard interface |

Install: `pip install torch numpy pyarrow gymnasium`

No GPU required. All training runs on CPU (M1 Mac, 8 cores). The 238K-parameter model trains in ~4 hours for Phase 2.

---

## Risks and Mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| sts2-cli stuck states during batch training | Wastes training time | Use existing stuck detection (20 identical states = abort game, -5 reward) |
| Python sim diverges from real engine | Agent learns wrong strategies | Calibrate on 100 combats; only use sim for combat pre-training, always validate on sts2-cli |
| 32 parallel sts2-cli processes exceed memory | Training stalls | Each process uses ~200 MB; 32 x 200 MB = 6.4 GB, fits in 16 GB RAM. Reduce to 16 if needed |
| Reward shaping too aggressive | Agent exploits shaped rewards instead of winning | Start with sparse terminal reward only; add per-step shaping only if learning is too slow |
| Action masking bugs | Agent tries illegal actions, engine errors | Unit test mask computation against 100 logged game states |
