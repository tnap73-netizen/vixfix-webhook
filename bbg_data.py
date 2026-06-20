"""
Bloomberg data pull via blpapi.
Usage: python bbg_data.py WMT 1
Basket 1: GP (price/volume/EMAs calculated via BDH), ANR (analyst recs), ATPR (price targets)
Basket 2: GF (fundamentals), OWN (ownership), NLRT (news alerts)
Basket 3: OMON (options monitor), ERN (earnings)
Returns clean JSON to stdout.
"""
import blpapi, json, sys, datetime

TICKER = sys.argv[1] if len(sys.argv) > 1 else "WMT"
BASKET = int(sys.argv[2]) if len(sys.argv) > 2 else 1
SECURITY = f"{TICKER} US Equity"

session = blpapi.Session()
if not session.start():
    print(json.dumps({"error": "Failed to start Bloomberg session"}))
    sys.exit(1)
if not session.openService("//blp/refdata"):
    print(json.dumps({"error": "Failed to open refdata service"}))
    sys.exit(1)

svc = session.getService("//blp/refdata")

def bdp(fields):
    """Single reference data request — returns only fields with values."""
    req = svc.createRequest("ReferenceDataRequest")
    req.append("securities", SECURITY)
    for f in fields:
        req.append("fields", f)
    session.sendRequest(req)
    results = {}
    while True:
        ev = session.nextEvent(2000)
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

def bdh(fields, start_date, end_date, periodicity="DAILY"):
    """Historical data request."""
    req = svc.createRequest("HistoricalDataRequest")
    req.append("securities", SECURITY)
    for f in fields:
        req.append("fields", f)
    req.set("startDate", start_date)
    req.set("endDate", end_date)
    req.set("periodicitySelection", periodicity)
    session.sendRequest(req)
    rows = []
    while True:
        ev = session.nextEvent(2000)
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
                        rows.append(row)
        if ev.eventType() == blpapi.Event.RESPONSE:
            break
    return rows

def calc_ema(closes, period):
    """Calculate EMA from list of closes."""
    if len(closes) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(closes[:period]) / period
    for price in closes[period:]:
        ema = price * k + ema * (1 - k)
    return round(ema, 4)

today = datetime.date.today()
today_str = today.strftime("%Y%m%d")
# Extended lookback: 400 calendar days = ~280 trading days (enough for 200 EMA)
start_400 = (today - datetime.timedelta(days=400)).strftime("%Y%m%d")

output = {"ticker": TICKER, "basket": BASKET, "security": SECURITY, "as_of": today_str}

