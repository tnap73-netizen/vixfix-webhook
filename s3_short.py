"""
S3 Partners short data via Bloomberg blpapi.
Usage: python s3_short.py HTZ
Tries multiple S3 field name conventions until one returns data.
"""
import blpapi, json, sys

TICKER   = sys.argv[1] if len(sys.argv) > 1 else "HTZ"
SECURITY = f"{TICKER} US Equity"

session = blpapi.Session()
session.start()
session.openService("//blp/refdata")
svc = session.getService("//blp/refdata")

def test_fields(fields):
    req = svc.createRequest("ReferenceDataRequest")
    req.append("securities", SECURITY)
    for f in fields:
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
                    # Check for field errors
                    if sec.hasElement("fieldExceptions"):
                        fe = sec.getElement("fieldExceptions")
                        for j in range(fe.numValues()):
                            err = fe.getValue(j)
                            fid = err.getElement("fieldId").getValue()
                            results[f"ERR_{fid}"] = "invalid"
                    if sec.hasElement("fieldData"):
                        fd = sec.getElement("fieldData")
                        for f in fields:
                            if fd.hasElement(f):
                                try:
                                    v = fd.getElement(f).getValue()
                                    if v is not None:
                                        results[f] = v
                                except:
                                    results[f] = str(fd.getElement(f))
        if ev.eventType() == blpapi.Event.RESPONSE:
            break
    return results

# Batch 1: S3 Partners specific fields
batch1 = [
    "SI_S3_SHORT_INTEREST_PCT",
    "SI_S3_SHORT_INTEREST_SHARES",
    "SI_S3_BORROW_RATE_AVG",
    "SI_S3_DAYS_TO_COVER",
    "SI_S3_CROWDING_SCORE",
    "SI_S3_SHORT_SQUEEZE_SCORE",
    "S3_PCT_FLOAT",
    "S3_SHARES_SHORTED",
    "S3_COST_TO_BORROW",
    "S3_DAYS_TO_COVER",
    "S3_CROWDING",
]

# Batch 2: Alternative naming
batch2 = [
    "SHORT_INT_PCT_FLOAT",
    "SHORT_INT",
    "SHORT_INT_RATIO",
    "EQY_SHORT_INT_PCT_FLOAT",
    "EQY_SI_PCT_FLOAT",
    "BORROWED_SHARES_S3",
    "SHORT_INT_FLOAT_PCT_S3",
    "CTB_RATE",
    "COST_TO_BORROW_CURRENT",
    "BORROW_COST_INDICATIVE",
]

r1 = test_fields(batch1)
r2 = test_fields(batch2)

combined = {**r1, **r2}
# Filter out errors and None
clean = {k: v for k, v in combined.items() if not k.startswith("ERR_") and v is not None}

session.stop()
print(json.dumps({"ticker": TICKER, "fields_with_data": clean, "all_results": combined}, default=str, indent=2))
