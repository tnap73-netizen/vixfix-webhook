#!/usr/bin/env python3
"""Repo-owned Massive/Benzinga verification probe.

Canonical proof that the one unified ``MASSIVE_API_KEY`` reaches the live
Benzinga-via-Massive feeds. This exists so future threads stop re-debugging
the credential: run it in the target runtime and read PASS/FAIL.

Canonical command (production web service):

    railway run --service web python3 scripts/probe_massive_benzinga.py

Notes:
  * Direct PC/sandbox bash may block outbound network; use Terminal/Railway or
    a normal Railway shell if the probe cannot reach ``api.massive.com``.
  * Auth follows the committed scanner behavior: ``Authorization: Bearer
    <MASSIVE_API_KEY>`` by default, header overridable via
    ``MASSIVE_API_KEY_HEADER``. If the header attempt returns non-200, the
    probe retries once with an ``apiKey`` query-string fallback.
  * Tests ``earnings``, ``guidance``, ``ratings`` with ``limit=1``.
  * Exit 0 only if MASSIVE_API_KEY is present AND all three endpoints return
    HTTP 200. Otherwise exit non-zero.
  * The key is never printed, logged, or echoed in any URL.
"""
from __future__ import annotations

import os
import sys
import json

# Reuse the committed scanner's auth/TLS behavior so the probe and the live
# scanner can never disagree about how the one key is presented.
_SCRAPERS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "edgar_speed_feeds",
    "scrapers",
)
if _SCRAPERS_DIR not in sys.path:
    sys.path.insert(0, _SCRAPERS_DIR)

try:
    import benzinga_scanner as _scanner

    BASE_URL = _scanner.BASE_URL
    ENDPOINTS = _scanner.ENDPOINTS
    _auth_headers = _scanner._auth_headers
    _ca_bundle = _scanner._ca_bundle
except Exception:  # self-contained fallback mirroring the committed defaults
    BASE_URL = "https://api.massive.com"
    ENDPOINTS = {
        "ratings": "/benzinga/v1/ratings",
        "earnings": "/benzinga/v1/earnings",
        "guidance": "/benzinga/v1/guidance",
    }

    def _auth_headers():
        key = os.environ.get("MASSIVE_API_KEY") or os.environ.get("BENZINGA_API_KEY")
        if not key:
            return {}
        header = (os.environ.get("MASSIVE_API_KEY_HEADER") or "Authorization").strip()
        if header.lower() == "authorization":
            return {"Authorization": "Bearer %s" % key}
        return {header: key}

    def _ca_bundle():
        for var in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
            path = os.environ.get(var)
            if path:
                return path
        try:
            import certifi

            return certifi.where()
        except Exception:
            return True


# Required endpoints, in a stable reporting order.
_REQUIRED = ("earnings", "guidance", "ratings")
_TIMEOUT = 30


def _http_get(path, params, headers):
    """GET BASE_URL+path returning (status_or_None, error_or_None).

    Never returns or logs the URL with secret params. Uses requests when
    available, else urllib, with TLS verification always on.
    """
    from urllib.parse import urlencode

    url = "%s%s?%s" % (BASE_URL, path, urlencode(params))
    bundle = _ca_bundle()
    try:
        import requests  # noqa: PLC0415

        resp = requests.get(url, timeout=_TIMEOUT, headers=headers, verify=bundle)
        return resp.status_code, None
    except ImportError:
        pass
    except Exception as exc:
        return None, _safe_err(exc)

    import urllib.request
    import urllib.error
    import ssl

    try:
        ctx = ssl.create_default_context(cafile=bundle) if isinstance(bundle, str) \
            else ssl.create_default_context()
        req = urllib.request.Request(url, headers=dict(headers, **{"Accept": "application/json"}))
        with urllib.request.urlopen(req, timeout=_TIMEOUT, context=ctx) as r:
            return (getattr(r, "status", 200) or 200), None
    except urllib.error.HTTPError as exc:
        return exc.code, None
    except Exception as exc:
        return None, _safe_err(exc)


def _safe_err(exc):
    """Stringify an exception without leaking a credential in a URL."""
    msg = str(exc)
    if "apiKey=" in msg or ("://" in msg and "@" in msg):
        msg = "connection error (redacted)"
    return "%s: %s" % (type(exc).__name__, msg)


def _probe_endpoint(name):
    """Probe one endpoint with limit=1. Returns (status, auth_mode, error)."""
    path = ENDPOINTS[name]
    params = {"limit": 1, "pageSize": 1}
    headers = {"Accept": "application/json"}
    headers.update(_auth_headers())

    status, err = _http_get(path, params, headers)
    if status == 200:
        return status, "header", None

    # apiKey query-string fallback (only if a key is available). The key value
    # is placed in params for the request but never printed.
    key = os.environ.get("MASSIVE_API_KEY") or os.environ.get("BENZINGA_API_KEY")
    if key:
        fb_params = dict(params)
        fb_params["apiKey"] = key
        fb_status, fb_err = _http_get(path, fb_params, {"Accept": "application/json"})
        if fb_status == 200:
            return fb_status, "apiKey", None
        # Prefer the more informative of the two attempts.
        return (fb_status if fb_status is not None else status), "apiKey", (fb_err or err)

    return status, "header", err


def main():
    key_present = bool(os.environ.get("MASSIVE_API_KEY"))

    results = {}
    all_ok = True
    for name in _REQUIRED:
        if not key_present:
            # Do not make network calls without the canonical key present.
            results[name] = {"http_status": None, "ok": False, "auth_mode": None,
                             "error": "MASSIVE_API_KEY missing"}
            all_ok = False
            continue
        status, auth_mode, err = _probe_endpoint(name)
        ok = status == 200
        all_ok = all_ok and ok
        results[name] = {"http_status": status, "ok": ok, "auth_mode": auth_mode, "error": err}

    overall = key_present and all_ok

    # Human-readable, machine-parseable lines (no secret printed anywhere).
    print("MASSIVE_API_KEY: %s" % ("present" if key_present else "missing"))
    for name in _REQUIRED:
        r = results[name]
        print("endpoint=%s http=%s ok=%s auth=%s%s" % (
            name,
            r["http_status"],
            r["ok"],
            r["auth_mode"],
            ("" if not r["error"] else " error=%s" % r["error"]),
        ))
    print("RESULT: %s" % ("PASS" if overall else "FAIL"))
    print("SUMMARY_JSON: " + json.dumps({
        "result": "PASS" if overall else "FAIL",
        "key_present": key_present,
        "endpoints": results,
    }, sort_keys=True))

    return 0 if overall else 1


if __name__ == "__main__":
    sys.exit(main())
