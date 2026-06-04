"""
Bloomberg full data pull — all 3 baskets in one session.
Usage: python bbg_all.py WMT
Optimized: single BDH pull, all BDP fields in one request, runs in <60s.
"""
import blpapi, json, sys, datetime

TICKER   = sys.argv[1] if len(sys.argv) > 1 else "WMT"
SECURITY = f"{TICKER} US Equity"

session = blpapi.Session()
if not session.start():
    print(json.dumps({"error": "Failed to start Bloomberg session"})); sys.exit(1)
if not session.openService("//blp/refdata"):
    print(json.dumps({"error": "Failed to open refdata service"})); sys.exit(1)

svc = session.getService("//blp/refdata")

def bdp(fields, timeout_ms=8000):
    req = svc.createRequest("ReferenceDataRequest")
    req.append("securities", SECURITY)
    for f in fields:
        req.append("fields", f)
    session.sendRequest(req)
    results = {}
    while True:
        ev = session.nextEvent(timeout_ms)
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
                                try:
                                    v = el.getValue()
                                    if v is not None:
                                        results[f] = v
                                except:
                                    results[f] = str(el)
        if ev.eventType() == blpapi.Event.RESPONSE:
            break
    return results

def bdh_closes(start_date, end_date):
    """Single BDH pull for PX_LAST — daily closes only."""
    req = svc.createRequest("HistoricalDataRequest")
    req.append("securities", SECURITY)
    req.append("fields", "PX_LAST")
    req.set("startDate", start_date)
    req.set("endDate", end_date)
    req.set("periodicitySelection", "DAILY")
    session.sendRequest(req)
    closes = []
    while True:
        ev = session.nextEvent(8000)
        for msg in ev:
            if msg.hasElement("securityData"):
                sd = msg.getElement("securityData")
                if sd.hasElement("fieldData"):
                    fd = sd.getElement("fieldData")
                    for i in range(fd.numValues()):
                        pt = fd.getValue(i)
                        if pt.hasElement("PX_LAST"):
                            closes.append(pt.getElement("PX_LAST").getValue())
        if ev.eventType() == blpapi.Event.RESPONSE:
            break
    return closes

def calc_ema(closes, period):
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 4)

today     = datetime.date.today()
today_str = today.strftime("%Y%m%d")
# 300 calendar days = ~210 trading days. Enough for 200 EMA with warmup.
start_str = (today - datetime.timedelta(days=300)).strftime("%Y%m%d")

output = {"ticker": TICKER, "security": SECURITY, "as_of": today_str}

# ── ONE BDH PULL: 300 days of closes ────────────────────────────────────────
closes = bdh_closes(start_str, today_str)

ema_20  = calc_ema(closes, 20)
ema_50  = calc_ema(closes, 50)
ema_100 = calc_ema(closes, 100)
ema_200 = calc_ema(closes, 200)

if all(v is not None for v in [ema_20, ema_50, ema_100, ema_200]):
    if   ema_20 > ema_50 > ema_100 > ema_200: fan = "INTACT (20>50>100>200)"
    elif ema_50 > ema_100 > ema_200:           fan = "TIER2 (50>100>200, 20 broken)"
    elif ema_100 > ema_200:                    fan = "TIER3 (100>200 only)"
    else:                                       fan = "BROKEN"
elif all(v is not None for v in [ema_20, ema_50, ema_100]):
    fan = "INTACT (20>50>100)" if ema_20 > ema_50 > ema_100 else "BROKEN"
else:
    fan = f"INSUFFICIENT DATA ({len(closes)} bars)"

