# BMCMC New Thread Bootstrap

Status: canonical repo-owned handoff for fresh Perplexity threads.

Purpose: make BMCMC trading infrastructure reachable without relying on the current chat transcript. A new thread should be able to recover doctrine, subscription state, Railway mapping, scheduled-task migration status, and current blockers from repo + Hindsight.

## First prompt for a new thread

Use this exact opener:

```text
BMCMC LLC. Pull Hindsight context first. Then read the repo-owned bootstrap and registries before acting:
- BMCMC_NEW_THREAD_BOOTSTRAP.md
- BMCMC_THREAD_INDEPENDENCE_AUDIT.md
- BMCMC_EDGE_DETECTOR_TWOSIDED_V3.md
- BMCMC_SUBSCRIPTION_AND_BACKTEST_REGISTRY.md
- cron_registry.json
- BMCMC_PEAD_PROTOCOL_v2.0.md
- BMCMC_CRON_CONTROL_DOCTRINE.md
- edgar_speed_feeds/config/SUBSCRIPTION_REGISTRY.md

Direct trading language. No filler. No emojis. Do not request new vendors before checking the subscription registry. Do not use /exec. Use Railway-native shell or repo-owned scripts.
```

## Hindsight

- Source id: `hindsight_461c3bf386b84a4fad415a6016d1c910`
- Recall tags to try first:
  - `bmcmc`
  - `cron`
  - `railway`
  - `subscription-registry`
  - `benzinga`
  - `massive`
  - `edge-detector-v3`
  - `market-health`
  - `schwab-api`
- Retain mode for durable updates: `sync_retain`

## Repo

- GitHub repo: `tnap73-netizen/vixfix-webhook`
- Mac checkout: `/Users/toddnapolitano/Downloads/vixfix-webhook`
- Production Railway app: `https://web-production-76c25d.up.railway.app`
- Railway project: `caring-happiness`
- Production web service: `web`

## Canonical files

| File | Purpose |
|---|---|
| `BMCMC_NEW_THREAD_BOOTSTRAP.md` | This file. Start here in new threads. |
| `BMCMC_THREAD_INDEPENDENCE_AUDIT.md` | Full-system audit for proving no single thread owns BMCMC operating context. |
| `BMCMC_EDGE_DETECTOR_TWOSIDED_V3.md` | Canonical two-sided Edge Detector v3 implementation spec and run checklist. |
| `BMCMC_SUBSCRIPTION_AND_BACKTEST_REGISTRY.md` | Space-canonical subscription map and required backtest data manifest rules. |
| `cron_registry.json` | Migration ledger for old thread-owned scheduled tasks moving to repo/Railway ownership. |
| `BMCMC_CRON_CONTROL_DOCTRINE.md` | Scheduling doctrine and safety rules. |
| `BMCMC_PEAD_PROTOCOL_v2.0.md` | PEAD protocol doctrine. |
| `edgar_speed_feeds/config/SUBSCRIPTION_REGISTRY.md` | Subscription/feed registry. Source of truth for vendor reachability and required Railway variables. |
| `scripts/verify_subscription_env.py` | Non-secret runtime validator for required subscription env vars. |
| `scripts/market_health_refresh.py` | Repo-owned market-health scheduled entrypoint. |
| `edgar_speed_feeds/RECOVERY_SHIM_NOT_FULL_V2.md` | Recovery-shim banner. Prevents confusing recovery state with full Protocol v2. |

## Railway services

| Service | Purpose | Status |
|---|---|---|
| `web` | Main app, Schwab routes, webhook app | Production app service. |
| `bmcmc-market-health` | Repo-owned market-health scheduled service | Test-verified; keep old Perplexity task live until Monday production-market-hours fire verifies. |

Market-health service metadata:

- Service id: `9c60529c-0e0e-41dd-988c-cf7d9a6019fe`
- Volume: `bmcmc-market-health-volume`
- Volume id: `aca12af7-1743-4202-b71c-97ea0b16334f`
- Mount path: `/data`
- Production branch: `railway-market-health`
- Production schedule UTC: `0 12-21 * * 1-5`
- Start command: `python3 scripts/market_health_refresh.py`
- Test branch: `railway-market-health-test`
- Test schedule: `*/5 * * * *`

## Active scheduled-task doctrine

- Verify-before-delete. Old thread-owned jobs stay live until repo/Railway replacement fires and produces equivalent output.
- Watchdog and SMS drain migrate last.
- Update `cron_registry.json` after every cutover.
- Do not use `send_notification`; SMS-only routing is via queue/email-to-SMS doctrine.
- Do not create or use a custom `/exec` endpoint.

Known task states:

