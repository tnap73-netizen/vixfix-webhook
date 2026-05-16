"""
TrendSpider VixFix Webhook Receiver
------------------------------------
Receives POST from TrendSpider when a VixFix + EMA loading zone alert fires.
For each triggered ticker:
  1. Pulls live stock quote via yFinance
  2. Pulls Finviz Elite daily chart
  3. Pulls NASDAQ Level 2 book via Schwab API
  4. Fires a Perplexity push notification

Credentials are loaded from environment variables — never hardcoded.
Set these in Railway → Variables:
  FINVIZ_AUTH      = your Finviz Elite auth token
  PPLX_USER_ID     = your Perplexity user ID (for push notifications)
  SCHWAB_TOKEN     = JSON token from schwab-py auth flow
  SCHWAB_CLIENT_ID = Schwab app client ID
  SCHWAB_CLIENT_SECRET = Schwab app client secret
"""

import os
import json
import requests
import yfinance as yf
from datetime import datetime
from flask import Flask, request, jsonify

app = Flask(__name__)

FINVIZ_AUTH        = os.environ.get("FINVIZ_AUTH", "")
PPLX_USER_ID       = os.environ.get("PPLX_USER_ID", "")
SCHWAB_TOKEN_JSON  = os.environ.get("SCHWAB_TOKEN", "")
SCHWAB_CLIENT_ID     = os.environ.get("SCHWAB_CLIENT_ID", "")
SCHWAB_CLIENT_SECRET = os.environ.get("SCHWAB_CLIENT_SECRET", "")

EMA_LABELS = {
    "50":  "GOOD — 50 EMA",
    "100": "STRONG — 100 EMA",
    "200": "NUCLEAR — 200 EMA",
}


def get_schwab_access_token():
    """Extract or refresh Schwab access token from stored JSON."""
    if not SCHWAB_TOKEN_JSON:
        return None
    try:
        token_data = json.loads(SCHWAB_TOKEN_JSON)
        token = token_data.get("token", {})
        access_token = token.get("access_token")
        expires_at = token_data.get("expires_at", 0)
        now = datetime.utcnow().timestamp()

        # If token expired, refresh it
        if now >= expires_at - 60:
            print("[SCHWAB] Token expired, refreshing...")
            refresh_token = token.get("refresh_token")
            if not refresh_token:
                print("[SCHWAB] No refresh token available")
                return access_token  # try anyway
            resp = requests.post(
                "https://api.schwabapi.com/v1/oauth/token",
                data={
                    "grant_type": "refresh_token",
                    "refresh_token": refresh_token,
                },
                auth=(SCHWAB_CLIENT_ID, SCHWAB_CLIENT_SECRET),
                timeout=10
            )
            if resp.status_code == 200:
                new_token = resp.json()
                access_token = new_token.get("access_token", access_token)
                print("[SCHWAB] Token refreshed successfully")
            else:
                print(f"[SCHWAB] Refresh failed: {resp.status_code} {resp.text}")

        return access_token
    except Exception as e:
        print(f"[SCHWAB] Token parse error: {e}")
        return None


