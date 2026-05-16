"""
TrendSpider VixFix Webhook Receiver
------------------------------------
Receives POST from TrendSpider when a VixFix + EMA loading zone alert fires.
For each triggered ticker:
  1. Pulls live stock quote via yFinance
  2. Pulls Finviz Elite daily chart
  3. Pulls NASDAQ Level 2 book via Schwab API
  4. Fires a Perplexity push notification

Credentials loaded from Railway environment variables:
  FINVIZ_AUTH          = Finviz Elite auth token
  PPLX_USER_ID         = Perplexity user ID (push notifications)
  SCHWAB_CLIENT_ID     = Schwab app client ID
  SCHWAB_CLIENT_SECRET = Schwab app client secret
  SCHWAB_TOKEN         = base64-encoded token JSON (auto-updated on refresh)
"""

import os
import json
import base64
import requests
import secrets
import yfinance as yf
from datetime import datetime, timezone
from urllib.parse import urlencode
from flask import Flask, request, jsonify, redirect

app = Flask(__name__)

FINVIZ_AUTH          = os.environ.get("FINVIZ_AUTH", "")
PPLX_USER_ID         = os.environ.get("PPLX_USER_ID", "")
SCHWAB_CLIENT_ID     = os.environ.get("SCHWAB_CLIENT_ID", "")
SCHWAB_CLIENT_SECRET = os.environ.get("SCHWAB_CLIENT_SECRET", "")
SCHWAB_TOKEN_B64     = os.environ.get("SCHWAB_TOKEN", "")
RAILWAY_TOKEN        = os.environ.get("RAILWAY_TOKEN", "")       # Railway API token for self-updating ENV
RAILWAY_SERVICE_ID   = os.environ.get("RAILWAY_SERVICE_ID", "")  # Railway service ID
RAILWAY_PROJECT_ID   = os.environ.get("RAILWAY_PROJECT_ID", "")  # Railway project ID

# Base URL for Schwab OAuth callback — must match Schwab developer portal exactly
BASE_URL = "https://web-production-76c25d.up.railway.app"
SCHWAB_REDIRECT_URI = f"{BASE_URL}/schwab/callback"

EMA_LABELS = {
    "50":  "GOOD — 50 EMA",
    "100": "STRONG — 100 EMA",
    "200": "NUCLEAR — 200 EMA",
}

# In-memory state store for OAuth flow (survives within a dyno lifetime)
_oauth_state = {}
_token_cache = {}


# ─────────────────────────────────────────────
# SCHWAB TOKEN HELPERS
# ─────────────────────────────────────────────

def decode_token():
    """Decode base64 SCHWAB_TOKEN env var into dict."""
    global SCHWAB_TOKEN_B64
    raw = SCHWAB_TOKEN_B64 or os.environ.get("SCHWAB_TOKEN", "")
    if not raw:
        return None
    try:
        decoded = base64.b64decode(raw).decode("utf-8")
        return json.loads(decoded)
    except Exception as e:
        print(f"[TOKEN] Decode error: {e}")
        return None


def encode_token(token_dict):
    """Encode token dict to base64 string for ENV storage."""
    return base64.b64encode(json.dumps(token_dict).encode()).decode()


