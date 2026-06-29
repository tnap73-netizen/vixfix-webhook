# BMCMC Thread Independence Audit

Status: canonical audit checklist for proving BMCMC work is no longer owned by a single Perplexity thread.

Purpose: give any new thread a fast way to verify durable ownership across Space, Hindsight, GitHub, Railway, scheduled jobs, subscriptions, Schwab, SMS routing, doctrine, and data architecture.

## Verdict

BMCMC doctrine and operating context are no longer owned by one chat thread when all checks below pass.

Current durable layers:

- Space stores recovery docs and handoff docs.
- Hindsight stores durable decisions, corrections, and future-revision notes.
- GitHub stores repo-owned docs, code, manifests, and scripts.
- Railway owns runtime services and scheduled service configs.
- Credential stores / Railway variables own secrets.
- Large historical datasets must live in durable storage outside the chat thread.

## Files every new BMCMC thread must be able to find

Space files:

- `BMCMC_NEW_THREAD_BOOTSTRAP.md`
- `BMCMC_THREAD_INDEPENDENCE_AUDIT.md`
- `BMCMC_SUBSCRIPTION_AND_BACKTEST_REGISTRY.md`
- `BMCMC_BACKTEST_THREAD_DATA_HANDOFF.md`
- `BMCMC_EDGE_DETECTOR_TWOSIDED_V3.md`

Repo files:

- `BMCMC_NEW_THREAD_BOOTSTRAP.md`
- `BMCMC_THREAD_INDEPENDENCE_AUDIT.md`
- `BMCMC_SUBSCRIPTION_AND_BACKTEST_REGISTRY.md`
- `BMCMC_BACKTEST_THREAD_DATA_HANDOFF.md`
- `BMCMC_EDGE_DETECTOR_TWOSIDED_V3.md`
- `cron_registry.json`
- `BMCMC_CRON_CONTROL_DOCTRINE.md`
- `BMCMC_PEAD_PROTOCOL_v2.0.md`
- `edgar_speed_feeds/config/SUBSCRIPTION_REGISTRY.md`
- `scripts/verify_subscription_env.py`

## Hindsight source

- `hindsight_461c3bf386b84a4fad415a6016d1c910`

Recall tags:

- `bmcmc`
- `new-thread-bootstrap`
- `subscription-registry`
- `massive`
- `benzinga`
- `railway`
- `cron`
- `schwab-api`
- `market-health`
- `sms`
- `universe-data`
- `edge-detector-v3`

Durable updates must be retained with `sync_retain`.

## GitHub anchor

Repo:

- `tnap73-netizen/vixfix-webhook`

Known continuity commit:

- `eba084e`

Commit contents:

- `BMCMC_BACKTEST_THREAD_DATA_HANDOFF.md`
- `BMCMC_SUBSCRIPTION_AND_BACKTEST_REGISTRY.md`
- `BMCMC_EDGE_DETECTOR_TWOSIDED_V3.md`
- `BMCMC_NEW_THREAD_BOOTSTRAP.md`

Any later thread must verify current `main` contains these files before assuming repo continuity is intact.

## Doctrine independence checks

A new thread must recover these without reading the old chat transcript:

- No price stops. Time stops only.
- PEAD uses 30-day ATM options, never Jan 2027 LEAPS.
- Friday entries are allowed.
- Market health must be included in every alert.
- Vendor audit before requesting new services.
- No Bloomberg after 2026-06-29.
- No `/exec` endpoint.
- SMS-only alert path; do not call `send_notification`.
- Grandfathered LEAPs:
  - HTZ 20x $5C Jan 2027 at $2.85.
  - FOXA 8x $65C Jan 2027 at $6.25.
  - GME 6x $22C Jan 2027 at $7.45.
  - WMT 10x $120C Jan 2027 at $13.05.

If a new thread cannot recover these from Space, Hindsight, or repo files, thread independence is incomplete.

## Subscription independence checks

Canonical rule:

- `MASSIVE_API_KEY` is the one key.
- Benzinga rides on the Massive key.
- No separate `BENZINGA_API_KEY` unless legacy code inspection proves a hardcoded compatibility path.

Covered package:

- Options Starter.
- Benzinga Analyst Ratings.
- Benzinga Corporate Guidance.
- Benzinga Earnings.

Perplexity runtime:

- `custom-cred:api.massive.com`

Railway runtime:

- `MASSIVE_API_KEY` must exist as a service/shared variable.

Verification:

- Benzinga Earnings endpoint returns HTTP 200.
- Benzinga Corporate Guidance endpoint returns HTTP 200.
- Benzinga Analyst Ratings endpoint returns HTTP 200.
- Options Starter access is available where the strategy needs options-layer checks.

## Cron and scheduler independence checks

Active scheduled-task doctrine:

- Verify-before-delete.
- Old thread-owned cron stays live until replacement fires and produces equivalent output.
- Watchdog and SMS drain migrate last.
- `cron_registry.json` is updated after every cutover.

Known slot states:

