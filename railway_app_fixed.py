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
    if "refresh_token" not in new_token:
        new_token["refresh_token"] = refresh_token
    _save_token(new_token)
    return new_token


def get_valid_token() -> str:
    token = _load_token()
    if not token:
        raise RuntimeError("No token available — re-authorize at /schwab/auth")
    obtained_at = token.get("obtained_at", 0)
    expires_in  = token.get("expires_in", 1800)
    if time.time() > obtained_at + expires_in - 300:
        token = _refresh_access_token(token)
    return token["access_token"]


# ── SCHWAB AUTH ROUTES ─────────────────────────────────────────────────────────

@app.route("/schwab/auth")
def schwab_auth():
    auth_url = (
        f"{SCHWAB_AUTH_URL}"
        f"?response_type=code"
        f"&client_id={SCHWAB_CLIENT_ID}"
        f"&redirect_uri={SCHWAB_CALLBACK_URL}"
    )
    return redirect(auth_url)


@app.route("/schwab/debug")
def schwab_debug():
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


@app.route("/schwab/keepalive")
def schwab_keepalive():
    try:
        get_valid_token()
        return jsonify({"status": "ok", "message": "Token refreshed"}), 200
    except RuntimeError as e:
        return jsonify({"status": "error", "message": str(e)}), 401


# ── SCHWAB MARKET DATA ─────────────────────────────────────────────────────────

@app.route("/schwab/quotes")
def schwab_quotes():
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


@app.route("/schwab/level2")
def schwab_level2():
    symbol = request.args.get("symbol", "")
    if not symbol:
        return jsonify({"error": "symbol param required"}), 400

    try:
        access_token = get_valid_token()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 401

    resp = requests.get(
        f"{SCHWAB_MARKET_URL}/quotes",
        headers={"Authorization": f"Bearer {access_token}"},
        params={"symbols": symbol, "fields": "quote,reference"},
        timeout=10,
    )

    if resp.status_code != 200:
        return jsonify({"error": f"Schwab API {resp.status_code}", "detail": resp.text}), resp.status_code

    return jsonify(resp.json()), 200


# ── SCHWAB TRADER (POSITIONS + ACCOUNTS) ──────────────────────────────────────

