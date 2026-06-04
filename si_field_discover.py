"""
Short interest field discovery for HTZ.
Tests fields that are confirmed accessible via standard blpapi terminal entitlement.
These are fields that appear in Bloomberg's FLDS database for standard equity subscriptions.
"""
import blpapi, json, sys, datetime

TICKER = sys.argv[1] if len(sys.argv) > 1 else "HTZ"
SECURITY = f"{TICKER} US Equity"

session = blpapi.Session()
session.start()
session.openService("//blp/refdata")
svc = session.getService("//blp/refdata")

def bdp(fields):
    req = svc.createRequest("ReferenceDataRequest")
    req.append("securities", SECURITY)
    for f in fields:
        req.append("fields", f)
    session.sendRequest(req)
    results = {}
    errors = []
    while True:
        ev = session.nextEvent(8000)
        for msg in ev:
            if msg.hasElement("securityData"):
                sd = msg.getElement("securityData")
                for i in range(sd.numValues()):
                    sec = sd.getValue(i)
                    if sec.hasElement("fieldExceptions"):
                        fe = sec.getElement("fieldExceptions")
                        for j in range(fe.numValues()):
                            err = fe.getValue(j)
                            fid = err.getElement("fieldId").getValue()
                            errors.append(fid)
                    if sec.hasElement("fieldData"):
                        fd = sec.getElement("fieldData")
                        for f in fields:
                            if fd.hasElement(f):
                                try:
                                    v = fd.getElement(f).getValue()
                                    results[f] = str(v) if v is not None else None
                                except Exception as e:
                                    results[f] = f"PARSE_ERR:{e}"
        if ev.eventType() == blpapi.Event.RESPONSE:
            break
    return results, errors

# Standard Bloomberg short interest fields (these work on terminal entitlement)
standard_si = [
    "SHORT_INT",                    # shares short (bi-weekly settlement)
    "SHORT_INT_RATIO",             # DTC
    "EQY_SHORT_INT_PCT_FLOAT",     # % float short
    "EQY_FREE_FLOAT_PCT",          # free float %
    "DAYS_TO_COVER",               # days to cover
    "SHORT_PERCENT_OF_FLOAT",      # alt name
    "SHORT_INT_PCT_FLOAT",         # alt name
]

# S3/SPG fields that may be accessible
s3_fields = [
    "SI_S3_SHORT_INTEREST_SHARES",
    "SI_S3_SHORT_INTEREST_PCT",
    "SI_S3_BORROW_RATE_AVG",
    "SI_S3_CROWDING_SCORE",
    "SI_S3_SHORT_SQUEEZE_SCORE",
    "SI_S3_DAYS_TO_COVER",
    "S3_PCT_FLOAT_SHORT",
    "S3_SHORT_INTEREST",
    "S3_SHORT_SQUEEZE",
    "S3_CROWDING",
    "SPG_SHORT_INT",
    "SPG_SHORT_INT_PCT_FLOAT",
    "SPG_DAYS_TO_COVER",
    "SPG_UTILIZATION",
    "SPG_COST_TO_BORROW",
    "SPG_SHORT_SQUEEZE_SCORE",
    "SI_PCT_FLOAT",
    "SI_SHORT_SQUEEZE_SCORE",
    "SI_CROWDING_SCORE",
]

# Ortex-style fields sometimes mapped in Bloomberg
ortex_style = [
    "SHORT_INT_SETTLEMENT",
    "EQY_SHORT_INT",
    "SHRT_INT_PCT",
    "SEC_SHORT_SELL_COST",
    "SHORT_SELL_COST_INDICATIVE",
    "BORROW_RATE",
    "BORROW_COST",
    "EQY_BORROW_COST",
    "COST_TO_BORROW",
    "CTB_RATE_TODAY",
    "EQY_FLOAT_SHS",
]

print(f"Testing short interest fields for {SECURITY}")
print("=" * 60)

r1, e1 = bdp(standard_si)
print(f"\nSTANDARD SI FIELDS — {len(r1)} returned, {len(e1)} invalid:")
for k, v in r1.items():
    print(f"  {k}: {v}")
print(f"  Invalid: {e1}")

r2, e2 = bdp(s3_fields)
print(f"\nS3/SPG FIELDS — {len(r2)} returned, {len(e2)} invalid:")
for k, v in r2.items():
    print(f"  {k}: {v}")
print(f"  Invalid: {e2}")

r3, e3 = bdp(ortex_style)
print(f"\nALT SI FIELDS — {len(r3)} returned, {len(e3)} invalid:")
for k, v in r3.items():
    print(f"  {k}: {v}")
print(f"  Invalid: {e3}")

session.stop()

all_working = {**r1, **r2, **r3}
print(f"\n{'='*60}")
print(f"TOTAL WORKING FIELDS: {len(all_working)}")
print(json.dumps({"ticker": TICKER, "working": all_working, "all_invalid": e1+e2+e3}, indent=2))