def get_level2_book(ticker):
    """Pull NASDAQ Level 2 book via Schwab Market Data API."""
    access_token = get_schwab_access_token()
    if not access_token:
        return None
    try:
        url = f"https://api.schwabapi.com/marketdata/v1/pricehistory"
        # Use quotes endpoint for Level 2 / book data
        book_url = f"https://api.schwabapi.com/marketdata/v1/{ticker}/books"
        headers = {"Authorization": f"Bearer {access_token}"}
        resp = requests.get(book_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            data = resp.json()
            bids = data.get("bids", [])[:5]
            asks = data.get("asks", [])[:5]
            return {"bids": bids, "asks": asks}
        else:
            print(f"[LEVEL2] {resp.status_code}: {resp.text[:200]}")
            # Fallback: pull real-time quote with bid/ask
            quote_url = f"https://api.schwabapi.com/marketdata/v1/quotes"
            resp2 = requests.get(
                quote_url,
                headers=headers,
                params={"symbols": ticker, "fields": "quote"},
                timeout=10
            )
            if resp2.status_code == 200:
                qdata = resp2.json()
                ticker_data = qdata.get(ticker, {}).get("quote", {})
                return {
                    "bid": ticker_data.get("bidPrice"),
                    "ask": ticker_data.get("askPrice"),
                    "bid_size": ticker_data.get("bidSize"),
                    "ask_size": ticker_data.get("askSize"),
                    "last": ticker_data.get("lastPrice"),
                    "mark": ticker_data.get("mark"),
                }
    except Exception as e:
        print(f"[LEVEL2] Error for {ticker}: {e}")
    return None


def format_level2(l2_data):
    """Format Level 2 data for notification body."""
    if not l2_data:
        return "Level 2: unavailable"

    # Full book format
    if "bids" in l2_data and "asks" in l2_data:
        bids = l2_data["bids"]
        asks = l2_data["asks"]
        lines = ["Level 2 Book (top 5):"]
        lines.append(f"  {'BID':>10}  {'SIZE':>6}    {'ASK':>10}  {'SIZE':>6}")
        max_rows = max(len(bids), len(asks))
        for i in range(min(max_rows, 5)):
            b = bids[i] if i < len(bids) else {}
            a = asks[i] if i < len(asks) else {}
            bp = f"${b.get('price', ''):<8}" if b else " " * 10
            bs = str(b.get("totalVolume", b.get("size", ""))) if b else ""
            ap = f"${a.get('price', ''):<8}" if a else " " * 10
            as_ = str(a.get("totalVolume", a.get("size", ""))) if a else ""
            lines.append(f"  {bp}  {bs:>6}    {ap}  {as_:>6}")
        return "\n".join(lines)

    # Simple quote format
    bid = l2_data.get("bid", "N/A")
    ask = l2_data.get("ask", "N/A")
    bid_sz = l2_data.get("bid_size", "")
    ask_sz = l2_data.get("ask_size", "")
    mark = l2_data.get("mark", "N/A")
    spread = round(float(ask) - float(bid), 4) if bid != "N/A" and ask != "N/A" else "N/A"
    return (
        f"Level 2 (Schwab):\n"
        f"  Bid: ${bid} x{bid_sz}  |  Ask: ${ask} x{ask_sz}\n"
        f"  Mark: ${mark}  |  Spread: ${spread}"
    )


def get_stock_quote(ticker):
    """Pull real-time quote via yFinance."""
    try:
        t = yf.Ticker(ticker)
        info = t.fast_info
        price      = round(info.last_price, 2)
        prev_close = round(info.previous_close, 2)
        change_pct = round(((price - prev_close) / prev_close) * 100, 2) if prev_close else 0
        volume     = int(info.last_volume)
        avg_vol    = int(info.three_month_average_volume) if info.three_month_average_volume else 1
        day_high   = round(info.day_high, 2)
        day_low    = round(info.day_low, 2)
        return {
            "price": price,
            "changesPercentage": change_pct,
            "volume": volume,
            "avgVolume": avg_vol,
            "dayHigh": day_high,
            "dayLow": day_low,
        }
    except Exception as e:
        print(f"[QUOTE] Error for {ticker}: {e}")
        return {}


def get_finviz_chart(ticker):
    """Pull Finviz Elite daily chart PNG."""
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


def build_notification(ticker, ema_level, quote, l2_data=None):
    """Build notification title and body."""
    price      = quote.get("price", "N/A")
    change_pct = quote.get("changesPercentage", 0)
    volume     = quote.get("volume", 0)
    avg_vol    = quote.get("avgVolume", 1)
    day_low    = quote.get("dayLow", "N/A")
    day_high   = quote.get("dayHigh", "N/A")
    vol_ratio  = round(volume / avg_vol, 1) if avg_vol else "N/A"
    ema_label  = EMA_LABELS.get(ema_level, f"{ema_level} EMA")
    direction  = "+" if change_pct >= 0 else ""
    vol_flag   = " ⚡ HIGH VOLUME" if vol_ratio != "N/A" and vol_ratio >= 2 else ""
    now        = datetime.now().strftime("%I:%M %p ET")
    l2_str     = format_level2(l2_data) if l2_data else "Level 2: unavailable"

    title = f"VixFix Loading Zone — {ticker} at {ema_label.split(' — ')[1]}"
    body  = (
        f"LOADING ZONE — {ema_label}\n\n"
        f"{ticker} | ${price} | {direction}{change_pct:.2f}%\n"
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
    """Send push notification via Perplexity notification endpoint."""
    if not PPLX_USER_ID:
        print("[NOTIFY] No PPLX_USER_ID set — skipping push")
        return False
    try:
        resp = requests.post(
            "https://api.perplexity.ai/notifications/push",
            headers={"Content-Type": "application/json"},
            json={"user_id": PPLX_USER_ID, "title": title, "body": body},
            timeout=10
        )
        print(f"[NOTIFY] Response: {resp.status_code} {resp.text}")
        return resp.status_code == 200
    except Exception as e:
        print(f"[NOTIFY] Error: {e}")
        return False


@app.route("/webhook", methods=["POST"])
def webhook():
    try:
        raw = request.get_data(as_text=True)
        print(f"[WEBHOOK] Received: {raw}")

        try:
            payload = request.get_json(force=True) or {}
        except Exception:
            payload = {}

        ticker = (
            payload.get("symbol") or
            payload.get("ticker") or
            request.args.get("symbol") or
            "UNKNOWN"
        ).upper().strip()

        alert_name = (
            payload.get("alert") or
            payload.get("alert_name") or
            request.args.get("alert") or
            "VixFix Loading Zone"
        )

        ema_level = "50"
        for lvl in ["200", "100", "50"]:
            if lvl in alert_name:
                ema_level = lvl
                break

        if ticker == "UNKNOWN":
            return jsonify({"status": "error", "message": "No ticker found"}), 400

        quote      = get_stock_quote(ticker)
        chart_path = get_finviz_chart(ticker)
        l2_data    = get_level2_book(ticker)
        title, body = build_notification(ticker, ema_level, quote, l2_data)

        notified = send_push_notification(title, body)

        return jsonify({
            "status": "ok",
            "ticker": ticker,
            "ema_level": ema_level,
            "quote": quote,
            "level2": l2_data,
            "chart_saved": chart_path is not None,
            "notified": notified,
            "notification_body": body
        }), 200

    except Exception as e:
        print(f"[WEBHOOK] Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "running", "service": "TrendSpider VixFix Webhook"}), 200


@app.route("/test/<ticker>", methods=["GET"])
def test_ticker(ticker):
    ticker = ticker.upper()
    quote   = get_stock_quote(ticker)
    l2_data = get_level2_book(ticker)
    title, body = build_notification(ticker, "200", quote, l2_data)
    notified = send_push_notification(title, body)
    return jsonify({
        "ticker": ticker,
        "quote": quote,
        "level2": l2_data,
        "notification_title": title,
        "notification_body": body,
        "notified": notified
    }), 200


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
