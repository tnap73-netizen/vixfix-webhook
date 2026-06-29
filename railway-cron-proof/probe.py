import json
import os
import sys
import time
import urllib.request

# MASSIVE_API_KEY is the sole required trading-feed secret (unified Massive/Benzinga
# key). BENZINGA_API_KEY is legacy/informational only and intentionally not tracked here.
CHECK_KEYS = [
    "BMCMC_PROOF_SENTINEL",
    "SCHWAB_CLIENT_ID",
    "SCHWAB_CLIENT_SECRET",
    "QUANT_DATA_EMAIL",
    "QUANT_DATA_PASS",
    "MASSIVE_API_KEY",
    "FINVIZ_AUTH",
]

def log(event, **kwargs):
    payload = {"event": event, "ts": int(time.time()), **kwargs}
    print(json.dumps(payload, sort_keys=True), flush=True)

log("scheduler_probe_start")
log("scheduler_env_presence", env={key: bool(os.environ.get(key)) for key in CHECK_KEYS})
url = os.environ.get("BMCMC_PROOF_HEALTH_URL", "https://web-production-76c25d.up.railway.app/health")
try:
    with urllib.request.urlopen(url, timeout=20) as r:
        body = r.read(500).decode("utf-8", "replace")
        log("scheduler_health_check", url=url, status=r.status, body=body[:200])
except Exception as exc:
    log("scheduler_health_check_error", url=url, error=repr(exc))
    sys.exit(2)
log("scheduler_probe_done")
