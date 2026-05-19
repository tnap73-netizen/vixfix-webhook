"""
Bloomberg Local Data Server
Runs on Windows machine with Bloomberg Terminal active.
Exposes endpoints via Cloudflare Tunnel for remote access.
Full functionality — reference data, bulk arrays, ALTD, historical, custom BQL.
"""

from flask import Flask, jsonify, request
import subprocess
import json
import os
import datetime

app = Flask(__name__)

API_KEY = "BGMS2024secure"

def check_api_key():
    key = request.headers.get('X-API-Key')
    if key != API_KEY:
        return False
    return True

def element_to_python(element):
    """Recursively convert any blpapi Element to Python — scalar, array, nested table."""
    try:
        if element.isArray():
            result = []
            for i in range(element.numValues()):
                item = element.getValue(i)
                if hasattr(item, 'numElements'):
                    row = {}
                    for j in range(item.numElements()):
                        child = item.getElement(j)
                        row[str(child.name())] = element_to_python(child)
                    result.append(row)
                else:
                    result.append(str(item))
            return result
        elif element.numElements() > 0:
            result = {}
            for i in range(element.numElements()):
                child = element.getElement(i)
                result[str(child.name())] = element_to_python(child)
            return result
        else:
            try:
                val = element.getValue()
                return str(val) if val is not None else "N/A"
            except:
                return "N/A"
    except:
        return "N/A"

def run_reference_request(ticker, fields, overrides=None):
    """Core Bloomberg reference data request — handles all field types including bulk arrays."""
    import blpapi
    sessionOptions = blpapi.SessionOptions()
    sessionOptions.setServerHost("localhost")
    sessionOptions.setServerPort(8194)
    session = blpapi.Session(sessionOptions)

    if not session.start():
        return None, "Bloomberg Terminal not running or not connected"

    if not session.openService("//blp/refdata"):
        session.stop()
        return None, "Failed to open Bloomberg reference data service"

    refDataService = session.getService("//blp/refdata")
    request_obj = refDataService.createRequest("ReferenceDataRequest")
    request_obj.append("securities", ticker)
    for field in fields:
        request_obj.append("fields", field)

    # Apply overrides if provided (e.g. date ranges, currency)
    if overrides:
        overridesElement = request_obj.getElement("overrides")
        for key, val in overrides.items():
            override = overridesElement.appendElement()
            override.setElement("fieldId", key)
            override.setElement("value", str(val))

    session.sendRequest(request_obj)

    results = {}
    while True:
        event = session.nextEvent(500)
        for msg in event:
            if msg.hasElement("securityData"):
                secData = msg.getElement("securityData")
                for i in range(secData.numValues()):
                    sec = secData.getValue(i)
                    # Capture field errors
                    if sec.hasElement("fieldExceptions"):
                        fe = sec.getElement("fieldExceptions")
                        for j in range(fe.numValues()):
                            exc = fe.getValue(j)
                            fid = str(exc.getElement("fieldId").getValue())
                            results[fid] = "FIELD_ERROR"
                    fieldData = sec.getElement("fieldData")
                    for field in fields:
                        if results.get(field) == "FIELD_ERROR":
                            continue
                        try:
                            el = fieldData.getElement(field)
                            results[field] = element_to_python(el)
                        except:
                            results[field] = "N/A"
        if event.eventType() == blpapi.Event.RESPONSE:
            break

    session.stop()
    return results, None

