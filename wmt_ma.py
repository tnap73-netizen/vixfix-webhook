import blpapi, json
SECURITY = "WMT US Equity"
s = blpapi.Session()
s.start()
s.openService("//blp/refdata")
svc = s.getService("//blp/refdata")
fields = [
    "MOV_AVG_20D","MOV_AVG_50D","MOV_AVG_100D","MOV_AVG_200D",
    "NUM_BUY_REC","NUM_HOLD_REC","NUM_SELL_REC",
    "BEST_TARGET_PRICE_HIGH","BEST_TARGET_PRICE_LOW","BEST_TARGET_PRICE_MEDIAN",
    "EARN_ANNOUNCE_DT","BEST_EPS_NTM","BEST_EPS_SURP_PCT",
    "BEST_ANALYST_RATING","TOT_ANALYST_REC"
]
req = svc.createRequest("ReferenceDataRequest")
req.append("securities", SECURITY)
for f in fields:
    req.append("fields", f)
s.sendRequest(req)
out = {}
while True:
    ev = s.nextEvent(500)
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
                                out[f] = el.getValue()
                            except:
                                out[f] = str(el)
    if ev.eventType() == blpapi.Event.RESPONSE:
        break
s.stop()
print(json.dumps(out, default=str))