- `aadcd5f8`: canonical Daily PEAD Protocol v2.0 slot. Keep live until replacement verified.
- `aa59ac63`: deleted duplicate PEAD slot. Historical only.
- `e2d79a04`: old market-health task. Keep live until Railway production market-hours run verifies.
- `43e3532a`: EDGAR Speed Feeds. Keep live until replacement verified.
- `e141cdb1`: SMS drain. Migrate last.
- `c688ccb1`: Watchlist re-grade. Keep live until replacement verified.

## Subscription persistence rule

The subscription map lives in `edgar_speed_feeds/config/SUBSCRIPTION_REGISTRY.md`. It is repo-owned canonical state. Threads and sandboxes are not canonical.

Secrets are never committed. Required Railway variable must be present in Railway:

- `MASSIVE_API_KEY`

`MASSIVE_API_KEY` is the unified key for Massive/Benzinga access through `api.massive.com`. Do not ask for a separate Benzinga key unless code inspection proves a legacy path still explicitly requires `BENZINGA_API_KEY`.

Canonical Massive package controlled by this one key:

- Options Starter.
- Benzinga Analyst Ratings.
- Benzinga Corporate Guidance.
- Benzinga Earnings.

Perplexity custom credential `custom-cred:api.massive.com` works only inside Perplexity bash calls that explicitly pass `api_credentials=["custom-cred:api.massive.com"]`. It does not carry into Railway runtime.

Before full PEAD / EDGAR / Edge Detector v3.0 runs on Railway:

```bash
python3 scripts/verify_subscription_env.py --strict
```

Strict pass is required for full ESS. If strict fails because Massive/Benzinga are missing, only reduced ESS is allowed.

## Edge Detector v3.0 gate

Edge Detector v3.0 is the current direction-agnostic three-arm attribution spec:

- Arm C: pre-print drift, stock-only, paper-first.
- Arm A: live PEAD v2 continuation, post-print.
- Arm B: market-neutral relative, post-print.
- Long and short tails must be logged separately.
- Output is PASS/FAIL evidence, not a prettier equity curve.

Full ESS needs five components:

- SUE / earnings surprise: 30%.
- Guidance impulse: 25%.
- Analyst/PT revision: 20%.
- Insider / EDGAR: 15%.
- Post-event confirmation: 10%.

If Massive/Benzinga are unavailable, Guidance and Analyst/PT must be logged as `unavailable_this_run` and reduced ESS weights are:

- SUE: 54.5%.
- EDGAR/insider: 27.3%.
- Post-event confirmation: 18.2%.

Reduced ESS headline must say reduced-signal run, 55% of design signal.

## Schwab

Schwab reporting layer is considered deployed and previously smoke-tested after re-auth.

Critical routes:

- `/schwab/status`
- `/schwab/keepalive`
- `/schwab/orders`
- `/schwab/transactions`
- HTZ-specific transactions query:
  `/schwab/transactions?startDate=2026-06-01T00:00:00.000Z&types=TRADE&symbol=HTZ`

Future multi-account note: current first-account default is acceptable only while account count is one. When BMCMC opens a second Schwab account, revise `/schwab/orders` and `/schwab/transactions` to either iterate all accounts and merge results or require explicit `account` param.

## Trading doctrine locks

- No price stops. Time stops only.
- PEAD uses 30-day ATM options, never Jan 2027 LEAPS.
- Friday entries are allowed.
- Market health must be included in every alert.
- Vendor audit before requesting new services.
- No Bloomberg after 2026-06-29.
- No `/exec` endpoint.
- SMS-only alert path; do not call `send_notification`.

Grandfathered LEAP positions:

- HTZ: 20x $5C Jan 2027 at $2.85.
- FOXA: 8x $65C Jan 2027 at $6.25.
- GME: 6x $22C Jan 2027 at $7.45.
- WMT: 10x $120C Jan 2027 at $13.05.

## New-thread operating checklist

1. Pull Hindsight with the BMCMC tags above.
2. Read this file.
3. Read `BMCMC_EDGE_DETECTOR_TWOSIDED_V3.md`.
4. Read `BMCMC_SUBSCRIPTION_AND_BACKTEST_REGISTRY.md`.
5. Read `cron_registry.json`.
6. Read `edgar_speed_feeds/config/SUBSCRIPTION_REGISTRY.md`.
7. Check repo head and working tree.
8. Check Railway service status before changing anything.
9. Run `python3 scripts/verify_subscription_env.py --strict` inside target runtime before claiming full ESS is unblocked.
10. If changing scheduled infrastructure, update `cron_registry.json` and retain the result to Hindsight.
11. If changing subscription reachability, update `SUBSCRIPTION_REGISTRY.md` and retain the result to Hindsight.

## Current blocker to clear

Add the raw Massive/Benzinga key directly to Railway variables:

- `MASSIVE_API_KEY`

Then verify from Railway runtime with:

```bash
python3 scripts/verify_subscription_env.py --strict
```