@app.route("/schwab/positions")
def schwab_positions():
    """All open positions across all accounts."""
    try:
        access_token = get_valid_token()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 401

    # Get account hash values
    resp = requests.get(
        f"{SCHWAB_TRADER_URL}/accounts/accountNumbers",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if resp.status_code != 200:
        return jsonify({"error": f"accountNumbers {resp.status_code}", "detail": resp.text}), resp.status_code

    account_numbers = resp.json()

    all_positions = []
    for acct in account_numbers:
        hash_val = acct.get("hashValue")
        acct_num = acct.get("accountNumber")
        if not hash_val:
            continue

        r = requests.get(
            f"{SCHWAB_TRADER_URL}/accounts/{hash_val}",
            headers={"Authorization": f"Bearer {access_token}"},
            params={"fields": "positions"},
            timeout=15,
        )
        if r.status_code != 200:
            continue

        acct_data = r.json()
        positions = acct_data.get("securitiesAccount", {}).get("positions", [])

        for pos in positions:
            instrument = pos.get("instrument", {})
            symbol = instrument.get("symbol", "")
            asset_type = instrument.get("assetType", "")
            desc = instrument.get("description", "")

            long_qty  = pos.get("longQuantity", 0)
            short_qty = pos.get("shortQuantity", 0)
            qty = long_qty if long_qty else -short_qty

            avg_price     = pos.get("averagePrice", 0)
            market_value  = pos.get("marketValue", 0)
            current_price = pos.get("currentDayProfitLossPercentage", None)

            pl_open = pos.get("longOpenProfitLoss", 0) or pos.get("shortOpenProfitLoss", 0)
            pl_day  = pos.get("currentDayProfitLoss", 0)

            all_positions.append({
                "account":      acct_num[-4:] if acct_num else "????",
                "symbol":       symbol,
                "description":  desc,
                "asset_type":   asset_type,
                "qty":          qty,
                "avg_price":    round(avg_price, 4),
                "market_value": round(market_value, 2),
                "pl_open":      round(pl_open, 2),
                "pl_day":       round(pl_day, 2),
            })

    return jsonify({"positions": all_positions, "count": len(all_positions)}), 200


@app.route("/schwab/accounts")
def schwab_accounts():
    """Account balances: net liq, buying power, P/L day."""
    try:
        access_token = get_valid_token()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 401

    resp = requests.get(
        f"{SCHWAB_TRADER_URL}/accounts/accountNumbers",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=15,
    )
    if resp.status_code != 200:
        return jsonify({"error": f"accountNumbers {resp.status_code}", "detail": resp.text}), resp.status_code

    account_numbers = resp.json()
    results = []

    for acct in account_numbers:
        hash_val = acct.get("hashValue")
        acct_num = acct.get("accountNumber")
        if not hash_val:
            continue

        r = requests.get(
            f"{SCHWAB_TRADER_URL}/accounts/{hash_val}",
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=15,
        )
        if r.status_code != 200:
            continue

        acct_data = r.json().get("securitiesAccount", {})
        balances  = acct_data.get("currentBalances", {})

        results.append({
            "account":          acct_num[-4:] if acct_num else "????",
            "type":             acct_data.get("type", ""),
            "net_liquidation":  round(balances.get("liquidationValue", 0), 2),
            "buying_power":     round(balances.get("buyingPower", 0) or balances.get("availableFunds", 0), 2),
            "cash_balance":     round(balances.get("cashBalance", 0), 2),
            "day_pl":           round(balances.get("dayTradingEquityCall", 0), 2),
            "equity":           round(balances.get("equity", 0), 2),
        })

    return jsonify({"accounts": results}), 200


# ── WEBHOOK ────────────────────────────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    data = request.get_json(silent=True) or {}
    ticker  = data.get("ticker", "UNKNOWN")
    price   = data.get("price", "?")
    ema     = str(data.get("ema", "50"))
    vixfix  = data.get("vixfix", "?")
    pct     = data.get("pct", "?")
    volume  = data.get("volume", "?")

    label = EMA_LABELS.get(ema, f"{ema} EMA")
    title = f"EMA SIGNAL — {ticker} | {label}"
    body  = (
        f"Price ${price} | {label} touch | "
        f"VixFix {vixfix} ({pct}th pct) | Vol {volume}x avg\n"
        f"Jan 2027 calls, 10 contracts, limit mid or below"
    )

    # Twilio SMS
    try:
        subprocess.run([
            "curl", "-s", "-X", "POST",
            "https://api.twilio.com/2010-04-01/Accounts/" + os.environ.get("TWILIO_ACCOUNT_SID", "") + "/Messages.json",
            "--user", os.environ.get("TWILIO_ACCOUNT_SID", "") + ":" + os.environ.get("TWILIO_AUTH_TOKEN", ""),
            "--data-urlencode", f"To=+17187047511",
            "--data-urlencode", f"From=+18442027763",
            "--data-urlencode", f"Body={title}\n{body}",
        ], timeout=10)
    except Exception:
        pass

    return jsonify({"status": "ok", "ticker": ticker}), 200


# ── HEALTH CHECK ───────────────────────────────────────────────────────────────

@app.route("/health")
def health():
    token = _load_token()
    schwab_auth = bool(token)
    if schwab_auth:
        obtained_at = token.get("obtained_at", 0)
        expires_in  = token.get("expires_in", 1800)
        schwab_auth = time.time() < obtained_at + expires_in

    return jsonify({
        "status":      "ok",
        "schwab_auth": schwab_auth,
        "timestamp":   datetime.utcnow().isoformat(),
    }), 200


# ── TEST ───────────────────────────────────────────────────────────────────────

@app.route("/test/<ticker>")
def test_alert(ticker):
    title = f"TEST — {ticker} | EMA Signal"
    body  = f"This is a test alert for {ticker}. System operational."
    return jsonify({"status": "ok", "title": title, "body": body}), 200


# ── LEGAL ──────────────────────────────────────────────────────────────────────

@app.route("/privacy")
def privacy():
    return """<html><body style="font-family:Arial;padding:40px;max-width:800px;">
    <h1>Privacy Policy — BMCMS LLC</h1>
    <p>Last updated: June 2, 2026</p>
    <p>BMCMS LLC ("we", "us") operates trading alert and notification services. We collect only the phone numbers necessary to deliver SMS alerts to authorized users. We do not sell or share personal information with third parties. SMS messages are sent solely for trading signal notifications requested by the account holder. To opt out, reply STOP to any message.</p>
    <p>Contact: connect@aemgworldwide.com</p>
    </body></html>"""


@app.route("/terms")
def terms():
    return """<html><body style="font-family:Arial;padding:40px;max-width:800px;">
    <h1>Terms of Service — BMCMS LLC</h1>
    <p>Last updated: June 2, 2026</p>
    <p>By using BMCMS LLC notification services, you agree that: (1) SMS alerts are for informational purposes only and do not constitute financial advice; (2) trading involves risk and past signals do not guarantee future results; (3) you are solely responsible for all trading decisions; (4) service availability is not guaranteed. BMCMS LLC is not liable for any trading losses.</p>
    <p>Contact: connect@aemgworldwide.com</p>
    </body></html>"""


# ── ENTRY POINT ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)


# ── SCHWAB OPTIONS CHAIN ───────────────────────────────────────────────────────

@app.route("/schwab/options")
def schwab_options():
    """
    Live options chain from Schwab.
    Params:
      symbol       — ticker (required), e.g. CC
      expiration   — YYYY-MM-DD (optional), filter to single expiry
      contract_type — CALL | PUT | ALL (default ALL)
      strike_count — number of strikes each side of ATM (default 20)
    Returns cleaned JSON: bid, ask, IV, delta, OI, volume per strike.
    """
    symbol = request.args.get("symbol", "").upper()
    if not symbol:
        return jsonify({"error": "symbol param required"}), 400

    expiration    = request.args.get("expiration", None)       # YYYY-MM-DD
    contract_type = request.args.get("contract_type", "ALL").upper()
    strike_count  = int(request.args.get("strike_count", 20))

    try:
        access_token = get_valid_token()
    except RuntimeError as e:
        return jsonify({"error": str(e)}), 401

    params = {
        "symbol":        symbol,
        "contractType":  contract_type,
        "strikeCount":   strike_count,
        "includeUnderlyingQuote": True,
        "strategy":      "SINGLE",
    }
    if expiration:
        params["fromDate"] = expiration
        params["toDate"]   = expiration

    resp = requests.get(
        f"{SCHWAB_MARKET_URL}/chains",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=15,
    )

    if resp.status_code != 200:
        return jsonify({"error": f"Schwab API {resp.status_code}", "detail": resp.text}), resp.status_code

    raw = resp.json()

    # Extract underlying price
    underlying_price = None
    uq = raw.get("underlyingQuote") or raw.get("underlying") or {}
    underlying_price = uq.get("last") or uq.get("mark") or uq.get("close")

    result = {
        "symbol":           symbol,
        "underlying_price": underlying_price,
        "status":           raw.get("status"),
        "expiration_dates": raw.get("callExpDateMap", {}) and list(raw.get("callExpDateMap", {}).keys()),
        "calls":            {},
        "puts":             {},
    }

    def parse_leg(exp_map):
        parsed = {}
        for exp_key, strikes in exp_map.items():
            exp_date = exp_key.split(":")[0]  # "2027-01-15:200"
            parsed[exp_date] = {}
            for strike_str, contracts in strikes.items():
                strike = float(strike_str)
                c = contracts[0] if contracts else {}
                parsed[exp_date][strike] = {
                    "bid":         c.get("bid"),
                    "ask":         c.get("ask"),
                    "last":        c.get("last"),
                    "mark":        c.get("mark"),
                    "iv":          round(c.get("volatility", 0), 4) if c.get("volatility") else None,
                    "delta":       round(c.get("delta", 0), 4) if c.get("delta") else None,
                    "theta":       round(c.get("theta", 0), 4) if c.get("theta") else None,
                    "oi":          c.get("openInterest"),
                    "volume":      c.get("totalVolume"),
                    "itm":         c.get("inTheMoney"),
                    "description": c.get("description"),
                }
        return parsed

    if contract_type in ("CALL", "ALL"):
        result["calls"] = parse_leg(raw.get("callExpDateMap", {}))
    if contract_type in ("PUT", "ALL"):
        result["puts"] = parse_leg(raw.get("putExpDateMap", {}))

    return jsonify(result), 200