- `aadcd5f8`: canonical Daily PEAD Protocol v2.0 slot. Keep live until replacement verified.
- `aa59ac63`: deleted duplicate PEAD slot. Historical only.
- `e2d79a04`: old market-health task. Keep live until Railway production market-hours run verifies.
- `43e3532a`: EDGAR Speed Feeds. Keep live until replacement verified.
- `e141cdb1`: SMS drain. Migrate last.
- `c688ccb1`: Watchlist re-grade. Keep live until replacement verified.

A new thread must read `cron_registry.json` before deleting or modifying any scheduled job.

## Railway independence checks

Production app:

- `https://web-production-76c25d.up.railway.app`

Project/service mapping:

- Railway project: `caring-happiness`
- Main service: `web`
- Repo: `tnap73-netizen/vixfix-webhook`

Market-health service:

- Service: `bmcmc-market-health`
- Service id: `9c60529c-0e0e-41dd-988c-cf7d9a6019fe`
- Volume: `bmcmc-market-health-volume`
- Volume id: `aca12af7-1743-4202-b71c-97ea0b16334f`
- Mount path: `/data`
- Production branch: `railway-market-health`
- Production schedule: `0 12-21 * * 1-5`
- Start command: `python3 scripts/market_health_refresh.py`

Runtime proof required:

- `railway run python3 --version`
- `python3 scripts/verify_subscription_env.py --strict`
- market-health scheduled production fire during market hours
- relevant PEAD/EDGAR pipeline smoke run

## Schwab independence checks

Schwab reporting layer is considered deployed and previously smoke-tested after re-auth, but any new thread should verify live if it is about reporting or journal/P&L work.

Critical routes:

- `/schwab/status`
- `/schwab/keepalive`
- `/schwab/orders`
- `/schwab/transactions`
- `/schwab/transactions?startDate=2026-06-01T00:00:00.000Z&types=TRADE&symbol=HTZ`

High-signal smoke:

- HTZ-specific transactions should return real fills because HTZ is the largest grandfathered LEAP position.

Future revision note:

- Current first-account default is acceptable only while account count is one.
- When BMCMC opens a second Schwab account, revise `/schwab/orders` and `/schwab/transactions` to iterate all accounts and merge results or require explicit `account` param.

## SMS independence checks

SMS doctrine:

- In-app notifications are not canonical.
- SMS-only routing is through email-to-SMS.
- Queue file: `edgar_speed_feeds/alerts/sms_queue.jsonl`.
- Do not call `send_notification`.

Before deleting old SMS infrastructure:

- Verify repo-owned SMS drain live.
- Verify queue append.
- Verify outbound email-to-SMS path.
- Migrate SMS drain last.

## Data independence checks

Research data is universe-dependent, not backtest-dependent.

Universe snapshots are the source of truth.

Backtests reference immutable `universe_snapshot_ids` and write only run manifests/results.

Large historical datasets must not live only in:

- a chat thread
- a transient sandbox
- a single backtest output folder

Durable storage target must be one of:

- Railway volume
- Google Drive
- object storage
- another declared archive

Required durable dataset categories:

- universe snapshots
- event calendar
- Benzinga Earnings
- Benzinga Corporate Guidance
- Benzinga Analyst Ratings
- EDGAR Speed Feeds
- adjusted OHLCV / relative volume
- factor data
- costs and frictions
- outcome tables

## New-thread full-system test prompt

Paste this into a brand-new thread in the TRADING CODING 2026 Space:

```text
BMCMC full continuity audit.

Do not rely on this chat transcript.

First search Space files, then recall Hindsight, then check GitHub repo state if tools are available.

Tell me:
1. What files define BMCMC new-thread continuity?
2. What GitHub repo and commit contain the continuity docs?
3. What key controls Massive and Benzinga?
4. What subscriptions are covered?
5. What are the doctrine locks?
6. Which cron slots must not be deleted yet?
7. What Railway project/service maps to web-production-76c25d.up.railway.app?
8. What Schwab routes need smoke tests?
9. What is the SMS-only doctrine?
10. Is research data universe-dependent or backtest-dependent?
11. What remains live-runtime verified versus merely documented?
```

Expected result:

- The thread should answer from Space/Hindsight/GitHub, not from pasted history.
- It should say doctrine is durable.
- It should say production runtime still needs live checks where applicable.

## What is fully solved

- New-thread recovery path.
- Space docs.
- Hindsight memory.
- GitHub continuity docs.
- Subscription doctrine.
- Edge Detector v3 spec.
- Universe-data architecture.
- Backtest handoff.
- Schwab future multi-account note.

## What still requires live production verification

These are not thread-ownership problems. They are runtime checks:

- Railway has `MASSIVE_API_KEY`.
- Railway can hit Massive/Benzinga live from target service.
- PEAD/EDGAR scheduled replacement fires and matches old output.
- Market-health production schedule fires during market hours.
- SMS drain replacement works before old drain is deleted.
- Durable universe archive exists and has snapshot manifests.

## Final rule

If a future thread can recover this audit, the bootstrap, the subscription registry, and the Edge Detector spec from Space/Hindsight/GitHub, then no single chat thread owns BMCMC operating context.

If a future thread cannot verify Railway runtime, credentials, schedulers, or data archive, that is a production-infra gap, not a thread-memory gap.

