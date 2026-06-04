import blpapi, json, sys

SECURITY = "HTZ US Equity"
session = blpapi.Session()
session.start()
session.openService("//blp/refdata")
svc = session.getService("//blp/refdata")

# S3 Partners fields on Bloomberg
s3_fields = [
    "S3_SI_PCT", "S3_SHORT_INTEREST", "S3_DTC", "S3_SQZ_SCORE", "S3_SQZ_RANK",
    "S3_SI_CHG_1D_PCT", "S3_SI_CHG_5D_PCT", "S3_SI_CHG_30D_PCT",
    "S3_BORROW_RATE", "S3_BORROW_FEE", "S3_AVAILABILITY",
    "SHORT_INT_PCT_FLOAT", "SHORT_INT_RATIO", "SHORT_INT",
    "EQY_SHORT_INT_PCT_FLOAT", "SHORT_INTEREST_PCT",
]

req = svc.createRequest("ReferenceDataRequest")
req.append("securities", SECURITY)
for f in s3_fields:
    req.append("fields", f)
session.sendRequest(req)

results = {}
while True:
    ev = session.nextEvent(5000)
    for msg in ev:
        if msg.hasElement("securityData"):
            sd = msg.getElement("securityData")
            for i in range(sd.numValues()):
                sec = sd.getValue(i)
                if sec.hasElement("fieldData"):
                    fd = sec.getElement("fieldData")
                    for f in s3_fields:
                        if fd.hasElement(f):
                            try:
                                v = fd.getElement(f).getValue()
                                if v is not None:
                                    results[f] = v
                            except:
                                pass
    if ev.eventType() == blpapi.Event.RESPONSE:
        break

session.stop()
print(json.dumps(results, default=str, indent=2))
