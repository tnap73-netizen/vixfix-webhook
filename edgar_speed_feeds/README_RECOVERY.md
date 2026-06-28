# PEAD Scanner — Recovery Shim

This package is a **minimal recovery shim**, created because the original
BMCMC PEAD scanner source artifact is missing from the sandbox, the Mac,
GitHub search, Railway, and Drive. It is **not** the full v2 PEAD
evaluator and does not attempt to reproduce its scoring/evaluation logic.

## What it does

- `scrapers/benzinga_scanner.py` — `scan_all(limit=100)` fetches Massive-proxied
  Benzinga endpoints (`/benzinga/v1/ratings`, `/benzinga/v1/earnings`,
  `/benzinga/v1/guidance`) under base URL `https://api.massive.com` using
  `requests` (falling back to `urllib`). Returns a JSON-serializable dict with
  `status`, `generated_at`, `endpoints`, `records`, and `counts`. Records are
  normalized to `source`, `ticker`, `date`, `action`, and `raw`.
- `scrapers/run_all.py` — calls `scan_all`, writes
  `alerts/YYYY-MM-DD_pead.jsonl`, appends to `logs/run_all.log`, and creates
  `alerts/market_health.json` if missing. Each record is tagged `event_type`:
  - `FIRE` only for explicit high-signal events:
    - ratings: `price_target_action == raises` or `rating_action == upgrades`
    - guidance: obvious positive/upward guidance
  - `OBSERVE` for everything else.
  - If no FIRE, it logs the real reason (auth OK but nothing matched, or the
    exact HTTP status / error if the API failed).

## Authentication

Credentials are **injected at the proxy layer** (Massive + Benzinga custom
credential, verified with HTTP 200 on `/benzinga/v1/ratings` using
`custom-cred:api.massive.com`). This code does **not** read or require raw
API keys, and never prints secrets. Because it uses `requests`/`urllib`,
`HTTPS_PROXY` credential injection works transparently.

## TLS verification (recovery shim only)

The platform custom-cred proxy presents a **self-signed certificate chain**,
which makes `requests` raise `SSLCertVerificationError` even though a direct
`curl` to the same endpoint returns HTTP 200. As a recovery measure this shim
**disables TLS verification only for `api.massive.com`**:

- `requests`: `verify=False` with the urllib3 `InsecureRequestWarning`
  suppressed for those calls only.
- `urllib` fallback: an unverified SSL context for those calls only.

All other hosts keep normal verification. **This is not acceptable as
permanent production scanner behavior.** The proper fix is to point
requests/urllib at the proxy's CA bundle (e.g. via `certifi` or
`REQUESTS_CA_BUNDLE`) so the self-signed chain validates, then re-enable
verification.

## Explicitly out of scope

No SMS sending, no `send_notification`, no `/exec`, no Bloomberg.

## Commands

From `/home/user/workspace/edgar_speed_feeds`:

```bash
# Full run (writes alerts + logs)
python3 -m scrapers.run_all --force

# Quick smoke test of the scanner
python3 -c "from scrapers.benzinga_scanner import scan_all; import json; print(json.dumps(scan_all(limit=5), indent=2))"
```

Run these with the parent's custom Massive/Benzinga credential active so the
proxy injects auth.
