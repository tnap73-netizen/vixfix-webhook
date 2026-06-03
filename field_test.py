import blpapi, json, sys

SECURITY = "WMT US Equity"

session = blpapi.Session()
session.start()
session.openService("//blp/refdata")
svc = session.getService("//blp/refdata")

# Test all the fields that returned null
test_fields = [
    # EMA alternatives
    "EMA20", "EMA50", "EMA100", "EMA200",
    "MOVING_AVG_20D", "MOVING_AVG_50D", "MOVING_AVG_100D", "MOVING_AVG_200D",
    # Price change
    "CHG_PCT_1D", "CHG_PCT_5D", "DAY_TO_DAY_TOT_RETURN_GROSS_DVDS",
    # Analyst
    "ANALYST_RATINGS_BUY", "ANALYST_RATINGS_HOLD", "ANALYST_RATINGS_SELL",
    "TOT_BUY_REC", "TOT_HOLD_REC", "TOT_SELL_REC",
    "BEST_ANALYST_RATING_BUY", "BEST_ANALYST_RATING_HOLD", "BEST_ANALYST_RATING_SELL",
    # Targets
    "BEST_PRICE_TGT", "BEST_PRICE_TGT_HIGH", "BEST_PRICE_TGT_LOW",
    "BEST_1YR_TARGET_PRICE",
    # Fundamentals
    "BEST_EPS", "BEST_SALES", "IS_EPS",
    "EQY_DVD_YLD_12M", "RETURN_COM_EQY", "PROF_MARGIN",
    # Ownership
    "IS_FUND_OWN_PCT", "EQY_INST_OWN_PCT",
    "SHORT_INT_PCT", "SI_PCT_FLOAT",
    # Earnings
    "NEXT_EARNINGS_DATE", "EARN_ANN_DT",
    "EPS_SURP_5YR_AVG", "BEST_EPS_SURP",
    # Options
    "HIST_CALL_PUT_RATIO_3M", "HIST_IMPL_VOL_30D",
    "IVOL_30D", "IVOL_60D", "IVOL_90D",
    "CALL_IMPL_VOL_30D", "PUT_IMPL_VOL_30D",
]

req = svc.createRequest("ReferenceDataRequest")
req.append("securities", SECURITY)
for f in test_fields:
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
                    for f in test_fields:
                        if fd.hasElement(f):
                            el = fd.getElement(f)
                            try:
                                v = el.getValue()
                                if v is not None:
                                    results[f] = v
                            except:
                                pass
    if ev.eventType() == blpapi.Event.RESPONSE:
        break

session.stop()
# Only print fields that actually returned data
print(json.dumps({k: v for k, v in results.items()}, default=str, indent=2))
