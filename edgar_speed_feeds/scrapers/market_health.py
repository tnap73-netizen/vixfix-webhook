"""BMCMC market-health refresh.

Repo-owned replacement for the old Perplexity-owned market-health task.
This module intentionally avoids Perplexity connectors so it can run under
Railway native cron.
"""

from __future__ import annotations

import csv
import json
import math
import os
import tempfile
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
ALERTS_DIR = ROOT / "alerts"
LOGS_DIR = ROOT / "logs"
MARKET_HEALTH_PATH = ALERTS_DIR / "market_health.json"
MARKET_HEALTH_LOG = LOGS_DIR / "market_health_cron.log"


STOOQ_SYMBOLS = {
    "SPY": "spy.us",
    "QQQ": "qqq.us",
    "IWM": "iwm.us",
    "HYG": "hyg.us",
    "TLT": "tlt.us",
    "UUP": "uup.us",
    "VIX": "^vix",
}

YAHOO_SYMBOLS = {
    "SPY": "SPY",
    "QQQ": "QQQ",
    "IWM": "IWM",
    "HYG": "HYG",
    "TLT": "TLT",
    "UUP": "UUP",
    "VIX": "^VIX",
}


@dataclass
class Quote:
    symbol: str
    source_symbol: str
    price: float | None
    previous_close: float | None
    change: float | None
    change_pct: float | None
    source: str
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "source_symbol": self.source_symbol,
            "price": self.price,
            "previous_close": self.previous_close,
            "change": self.change,
            "changesPercentage": self.change_pct,
            "source": self.source,
            "error": self.error,
        }


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _ensure_dirs() -> None:
    ALERTS_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def _safe_float(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    if not value or value.upper() == "N/D":
        return None
    try:
        out = float(value)
    except ValueError:
        return None
    if math.isnan(out) or math.isinf(out):
        return None
    return out


def fetch_stooq_quote(symbol: str, timeout: int = 15) -> Quote:
    source_symbol = STOOQ_SYMBOLS[symbol]
    params = urllib.parse.urlencode({"s": source_symbol, "f": "sd2t2ohlcv", "h": "", "e": "csv"})
    url = f"https://stooq.com/q/l/?{params}"
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            text = resp.read().decode("utf-8", "replace")
        rows = list(csv.DictReader(text.splitlines()))
        if not rows:
            raise RuntimeError("empty CSV")
        row = rows[0]
        close = _safe_float(row.get("Close"))
        previous_close = _safe_float(row.get("Open"))
        if close is None:
            raise RuntimeError(f"missing close in Stooq row: {row}")
        change = None
        change_pct = None
        if previous_close:
            change = close - previous_close
            change_pct = change / previous_close * 100.0
        return Quote(
            symbol=symbol,
            source_symbol=source_symbol,
            price=round(close, 4),
            previous_close=round(previous_close, 4) if previous_close is not None else None,
            change=round(change, 4) if change is not None else None,
            change_pct=round(change_pct, 4) if change_pct is not None else None,
            source="stooq",
        )
    except Exception as exc:  # noqa: BLE001 - preserve exact runtime cause in output/log.
        return Quote(
            symbol=symbol,
            source_symbol=source_symbol,
            price=None,
            previous_close=None,
            change=None,
            change_pct=None,
            source="stooq",
            error=repr(exc),
        )


def fetch_yahoo_quote(symbol: str, timeout: int = 15) -> Quote:
    source_symbol = YAHOO_SYMBOLS[symbol]
    encoded = urllib.parse.quote(source_symbol, safe="")
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{encoded}?range=2d&interval=1d"
    try:
        req = urllib.request.Request(
            url,
            headers={"User-Agent": "BMCMC-market-health/1.0"},
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            payload = json.loads(resp.read().decode("utf-8", "replace"))
        result = (payload.get("chart") or {}).get("result") or []
        if not result:
            raise RuntimeError(f"empty Yahoo chart result: {payload}")
        meta = result[0].get("meta") or {}
        price = _safe_float(str(meta.get("regularMarketPrice")))
        previous_close = _safe_float(str(meta.get("chartPreviousClose") or meta.get("previousClose")))
        if price is None:
            closes = ((result[0].get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
            numeric_closes = [float(close) for close in closes if close is not None]
            price = numeric_closes[-1] if numeric_closes else None
        if previous_close is None:
            closes = ((result[0].get("indicators") or {}).get("quote") or [{}])[0].get("close") or []
            numeric_closes = [float(close) for close in closes if close is not None]
            previous_close = numeric_closes[-2] if len(numeric_closes) >= 2 else None
        if price is None:
            raise RuntimeError(f"missing price in Yahoo payload for {source_symbol}")
        change = None
        change_pct = None
        if previous_close:
            change = price - previous_close
            change_pct = change / previous_close * 100.0
        return Quote(
            symbol=symbol,
            source_symbol=source_symbol,
            price=round(price, 4),
            previous_close=round(previous_close, 4) if previous_close is not None else None,
            change=round(change, 4) if change is not None else None,
            change_pct=round(change_pct, 4) if change_pct is not None else None,
            source="yahoo_chart",
        )
    except Exception as exc:  # noqa: BLE001
        fallback = fetch_stooq_quote(symbol, timeout=timeout)
        if fallback.error:
            fallback.error = f"yahoo={repr(exc)}; stooq={fallback.error}"
        else:
            fallback.error = f"yahoo fallback used: {repr(exc)}"
        return fallback


def fetch_snapshot() -> dict[str, Quote]:
    return {symbol: fetch_yahoo_quote(symbol) for symbol in STOOQ_SYMBOLS}


def _pct(snapshot: dict[str, Quote], symbol: str) -> float | None:
    return snapshot.get(symbol, Quote(symbol, "", None, None, None, None, "")).change_pct


def classify_regime(snapshot: dict[str, Quote]) -> tuple[str, str]:
    spy = _pct(snapshot, "SPY")
    qqq = _pct(snapshot, "QQQ")
    iwm = _pct(snapshot, "IWM")
    hyg = _pct(snapshot, "HYG")
    tlt = _pct(snapshot, "TLT")
    uup = _pct(snapshot, "UUP")
    vix = _pct(snapshot, "VIX")

    equity = _avg([spy, qqq, iwm])
    credit_ok = hyg is not None and hyg >= -0.25
    credit_bad = hyg is not None and hyg <= -0.50
    vix_up = vix is not None and vix >= 3.0
    vix_down = vix is not None and vix <= -3.0
    rates_bid = tlt is not None and tlt >= 0.40
    dollar_hot = uup is not None and uup >= 0.30

    if credit_bad and vix_up:
        regime = "DEFENSIVE"
    elif credit_ok and vix_up and equity is not None and equity >= -0.60:
        regime = "OPPORTUNITY"
    elif credit_ok and (vix_down or (equity is not None and equity >= 0.40)):
        regime = "CONSTRUCTIVE"
    elif credit_bad or vix_up or rates_bid or dollar_hot:
        regime = "CAUTION"
    else:
        regime = "NEUTRAL"

    summary_bits = []
    if equity is not None:
        summary_bits.append(f"EQ {equity:+.2f}%")
    if hyg is not None:
        summary_bits.append(f"HYG {hyg:+.2f}%")
    if vix is not None:
        summary_bits.append(f"VIX {vix:+.2f}%")
    if tlt is not None:
        summary_bits.append(f"TLT {tlt:+.2f}%")
    if uup is not None:
        summary_bits.append(f"UUP {uup:+.2f}%")
    summary = f"{regime} | " + " | ".join(summary_bits) if summary_bits else f"{regime} | quote gaps"
    return regime, summary


def _avg(values: list[float | None]) -> float | None:
    good = [value for value in values if value is not None]
    if not good:
        return None
    return sum(good) / len(good)


def load_previous_payload() -> dict[str, Any] | None:
    if not MARKET_HEALTH_PATH.exists():
        return None
    try:
        return json.loads(MARKET_HEALTH_PATH.read_text())
    except Exception:
        return None


def build_payload() -> dict[str, Any]:
    snapshot = fetch_snapshot()
    previous = load_previous_payload()

    if snapshot["VIX"].price is None and previous:
        old_vix = (previous.get("instruments") or {}).get("VIX") or {}
        if old_vix.get("price") is not None:
            snapshot["VIX"] = Quote(
                symbol="VIX",
                source_symbol="previous",
                price=old_vix.get("price"),
                previous_close=old_vix.get("previous_close"),
                change=old_vix.get("change"),
                change_pct=old_vix.get("changesPercentage"),
                source="previous_market_health",
                error="live VIX unavailable; reused previous value",
            )

    regime, summary = classify_regime(snapshot)
    errors = {symbol: quote.error for symbol, quote in snapshot.items() if quote.error}

    return {
        "schema": "bmcmc.market_health.v1",
        "generated_at": _now_iso(),
        "regime": regime,
        "summary": summary,
        "source": "repo_owned_stooq_fallback",
        "instruments": {symbol: quote.as_dict() for symbol, quote in snapshot.items()},
        "spy": snapshot["SPY"].as_dict(),
        "qqq": snapshot["QQQ"].as_dict(),
        "iwm": snapshot["IWM"].as_dict(),
        "vix": snapshot["VIX"].as_dict(),
        "hyg": snapshot["HYG"].as_dict(),
        "tlt": snapshot["TLT"].as_dict(),
        "uup": snapshot["UUP"].as_dict(),
        "dxy_pct": snapshot["UUP"].change_pct,
        "errors": errors,
    }


def atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", dir=str(path.parent), delete=False) as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        tmp_path = Path(tmp.name)
    os.replace(tmp_path, path)


def append_log(payload: dict[str, Any]) -> None:
    MARKET_HEALTH_LOG.parent.mkdir(parents=True, exist_ok=True)
    record = {
        "ts": payload["generated_at"],
        "regime": payload["regime"],
        "summary": payload["summary"],
        "errors": payload["errors"],
    }
    with MARKET_HEALTH_LOG.open("a") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def refresh_market_health() -> dict[str, Any]:
    _ensure_dirs()
    payload = build_payload()
    hard_failures = [
        symbol
        for symbol in ("SPY", "QQQ", "IWM", "HYG", "TLT", "UUP")
        if payload["instruments"][symbol]["price"] is None
    ]
    atomic_write_json(MARKET_HEALTH_PATH, payload)
    append_log(payload)
    if hard_failures:
        raise RuntimeError(f"market health quote failures: {hard_failures}")
    return payload


def main() -> int:
    try:
        payload = refresh_market_health()
    except Exception as exc:  # noqa: BLE001
        _ensure_dirs()
        error_record = {"ts": _now_iso(), "event": "market_health_failed", "error": repr(exc)}
        with MARKET_HEALTH_LOG.open("a") as handle:
            handle.write(json.dumps(error_record, sort_keys=True) + "\n")
        print(json.dumps(error_record, sort_keys=True))
        return 1

    if os.environ.get("BMCMC_MARKET_HEALTH_VERBOSE") == "1":
        print(json.dumps({"event": "market_health_refreshed", "regime": payload["regime"], "summary": payload["summary"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