def run_historical_request(ticker, fields, start_date, end_date, frequency="DAILY"):
    """Bloomberg historical data request — time series."""
    import blpapi
    sessionOptions = blpapi.SessionOptions()
    sessionOptions.setServerHost("localhost")
    sessionOptions.setServerPort(8194)
    session = blpapi.Session(sessionOptions)

    if not session.start():
        return None, "Bloomberg Terminal not running"

    if not session.openService("//blp/refdata"):
        session.stop()
        return None, "Failed to open refdata service"

    refDataService = session.getService("//blp/refdata")
    request_obj = refDataService.createRequest("HistoricalDataRequest")
    request_obj.append("securities", ticker)
    for field in fields:
        request_obj.append("fields", field)
    request_obj.set("startDate", start_date)
    request_obj.set("endDate", end_date)
    request_obj.set("periodicitySelection", frequency)

    session.sendRequest(request_obj)

    results = []
    while True:
        event = session.nextEvent(500)
        for msg in event:
            if msg.hasElement("securityData"):
                secData = msg.getElement("securityData")
                fieldData = secData.getElement("fieldData")
                for i in range(fieldData.numValues()):
                    point = fieldData.getValue(i)
                    row = {}
                    for j in range(point.numElements()):
                        el = point.getElement(j)
                        row[str(el.name())] = element_to_python(el)
                    results.append(row)
        if event.eventType() == blpapi.Event.RESPONSE:
            break

    session.stop()
    return results, None

