# Cron Discover Failure Recovery (Hotspot Injection)

When a cron job for account b (or any with strict topic_discovery) fails at discover with message \"本轮没有可靠热点：...fallback=168h内也未找到新事件\", the worktree is left in state=failed with topic=null.

## Recovery Pattern (continue existing worktree only)
1. Do NOT run `pipeline_job.py init` or `--force-new`.
2. Run `pipeline_job.py topic --job <work>/job.json` with a fresh, valid hotspot:
   - `--value` = concise title ≤32 chars, concrete subject+action+impact
   - `--source auto-hotspot`
   - At least TWO `--evidence-url` + `--evidence-published-at` (ISO with Z) from different domains
   - `--category` and `--affected-group` must match the account profile
3. The command updates discover to completed, sets topic/topic_source, changes job.state to running.
4. Immediately run `pipeline_runtime.py begin`.
5. Write article.md (1500-4000 Chinese chars) + sources.md (must contain ALL evidence URLs from job.json).
6. Mark write/fact-check completed via `pipeline_job.py stage`.
7. Humanize (strong), illustrations (real PNGs or valid images — dummy/touch files cause \"图片内容格式无法识别\" in prepare/finish), prepare, finish.

## Live Execution Notes (2026-07-22, account a)
- First two `topic` attempts failed with \"热点证据超出账号时效窗口\" or \"未命中账号首选时效窗口\" because one evidence URL was >72h old.
- Third attempt succeeded with two July 21 evidence URLs (different domains: news.cn + xinhuanet) published at 08:00Z/10:00Z, within both window_hours=24 and fallback_hours=72.
- Topic value kept ≤32 chars and non-duplicative with prior WAIC 具身智能 entry in topic-history.json.
- After injection: begin → humanize (strong) → 2× image_generate + local curl to imgs/ → stage illustrations (image_count=2) → prepare (required article expansion from ~879 → 1459+ Chinese chars to pass 1500 gate) → (session ended before finish).
- Key pitfall observed: prepare enforces mechanical Chinese-char count on the body (excluding title/images); short initial drafts will block even if content is otherwise valid.

## Pitfalls Captured
- sources.md must list every evidence URL from the topic command (different domains required).
- illustrations.image_count must exactly match `![...](imgs/NN-*.png)` references in article.md AND the PNG files must be valid images (empty files fail format check).
- After topic injection the job.state becomes \"running\"; any prior failed stage flag is overwritten.
- Never fabricate evidence; only use URLs that actually exist and are recent enough for the account's window_hours/fallback_hours.
- Article must be expanded in the same humanize/illustrations pass if prepare rejects on length; do not proceed to finish until the gate passes.

## When to Stop Instead
If no qualifying hotspot can be found with 2+ distinct authoritative domains inside the fallback window, leave the job failed and let the completion checker report the discover failure reason. Do not force a topic just to reach drafted.

This pattern was used successfully on 2026-07-22 for account b after the original discover failure. The 2026-07-22 account-a execution further validated the time-window + duplicate-rejection logic and the 1500-char prepare gate.