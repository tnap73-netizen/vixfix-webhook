"""
TrendSpider VixFix Webhook + Schwab Market Data
-------------------------------------------------
Endpoints:
  POST /webhook            — TrendSpider VixFix alert receiver
  GET  /health             — health check
  GET  /test/<ticker>      — test notification
  GET  /schwab/auth        — initiate Schwab OAuth flow
  GET  /schwab/debug       — OAuth callback / token capture
  GET  /schwab/status      — token status check
  GET  /schwab/quotes      — live quotes: ?symbols=HTZ,FOXA,WMT,GME
  GET  /schwab/level2      — Level 2 order book: ?symbol=HTZ
  GET  /schwab/keepalive   — silent token refresh (called by daily cron)
  GET  /schwab/positions   — all open positions across all accounts
  GET  /schwab/accounts    — account balances (net liq, buying power, P/L)
  GET  /privacy             — BMCMS LLC Privacy Policy (public, for Twilio A2P)
  GET  /terms               — BMCMS LLC Terms of Service (public, for Twilio A2P)

Railway environment variables required:
  FINVIZ_AUTH        — Finviz Elite auth token
  SCHWAB_CLIENT_ID   — Schwab app key
  SCHWAB_CLIENT_SECRET — Schwab app secret
  SCHWAB_CALLBACK_URL  — must match Schwab developer portal exactly
"""

import os
import json
import time
import base64
import subprocess
import requests
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, redirect

app = Flask(__name__)

# ── CREDENTIALS ────────────────────────────────────────────────────────────────
FINVIZ_AUTH           = os.environ.get("FINVIZ_AUTH", "bd60c09b-06cb-42ab-9ef7-5b9d7259aedd")
SCHWAB_CLIENT_ID      = os.environ.get("SCHWAB_CLIENT_ID", "JmibNjVXEBxV0ALDHbDzuah9afosZ8YaBTjWM2TAjzuXNyZA")
SCHWAB_CLIENT_SECRET  = os.environ.get("SCHWAB_CLIENT_SECRET", "ylrPEvW7JmHLvrBpcDlX6MAztHg3EikJubvjbfIgUJODRXfAbBupZK2rEDwrAhKX")
SCHWAB_CALLBACK_URL   = os.environ.get("SCHWAB_CALLBACK_URL", "https://web-production-76c25d.up.railway.app/schwab/debug")

SCHWAB_AUTH_URL    = "https://api.schwabapi.com/v1/oauth/authorize"
SCHWAB_TOKEN_URL   = "https://api.schwabapi.com/v1/oauth/token"
SCHWAB_MARKET_URL  = "https://api.schwabapi.com/marketdata/v1"
SCHWAB_TRADER_URL  = "https://api.schwabapi.com/trader/v1"

# Token stored in memory (Railway persists env vars; token refreshed in-process)
_token_store = {}

TOKEN_FILE = "/tmp/schwab_token.json"

EMA_LABELS = {
    "50":  "GOOD — 50 EMA",
    "100": "STRONG — 100 EMA",
    "200": "NUCLEAR — 200 EMA",
}


# ── TOKEN MANAGEMENT ───────────────────────────────────────────────────────────

def _save_token(token_data: dict):
    _token_store.update(token_data)
    with open(TOKEN_FILE, "w") as f:
        json.dump(token_data, f)


def _load_token() -> dict:
    if _token_store:
        return _token_store
    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE) as f:
            data = json.load(f)
            _token_store.update(data)
            return data
    return {}


def _refresh_access_token(token_data: dict) -> dict:
    """Exchange refresh token for new access token."""
    refresh_token = token_data.get("refresh_token")
    if not refresh_token:
        raise RuntimeError("No refresh token available")

    credentials = base64.b64encode(
        f"{SCHWAB_CLIENT_ID}:{SCHWAB_CLIENT_SECRET}".encode()
    ).decode()

    resp = requests.post(
        SCHWAB_TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=15,
    )
    resp.raise_for_status()
    new_token = resp.json()
    new_token["obtained_at"] = time.time()
    # Preserve refresh token if not returned
    if "refresh_token" not in new_token:
        new_token["refresh_token"] = refresh_token
    _save_token(new_token)
    return new_token


def get_valid_token() -> str:
    """Returns a valid access token, refreshing if needed."""
    token = _load_token()
    if not token:
        raise RuntimeError("No token available — re-authorize at /schwab/auth")

    obtained_at = token.get("obtained_at", 0)
    expires_in  = token.get("expires_in", 1800)  # default 30 min
    # Refresh if within 5 minutes of expiry
    if time.time() > obtained_at + expires_in - 300:
        token = _refresh_access_token(token)

    return token["access_token"]


# ── SCHWAB AUTH ROUTES ─────────────────────────────────────────────────────────

@app.route("/schwab/auth")
def schwab_auth():
    """Redirect to Schwab OAuth login."""
    auth_url = (
        f"{SCHWAB_AUTH_URL}"
        f"?response_type=code"
        f"&client_id={SCHWAB_CLIENT_ID}"
        f"&redirect_uri={SCHWAB_CALLBACK_URL}"
    )
    return redirect(auth_url)


