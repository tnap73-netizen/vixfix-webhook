# BMCMC Subscription Registry

Status: repo-owned canonical registry. This file exists so feed availability survives Perplexity thread resets, sandbox resets, and handoff drift.

Do not commit raw keys. Secrets live in Railway variables or approved connector vaults only.

## Governance

- Vendor audit before requesting any new data service.
- No Bloomberg dependency after 2026-06-29.
- No custom `/exec` endpoint for recovery or credential inspection.
- Railway-native shell, Railway variables, GitHub, and this registry are the persistence layer.
- If this file and a thread disagree, this file wins unless a later commit updates it.

## Runtime secret locations

| Capability | Runtime variable / connector | Required for Railway? | Secret value allowed in git? | Notes |
|---|---|---:|---:|---|
| Massive API | `MASSIVE_API_KEY` | yes | no | Must be added directly to Railway service/shared variables. Perplexity `custom-cred:api.massive.com` does not carry into Railway. |
| Benzinga API | `BENZINGA_API_KEY` | yes | no | Required for guidance and analyst/PT endpoints. Add directly to Railway variables. |
| QuantData | Railway variable already present if service env includes it | yes for QuantData jobs | no | Verify by runtime env audit before cutover. |
| Schwab Client ID | `SCHWAB_CLIENT_ID` | yes | no | OAuth app credential. |
| Schwab Client Secret | `SCHWAB_CLIENT_SECRET` | yes | no | OAuth app credential. |
| Schwab tokens | Railway persistent runtime storage / token file / variables depending deployment | yes | no | Re-auth at `/schwab/auth` after app or scope changes. |
| Perplexity custom credential | `custom-cred:api.massive.com` | no | no | Usable only in Perplexity bash calls with `api_credentials=["custom-cred:api.massive.com"]`. Not a Railway runtime secret. |

## Feed map

| Feed / endpoint family | Provider | BMCMC use | Status | Persistence rule |
|---|---|---|---|---|
| Earnings surprise / historical EPS-revenue surprise | finance connector or Massive/Benzinga | ESS SUE component; PEAD context | substitutable | Use finance connector where available; if Railway engine needs Massive/Benzinga, require Railway keys. |
| Corporate guidance | Benzinga via Massive | ESS guidance impulse | gap until Railway keys exist | Do not fabricate. Mark `unavailable_this_run` for reduced ESS. |
| Analyst ratings / price-target revisions | Benzinga via Massive | ESS analyst/PT revision | gap until Railway keys exist | Do not fabricate. Mark `unavailable_this_run` for reduced ESS. |
| SEC EDGAR Form 4 / 13D / 8-K | SEC public endpoints | Insider and event catalysts | available | No paid key required. Must respect public endpoint rate limits. |
| Post-event OHLCV confirmation | yfinance / public OHLCV fallback | Post-event confirmation | substitutable | Schwab lacks canonical `/pricehistory`; yfinance is the accepted substitute unless changed by commit. |
| Schwab Trader API | Schwab | Orders, transactions, positions, account reporting | available after entitlement + re-auth | Smoke-test `/schwab/status`, `/schwab/keepalive`, `/schwab/orders`, `/schwab/transactions`, HTZ transaction query after deploy. |
| Market health | Yahoo chart API with Stooq fallback | Required in every alert | available | Railway `bmcmc-market-health` writes to `/data/edgar_speed_feeds`. |
| SMS dispatch | Gmail calendar email to `7187047511@vtext.com` | Alert delivery | active doctrine | Append to `edgar_speed_feeds/alerts/sms_queue.jsonl`. Do not use `send_notification`. |

## Edge Detector v3.0 ESS registry gate

Full ESS requires five components:

| Component | Design weight | Source | Current runtime state |
|---|---:|---|---|
| SUE / earnings surprise | 30% | finance connector or Massive/Benzinga | reachable/substitutable |
| Guidance impulse | 25% | Benzinga guidance via Massive | blocked until Railway has `MASSIVE_API_KEY` and `BENZINGA_API_KEY` |
| Analyst/PT revision | 20% | Benzinga ratings via Massive | blocked until Railway has `MASSIVE_API_KEY` and `BENZINGA_API_KEY` |
| Smart-money / insider catalyst | 15% | SEC EDGAR | reachable |
| Post-event confirmation | 10% | yfinance/public OHLCV | reachable/substitutable |

If Benzinga/Massive are not reachable from the engine runtime, only a reduced ESS run is allowed and the archive must record:

- `guidance_impulse=unavailable_this_run`
- `analyst_pt_revision=unavailable_this_run`
- reduced weights: SUE 54.5%, EDGAR/insider 27.3%, post-event confirmation 18.2%
- headline caveat: reduced-signal run, 55% of design signal

Full ESS is allowed only after `scripts/verify_subscription_env.py --strict` passes in the target runtime.

## Railway verification commands

Run inside the target runtime before cutover:

```bash
python3 scripts/verify_subscription_env.py --strict
```

Run locally or in Perplexity for registry-only validation:

```bash
python3 scripts/verify_subscription_env.py
```

## Open blocker

Railway PEAD/EDGAR and full Edge Detector v3.0 remain blocked until raw `MASSIVE_API_KEY` and `BENZINGA_API_KEY` are added to Railway. Do not paste keys in chat. Add them directly in Railway variables from the vendor dashboards or approved credential vault UI.
