"""
Bloomberg data pull via blpapi.
Usage: python bbg_data.py WMT 1
Basket 1: GP (price/volume), ANR (analyst recs), ATPR (price targets)
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
    """Single reference data request."""
    req = svc.createRequest("ReferenceDataRequest")
    req.append("securities", SECURITY)
    for f in fields:
        req.append("fields", f)
    session.sendRequest(req)
    results = {}
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
                                try:
                                    results[f] = el.getValue()
                                except:
                                    results[f] = str(el)
        if ev.eventType() == blpapi.Event.RESPONSE:
            break
    return results

def bdh(fields, start_date, end_date):
    """Historical data request."""
    req = svc.createRequest("HistoricalDataRequest")
    req.append("securities", SECURITY)
    for f in fields:
        req.append("fields", f)
    req.set("startDate", start_date)
    req.set("endDate", end_date)
    req.set("periodicitySelection", "DAILY")
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
                        rows.append(row)
        if ev.eventType() == blpapi.Event.RESPONSE:
            break
    return rows

today = datetime.date.today().strftime("%Y%m%d")
thirty_ago = (datetime.date.today() - datetime.timedelta(days=30)).strftime("%Y%m%d")

output = {"ticker": TICKER, "basket": BASKET, "security": SECURITY}

if BASKET == 1:
    # GP — price, volume, EMAs
    gp = bdp([
        "PX_LAST", "PX_OPEN", "PX_HIGH", "PX_LOW",
        "VOLUME", "VOLUME_AVG_20D",
        "EMA_20D", "EMA_50D", "EMA_100D", "EMA_200D",
        "RSI_14D", "PCT_CHG_1D", "PCT_CHG_5D"
    ])
    output["GP"] = gp

    # ANR — analyst recommendations
    anr = bdp([
        "TOT_ANALYST_REC", "BEST_ANALYST_RATING",
        "NUM_BUY_REC", "NUM_HOLD_REC", "NUM_SELL_REC",
        "BEST_TARGET_PRICE", "BEST_TARGET_UP_DOWN_PCT"
    ])
    output["ANR"] = anr

    # ATPR — price targets
    atpr = bdp([
        "BEST_TARGET_PRICE", "BEST_TARGET_PRICE_HIGH",
        "BEST_TARGET_PRICE_LOW", "BEST_TARGET_PRICE_MEDIAN",
        "BEST_TARGET_UP_DOWN_PCT"
    ])
    output["ATPR"] = atpr

elif BASKET == 2:
    # GF — fundamentals
    gf = bdp([
        "BEST_PE_RATIO", "BEST_EPS_NTM", "BEST_SALES_NTM",
        "EV_TO_T12M_EBITDA", "CURRENT_TRR_1YR",
        "RETURN_ON_EQUITY", "GROSS_MARGIN", "NET_INCOME_MARGIN"
    ])
    output["GF"] = gf

    # OWN — ownership
    own = bdp([
        "PX_LAST",
        "IS_FUND_OWNERSHIP_PCT", "EQY_INST_HOLDING_PCT",
        "SHORT_INT_RATIO", "SHORT_INT_PCT_FLOAT"
    ])
    output["OWN"] = own

    # NLRT placeholder — news alerts are terminal-side
    output["NLRT"] = {"note": "NLRT is a terminal alert setup — not a data pull"}

elif BASKET == 3:
    # ERN — earnings
    ern = bdp([
        "BEST_EPS_NTM", "EARN_ANNOUNCE_DT",
        "SALES_REV_TURN", "BEST_SALES_NTM",
        "EPS_SURP_PCT_5YR_AVG", "BEST_EPS_SURPRISE_PCT"
    ])
    output["ERN"] = ern

    # OMON — options
    omon = bdp([
        "IVOL_MID_ATM_3MO", "SKEW_3MO",
        "CALL_PUT_RATIO", "OPT_IMPL_VOLAT_CALL_3MO",
        "OPT_IMPL_VOLAT_PUT_3MO"
    ])
    output["OMON"] = omon

session.stop()
print(json.dumps(output, default=str, indent=2))