def get_schwab_access_token():
    """Return a valid Schwab access token, refreshing if needed."""
    token_data = _token_cache if _token_cache else decode_token()
    if not token_data:
        return None

    access_token  = token_data.get("access_token")
    refresh_token = token_data.get("refresh_token")
    expires_at    = token_data.get("expires_at", 0)
    now           = datetime.now(timezone.utc).timestamp()

    if now < expires_at - 60:
        return access_token  # still valid

    # Refresh
    print("[SCHWAB] Token expired, refreshing...")
    if not refresh_token:
        print("[SCHWAB] No refresh token — re-auth required")
        return None

    try:
        resp = requests.post(
            "https://api.schwabapi.com/v1/oauth/token",
            data={"grant_type": "refresh_token", "refresh_token": refresh_token},
            auth=(SCHWAB_CLIENT_ID, SCHWAB_CLIENT_SECRET),
            timeout=10,
        )
        if resp.status_code == 200:
            new_data = resp.json()
            token_data["access_token"]  = new_data["access_token"]
            token_data["refresh_token"] = new_data.get("refresh_token", refresh_token)
            token_data["expires_at"]    = now + new_data.get("expires_in", 1800)
            _token_cache.update(token_data)
            save_token_to_env(token_data)
            print("[SCHWAB] Token refreshed")
            return token_data["access_token"]
        else:
            print(f"[SCHWAB] Refresh failed: {resp.status_code} — re-auth required")
            return None
    except Exception as e:
        print(f"[SCHWAB] Refresh error: {e}")
        return None


def save_token_to_env(token_dict):
    """Persist refreshed token back to Railway ENV via Railway API (optional)."""
    global SCHWAB_TOKEN_B64
    encoded = encode_token(token_dict)
    SCHWAB_TOKEN_B64 = encoded
    # If Railway API credentials are set, update the variable automatically
    if RAILWAY_TOKEN and RAILWAY_SERVICE_ID and RAILWAY_PROJECT_ID:
        try:
            mutation = """
            mutation variableUpsert($input: VariableUpsertInput!) {
              variableUpsert(input: $input)
            }
            """
            payload = {
                "query": mutation,
                "variables": {
                    "input": {
                        "projectId": RAILWAY_PROJECT_ID,
                        "serviceId": RAILWAY_SERVICE_ID,
                        "name": "SCHWAB_TOKEN",
                        "value": encoded,
                    }
                }
            }
            r = requests.post(
                "https://backboard.railway.app/graphql/v2",
                json=payload,
                headers={"Authorization": f"Bearer {RAILWAY_TOKEN}", "Content-Type": "application/json"},
                timeout=10,
            )
            if r.status_code == 200:
                print("[TOKEN] Saved to Railway ENV")
            else:
                print(f"[TOKEN] Railway save failed: {r.status_code}")
        except Exception as e:
            print(f"[TOKEN] Railway save error: {e}")


# ─────────────────────────────────────────────
# SCHWAB OAUTH ENDPOINTS
# ─────────────────────────────────────────────

@app.route("/schwab/auth", methods=["GET"])
def schwab_auth():
    """
    Step 1 — Open this URL on any device (phone/desktop) to start Schwab OAuth.
    Redirects to Schwab login page. After login, Schwab redirects to /schwab/callback.
    """
    if not SCHWAB_CLIENT_ID:
        return jsonify({"error": "SCHWAB_CLIENT_ID not set in Railway variables"}), 500

    state = secrets.token_urlsafe(16)
    _oauth_state["state"] = state

    params = {
        "response_type": "code",
        "client_id":     SCHWAB_CLIENT_ID,
        "redirect_uri":  SCHWAB_REDIRECT_URI,
        "scope":         "readonly",
        "state":         state,
    }
    auth_url = "https://api.schwabapi.com/v1/oauth/authorize?" + urlencode(params)
    print(f"[AUTH] Redirecting to Schwab: {auth_url}")
    return redirect(auth_url)


