import blpapi
import json
import sys

def get_anr(ticker):
    sessionOptions = blpapi.SessionOptions()
    sessionOptions.setServerHost("localhost")
    sessionOptions.setServerPort(8194)
    session = blpapi.Session(sessionOptions)
    if not session.start():
        print(json.dumps({"error": "Failed to start session"}))
        return
    if not session.openService("//blp/refdata"):
        print(json.dumps({"error": "Failed to open refdata"}))
        return
    refDataService = session.getService("//blp/refdata")
    request = refDataService.createRequest("ReferenceDataRequest")
    request.append("securities", ticker)
    fields = [
        "BEST_ANALYST_RATING",
        "BEST_TARGET_PRICE",
        "TOT_ANALYST_REC",
        "BEST_EPS_MEDIAN",
        "BEST_EPS_NXT_YR",
        "BEST_SALES_NXT_YR",
        "BEST_SALES_MEDIAN",
        "BEST_EPS_YR1",
        "BEST_EPS_YR2",
        "BEST_NET_INC_NXT_YR",
        "BEST_ROE_NXT_YR",
        "BEST_DPS_NXT_YR",
    ]
    for f in fields:
        request.append("fields", f)
    session.sendRequest(request)
    results = {}
    while True:
        ev = session.nextEvent(500)
        for msg in ev:
            if msg.hasElement("securityData"):
                secData = msg.getElement("securityData")
                for i in range(secData.numValues()):
                    sec = secData.getValue(i)
                    fieldData = sec.getElement("fieldData")
                    for f in fields:
                        try:
                            results[f] = str(fieldData.getElementAsString(f))
                        except:
                            results[f] = "N/A"
        if ev.eventType() == blpapi.Event.RESPONSE:
            break
    print(json.dumps(results, indent=2))
    session.stop()

# Accept ticker as command line argument
# Usage: python anr_universal.py AROC
# or:    python anr_universal.py "AROC US Equity"
ticker = sys.argv[1] if len(sys.argv) > 1 else "HASI US Equity"
if " " not in ticker:
    ticker = ticker + " US Equity"
get_anr(ticker)
