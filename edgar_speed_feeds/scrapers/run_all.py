"""Recovery runner: scan Benzinga endpoints and write alert/log artifacts.

Usage:
    python3 -m scrapers.run_all --force

Writes:
    alerts/YYYY-MM-DD_pead.jsonl   one normalized record per line (with event_type)
    logs/run_all.log               human-readable run log
    alerts/market_health.json      created only if missing

This is a recovery shim, not the original v2 PEAD evaluator. It emits
FIRE only for explicit, high-signal events and OBSERVE otherwise.
"""

from __future__ import annotations

import os
import sys
import json
import argparse
import datetime as _dt

try:
    from scrapers.benzinga_scanner import scan_all
except Exception:  # allow running as a loose script
    from benzinga_scanner import scan_all  # type: ignore

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ALERTS_DIR = os.path.join(_ROOT, "alerts")
_LOGS_DIR = os.path.join(_ROOT, "logs")
_LOG_PATH = os.path.join(_LOGS_DIR, "run_all.log")
_HEALTH_PATH = os.path.join(_ALERTS_DIR, "market_health.json")


def _log(line):
    stamp = _dt.datetime.now().isoformat(timespec="seconds")
    msg = "[%s] %s" % (stamp, line)
    os.makedirs(_LOGS_DIR, exist_ok=True)
    with open(_LOG_PATH, "a", encoding="utf-8") as fh:
        fh.write(msg + "\n")
    print(msg)


def _str_eq(val, target):
    return isinstance(val, str) and val.strip().lower() == target


def _str_has(val, *needles):
    if not isinstance(val, str):
        return False
    low = val.strip().lower()
    return any(n in low for n in needles)


def _classify(rec):
    """Return (event_type, reason) for a normalized record.

    FIRE only for explicit high-signal events:
      - ratings: price_target_action == raises, or rating_action == upgrades
      - guidance: obvious positive/up/upward guidance
    Everything else is OBSERVE.
    """
    endpoint = rec.get("endpoint")
    action = rec.get("action") or {}

    if endpoint == "ratings":
        if _str_eq(action.get("price_target_action"), "raises"):
            return "FIRE", "ratings price_target_action=raises"
        if _str_eq(action.get("rating_action"), "upgrades"):
            return "FIRE", "ratings rating_action=upgrades"

    if endpoint == "guidance":
        gtype = action.get("guidance_type")
        if _str_has(gtype, "positive", "upward", "raises", "raised") or _str_eq(gtype, "up"):
            return "FIRE", "guidance type indicates positive/upward"

    return "OBSERVE", "no high-signal match"


def run(force=False, limit=100):
    os.makedirs(_ALERTS_DIR, exist_ok=True)
    os.makedirs(_LOGS_DIR, exist_ok=True)

    _log("run_all start (force=%s, limit=%s) -- recovery shim" % (force, limit))
    _log(
        "TLS NOTE: verify disabled only for api.massive.com (platform custom-cred "
        "proxy self-signed chain). Not acceptable as permanent production behavior "
        "unless replaced with a proper CA bundle."
    )

    result = scan_all(limit=limit)
    status = result.get("status")
    records = result.get("records", [])
    counts = result.get("counts", {})
    endpoints = result.get("endpoints", {})

    date = result.get("date") or _dt.date.today().strftime("%Y-%m-%d")
    jsonl_path = os.path.join(_ALERTS_DIR, "%s_pead.jsonl" % date)

    fire_count = 0
    observe_count = 0

    with open(jsonl_path, "w", encoding="utf-8") as fh:
        for rec in records:
            event_type, reason = _classify(rec)
            out = dict(rec)
            out["event_type"] = event_type
            # Legacy-compatible aliases for older BMCMC readers/instructions.
            out["event"] = event_type
            out["type"] = "PEAD_ALERT" if event_type == "FIRE" else "BENZINGA_OBSERVE"
            out["classification_reason"] = reason
            fh.write(json.dumps(out) + "\n")
            if event_type == "FIRE":
                fire_count += 1
            else:
                observe_count += 1

    _log("scan status=%s counts=%s" % (status, counts))
    for name, meta in endpoints.items():
        _log(
            "endpoint %s http_status=%s ok=%s error=%s count=%s"
            % (name, meta.get("http_status"), meta.get("ok"), meta.get("error"), meta.get("count"))
        )
    _log("wrote %s (%s FIRE, %s OBSERVE)" % (jsonl_path, fire_count, observe_count))

    if fire_count == 0:
        if status == "error":
            errs = "; ".join(
                "%s=%s" % (n, m.get("error") or ("HTTP %s" % m.get("http_status")))
                for n, m in endpoints.items()
            )
            _log("NO FIRE: API failed. " + errs)
        else:
            _log(
                "NO FIRE: API auth OK, %s records fetched, but no recovery FIRE "
                "events matched the minimal high-signal criteria." % len(records)
            )

    if not os.path.exists(_HEALTH_PATH):
        health = {
            "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
            "source": "recovery_shim",
            "note": "Created by run_all recovery shim; not the v2 evaluator.",
            "status": "unknown",
        }
        with open(_HEALTH_PATH, "w", encoding="utf-8") as fh:
            json.dump(health, fh, indent=2)
        _log("created missing market_health.json")
    else:
        _log("market_health.json already exists; left untouched")

    _log("run_all done")
    return {
        "status": status,
        "jsonl": jsonl_path,
        "fire": fire_count,
        "observe": observe_count,
        "total": len(records),
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Benzinga PEAD recovery runner")
    parser.add_argument("--force", action="store_true", help="run regardless of cached state")
    parser.add_argument("--limit", type=int, default=100, help="max records per endpoint")
    args = parser.parse_args(argv)

    summary = run(force=args.force, limit=args.limit)
    print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