def run_altd_request(ticker, fields):
    """
    Bloomberg ALTD alternative data — uses same refdata service but
    with ALTD-specific field names and session handling.
    Covers Second Measure, Similarweb, Placer, Quant Insight, etc.
    """
    import blpapi
    sessionOptions = blpapi.SessionOptions()
    sessionOptions.setServerHost("localhost")
    sessionOptions.setServerPort(8194)
    session = blpapi.Session(sessionOptions)

    if not session.start():
        return None, "Bloomberg Terminal not running"

    if not session.openService("//blp/refdata"):
        session.stop()
        return None, "Failed to open refdata service"

    refDataService = session.getService("//blp/refdata")
    request_obj = refDataService.createRequest("ReferenceDataRequest")
    request_obj.append("securities", ticker)
    for field in fields:
        request_obj.append("fields", field)

    session.sendRequest(request_obj)

    results = {}
    errors = []
    while True:
        event = session.nextEvent(500)
        for msg in event:
            if msg.hasElement("securityData"):
                secData = msg.getElement("securityData")
                for i in range(secData.numValues()):
                    sec = secData.getValue(i)
                    if sec.hasElement("fieldExceptions"):
                        fe = sec.getElement("fieldExceptions")
                        for j in range(fe.numValues()):
                            exc = fe.getValue(j)
                            fid = str(exc.getElement("fieldId").getValue())
                            err_info = exc.getElement("errorInfo")
                            msg_str = str(err_info.getElement("message").getValue()) if err_info.hasElement("message") else "unknown"
                            errors.append({"field": fid, "error": msg_str})
                            results[fid] = f"NOT_AVAILABLE: {msg_str}"
                    fieldData = sec.getElement("fieldData")
                    for field in fields:
                        if field in results:
                            continue
                        try:
                            el = fieldData.getElement(field)
                            results[field] = element_to_python(el)
                        except:
                            results[field] = "N/A"
        if event.eventType() == blpapi.Event.RESPONSE:
            break

    session.stop()
    return results, errors


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
    General purpose Bloomberg reference data pull.
    Body: {"ticker": "MRVL US Equity", "fields": ["PX_LAST", ...], "overrides": {"VWAP_START_TIME": "09:30"}}
    """
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    ticker = data.get('ticker', '')
    fields = data.get('fields', [])
    overrides = data.get('overrides', None)
    try:
        import blpapi
        results, error = run_reference_request(ticker, fields, overrides)
        if error:
            return jsonify({"error": error}), 503
        return jsonify({"ticker": ticker, "data": results, "timestamp": datetime.datetime.now().isoformat()})
    except ImportError:
        return jsonify({"error": "blpapi not installed"}), 503
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/bloomberg/historical', methods=['POST'])
def run_historical():
    """
    Bloomberg historical time series data.
    Body: {"ticker": "MRVL US Equity", "fields": ["PX_LAST", "VOLUME"], "start": "20250101", "end": "20260518", "frequency": "DAILY"}
    Frequency options: DAILY, WEEKLY, MONTHLY, QUARTERLY, YEARLY
    """
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    ticker = data.get('ticker', '')
    fields = data.get('fields', [])
    start = data.get('start', '')
    end = data.get('end', datetime.datetime.now().strftime('%Y%m%d'))
    frequency = data.get('frequency', 'DAILY')
    try:
        import blpapi
        results, error = run_historical_request(ticker, fields, start, end, frequency)
        if error:
            return jsonify({"error": error}), 503
        return jsonify({"ticker": ticker, "data": results, "start": start, "end": end, "frequency": frequency, "timestamp": datetime.datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/bloomberg/altd', methods=['POST'])
def run_altd():
    """
    Bloomberg Alternative Data (ALTD) endpoint.
    Covers: Second Measure (consumer spend), Similarweb (web traffic),
    Placer.ai (foot traffic), Quant Insight, earnings beat probability.
    Body: {"ticker": "AAPL US Equity", "dataset": "all"}
    dataset options: "earnings", "web", "foot_traffic", "sentiment", "all"
    """
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    ticker = data.get('ticker', '')
    dataset = data.get('dataset', 'all')

    field_sets = {
        "earnings": [
            "BLOOMBERG_EARN_ALPHA",
            "BLOOMBERG_EARN_BEAT_PROB",
            "BLOOMBERG_EARN_SURPRISE_PRED",
            "BLOOMBERG_EARN_SIGNAL",
            "BLOOMBERG_EARN_DIRECTION",
            "EARN_EST_REVISION_TREND_UP",
            "EARN_EST_REVISION_TREND_DOWN",
            "BEST_EPS_NUMEST",
            "EPS_SURPRISE_HIST",
        ],
        "web": [
            "SIMILARWEB_MONTHLY_VISITS",
            "SIMILARWEB_VISITS_GROWTH_YOY",
            "SIMILARWEB_VISITS_GROWTH_MOM",
            "SIMILARWEB_BOUNCE_RATE",
            "SIMILARWEB_PAGES_PER_VISIT",
            "SIMILARWEB_VISIT_DURATION",
            "SIMILARWEB_TRAFFIC_SHARE_ORGANIC",
            "SIMILARWEB_TRAFFIC_SHARE_PAID",
        ],
        "foot_traffic": [
            "PLACER_MONTHLY_VISITS",
            "PLACER_VISITS_GROWTH_YOY",
            "PLACER_VISITS_GROWTH_MOM",
            "PLACER_MEDIAN_DWELL_TIME",
            "PLACER_TRADE_AREA_SIZE",
        ],
        "sentiment": [
            "SECOND_MEASURE_SALES_GROWTH_YOY",
            "SECOND_MEASURE_SALES_GROWTH_MOM",
            "SECOND_MEASURE_MARKET_SHARE",
            "SECOND_MEASURE_CUSTOMER_GROWTH",
            "SECOND_MEASURE_SPEND_PER_CUSTOMER",
            "NEWS_SENTIMENT_DAILY",
            "SOCIAL_MEDIA_SENTIMENT",
            "TWITTER_SENTIMENT_DAILY",
        ],
    }

    if dataset == "all":
        fields = []
        for v in field_sets.values():
            fields.extend(v)
    else:
        fields = field_sets.get(dataset, [])

    if not fields:
        return jsonify({"error": f"Unknown dataset: {dataset}. Options: earnings, web, foot_traffic, sentiment, all"}), 400

    try:
        import blpapi
        results, errors = run_altd_request(ticker, fields)
        # Filter out N/A to show only what actually returned data
        clean = {k: v for k, v in results.items() if v != "N/A" and not str(v).startswith("NOT_AVAILABLE")}
        unavailable = {k: v for k, v in results.items() if v == "N/A" or str(v).startswith("NOT_AVAILABLE")}
        return jsonify({
            "ticker": ticker,
            "dataset": dataset,
            "data": clean,
            "unavailable_fields": list(unavailable.keys()),
            "field_errors": errors,
            "note": "Unavailable fields may require specific ALTD subscription or field name differs by terminal version",
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/bloomberg/institutional', methods=['POST'])
def get_institutional():
    """
    Full institutional ownership — top holders, fund ownership, insider activity, short interest.
    Body: {"ticker": "MRVL US Equity"}
    """
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    ticker = data.get('ticker', '')

    fields = [
        "INST_HOLDER_1", "INST_HOLDER_2", "INST_HOLDER_3", "INST_HOLDER_4", "INST_HOLDER_5",
        "INST_HOLDER_6", "INST_HOLDER_7", "INST_HOLDER_8", "INST_HOLDER_9", "INST_HOLDER_10",
        "INST_HOLDING_PCT_1", "INST_HOLDING_PCT_2", "INST_HOLDING_PCT_3", "INST_HOLDING_PCT_4", "INST_HOLDING_PCT_5",
        "INST_HOLDING_PCT_6", "INST_HOLDING_PCT_7", "INST_HOLDING_PCT_8", "INST_HOLDING_PCT_9", "INST_HOLDING_PCT_10",
        "INST_HOLDING_CHNG_1", "INST_HOLDING_CHNG_2", "INST_HOLDING_CHNG_3", "INST_HOLDING_CHNG_4", "INST_HOLDING_CHNG_5",
        "INST_HOLDING_CHNG_6", "INST_HOLDING_CHNG_7", "INST_HOLDING_CHNG_8", "INST_HOLDING_CHNG_9", "INST_HOLDING_CHNG_10",
        "SHORT_INT", "SHORT_INT_RATIO", "EQY_FLOAT", "INSIDER_SHARES_OWNED_PCT",
    ]

    try:
        import blpapi
        results, error = run_reference_request(ticker, fields)
        if error:
            return jsonify({"error": error}), 503

        holders = []
        for i in range(1, 11):
            name = results.get(f"INST_HOLDER_{i}", "N/A")
            pct = results.get(f"INST_HOLDING_PCT_{i}", "N/A")
            chng = results.get(f"INST_HOLDING_CHNG_{i}", "N/A")
            if name != "N/A":
                holders.append({"rank": i, "holder": name, "pct_owned": pct, "qtr_change": chng})

        return jsonify({
            "ticker": ticker,
            "top_holders": holders,
            "short_interest": results.get("SHORT_INT"),
            "short_ratio": results.get("SHORT_INT_RATIO"),
            "float_shares_M": results.get("EQY_FLOAT"),
            "insider_pct": results.get("INSIDER_SHARES_OWNED_PCT"),
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/bloomberg/splc', methods=['POST'])
def get_supply_chain():
    """
    Full SPLC supply chain — suppliers and customers with tickers and countries.
    Body: {"ticker": "MRVL US Equity"}
    """
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    ticker = data.get('ticker', '')

    fields = [
        "SUPPLY_CHAIN_SUPPLIERS",
        "SUPPLY_CHAIN_CUSTOMERS",
        "SUPPLY_CHAIN_SUPPLIERS_EX_TREASURY",
        "SUPPLY_CHAIN_CUSTOMERS_EX_TREASURY",
    ]

    try:
        import blpapi
        results, error = run_reference_request(ticker, fields)
        if error:
            return jsonify({"error": error}), 503
        return jsonify({"ticker": ticker, "supply_chain": results, "timestamp": datetime.datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/bloomberg/earnings', methods=['POST'])
def get_earnings():
    """
    Full earnings picture — estimates, revisions, surprise history, analyst breakdown.
    Body: {"ticker": "MRVL US Equity"}
    """
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    ticker = data.get('ticker', '')

    fields = [
        "BEST_EPS_CUR_QTR", "BEST_EPS_NXT_QTR", "BEST_EPS_CUR_YR", "BEST_EPS_NXT_YR",
        "BEST_SALES_CUR_QTR", "BEST_SALES_NXT_QTR", "BEST_SALES_CUR_YR", "BEST_SALES_NXT_YR",
        "BEST_TARGET_PRICE", "BEST_BUY_REC", "BEST_HOLD_REC", "BEST_SELL_REC",
        "TOT_ANALYST_REC", "BEST_ANALYST_RATING", "EARN_ANN_DT",
        "IS_EPS", "TRAIL_12M_EPS", "PE_RATIO", "BEST_PE_RATIO",
        "EPS_SURPRISE_HIST", "BEST_EPS_NUMEST",
        "EARN_EST_REVISION_TREND_UP", "EARN_EST_REVISION_TREND_DOWN",
        "GROSS_MARGIN", "EBITDA", "NET_INCOME", "SALES_REV_TURN",
    ]

    try:
        import blpapi
        results, error = run_reference_request(ticker, fields)
        if error:
            return jsonify({"error": error}), 503
        return jsonify({"ticker": ticker, "earnings": results, "timestamp": datetime.datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/bloomberg/options', methods=['POST'])
def get_options():
    """
    Options market data — put/call ratios, open interest, implied vol.
    Body: {"ticker": "MRVL US Equity"}
    """
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    ticker = data.get('ticker', '')

    fields = [
        "OPT_PUT_CALL_RATIO_OI", "OPT_PUT_CALL_RATIO_VOLUME",
        "OPT_CALL_OPEN_INT", "OPT_PUT_OPEN_INT",
        "OPT_VOLUME_CALL", "OPT_VOLUME_PUT",
        "30DAY_IMPVOL_100_CALL", "30DAY_IMPVOL_100_PUT",
        "IVOL_DELTA_25_CALL_3MO", "IVOL_DELTA_25_PUT_3MO",
        "HIST_CALL_IMP_VOL", "HIST_PUT_IMP_VOL",
        "OPT_SKEW", "OPT_TERM_STRUCTURE",
    ]

    try:
        import blpapi
        results, error = run_reference_request(ticker, fields)
        if error:
            return jsonify({"error": error}), 503
        return jsonify({"ticker": ticker, "options": results, "timestamp": datetime.datetime.now().isoformat()})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/bloomberg/full', methods=['POST'])
def get_full():
    """
    Full pre-trade picture in one call.
    Body: {"ticker": "MRVL US Equity"}
    """
    if not check_api_key():
        return jsonify({"error": "Unauthorized"}), 401
    data = request.json
    ticker = data.get('ticker', '')

    fields = [
        "PX_LAST", "CHG_PCT_1D", "VOLUME", "VOLUME_AVG_20D",
        "PE_RATIO", "TRAIL_12M_EPS", "GROSS_MARGIN", "EBITDA", "NET_INCOME", "SALES_REV_TURN",
        "BEST_EPS_CUR_QTR", "BEST_EPS_NXT_QTR", "BEST_EPS_NXT_YR", "BEST_SALES_NXT_YR",
        "BEST_TARGET_PRICE", "TOT_ANALYST_REC", "BEST_BUY_REC", "BEST_HOLD_REC", "BEST_SELL_REC",
        "EQY_FLOAT", "SHORT_INT", "SHORT_INT_RATIO", "INSIDER_SHARES_OWNED_PCT",
        "INST_HOLDER_1", "INST_HOLDER_2", "INST_HOLDER_3", "INST_HOLDER_4", "INST_HOLDER_5",
        "INST_HOLDING_PCT_1", "INST_HOLDING_PCT_2", "INST_HOLDING_PCT_3", "INST_HOLDING_PCT_4", "INST_HOLDING_PCT_5",
        "INST_HOLDING_CHNG_1", "INST_HOLDING_CHNG_2", "INST_HOLDING_CHNG_3", "INST_HOLDING_CHNG_4", "INST_HOLDING_CHNG_5",
        "SUPPLY_CHAIN_SUPPLIERS", "SUPPLY_CHAIN_CUSTOMERS",
        "OPT_PUT_CALL_RATIO_OI", "OPT_PUT_CALL_RATIO_VOLUME",
        "OPT_CALL_OPEN_INT", "OPT_PUT_OPEN_INT",
        "30DAY_IMPVOL_100_CALL", "30DAY_IMPVOL_100_PUT",
    ]

    try:
        import blpapi
        results, error = run_reference_request(ticker, fields)
        if error:
            return jsonify({"error": error}), 503

        holders = []
        for i in range(1, 6):
            name = results.get(f"INST_HOLDER_{i}", "N/A")
            pct = results.get(f"INST_HOLDING_PCT_{i}", "N/A")
            chng = results.get(f"INST_HOLDING_CHNG_{i}", "N/A")
            if name != "N/A":
                holders.append({"rank": i, "holder": name, "pct_owned": pct, "qtr_change": chng})

        return jsonify({
            "ticker": ticker,
            "price": {
                "last": results.get("PX_LAST"),
                "chg_pct": results.get("CHG_PCT_1D"),
                "volume": results.get("VOLUME"),
                "avg_volume_20d": results.get("VOLUME_AVG_20D"),
            },
            "fundamentals": {
                "pe_ratio": results.get("PE_RATIO"),
                "trailing_eps": results.get("TRAIL_12M_EPS"),
                "gross_margin": results.get("GROSS_MARGIN"),
                "ebitda": results.get("EBITDA"),
                "net_income": results.get("NET_INCOME"),
                "revenue": results.get("SALES_REV_TURN"),
            },
            "estimates": {
                "eps_cur_qtr": results.get("BEST_EPS_CUR_QTR"),
                "eps_nxt_qtr": results.get("BEST_EPS_NXT_QTR"),
                "eps_nxt_yr": results.get("BEST_EPS_NXT_YR"),
                "sales_nxt_yr": results.get("BEST_SALES_NXT_YR"),
                "target_price": results.get("BEST_TARGET_PRICE"),
                "analysts_total": results.get("TOT_ANALYST_REC"),
                "buys": results.get("BEST_BUY_REC"),
                "holds": results.get("BEST_HOLD_REC"),
                "sells": results.get("BEST_SELL_REC"),
            },
            "institutional": {
                "float_M": results.get("EQY_FLOAT"),
                "short_int": results.get("SHORT_INT"),
                "short_ratio": results.get("SHORT_INT_RATIO"),
                "insider_pct": results.get("INSIDER_SHARES_OWNED_PCT"),
                "top_holders": holders,
            },
            "supply_chain": {
                "suppliers": results.get("SUPPLY_CHAIN_SUPPLIERS"),
                "customers": results.get("SUPPLY_CHAIN_CUSTOMERS"),
            },
            "options": {
                "put_call_ratio_oi": results.get("OPT_PUT_CALL_RATIO_OI"),
                "put_call_ratio_vol": results.get("OPT_PUT_CALL_RATIO_VOLUME"),
                "call_oi": results.get("OPT_CALL_OPEN_INT"),
                "put_oi": results.get("OPT_PUT_OPEN_INT"),
                "iv_30d_call": results.get("30DAY_IMPVOL_100_CALL"),
                "iv_30d_put": results.get("30DAY_IMPVOL_100_PUT"),
            },
            "timestamp": datetime.datetime.now().isoformat()
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@app.route('/bloomberg/quick', methods=['GET'])
def quick_check():
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
    print("Endpoints:")
    print("  /health                  — server status")
    print("  /bloomberg/run           — custom field pull with optional overrides")
    print("  /bloomberg/full          — complete pre-trade picture")
    print("  /bloomberg/institutional — top 10 holders + short interest + insider %")
    print("  /bloomberg/splc          — supply chain suppliers + customers")
    print("  /bloomberg/earnings      — estimates, revisions, analyst breakdown")
    print("  /bloomberg/options       — put/call ratios, OI, implied vol, skew")
    print("  /bloomberg/altd          — alternative data (Second Measure, Similarweb, Placer)")
    print("  /bloomberg/historical    — time series historical data")
    print("  /bloomberg/quick         — terminal status check")
    app.run(host='0.0.0.0', port=5001, debug=False)
