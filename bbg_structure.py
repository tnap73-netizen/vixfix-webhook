"""
Multi-timeframe EMA structure check via blpapi.
Usage: python bbg_structure.py WMT
Returns daily/weekly/monthly EMA fan status, price vs EMAs, RSI.
"""
import blpapi, json, sys, datetime

TICKER = sys.argv[1] if len(sys.argv) > 1 else "WMT"
SECURITY = f"{TICKER} US Equity"

session = blpapi.Session()
session.start()
session.openService("//blp/refdata")
svc = session.getService("//blp/refdata")

def bdp(fields, overrides=None):
    req = svc.createRequest("ReferenceDataRequest")
    req.append("securities", SECURITY)
    for f in fields:
        req.append("fields", f)
    if overrides:
        ov = req.getElement("overrides")
        for k, v in overrides.items():
            o = ov.appendElement()
            o.setElement("fieldId", k)
            o.setElement("value", v)
    session.sendRequest(req)
    out = {}
    while True:
        ev = session.nextEvent(500)
        for msg in ev:
            if msg.hasElement("securityData"):
                sd = msg.getElement("securityData")
                for i in range(sd.numValues()):
                    sec = sd.getValue(i)
                    if sec.hasElement("fieldData"):
                        fd = sec.getElement("fieldData")
                        for f in fields:
                            if fd.hasElement(f):
                                el = fd.getElement(f)
                                try: out[f] = el.getValue()
                                except: out[f] = str(el)
        if ev.eventType() == blpapi.Event.RESPONSE:
            break
    return out

def bdh(fields, start, end, period="DAILY"):
    req = svc.createRequest("HistoricalDataRequest")
    req.append("securities", SECURITY)
    for f in fields:
        req.append("fields", f)
    req.set("startDate", start)
    req.set("endDate", end)
    req.set("periodicitySelection", period)
    session.sendRequest(req)
    rows = []
    while True:
        ev = session.nextEvent(500)
        for msg in ev:
            if msg.hasElement("securityData"):
                sd = msg.getElement("securityData")
                if sd.hasElement("fieldData"):
                    fd = sd.getElement("fieldData")
                    for i in range(fd.numValues()):
                        pt = fd.getValue(i)
                        row = {}
                        for f in ["date"] + fields:
                            if pt.hasElement(f):
                                v = pt.getElement(f).getValue()
                                row[f] = str(v) if isinstance(v, datetime.date) else v
                        if row:
                            rows.append(row)
        if ev.eventType() == blpapi.Event.RESPONSE:
            break
    return rows

today = datetime.date.today()
d_end   = today.strftime("%Y%m%d")
d_start = (today - datetime.timedelta(days=400)).strftime("%Y%m%d")   # 400 days = ~280 trading days (200 EMA needs 200+)
w_start = (today - datetime.timedelta(days=365*8)).strftime("%Y%m%d")  # 8 years weekly = ~416 weekly bars (200w EMA needs 200+)
m_start = (today - datetime.timedelta(days=365*25)).strftime("%Y%m%d") # 25 years monthly

price_fields = ["PX_LAST", "PX_OPEN", "PX_HIGH", "PX_LOW", "VOLUME"]

def calc_ema(closes, period):
    if len(closes) < period:
        return None
    k = 2.0 / (period + 1)
    ema = sum(closes[:period]) / period
    for c in closes[period:]:
        ema = c * k + ema * (1 - k)
    return round(ema, 2)

def calc_rsi(closes, period=14):
    if len(closes) < period + 1:
        return None
    deltas = [closes[i+1] - closes[i] for i in range(len(closes)-1)]
    gains  = [max(d, 0) for d in deltas]
    losses = [abs(min(d, 0)) for d in deltas]
    avg_g  = sum(gains[:period]) / period
    avg_l  = sum(losses[:period]) / period
    for i in range(period, len(deltas)):
        avg_g = (avg_g * (period-1) + gains[i]) / period
        avg_l = (avg_l * (period-1) + losses[i]) / period
    if avg_l == 0:
        return 100.0
    rs = avg_g / avg_l
    return round(100 - (100 / (1 + rs)), 2)