@app.route("/schwab/debug")
def schwab_debug():
    """OAuth callback — exchanges code for token."""
    code = request.args.get("code")
    if not code:
        return jsonify({"message": "No code received", "params": dict(request.args)}), 400

    credentials = base64.b64encode(
        f"{SCHWAB_CLIENT_ID}:{SCHWAB_CLIENT_SECRET}".encode()
    ).decode()

    resp = requests.post(
        SCHWAB_TOKEN_URL,
        headers={
            "Authorization": f"Basic {credentials}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": SCHWAB_CALLBACK_URL,
        },
        timeout=15,
    )

    if resp.status_code != 200:
        return f"<pre>Token exchange failed: {resp.status_code}\n{resp.text}</pre>", 400

    token_data = resp.json()
    token_data["obtained_at"] = time.time()
    _save_token(token_data)

    # Mask token for display
    masked = token_data.get("access_token", "")[:40] + "..."
    return f"""
    <html><body style="font-family:monospace;padding:40px;background:#0a0a0a;color:#00ff88;">
    <h2>&#x2705; Token captured!</h2>
    <p>Access token: {masked}</p>
    <p>Expires in: {token_data.get('expires_in', '?')} seconds</p>
    <p>Refresh token: {'YES' if token_data.get('refresh_token') else 'NO'}</p>
    <br>
    <a href="/schwab/status" style="background:#0066cc;color:white;padding:12px 24px;text-decoration:none;border-radius:6px;">Check Status</a>
    </body></html>
    """


@app.route("/schwab/status")
def schwab_status():
    """Token status check."""
    token = _load_token()
    if not token:
        return """
        <html><body style="font-family:monospace;padding:40px;background:#0a0a0a;color:#ff4444;">
        <h2>No Token</h2>
        <a href="/schwab/auth" style="background:#0066cc;color:white;padding:16px 32px;text-decoration:none;font-size:18px;border-radius:8px;">
          Authorize Schwab
        </a>
        </body></html>
        """

    obtained_at = token.get("obtained_at", 0)
    expires_in  = token.get("expires_in", 1800)
    remaining   = max(0, int(obtained_at + expires_in - time.time()))
    minutes     = remaining // 60

    return f"""
    <html><body style="font-family:monospace;padding:40px;background:#0a0a0a;color:#00ff88;">
    <h2>Schwab Token Status: {'VALID' if remaining > 0 else 'EXPIRED'}</h2>
    <p>Expires in: {minutes} minutes</p>
    <p>Refresh token: {'YES' if token.get('refresh_token') else 'NO'}</p>
    <br>
    <a href="/schwab/auth" style="background:#0066cc;color:white;padding:16px 32px;text-decoration:none;font-size:18px;border-radius:8px;">
      Re-Authorize Schwab
    </a>
    </body></html>
    """


# ── SCHWAB MARKET DATA ROUTES ──────────────────────────────────────────────────

@app.route("/schwab/quotes")
def schwab_quotes():
    """
    Live quotes for one or more symbols.
    Usage: /schwab/quotes?symbols=HTZ,FOXA,WMT,GME
    """
    symbols = request.args.get("symbols", "")
    if not symbols:
        return jsonify({"error": "symbols param required"}), 400

    try:
        access_token = get_valid_token()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 401

    resp = requests.get(
        f"{SCHWAB_MARKET_URL}/quotes",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"symbols": symbols, "fields": "quote,reference"},
        timeout=10,
    )

    if resp.status_code != 200:
        return jsonify({"error": f"Schwab API {resp.status_code}", "detail": resp.text}), resp.status_code

    data = resp.json()
    # Simplify output to key fields
    result = {}
    for sym, info in data.items():
        q = info.get("quote", {})
        result[sym] = {
            "price":        q.get("lastPrice") or q.get("mark"),
            "change":       q.get("netChange"),
            "change_pct":   q.get("netPercentChangeInDouble"),
            "volume":       q.get("totalVolume"),
            "bid":          q.get("bidPrice"),
            "ask":          q.get("askPrice"),
            "day_high":     q.get("highPrice"),
            "day_low":      q.get("lowPrice"),
            "52w_high":     q.get("52WeekHigh"),
            "52w_low":      q.get("52WeekLow"),
        }

    return jsonify(result), 200


@app.route("/schwab/positions")
def schwab_positions():
    """
    All open positions across all accounts.
    Returns simplified position data: symbol, qty, avg price, current value, P/L open, P/L day.
    """
    try:
        access_token = get_valid_token()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 401

    # First get account numbers
    resp = requests.get(
        f"{SCHWAB_TRADER_URL}/accounts/accountNumbers",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if resp.status_code != 200:
        return jsonify({"error": f"accountNumbers {resp.status_code}", "detail": resp.text}), resp.status_code

    account_numbers = resp.json()  # [{"accountNumber": "...", "hashValue": "..."}]

    all_positions = []
    for acct in account_numbers:
        hash_val = acct.get("hashValue")
        acct_num = acct.get("accountNumber")
        if not hash_val:
            continue

        r = requests.get(
            f"{SCHWAB_TRADER_URL}/accounts/{hash_val}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fie
