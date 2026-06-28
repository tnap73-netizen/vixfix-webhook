"""Minimal Benzinga scanner recovery shim.

Fetches Massive-proxied Benzinga endpoints using `requests` (so an
HTTPS_PROXY-based credential injection works transparently) and falls
back to `urllib` if `requests` is not installed.

This module does NOT read or require raw API keys. Authentication is
expected to be injected by the parent at the proxy layer (Massive +
Benzinga custom credential). We never print secrets.

TLS NOTE (recovery shim only): the platform custom-cred proxy presents a
self-signed certificate chain, which makes `requests` raise
SSLCertVerificationError even though direct curl to the same endpoint
returns HTTP 200. As a recovery measure this shim disables TLS
verification *only* for api.massive.com calls (requests `verify=False`
with the urllib3 InsecureRequestWarning suppressed, and an unverified SSL
context for the urllib fallback). This is NOT acceptable as permanent
production scanner behavior; the real fix is to point requests/urllib at
the proxy's CA bundle (e.g. via certifi or REQUESTS_CA_BUNDLE) so the
self-signed chain validates.

This is a recovery shim, not the original v2 PEAD evaluator.
"""

from __future__ import annotations

import json
import datetime as _dt
from urllib.parse import urlencode

BASE_URL = "https://api.massive.com"

ENDPOINTS = {
    "ratings": "/benzinga/v1/ratings",
    "earnings": "/benzinga/v1/earnings",
    "guidance": "/benzinga/v1/guidance",
}

_TIMEOUT = 30

# Hosts for which we tolerate the platform proxy's self-signed cert chain.
# Recovery-shim only — see module docstring / README_RECOVERY.md.
_INSECURE_HOSTS = ("api.massive.com",)


def _is_insecure_host(url):
    try:
        from urllib.parse import urlparse

        host = (urlparse(url).hostname or "").lower()
    except Exception:
        return False
    return any(host == h or host.endswith("." + h) for h in _INSECURE_HOSTS)


def _today_str():
    """Return today's date as YYYY-MM-DD.

    America/New_York is not critical for the recovery shim; system date
    is acceptable per the recovery requirements.
    """
    try:
        from zoneinfo import ZoneInfo

        return _dt.datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")
    except Exception:
        return _dt.date.today().strftime("%Y-%m-%d")


def _fetch(url):
    """Fetch a URL returning (status_code, parsed_json_or_none, error_or_none).

    Uses requests if available so proxy credential injection works, else
    falls back to urllib.
    """
    insecure = _is_insecure_host(url)

    try:
        import requests  # noqa: PLC0415

        # Recovery shim: the platform custom-cred proxy presents a self-signed
        # chain, so verification must be disabled for the proxied Massive host.
        if insecure:
            try:
                import urllib3  # noqa: PLC0415

                urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
            except Exception:
                pass

        resp = requests.get(url, timeout=_TIMEOUT, verify=not insecure)
        status = resp.status_code
        try:
            data = resp.json()
        except Exception:
            data = None
        err = None if status == 200 else "HTTP %s" % status
        return status, data, err
    except ImportError:
        pass
    except Exception as exc:  # network/other errors from requests
        return None, None, _safe_err(exc)

    # urllib fallback
    import urllib.request
    import urllib.error
    import ssl

    try:
        # Recovery shim: unverified SSL context for the proxied Massive host
        # (self-signed proxy chain). Normal verification for any other host.
        ctx = ssl._create_unverified_context() if insecure else None
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as r:
            status = getattr(r, "status", 200) or 200
            body = r.read().decode("utf-8", "replace")
        try:
            data = json.loads(body)
        except Exception:
            data = None
        return status, data, None
    except urllib.error.HTTPError as exc:
        return exc.code, None, "HTTP %s" % exc.code
    except Exception as exc:
        return None, None, _safe_err(exc)