if BASKET == 1:
    # GP — price and volume via BDP (real-time fields)
    gp_realtime = bdp([
        "PX_LAST", "PX_OPEN", "PX_HIGH", "PX_LOW",
        "VOLUME", "VOLUME_AVG_20D",
        "RSI_14D", "CHG_PCT_1D", "CHG_PCT_5D"
    ])

    # EMAs — calculated from 400-day BDH history (BDP EMA fields unreliable)
    hist = bdh(["PX_LAST"], start_400, today_str, "DAILY")
    closes = [row["PX_LAST"] for row in hist if "PX_LAST" in row]

    ema_20  = calc_ema(closes, 20)
    ema_50  = calc_ema(closes, 50)
    ema_100 = calc_ema(closes, 100)
    ema_200 = calc_ema(closes, 200)

    px = gp_realtime.get("PX_LAST")

    # Fan status
    fan = "UNKNOWN"
    if all(v is not None for v in [ema_20, ema_50, ema_100, ema_200]):
        if ema_20 > ema_50 > ema_100 > ema_200:
            fan = "INTACT (20>50>100>200)"
        elif ema_50 > ema_100 > ema_200:
            fan = "TIER2 (50>100>200 intact, 20 broken)"
        elif ema_100 > ema_200:
            fan = "TIER3 (100>200 only)"
        else:
            fan = "BROKEN"
    elif all(v is not None for v in [ema_20, ema_50, ema_100]):
        if ema_20 > ema_50 > ema_100:
            fan = "INTACT (20>50>100, 200 EMA needs more history)"
        else:
            fan = "BROKEN"

    gp_realtime["EMA_20D"]     = ema_20
    gp_realtime["EMA_50D"]     = ema_50
    gp_realtime["EMA_100D"]    = ema_100
    gp_realtime["EMA_200D"]    = ema_200
    gp_realtime["EMA_FAN"]     = fan
    gp_realtime["BARS_LOADED"] = len(closes)

    # Price vs EMA summary
    if px and ema_50 and ema_100 and ema_200:
        gp_realtime["VS_50EMA"]  = round((px / ema_50 - 1) * 100, 2)
        gp_realtime["VS_100EMA"] = round((px / ema_100 - 1) * 100, 2)
        gp_realtime["VS_200EMA"] = round((px / ema_200 - 1) * 100, 2)

    output["GP"] = gp_realtime

    # ANR — analyst recommendations (corrected field names)
    anr = bdp([
        "TOT_ANALYST_REC", "BEST_ANALYST_RATING",
        "TOT_BUY_REC", "TOT_HOLD_REC", "TOT_SELL_REC",
        "BEST_TARGET_PRICE"
    ])
    # Upside % calculated from price and target
    if anr.get("BEST_TARGET_PRICE") and gp_realtime.get("PX_LAST"):
        anr["UPSIDE_PCT"] = round((anr["BEST_TARGET_PRICE"] / gp_realtime["PX_LAST"] - 1) * 100, 2)
    output["ANR"] = anr

    # ATPR — price target distribution
    atpr = bdp([
        "BEST_TARGET_PRICE",
        "BEST_TARGET_PRICE_HIGH",
        "BEST_TARGET_PRICE_LOW",
        "BEST_TARGET_PRICE_MEDIAN"
    ])
    output["ATPR"] = atpr

elif BASKET == 2:
    # GF — fundamentals (corrected field names)
    gf = bdp([
        "BEST_PE_RATIO", "BEST_EPS", "BEST_SALES",
        "EV_TO_T12M_EBITDA", "CURRENT_TRR_1YR",
        "RETURN_COM_EQY", "GROSS_MARGIN", "PROF_MARGIN",
        "EQY_DVD_YLD_12M", "IS_EPS",
        "CF_RETURN", "EARN_RETURN", "PE_RETURN", "DIV_RETURN"
    ])
    # Compute PE expansion % of total return
    try:
        pe_ret  = float(gf.get("PE_RETURN")  or 0)
        ern_ret = float(gf.get("EARN_RETURN") or 0)
        div_ret = float(gf.get("DIV_RETURN")  or 0)
        total   = pe_ret + ern_ret + div_ret
        gf["PE_PCT_OF_TOTAL_RETURN"] = round((pe_ret / total * 100), 1) if total != 0 else None
        gf["GF_GATE"] = "HARD FAIL" if (gf["PE_PCT_OF_TOTAL_RETURN"] or 0) > 60 else "PASS"
    except Exception:
        gf["PE_PCT_OF_TOTAL_RETURN"] = None
        gf["GF_GATE"] = "UNKNOWN"
    output["GF"] = gf

    # OWN — ownership and short interest (corrected field names)
    own = bdp([
        "PX_LAST",
        "SHORT_INT_RATIO",
        "RETURN_COM_EQY"
    ])
    output["OWN"] = own

    # NLRT — terminal-side only
    output["NLRT"] = {"note": "NLRT is a terminal alert setup — configure via NLRT GO on Bloomberg"}

elif BASKET == 3:
    # ERN — earnings (corrected field names)
    ern = bdp([
        "BEST_EPS", "IS_EPS",
        "NEXT_EARNINGS_DATE",
        "SALES_REV_TURN", "BEST_SALES",
        "EPS_SURP_5YR_AVG"
    ])
    output["ERN"] = ern

    # OMON — options implied vol (corrected field names)
    omon = bdp([
        "IVOL_30D", "IVOL_60D", "IVOL_90D",
        "CALL_IMPL_VOL_30D", "PUT_IMPL_VOL_30D",
        "HIST_CALL_PUT_RATIO_3M",
        "HIST_IMPL_VOL_30D"
    ])
    output["OMON"] = omon

session.stop()
print(json.dumps(output, default=str, indent=2))
