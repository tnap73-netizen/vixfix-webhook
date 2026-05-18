"""
Bloomberg Local Data Server
Runs on Windows machine with Bloomberg Terminal active.
Exposes endpoints via Cloudflare Tunnel for remote access.
"""

from flask import Flask, jsonify, request
import subprocess
import json
import os
import datetime

app = Flask(__name__)

# Simple API key for security
API_KEY = "BGMS2024secure"

def check_api_key():
    key = request.headers.get('X-API-Key')
    if key != API_KEY:
        return False
    return True

def element_to_python(element):
    """Recursively convert a blpapi Element to a Python object."""
    import blpapi
    if element.isArray():
        result = []
        for i in range(element.numValues()):
            val = element.getValue(i)
            if hasattr(val, 'numElements'):
                result.append(element_to_python(val))
            else:
                result.append(str(val))
        return result
    elif element.numElements() > 0:
        result = {}
        for i in range(element.numElements()):
            child = element.getElement(i)
            result[str(child.name())] = element_to_python(child)
        return result
    else:
        try:
            return str(element.getValue())
        except:
            return "N/A"

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "online",
        "machine": os.environ.get('COMPUTERNAME', 'unknown'),
        "time": datetime.datetime.now().isoformat()
    })

@app.route('/bloomberg/run', methods=['POST'])
def run_bloomberg():
    """
    Run a Bloomberg reference data request via blpapi.
    Handles both scalar and bulk array fields (SPLC, etc.)
    Expects JSON: {"ticker": "MRVL US Equity", "fields": ["PX_LAST", "SPLC_PRIM_SUPPLIER_NAMES"]}
    """
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    ticker = data.get('ticker', '')
    fields = data.get('fields', [])

    try:
        import blpapi
        sessionOptions = blpapi.SessionOptions()
        sessionOptions.setServerHost("localhost")
        sessionOptions.setServerPort(8194)
        session = blpapi.Session(sessionOptions)

        if not session.start():
            return jsonify({"error": "Bloomberg Terminal not running or not connected"}), 503

        if not session.openService("//blp/refdata"):
            return jsonify({"error": "Failed to open Bloomberg reference data service"}), 503

        refDataService = session.getService("//blp/refdata")
        request_obj = refDataService.createRequest("ReferenceDataRequest")
        request_obj.append("securities", ticker)
        for field in fields:
            request_obj.append("fields", field)

        session.sendRequest(request_obj)

        results = {}
        while True:
            event = session.nextEvent(500)
            for msg in event:
                if msg.hasElement("securityData"):
                    secData = msg.getElement("securityData")
                    for i in range(secData.numValues()):
                        sec = secData.getValue(i)
                        fieldData = sec.getElement("fieldData")
                        for field in fields:
                            try:
                                el = fieldData.getElement(field)
                                results[field] = element_to_python(el)
                            except:
                                results[field] = "N/A"
            if event.eventType() == blpapi.Event.RESPONSE:
                break

        session.stop()
        return jsonify({"ticker": ticker, "data": results, "timestamp": datetime.datetime.now().isoformat()})

    except ImportError:
        return jsonify({"error": "blpapi not installed - run: pip install blpapi"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/bloomberg/splc', methods=['POST'])
def get_supply_chain():
    """
    Pull full SPLC supply chain data for a ticker.
    Expects JSON: {"ticker": "MRVL US Equity"}
    Returns suppliers, customers, revenue exposure percentages.
    """
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    ticker = data.get('ticker', '')

    fields = [
        "SPLC_PRIM_SUPPLIER_NAMES",
        "SPLC_PRIM_CUSTOMER_NAMES",
        "SPLC_PRIM_SUPPLIER_TICKER",
        "SPLC_PRIM_CUSTOMER_TICKER",
        "SPLC_PRIM_SUPPLIER_COUNTRY",
        "SPLC_PRIM_CUSTOMER_COUNTRY",
        "SPLC_PRIM_SUPPLIER_REL_RISK",
        "SPLC_PRIM_CUSTOMER_REL_RISK",
    ]

    try:
        import blpapi
        sessionOptions = blpapi.SessionOptions()
        sessionOptions.setServerHost("localhost")
        sessionOptions.setServerPort(8194)
        session = blpapi.Session(sessionOptions)

        if not session.start():
            return jsonify({"error": "Bloomberg Terminal not running"}), 503

        if not session.openService("//blp/refdata"):
            return jsonify({"error": "Failed to open refdata service"}), 503

        refDataService = session.getService("//blp/refdata")
        request_obj = refDataService.createRequest("ReferenceDataRequest")
        request_obj.append("securities", ticker)
        for field in fields:
            request_obj.append("fields", field)

        session.sendRequest(request_obj)

        results = {}
        while True:
            event = session.nextEvent(500)
            for msg in event:
                if msg.hasElement("securityData"):
                    secData = msg.getElement("securityData")
                    for i in range(secData.numValues()):
                        sec = secData.getValue(i)
                        fieldData = sec.getElement("fieldData")
                        for field in fields:
                            try:
                                el = fieldData.getElement(field)
                                results[field] = element_to_python(el)
                            except:
                                results[field] = "N/A"
            if event.eventType() == blpapi.Event.RESPONSE:
                break

        session.stop()
        return jsonify({"ticker": ticker, "supply_chain": results, "timestamp": datetime.datetime.now().isoformat()})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/bloomberg/institutional', methods=['POST'])
def get_institutional():
    """
    Pull institutional ownership and insider data.
    Expects JSON: {"ticker": "MRVL US Equity"}
    """
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    ticker = data.get('ticker', '')

    fields = [
        "EQY_INST_PCT_SHARES_OUT",
        "EQY_INST_SHARES_OUT",
        "SHORT_INT",
        "SHORT_INT_RATIO",
        "INSIDER_SHARES_OWNED_PCT",
        "PX_LAST",
        "BEST_EPS_NXT_YR",
        "BEST_EPS_CUR_YR",
        "EARN_ANN_DT_TIME_HIST_WITH_EPS",
        "ANALYST_RECOMMENDATIONS_HIST",
        "TOT_ANALYST_REC",
        "BEST_TARGET_PRICE",
        "BEST_TARGET_PRICE_MEDIAN",
    ]

    try:
        import blpapi
        sessionOptions = blpapi.SessionOptions()
        sessionOptions.setServerHost("localhost")
        sessionOptions.setServerPort(8194)
        session = blpapi.Session(sessionOptions)

        if not session.start():
            return jsonify({"error": "Bloomberg Terminal not running"}), 503

        if not session.openService("//blp/refdata"):
            return jsonify({"error": "Failed to open refdata service"}), 503

        refDataService = session.getService("//blp/refdata")
        request_obj = refDataService.createRequest("ReferenceDataRequest")
        request_obj.append("securities", ticker)
        for field in fields:
            request_obj.append("fields", field)

        session.sendRequest(request_obj)

        results = {}
        while True:
            event = session.nextEvent(500)
            for msg in event:
                if msg.hasElement("securityData"):
                    secData = msg.getElement("securityData")
                    for i in range(secData.numValues()):
                        sec = secData.getValue(i)
                        fieldData = sec.getElement("fieldData")
                        for field in fields:
                            try:
                                el = fieldData.getElement(field)
                                results[field] = element_to_python(el)
                            except:
                                results[field] = "N/A"
            if event.eventType() == blpapi.Event.RESPONSE:
                break

        session.stop()
        return jsonify({"ticker": ticker, "institutional": results, "timestamp": datetime.datetime.now().isoformat()})

    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/bloomberg/quick', methods=['GET'])
def quick_check():
    """
    Quick check - is Bloomberg Terminal running?
    """
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401

    try:
        result = subprocess.run(
            ['tasklist', '/FI', 'IMAGENAME eq bbcomm.exe'],
            capture_output=True, text=True
        )
        bloomberg_running = 'bbcomm.exe' in result.stdout
        return jsonify({
            "bloomberg_running": bloomberg_running,
            "status": "Terminal active" if bloomberg_running else "Terminal not detected",
            "time": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    print("Bloomberg Local Server starting on port 5001...")
    print(f"API Key: {API_KEY}")
    print("Keep this running while Bloomberg Terminal is active.")
    print("Endpoints: /health | /bloomberg/run | /bloomberg/splc | /bloomberg/institutional | /bloomberg/quick")
    app.run(host='0.0.0.0', port=5001, debug=False)
