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

One unified key (doctrine): **`MASSIVE_API_KEY`** covers Massive/Benzinga
access (earnings, guidance, ratings) via `api.massive.com`.

- When `MASSIVE_API_KEY` is set, the scanner authenticates explicitly with
  `Authorization: Bearer <key>` (override the header name with
  `MASSIVE_API_KEY_HEADER` for non-Bearer schemes).
- When no key is set, no auth header is sent, preserving **proxy-injection /
  no-key** behavior for Perplexity `custom-cred:api.massive.com` environments.
- `BENZINGA_API_KEY` is an **optional legacy fallback** credential value only;
  it is never required and is not canonical.

The key is never printed or logged.

## TLS verification

Verification is **always on**. The scanner honors `REQUESTS_CA_BUNDLE` /
`SSL_CERT_FILE` when set, otherwise uses `certifi`'s bundle when available,
otherwise system trust. TLS verification is **never globally disabled**.

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
