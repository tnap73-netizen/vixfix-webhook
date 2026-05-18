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
    Run a Bloomberg BQL query or function via blpapi.
    Expects JSON: {"ticker": "MRVL US", "fields": ["EQY_INST_PCT_SHARES_OUT", "BEST_EPS"]}
    """
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401

    data = request.json
    ticker = data.get('ticker', '')
    fields = data.get('fields', [])

    try:
        import blpapi
        # Start Bloomberg session
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
                                results[field] = str(fieldData.getElementValue(field))
                            except:
                                results[field] = "N/A"
            if event.eventType() == blpapi.Event.RESPONSE:
                break

        session.stop()
        return jsonify({"ticker": ticker, "data": results, "timestamp": datetime.datetime.now().isoformat()})

    except ImportError:
        return jsonify({"error": "blpapi not installed — run: pip install blpapi"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/bloomberg/quick', methods=['GET'])
def quick_check():
    """
    Quick check — is Bloomberg Terminal running?
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
    app.run(host='0.0.0.0', port=5001, debug=False)
