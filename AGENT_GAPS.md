# STS2 Agent Gap Tracker

Gaps discovered while building the STS2 agent. Another agent monitors this file
and fixes issues in sts2-cli and sts2-tui.

## Format
Each gap: `- [ ] [severity] [component] Description`
Severity: CRITICAL (blocks gameplay), HIGH (wrong behavior), LOW (cosmetic/minor)

## Open Gaps


## Resolved Gaps

- [x] CRITICAL [sts2-cli] card_reward with empty cards[] after combat is STUCK — **FIXED**: DoSkipCardReward now clears orphaned _pendingPotionRewards when no card reward is pending. Commit 4377a53.
- [x] HIGH [sts2-cli] skip_card_reward sometimes doesn't advance — **FIXED**: Added Thread.Sleep(50), _syncCtx.Pump(), WaitForActionExecutor() after OnSkipped() so the game processes the skip before DetectDecisionPoint runs. Commit 1281a2b.
- [x] HIGH [sts2-cli] potion_reward decision type unclear — **NOT A SEPARATE TYPE**: potion rewards are sent as `potion_rewards` field within `card_reward` decision. Use `collect_potion_reward` (with `potion_index`) or `skip_potion_reward` commands. If potion belt is full, use `discard_potion_for_reward` (with `discard_index` and `potion_index`).
- [x] LOW [sts2-cli] card_select min_select/max_select missing — **NOT CONFIRMED**: Both fields are always sent as `int` (default 0) via `_cardSelector.PendingMinSelect/MaxSelect`. All card_select states go through this path.
- [x] LOW [sts2-cli] shop card_removal_available missing — **NOT CONFIRMED**: Field is always sent (`removal != null && !_shopCardRemoved`). When shop has no removal service, it's `false`. Agent should treat missing as `false`.
- [x] LOW [sts2-tui] tuned_bot.py doesn't handle potion_reward decision — **FIXED**: card_reward handler now collects or skips potion rewards before handling cards.
- [x] HIGH [sts2-cli] Engine hangs during combat (30-50% timeout rate) — **FIXED**: Three-layer fix: (1) Pump() callbacks run on ThreadPool with 5s timeout, (2) all bare GetAwaiter().GetResult() wrapped with RunWithTimeout(3-5s), (3) global 12s action watchdog force-kills player if any action exceeds deadline. No action can block the engine indefinitely.
