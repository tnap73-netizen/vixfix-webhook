#!/usr/bin/env python3
"""BMCMC repo-owned scheduler proof.
Runs once, logs scheduler/runtime/secret-injection facts, then exits cleanly.
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone

HEALTH_URL = os.environ.get("BMCMC_PROOF_HEALTH_URL", "https://web-production-76c25d.up.railway.app/health")
SECRET_KEYS = [
    "SCHWAB_CLIENT_ID",
    "SCHWAB_CLIENT_SECRET",
    "QUANT_DATA_EMAIL",
    "QUANT_DATA_PASS",
    "MASSIVE_API_KEY",
    "BENZINGA_API_KEY",
    "FINVIZ_AUTH",
    "BMCMC_PROOF_SENTINEL",
]

def log(event, **fields):
    rec = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "event": event,
        **fields,
    }
    print(json.dumps(rec, sort_keys=True), flush=True)

def fetch_health():
    req = urllib.request.Request(HEALTH_URL, headers={"User-Agent": "bmcmc-scheduler-proof/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        body = r.read().decode("utf-8", errors="replace")
        return r.status, json.loads(body)

def main():
    log("scheduler_probe_start", service=os.environ.get("RAILWAY_SERVICE_NAME"), env=os.environ.get("RAILWAY_ENVIRONMENT_NAME"))
    log("scheduler_env_presence", present={k: bool(os.environ.get(k)) for k in SECRET_KEYS})
    try:
        status, health = fetch_health()
        log("scheduler_health_check", http_status=status, health=health)
        if status != 200 or health.get("status") != "ok":
            return 2
    except Exception as exc:
        log("scheduler_health_error", error=type(exc).__name__, message=str(exc))
        return 1
    log("scheduler_probe_done", runtime_seconds=round(time.time() - START, 3))
    return 0

START = time.time()
if __name__ == "__main__":
    sys.exit(main())
