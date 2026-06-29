# BMCMC Subscription and Universe Data Registry

Status: Space-canonical recovery file for new Perplexity threads.

Purpose: make BMCMC subscription access and universe-level research data requirements discoverable without relying on the current thread transcript.

## New-thread rule

Any BMCMC trading thread must read this file before requesting new vendors, debugging Benzinga/Massive access, building a research universe, or running Edge Detector / PEAD backtests.

## Canonical subscription state

BMCMC uses one unified Massive key for both Massive and Benzinga feeds through `api.massive.com`.

Required runtime secret:

- `MASSIVE_API_KEY`

Do not require a separate `BENZINGA_API_KEY` unless code inspection proves a legacy path still explicitly reads it.

## Massive package controlled by the one key

- Options Starter.
- Benzinga Analyst Ratings.
- Benzinga Corporate Guidance.
- Benzinga Earnings.

## Perplexity credential handle

Inside Perplexity bash only:

- `custom-cred:api.massive.com`

This handle injects auth through the Perplexity custom-credentials proxy. It does not automatically exist in Railway. Railway must receive `MASSIVE_API_KEY` as a service/shared variable.

Known proxy note:

- `api.massive.com` may require the existing recovery shim TLS handling inside Perplexity because the proxy path has presented a self-signed chain.
- Permanent fix is a proper CA bundle, not disabling TLS globally.

## Feed-to-signal map

| Signal component | Required feed | Subscription source | Edge Detector weight |
|---|---|---|---:|
| Options liquidity / options layer readiness | Options Starter | Massive | Used for deployability checks, not Arm C live capital |
| Earnings surprise / SUE | Benzinga Earnings | Massive key through `api.massive.com` | 30% |
| Guidance impulse | Benzinga Corporate Guidance | Massive key through `api.massive.com` | 25% |
| Analyst rating / price-target revision | Benzinga Analyst Ratings | Massive key through `api.massive.com` | 20% |
| Insider / filing catalyst | EDGAR Speed Feeds | Repo-owned EDGAR pipeline | 15% |
| Post-event confirmation | Schwab/ToS market data or registered OHLCV substitute | Schwab/market-data layer | 10% |

## Universe data required

The data archive must be universe-dependent, not backtest-dependent. BMCMC will run many backtests against the same underlying research universe, so the durable archive should store point-in-time datasets by universe, date range, source, and schema version. Individual backtests should only reference immutable universe snapshots and write their own run outputs.

Required datasets:

- Universe snapshots: ticker, date, liquidity, price floor, sector, industry, borrow realism where applicable.
- Event calendar: earnings announcement timestamp, before/after-market flag, reporting period, source timestamp.
- Benzinga Earnings: EPS actual, EPS estimate, revenue actual, revenue estimate, surprise fields, timestamp as delivered.
- Benzinga Corporate Guidance: raise/cut direction, metric, prior guide, new guide, magnitude, source timestamp.
- Benzinga Analyst Ratings: firm, action, prior rating, new rating, prior PT, new PT, timestamp, post-print window tag.
- EDGAR Speed Feeds: Form 4 clusters, insider buy/sell tags, critical filing flags, filing timestamp.
- Price and volume: adjusted OHLCV, relative volume, first-session abnormal return, split/dividend adjustment metadata.
- Factor data: MKT, MOM, SMB, HML, risk-free rate, daily timestamps.
- Costs and frictions: commissions, spread/slippage model, borrow cost and locate feasibility for short tails.
- Outcome tables: forward returns and tradeability outcomes by ticker/date for T+1, T+5, T+30, and T+90 windows.
- Backtest run outputs: arm, tail, parameters, git commit, universe snapshot id, run timestamp, SHA-256 hash, and selected outcome windows.

## Storage doctrine

- Git stores manifests, schemas, docs, and verification scripts.
- Large historical datasets do not belong in Git.
- Durable historical data should live in a repo-referenced storage layer: Railway volume, Google Drive, object storage, or another declared archive.
- Universe snapshots are reusable. They should not be duplicated for every backtest.
- Every backtest run must write a manifest pointing to the exact universe snapshot ids used.

## Minimum manifest fields

Each universe dataset snapshot must include:

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

## Verification gate

Before claiming full ESS or full Edge Detector v3 readiness:

1. Verify `MASSIVE_API_KEY` exists in target runtime.
2. Verify Benzinga Earnings endpoint returns HTTP 200.
3. Verify Benzinga Corporate Guidance endpoint returns HTTP 200.
4. Verify Benzinga Analyst Ratings endpoint returns HTTP 200.
5. Verify universe data manifests exist for the run window.
6. Verify missing feeds are explicitly marked `unavailable_this_run` if reduced ESS is used.

## Current canonical conclusion

Massive/Benzinga is not two subscriptions or two keys for BMCMC. It is one Massive key controlling Options Starter, Benzinga Analyst Ratings, Benzinga Corporate Guidance, and Benzinga Earnings.

## Production verification

As of 2026-06-29, Railway project `caring-happiness`, service `web`, environment `production` has `MASSIVE_API_KEY` present.

Use `railway run --service web ...` for production web-service verification. The Railway CLI may default to another linked service such as `bmcmc-market-health`; if `--service web` is omitted, environment checks can falsely report `MASSIVE_API_KEY` missing.

Verified from Railway `web` runtime:

- `python3 scripts/verify_subscription_env.py --strict` returns `STRICT_PASS`.
- Benzinga Earnings through Massive returns HTTP 200.
- Benzinga Corporate Guidance through Massive returns HTTP 200.
- Benzinga Analyst Ratings through Massive returns HTTP 200.

Both `Authorization: Bearer <MASSIVE_API_KEY>` and `?apiKey=<MASSIVE_API_KEY>` returned HTTP 200 in live checks. The committed scanner defaults to bearer auth when `MASSIVE_API_KEY` is present and preserves proxy fallback when no key is present.

## Canonical proof command

Do not re-debug the key. The repo owns the verification. Run:

```bash
railway run --service web python3 scripts/probe_massive_benzinga.py
```

`scripts/probe_massive_benzinga.py` checks `MASSIVE_API_KEY` presence and hits Benzinga Earnings, Corporate Guidance, and Analyst Ratings through Massive with `limit=1`. It prints `RESULT: PASS`/`FAIL` plus per-endpoint HTTP statuses and a `SUMMARY_JSON:` line, and never prints the key. It exits `0` only when the key is present and all three endpoints return HTTP 200. Auth follows the committed scanner: `Authorization: Bearer <MASSIVE_API_KEY>` (header overridable via `MASSIVE_API_KEY_HEADER`), with an `apiKey` query-string fallback if the header attempt does not return 200.

Notes:

- Use `--service web`. Without it the Railway CLI may target another linked service (e.g. `bmcmc-market-health`) and falsely report the key missing.
- Direct PC/sandbox bash may block outbound network. Use Terminal/Railway or a normal Railway shell if the probe cannot reach `api.massive.com`.
