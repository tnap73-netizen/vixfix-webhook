# BMCMC Backtest Thread Data Handoff

Status: Space-canonical handoff for any new BMCMC backtest thread.

Purpose: tell the backtest thread where to find doctrine, subscriptions, universe data requirements, and runtime access rules before building or running tests.

## First instruction to the backtest thread

Use this opener:

> BMCMC backtest work. Pull Hindsight first, then read the Space files before acting. Data is universe-dependent, not backtest-dependent. Backtests must reference immutable universe snapshots and must not create one-off raw datasets per test.

## Read order

The backtest thread should read these Space files first:

1. `BMCMC_NEW_THREAD_BOOTSTRAP.md`
2. `BMCMC_SUBSCRIPTION_AND_BACKTEST_REGISTRY.md`
3. `BMCMC_EDGE_DETECTOR_TWOSIDED_V3.md`

Then check repo-owned files when the repo is available:

1. `cron_registry.json`
2. `BMCMC_PEAD_PROTOCOL_v2.0.md`
3. `BMCMC_CRON_CONTROL_DOCTRINE.md`
4. `edgar_speed_feeds/config/SUBSCRIPTION_REGISTRY.md`
5. `scripts/verify_subscription_env.py`

## Hindsight lookup

Use Hindsight source:

- `hindsight_461c3bf386b84a4fad415a6016d1c910`

Recall tags:

- `bmcmc`
- `backtest-data`
- `universe-data`
- `edge-detector-v3`
- `subscription-registry`
- `massive`
- `benzinga`
- `pead`

Retain durable results with `sync_retain`.

## Canonical subscription rule

There is one key:

- `MASSIVE_API_KEY`

This same key covers:

- Options Starter
- Benzinga Analyst Ratings
- Benzinga Corporate Guidance
- Benzinga Earnings

Do not require a separate `BENZINGA_API_KEY` unless code inspection proves a legacy path still explicitly reads that variable.

## Runtime access rules

Inside Perplexity bash:

- Use `api_credentials=["custom-cred:api.massive.com"]`
- Hit `https://api.massive.com/...`

Inside Railway:

- The service must have `MASSIVE_API_KEY` set as a Railway variable.
- Perplexity custom credentials do not automatically carry into Railway.
- Before claiming full ESS readiness, run the repo verifier inside the target runtime.

## Where the backtest data comes from

The backtest thread does not get durable research data from the chat transcript. It gets it from a universe-level archive.

Current design:

- Space stores doctrine and data contracts.
- Hindsight stores durable decisions and corrections.
- GitHub stores code, manifests, schemas, and verification scripts.
- Railway volume, Google Drive, object storage, or another declared archive stores large historical datasets.

The durable data archive still needs to be built if it does not already exist in the target repo/runtime.

## Universe-dependent data rule

Raw and cleaned research data must be keyed to the universe, not to a single backtest.

Backtests are consumers.

Universe snapshots are the source of truth.

Each backtest run must reference immutable `universe_snapshot_ids` and write only:

- run parameters
- strategy or arm name
- git commit
- universe snapshot ids
- result files
- hashes
- outcome windows
- notes

Do not duplicate raw source data per backtest.

## Required universe datasets

The universe archive must include:

1. Universe snapshots
   - ticker
   - date
   - liquidity
   - price floor
   - sector
   - industry
   - borrow realism where applicable

2. Event calendar
   - earnings announcement timestamp
   - before/after-market flag
   - reporting period
   - source timestamp

3. Benzinga Earnings
   - EPS actual
   - EPS estimate
   - revenue actual
   - revenue estimate
   - surprise fields
   - timestamp as delivered

4. Benzinga Corporate Guidance
   - raise/cut direction
   - metric
   - prior guide
   - new guide
   - magnitude
   - source timestamp

5. Benzinga Analyst Ratings
   - firm
   - action
   - prior rating
   - new rating
   - prior price target
   - new price target
   - timestamp
   - post-print window tag

6. EDGAR Speed Feeds
   - Form 4 clusters
   - insider buy/sell tags
   - critical filing flags
   - filing timestamp

7. Price and volume
   - adjusted OHLCV
   - relative volume
   - first-session abnormal return
   - split/dividend adjustment metadata

8. Factor data
   - MKT
   - MOM
   - SMB
   - HML
   - risk-free rate
   - daily timestamps

9. Costs and frictions
   - commissions
   - spread/slippage model
   - borrow cost
   - locate feasibility for short tails

10. Outcome tables
   - forward returns and tradeability outcomes by ticker/date
   - T+1
   - T+5
   - T+30
   - T+90

## Minimum universe snapshot manifest

Each universe snapshot manifest must include:

- `snapshot_id`
- `universe_id`
- `universe_definition`
- `created_at_utc`
- `source`
- `endpoint_or_file`
- `date_range_start`
- `date_range_end`
- `row_count`
- `schema_version`
- `sha256`
- `notes`

## Minimum backtest run manifest

Each backtest run manifest must include:

- `run_id`
- `created_at_utc`
- `strategy_or_arm`
- `parameters`
- `git_commit`
- `universe_snapshot_ids`
- `outcome_window`
- `result_file`
- `sha256`
- `notes`

## Edge Detector v3 dependency

The backtest thread must use `BMCMC_EDGE_DETECTOR_TWOSIDED_V3.md` as the spec for:

- Arm C pre-EAD drift
- Arm A PEAD v2 continuation
- Arm B market-neutral relative
- long and short tail separation
- no double-counting
- factor-regression gate
- out-of-sample discipline

Full ESS requires:

- SUE / Earnings: 30
- Guidance impulse: 25
- Analyst / price-target revision: 20
- EDGAR / insider: 15
- Post-event confirmation: 10

If any subscribed feed is missing during a run, mark it `unavailable_this_run` and label the result as reduced-signal. Do not silently reweight without logging.

## Verification gate before a real backtest

Before claiming the backtest is valid:

1. Confirm the three Space files are readable.
2. Confirm Hindsight recall works.
3. Confirm `MASSIVE_API_KEY` exists in the runtime being used.
4. Confirm Benzinga Earnings returns HTTP 200.
5. Confirm Benzinga Corporate Guidance returns HTTP 200.
6. Confirm Benzinga Analyst Ratings returns HTTP 200.
7. Confirm EDGAR Speed Feeds data is available for the test window.
8. Confirm OHLCV and factor data exist for the same test window.
9. Confirm universe snapshot manifests exist.
10. Confirm the backtest run writes a manifest referencing `universe_snapshot_ids`.

## Do not do

- Do not ask for a new Benzinga vendor or key before checking the registry.
- Do not build data only inside a chat thread.
- Do not store raw large historical data only in the sandbox.
- Do not duplicate raw datasets per backtest.
- Do not use Bloomberg after 2026-06-29.
- Do not use `/exec`.
- Do not claim full ESS if Massive/Benzinga verification fails.

## Current status

Thread continuity is solved through Space and Hindsight.

Subscription doctrine is solved:

- one `MASSIVE_API_KEY`
- four covered subscriptions

Universe data architecture is defined.

The remaining engineering step is to build or confirm the durable universe archive and commit the registry/manifests into the repo so GitHub, Space, Hindsight, and Railway all agree.