@app.route("/schwab/callback", methods=["GET"])
def schwab_callback():
    """
    Step 2 — Schwab redirects here after login.
    Exchanges auth code for access + refresh tokens, stores in ENV.
    """
    error = request.args.get("error")
    if error:
        desc = request.args.get("error_description", "Unknown error")
        return f"<h2>Auth failed: {error}</h2><p>{desc}</p>", 400

    code  = request.args.get("code")
    state = request.args.get("state")

    # State check is best-effort only — Railway may route to different worker
    if state and _oauth_state.get("state") and state != _oauth_state.get("state"):
        print(f"[AUTH] State mismatch (multi-worker) — proceeding anyway")

    if not code:
        return "<h2>No auth code received from Schwab.</h2>", 400

    # Exchange code for tokens
    try:
        resp = requests.post(
            "https://api.schwabapi.com/v1/oauth/token",
            data={
                "grant_type":   "authorization_code",
                "code":         code,
                "redirect_uri": SCHWAB_REDIRECT_URI,
            },
            auth=(SCHWAB_CLIENT_ID, SCHWAB_CLIENT_SECRET),
            timeout=15,
        )

        if resp.status_code != 200:
            return f"<h2>Token exchange failed</h2><pre>{resp.status_code}: {resp.text}</pre>", 500

        token_data = resp.json()
        now        = datetime.now(timezone.utc).timestamp()
        token_data["expires_at"] = now + token_data.get("expires_in", 1800)

        # Store in memory and persist
        _token_cache.clear()
        _token_cache.update(token_data)
        save_token_to_env(token_data)

        encoded = encode_token(token_data)
        expires_dt = datetime.fromtimestamp(token_data["expires_at"]).strftime("%I:%M %p ET")

        return f"""
        <html><body style="font-family:monospace;padding:40px;background:#0a0a0a;color:#00ff88;">
        <h2>✅ Schwab Auth Successful</h2>
        <p>Token stored. Expires: {expires_dt}</p>
        <p>Copy this value into Railway → Variables → SCHWAB_TOKEN:</p>
        <textarea rows="4" style="width:100%;background:#111;color:#0f0;border:1px solid #0f0;padding:10px;font-size:12px;">{encoded}</textarea>
        <br><br>
        <p style="color:#888;">If RAILWAY_TOKEN is set, this was already saved automatically.</p>
        <p><a href="/schwab/status" style="color:#0f0;">Check token status →</a></p>
        </body></html>
        """, 200

    except Exception as e:
        return f"<h2>Error: {e}</h2>", 500


@app.route("/schwab/status", methods=["GET"])
def schwab_status():
    """Check current Schwab token status."""
    token_data = _token_cache if _token_cache else decode_token()
    if not token_data:
        auth_url = f"{BASE_URL}/schwab/auth"
        return f"""
        <html><body style="font-family:monospace;padding:40px;background:#0a0a0a;color:#ff4444;">
        <h2>❌ No Schwab Token</h2>
        <p>Tap below to authorize:</p>
        <a href="{auth_url}" style="background:#ff4444;color:white;padding:16px 32px;text-decoration:none;font-size:18px;border-radius:8px;">
          Authorize Schwab
        </a>
        </body></html>
        """, 200

    expires_at = token_data.get("expires_at", 0)
    now        = datetime.now(timezone.utc).timestamp()
    remaining  = int(expires_at - now)
    status     = "VALID" if remaining > 0 else "EXPIRED"
    color      = "#00ff88" if remaining > 0 else "#ff4444"
    mins       = remaining // 60

    return f"""
    <html><body style="font-family:monospace;padding:40px;background:#0a0a0a;color:{color};">
    <h2>Schwab Token Status: {status}</h2>
    <p>{'Expires in: ' + str(mins) + ' minutes' if remaining > 0 else 'Token expired — re-auth required'}</p>
    <br>
    <a href="/schwab/auth" style="background:#0066cc;color:white;padding:16px 32px;text-decoration:none;font-size:18px;border-radius:8px;">
      Re-Authorize Schwab
    </a>
    </body></html>
    """, 200


# ─────────────────────────────────────────────
# MARKET DATA
# ─────────────────────────────────────────────