def _safe_err(exc):
    """Stringify an exception without leaking credentials."""
    msg = str(exc)
    # Defensive: never echo anything that looks like a credential token.
    if "://" in msg and "@" in msg:
        msg = "connection error (redacted)"
    return "%s: %s" % (type(exc).__name__, msg)


def _extract_records(data):
    """Pull a list of record dicts out of a variety of envelope shapes."""
    if data is None:
        return []
    if isinstance(data, list):
        return [r for r in data if isinstance(r, dict)]
    if isinstance(data, dict):
        for key in ("ratings", "earnings", "guidance", "data", "results", "items"):
            val = data.get(key)
            if isinstance(val, list):
                return [r for r in val if isinstance(r, dict)]
        # single record
        return [data]
    return []


def _first(rec, *keys):
    for k in keys:
        if k in rec and rec[k] not in (None, ""):
            return rec[k]
    return None


def _normalize(name, rec, date_default):
    """Normalize a raw record into a common shape; keep raw payload."""
    ticker = _first(rec, "ticker", "symbol", "Symbol", "tk")
    date = _first(rec, "date", "Date", "time", "datetime", "updated") or date_default

    action = {}
    if name == "ratings":
        action = {
            "rating_action": _first(rec, "action_company", "rating_action", "action"),
            "price_target_action": _first(rec, "action_pt", "price_target_action"),
            "rating_current": _first(rec, "rating_current", "rating"),
            "pt_current": _first(rec, "pt_current", "price_target"),
            "analyst": _first(rec, "analyst", "firm", "analyst_name"),
        }
    elif name == "guidance":
        action = {
            "guidance_type": _first(rec, "guidance_type", "type"),
            "period": _first(rec, "period", "fiscal_period"),
            "eps_guidance_est": _first(rec, "eps_guidance_est", "estimated_eps_guidance"),
            "prelim": _first(rec, "prelim", "preliminary"),
        }
    elif name == "earnings":
        action = {
            "eps": _first(rec, "eps", "eps_actual"),
            "eps_est": _first(rec, "eps_est", "eps_estimate"),
            "period": _first(rec, "period", "fiscal_period"),
        }

    return {
        "source": "benzinga",
        "endpoint": name,
        "ticker": ticker,
        "date": date,
        "action": action,
        "raw": rec,
    }


def scan_all(limit=100):
    """Fetch all configured Benzinga endpoints and return a JSON-serializable dict.

    Credentials are injected at the proxy layer; this function does not
    read API keys. Returns a dict with status, generated_at, endpoints,
    records, and counts.
    """
    date_default = _today_str()
    generated_at = _dt.datetime.now().isoformat(timespec="seconds")

    endpoints_meta = {}
    all_records = []
    counts = {}
    any_ok = False
    any_fail = False

    for name, path in ENDPOINTS.items():
        params = {"date": date_default, "pageSize": limit, "limit": limit}
        url = "%s%s?%s" % (BASE_URL, path, urlencode(params))
        status, data, err = _fetch(url)

        recs = _extract_records(data)
        if limit and len(recs) > limit:
            recs = recs[:limit]

        norm = [_normalize(name, r, date_default) for r in recs]
        all_records.extend(norm)
        counts[name] = len(norm)

        ok = status == 200 and err is None
        any_ok = any_ok or ok
        any_fail = any_fail or (not ok)

        endpoints_meta[name] = {
            "url": "%s%s" % (BASE_URL, path),
            "http_status": status,
            "ok": ok,
            "error": err,
            "count": len(norm),
        }

    if any_ok and not any_fail:
        status = "ok"
    elif any_ok and any_fail:
        status = "partial"
    else:
        status = "error"

    return {
        "status": status,
        "generated_at": generated_at,
        "date": date_default,
        "limit": limit,
        "endpoints": endpoints_meta,
        "records": all_records,
        "counts": counts,
    }


if __name__ == "__main__":
    print(json.dumps(scan_all(limit=5), indent=2))