# ── ONE BDP PULL: ALL fields in a single request ─────────────────────────────
all_fields = [
    # Price / volume
    "PX_LAST", "PX_OPEN", "PX_HIGH", "PX_LOW",
    "VOLUME", "VOLUME_AVG_20D",
    "RSI_14D", "CHG_PCT_1D", "CHG_PCT_5D",
    # Analyst
    "TOT_ANALYST_REC", "BEST_ANALYST_RATING",
    "TOT_BUY_REC", "TOT_HOLD_REC", "TOT_SELL_REC",
    "BEST_TARGET_PRICE",
    "BEST_TARGET_PRICE_HIGH", "BEST_TARGET_PRICE_LOW", "BEST_TARGET_PRICE_MEDIAN",
    # Fundamentals
    "BEST_PE_RATIO", "BEST_EPS", "BEST_SALES",
    "EV_TO_T12M_EBITDA", "CURRENT_TRR_1YR",
    "RETURN_COM_EQY", "GROSS_MARGIN", "PROF_MARGIN",
    "EQY_DVD_YLD_12M", "IS_EPS",
    # Ownership / short
    "SHORT_INT_RATIO",
    # Earnings
    "NEXT_EARNINGS_DATE", "SALES_REV_TURN", "EPS_SURP_5YR_AVG",
    # Options IV
    "IVOL_30D", "IVOL_60D", "IVOL_90D",
    "CALL_IMPL_VOL_30D", "PUT_IMPL_VOL_30D",
    "HIST_CALL_PUT_RATIO_3M", "HIST_IMPL_VOL_30D",
]
d = bdp(all_fields)

px = d.get("PX_LAST")

# ── BASKET 1: GP / ANR / ATPR ───────────────────────────────────────────────
gp = {k: d.get(k) for k in ["PX_LAST","PX_OPEN","PX_HIGH","PX_LOW","VOLUME","VOLUME_AVG_20D","RSI_14D","CHG_PCT_1D","CHG_PCT_5D"]}
gp.update({"EMA_20D": ema_20, "EMA_50D": ema_50, "EMA_100D": ema_100, "EMA_200D": ema_200, "EMA_FAN": fan, "BARS_LOADED": len(closes)})
if px and ema_50:  gp["VS_50EMA"]  = round((px/ema_50 - 1)*100, 2)
if px and ema_100: gp["VS_100EMA"] = round((px/ema_100 - 1)*100, 2)
if px and ema_200: gp["VS_200EMA"] = round((px/ema_200 - 1)*100, 2)
output["GP"] = gp

anr = {k: d.get(k) for k in ["TOT_ANALYST_REC","BEST_ANALYST_RATING","TOT_BUY_REC","TOT_HOLD_REC","TOT_SELL_REC","BEST_TARGET_PRICE"]}
if anr.get("BEST_TARGET_PRICE") and px:
    anr["UPSIDE_PCT"] = round((anr["BEST_TARGET_PRICE"]/px - 1)*100, 2)
output["ANR"] = anr

output["ATPR"] = {k: d.get(k) for k in ["BEST_TARGET_PRICE","BEST_TARGET_PRICE_HIGH","BEST_TARGET_PRICE_LOW","BEST_TARGET_PRICE_MEDIAN"]}

# ── BASKET 2: GF / OWN ──────────────────────────────────────────────────────
output["GF"]  = {k: d.get(k) for k in ["BEST_PE_RATIO","BEST_EPS","BEST_SALES","EV_TO_T12M_EBITDA","CURRENT_TRR_1YR","RETURN_COM_EQY","GROSS_MARGIN","PROF_MARGIN","EQY_DVD_YLD_12M","IS_EPS"]}
output["OWN"] = {k: d.get(k) for k in ["PX_LAST","SHORT_INT_RATIO","RETURN_COM_EQY"]}
output["NLRT"]= {"note": "Terminal-side only — configure via NLRT GO"}

# ── BASKET 3: ERN / OMON ────────────────────────────────────────────────────
output["ERN"]  = {k: d.get(k) for k in ["BEST_EPS","IS_EPS","NEXT_EARNINGS_DATE","SALES_REV_TURN","BEST_SALES","EPS_SURP_5YR_AVG"]}
output["OMON"] = {k: d.get(k) for k in ["IVOL_30D","IVOL_60D","IVOL_90D","CALL_IMPL_VOL_30D","PUT_IMPL_VOL_30D","HIST_CALL_PUT_RATIO_3M","HIST_IMPL_VOL_30D"]}

session.stop()
print(json.dumps(output, default=str, indent=2))