def get_level2_book(ticker):
    """Pull NASDAQ Level 2 book via Schwab Market Data API."""
    access_token = get_schwab_access_token()
    if not access_token:
        return None
    try:
        book_url = f"https://api.schwabapi.com/marketdata/v1/{ticker}/books"
        headers  = {"Authorization": f"Bearer {access_token}"}
        resp     = requests.get(book_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            return {"bids": data.get("bids", [])[:5], "asks": data.get("asks", [])[:5]}
        # Fallback: basic quote
        resp2 = requests.get(
            "https://api.schwabapi.com/marketdata/v1/quotes",
            headers=headers,
            params={"symbols": ticker, "fields": "quote"},
            timeout=10,
        )
        if resp2.status_code == 200:
            qd = resp2.json().get(ticker, {}).get("quote", {})
            return {
                "bid": qd.get("bidPrice"), "ask": qd.get("askPrice"),
                "bid_size": qd.get("bidSize"), "ask_size": qd.get("askSize"),
                "last": qd.get("lastPrice"), "mark": qd.get("mark"),
            }
    except Exception as e:
        print(f"[LEVEL2] Error for {ticker}: {e}")
    return None


def format_level2(l2_data):
    if not l2_data:
        return "Level 2: unavailable"
    if "bids" in l2_data and "asks" in l2_data:
        bids, asks = l2_data["bids"], l2_data["asks"]
        lines = ["Level 2 Book (top 5):", f"  {'BID':>10}  {'SIZE':>6}    {'ASK':>10}  {'SIZE':>6}"]
        for i in range(min(max(len(bids), len(asks)), 5)):
            b  = bids[i] if i < len(bids) else {}
            a  = asks[i] if i < len(asks) else {}
            bp = f"${b.get('price',''):<8}" if b else " " * 10
            bs = str(b.get("totalVolume", b.get("size", ""))) if b else ""
            ap = f"${a.get('price',''):<8}" if a else " " * 10
            as_ = str(a.get("totalVolume", a.get("size", ""))) if a else ""
            lines.append(f"  {bp}  {bs:>6}    {ap}  {as_:>6}")
        return "\n".join(lines)
    bid, ask = l2_data.get("bid","N/A"), l2_data.get("ask","N/A")
    spread   = round(float(ask)-float(bid), 4) if bid!="N/A" and ask!="N/A" else "N/A"
    return (f"Level 2 (Schwab):\n"
            f"  Bid: ${bid} x{l2_data.get('bid_size','')}  |  Ask: ${ask} x{l2_data.get('ask_size','')}\n"
            f"  Mark: ${l2_data.get('mark','N/A')}  |  Spread: ${spread}")


def get_stock_quote(ticker):
    try:
        fi = yf.Ticker(ticker).fast_info
        price     = round(fi.last_price, 2)
        prev      = round(fi.previous_close, 2)
        chg       = round(((price - prev) / prev) * 100, 2) if prev else 0
        vol       = int(fi.last_volume)
        avg_vol   = int(fi.three_month_average_volume) if fi.three_month_average_volume else 1
        return {
            "price": price, "changesPercentage": chg,
            "volume": vol, "avgVolume": avg_vol,
            "dayHigh": round(fi.day_high, 2), "dayLow": round(fi.day_low, 2),
        }
    except Exception as e:
        print(f"[QUOTE] Error for {ticker}: {e}")
        return {}


def get_finviz_chart(ticker):
    url  = f"https://elite.finviz.com/chart.ashx?t={ticker}&ty=c&ta=1&p=d&auth={FINVIZ_AUTH}"
    path = f"/tmp/{ticker}_vixfix_chart.png"
    try:
        resp = requests.get(url, allow_redirects=True, timeout=10)
        if resp.status_code == 200 and resp.content[:4] == b'\x89PNG':
            with open(path, "wb") as f:
                f.write(resp.content)
            return path
    except Exception as e:
        print(f"[CHART] Error for {ticker}: {e}")
    return None


# ─────────────────────────────────────────────
# NOTIFICATION
# ─────────────────────────────────────────────

def build_notification(ticker, ema_level, quote, l2_data=None):
    price     = quote.get("price", "N/A")
    chg       = quote.get("changesPercentage", 0)
    vol       = quote.get("volume", 0)
    avg_vol   = quote.get("avgVolume", 1)
    day_low   = quote.get("dayLow", "N/A")
    day_high  = quote.get("dayHigh", "N/A")
    vol_ratio = round(vol / avg_vol, 1) if avg_vol else "N/A"
    ema_label = EMA_LABELS.get(ema_level, f"{ema_level} EMA")
    direction = "+" if chg >= 0 else ""
    vol_flag  = " ⚡ HIGH VOLUME" if vol_ratio != "N/A" and vol_ratio >= 2 else ""
    now       = datetime.now().strftime("%I:%M %p ET")
    l2_str    = format_level2(l2_data) if l2_data else "Level 2: unavailable"

    title = f"VixFix Loading Zone — {ticker} at {ema_label.split(' — ')[1]}"
    body  = (
        f"LOADING ZONE — {ema_label}\n\n"
        f"{ticker} | ${price} | {direction}{chg:.2f}%\n"
        f"Range: ${day_low} – ${day_high}\n"
        f"Volume: {vol_ratio}x avg{vol_flag}\n\n"
        f"{l2_str}\n\n"
        f"Signal: VixFix outstretched + price above {ema_level} EMA on pullback\n"
        f"Action: Level 2 stacking bids = entry confirmed\n\n"
        f"Bloomberg: {ticker} OMON for options chain\n"
        f"OptionStrat: https://optionstrat.com/build/long-call/{ticker}\n"
        f"Time: {now}"
    )
    return title, body


def send_push_notification(title, body):
    if not PPLX_USER_ID:
        print("[NOTIFY] No PPLX_USER_ID — skipping")
        return False
    try:
        resp = requests.post(
            "https://api.perplexity.ai/notifications/push",
            headers={"Content-Type": "application/json"},
            json={"user_id": PPLX_USER_ID, "title": title, "body": body},
            timeout=10,
        )
        return resp.status_code == 200
    except Exception as e:
        print(f"[NOTIFY] Error: {e}")
        return False


# ─────────────────────────────────────────────
# ROUTES
# ─────────────────────────────────────────────

@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        payload    = request.get_json(force=True) or {}
        ticker     = (payload.get("symbol") or payload.get("ticker") or
                      request.args.get("symbol") or "UNKNOWN").upper().strip()
        alert_name = (payload.get("alert") or payload.get("alert_name") or
                      request.args.get("alert") or "VixFix Loading Zone")
        ema_level  = next((lvl for lvl in ["200","100","50"] if lvl in alert_name), "50")

        if ticker == "UNKNOWN":
            return jsonify({"status": "error", "message": "No ticker found"}), 400

        quote       = get_stock_quote(ticker)
        chart_path  = get_finviz_chart(ticker)
        l2_data     = get_level2_book(ticker)
        title, body = build_notification(ticker, ema_level, quote, l2_data)
        notified    = send_push_notification(title, body)

        return jsonify({
            "status": "ok", "ticker": ticker, "ema_level": ema_level,
            "quote": quote, "level2": l2_data,
            "chart_saved": chart_path is not None,
            "notified": notified, "notification_body": body
        }), 200
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    token_data = _token_cache if _token_cache else decode_token()
    schwab_ok  = token_data is not None
    return jsonify({
        "status":      "running",
        "service":     "TrendSpider VixFix Webhook",
        "schwab_auth": schwab_ok,
        "auth_url":    f"{BASE_URL}/schwab/auth",
    }), 200


@app.route("/test/<ticker>", methods=["GET"])
def test_ticker(ticker):
    ticker      = ticker.upper()
    quote       = get_stock_quote(ticker)
    l2_data     = get_level2_book(ticker)
    title, body = build_notification(ticker, "200", quote, l2_data)
    notified    = send_push_notification(title, body)
    return jsonify({
        "ticker": ticker, "quote": quote, "level2": l2_data,
        "notification_title": title, "notification_body": body,
        "notified": notified
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