def fan_status(e20, e50, e100, e200, price):
    if None in [e20, e50, e100]:
        return "INSUFFICIENT DATA"
    if e200 is None:
        # Work with available EMAs
        fan_intact = e20 > e50 > e100
        if not fan_intact:
            return "BROKEN (200 EMA unavailable)"
        if price > e20:
            return "FAN INTACT (20/50/100) — price above 20 EMA (extended)"
        elif price > e50:
            return "FAN INTACT (20/50/100) — price between 20 and 50 EMA"
        elif price >= e50 * 0.97:
            return "FAN INTACT (20/50/100) — price at 50 EMA (entry zone)"
        elif price > e100:
            return "FAN INTACT (20/50/100) — price between 50 and 100 EMA"
        elif price >= e100 * 0.97:
            return "FAN INTACT (20/50/100) — price at 100 EMA (entry zone)"
        else:
            return "FAN INTACT (20/50/100) — price below 100 EMA"
    if None in [e20, e50, e100, e200]:
        return "INSUFFICIENT DATA"
    fan_intact = e20 > e50 > e100 > e200
    if not fan_intact:
        # Check partial
        if e100 > e200:
            tier = "TIER 2 (100/200 intact)"
        elif e200:
            tier = "TIER 3 (200 only)"
        else:
            tier = "BROKEN"
        return tier
    # Fan intact — where is price?
    if price > e20:
        return "FAN INTACT — price above 20 EMA (extended)"
    elif price > e50:
        return "FAN INTACT — price between 20 and 50 EMA"
    elif price >= e50 * 0.97:
        return "FAN INTACT — price at 50 EMA (entry zone)"
    elif price > e100:
        return "FAN INTACT — price between 50 and 100 EMA"
    elif price >= e100 * 0.97:
        return "FAN INTACT — price at 100 EMA (entry zone)"
    elif price > e200:
        return "FAN INTACT — price between 100 and 200 EMA"
    elif price >= e200 * 0.97:
        return "FAN INTACT — price at 200 EMA (NUCLEAR entry zone)"
    else:
        return "FAN INTACT — price below 200 EMA (breakdown risk)"

results = {"ticker": TICKER, "as_of": d_end}

# DAILY
daily = bdh(["PX_LAST"], d_start, d_end, "DAILY")
if daily:
    closes_d = [r["PX_LAST"] for r in daily if "PX_LAST" in r]
    price = closes_d[-1]
    e20d  = calc_ema(closes_d, 20)
    e50d  = calc_ema(closes_d, 50)
    e100d = calc_ema(closes_d, 100)
    e200d = calc_ema(closes_d, 200)
    rsi_d = calc_rsi(closes_d, 14)
    results["daily"] = {
        "price": round(price, 2),
        "ema_20": e20d, "ema_50": e50d, "ema_100": e100d, "ema_200": e200d,
        "rsi_14": rsi_d,
        "structure": fan_status(e20d, e50d, e100d, e200d, price)
    }

# WEEKLY
weekly = bdh(["PX_LAST"], w_start, d_end, "WEEKLY")
if weekly:
    closes_w = [r["PX_LAST"] for r in weekly if "PX_LAST" in r]
    price_w = closes_w[-1]
    e20w  = calc_ema(closes_w, 20)
    e50w  = calc_ema(closes_w, 50)
    e100w = calc_ema(closes_w, 100)
    e200w = calc_ema(closes_w, 200)
    rsi_w = calc_rsi(closes_w, 14)
    results["weekly"] = {
        "price": round(price_w, 2),
        "ema_20": e20w, "ema_50": e50w, "ema_100": e100w, "ema_200": e200w,
        "rsi_14": rsi_w,
        "structure": fan_status(e20w, e50w, e100w, e200w, price_w)
    }

# MONTHLY
monthly = bdh(["PX_LAST"], m_start, d_end, "MONTHLY")
if monthly:
    closes_m = [r["PX_LAST"] for r in monthly if "PX_LAST" in r]
    price_m = closes_m[-1]
    e20m  = calc_ema(closes_m, 20)
    e50m  = calc_ema(closes_m, 50)
    e100m = calc_ema(closes_m, 100)
    rsi_m = calc_rsi(closes_m, 14)
    results["monthly"] = {
        "price": round(price_m, 2),
        "ema_20": e20m, "ema_50": e50m, "ema_100": e100m,
        "rsi_14": rsi_m,
        "structure": fan_status(e20m, e50m, e100m, None, price_m)
    }

session.stop()
print(json.dumps(results, default=str, indent=2))
