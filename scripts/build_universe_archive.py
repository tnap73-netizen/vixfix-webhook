#!/usr/bin/env python3
"""Build the curated universe archive.

UVOL arm: reads injected ``prices.csv`` and v0 ``events.csv`` from
``--inputs-dir`` and writes the UVOL event ledger and forward-return tables
into the curated archive, alongside the shared ``universe_members``, raw
``prices`` and a zero-cost ``costs`` placeholder.

Forward returns are close-to-close, signed by direction, net of costs, at
horizons t1/t3/t5/t10/t20/t30, and PIT-gated: a horizon that has not matured
as of ``--end`` is written as NULL.

UVOL needs no Massive/Benzinga key because prices are injected. The Benzinga
arm of the same build is a separate concern; here its ledger is reported as
0 rows unless built elsewhere.

Example::

    python3 scripts/build_universe_archive.py \
        --inputs-dir uvol_build/inputs \
        --archive-root uvol_build/archive \
        --snapshot-id bmcmc_v1 --end 2026-06-29 --family uvol
"""

from __future__ import annotations

import os
import sys
import json
import argparse

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from edge_detector import archive_layer as al  # noqa: E402

HORIZONS = (1, 3, 5, 10, 20, 30)
PRIMARY_HORIZON_DAYS = 20  # UVOL primary horizon is t20.

# Zero-cost placeholder: no cost dataset was injected for v0. Net == gross
# under this assumption, recorded explicitly so it is never mistaken for a
# real cost-adjusted figure.
ZERO_COST = {"slippage": 0.0, "borrow": 0.0, "commission": 0.0,
             "model": "zero_cost_placeholder"}


def _load_prices(inputs_dir: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(inputs_dir, "prices.csv"))
    df["date"] = pd.to_datetime(df["date"])
    for c in ("open", "high", "low", "close", "volume"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df.sort_values(["ticker", "date"]).reset_index(drop=True)
    return df


def _load_events(inputs_dir: str) -> pd.DataFrame:
    df = pd.read_csv(os.path.join(inputs_dir, "events.csv"))
    df["date"] = pd.to_datetime(df["date"])
    return df


def _build_uvol_ledger(events: pd.DataFrame) -> pd.DataFrame:
    """Rename v0 events into the UVOL ledger schema keyed (ticker, uvol_event)."""
    out = pd.DataFrame({
        "ticker": events["ticker"].astype(str),
        "uvol_event": events["event_id"].astype(str),
        "event_ts": pd.to_datetime(events["date"]),
        "event_type": "unusual_volume",
        "direction": events["event_direction"].astype(str).str.upper(),
        "event_strength": pd.to_numeric(events["event_strength"], errors="coerce"),
        "participation_score": pd.to_numeric(events["participation_score"], errors="coerce"),
        "rvol_20d": pd.to_numeric(events["rvol_20d"], errors="coerce"),
        "gap_pct": pd.to_numeric(events["gap_pct"], errors="coerce"),
        "close_strength": pd.to_numeric(events["close_strength"], errors="coerce"),
        "rs_vs_spy_1d": pd.to_numeric(events["rs_vs_spy_1d"], errors="coerce"),
        "event_description": events["event_description"].astype(str),
    })
    return out


def _build_uvol_forward_returns(ledger: pd.DataFrame, prices: pd.DataFrame,
                                end_date: pd.Timestamp) -> tuple[pd.DataFrame, dict]:
    """Close-to-close, signed-by-direction, cost-net, PIT-gated forward returns."""
    by_ticker = {tk: g.reset_index(drop=True) for tk, g in prices.groupby("ticker")}

    rows = []
    matured = {h: 0 for h in HORIZONS}
    immature = {h: 0 for h in HORIZONS}

    for _, ev in ledger.iterrows():
        tk = ev["ticker"]
        ev_ts = ev["event_ts"]
        direction = ev["direction"]
        sign = 1.0 if direction == "LONG" else -1.0

        g = by_ticker.get(tk)
        rec = {
            "ticker": tk,
            "uvol_event": ev["uvol_event"],
            "event_ts": ev_ts,
            "direction": direction,
            "entry_rule": "event_close",
            "entry_price": np.nan,
        }
        for h in HORIZONS:
            rec["raw_return_t%d" % h] = np.nan
            rec["directional_return_t%d" % h] = np.nan
            rec["gross_directional_return_t%d" % h] = np.nan
        rec["max_favorable_30d"] = np.nan
        rec["max_adverse_30d"] = np.nan

        if g is not None:
            idx_arr = g.index[g["date"] == ev_ts]
            if len(idx_arr):
                i = int(idx_arr[0])
                entry = float(g.at[i, "close"])
                rec["entry_price"] = entry
                n = len(g)

                # round-trip cost as a return drag (zero under placeholder)
                cost = ZERO_COST["slippage"] + ZERO_COST["borrow"] + ZERO_COST["commission"]

                for h in HORIZONS:
                    j = i + h
                    # matured iff the exit bar exists and its date is <= --end
                    if j < n and g.at[j, "date"] <= end_date:
                        exit_close = float(g.at[j, "close"])
                        raw = exit_close / entry - 1.0
                        gross_dir = sign * raw
                        net_dir = gross_dir - cost
                        rec["raw_return_t%d" % h] = raw
                        rec["gross_directional_return_t%d" % h] = gross_dir
                        rec["directional_return_t%d" % h] = net_dir
                        matured[h] += 1
                    else:
                        immature[h] += 1

                # excursions over the matured portion of the next 30 bars
                last = i
                for k in range(i + 1, min(i + 30, n - 1) + 1):
                    if g.at[k, "date"] > end_date:
                        break
                    last = k
                if last > i:
                    win = g.iloc[i + 1:last + 1]
                    if direction == "LONG":
                        fav = float((win["high"].max() - entry) / entry)
                        adv = float((win["low"].min() - entry) / entry)
                    else:
                        fav = float((entry - win["low"].min()) / entry)
                        adv = float((entry - win["high"].max()) / entry)
                    rec["max_favorable_30d"] = fav
                    rec["max_adverse_30d"] = adv
        rows.append(rec)

    fwd = pd.DataFrame(rows)
    coverage = {
        "matured_by_horizon": {("t%d" % h): matured[h] for h in HORIZONS},
        "immature_by_horizon": {("t%d" % h): immature[h] for h in HORIZONS},
    }
    return fwd, coverage


def _trading_cutoff(prices: pd.DataFrame, end_date: pd.Timestamp, days: int) -> pd.Timestamp | None:
    """The event date <= which a `days`-horizon event is mature as of end_date."""
    cal = np.sort(prices["date"].unique())
    cal = cal[cal <= np.datetime64(end_date)]
    if len(cal) <= days:
        return None
    return pd.Timestamp(cal[-(days + 1)])


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inputs-dir", required=True)
    # --root is Todd's alias for --archive-root; either may be omitted when
    # BMCMC_DATA_ROOT is set in the environment.
    ap.add_argument("--archive-root", "--root", dest="archive_root", default=None)
    # --universe is Todd's alias for the snapshot id.
    ap.add_argument("--snapshot-id", "--universe", dest="snapshot_id", default="bmcmc_v1")
    ap.add_argument("--end", required=True, help="YYYY-MM-DD PIT cutoff")
    # --start is accepted for CLI compatibility and recorded in the report
    # only; the build itself is PIT-gated by --end.
    ap.add_argument("--start", default=None, help="YYYY-MM-DD start (report metadata only)")
    ap.add_argument("--family", choices=al.VALID_FAMILIES, default="benzinga")
    args = ap.parse_args()

    archive_root = args.archive_root or os.environ.get("BMCMC_DATA_ROOT")
    if not archive_root:
        ap.error("archive root required: pass --archive-root/--root or set BMCMC_DATA_ROOT")
    args.archive_root = archive_root

    end_date = pd.Timestamp(args.end)
    auth_mode = "prices_injected_no_key"  # UVOL needs no Massive key.

    prices = _load_prices(args.inputs_dir)
    events = _load_events(args.inputs_dir)

    # universe_members (shared, NON-PIT, survivorship-biased v0)
    universe_path = os.path.join(args.inputs_dir, "universe.csv")
    if os.path.exists(universe_path):
        uni = pd.read_csv(universe_path)
    else:
        uni = pd.DataFrame({"ticker": sorted(prices["ticker"].unique())})
    al.write_dataset(
        args.archive_root, "universe_members", uni, kind="curated",
        extra_meta={
            "membership_is_point_in_time": False,
            "membership_note": al.DERIVED_NON_PIT_PLACEHOLDER,
            "snapshot_id": args.snapshot_id,
        },
    )

    # raw prices (shared)
    al.write_dataset(args.archive_root, "prices", prices, kind="raw",
                     extra_meta={"snapshot_id": args.snapshot_id})

    # costs (shared, zero placeholder)
    costs_df = pd.DataFrame([ZERO_COST])
    al.write_dataset(args.archive_root, "costs", costs_df, kind="curated",
                     extra_meta={"snapshot_id": args.snapshot_id})

    ledger_rows = {"benzinga": 0, "uvol": 0}
    coverage = {}

    # UVOL inputs are detected from the events file regardless of --family, so
    # Todd's family-less build still produces the UVOL ledger/forward returns
    # that `probe_backtest_data.py --family uvol` requires.
    events_are_uvol = bool(
        events["event_type"].astype(str).str.lower().eq("unusual_volume").any()
    )

    if args.family == "uvol" or events_are_uvol:
        ledger = _build_uvol_ledger(events)
        al.write_dataset(args.archive_root, "event_ledger_uvol", ledger, kind="curated",
                         extra_meta={"snapshot_id": args.snapshot_id,
                                     "event_key": ["ticker", "uvol_event"]})
        fwd, fwd_cov = _build_uvol_forward_returns(ledger, prices, end_date)
        al.write_dataset(args.archive_root, "forward_returns_uvol", fwd, kind="curated",
                         extra_meta={"snapshot_id": args.snapshot_id,
                                     "event_key": ["ticker", "uvol_event"],
                                     "cost_model": ZERO_COST["model"],
                                     "primary_horizon": "t20"})
        ledger_rows["uvol"] = int(len(ledger))

        cutoff = _trading_cutoff(prices, end_date, PRIMARY_HORIZON_DAYS)
        post_cutoff_n = int((ledger["event_ts"] > cutoff).sum()) if cutoff is not None else None
        usable_t20_n = int((ledger["event_ts"] <= cutoff).sum()) if cutoff is not None else None
        coverage = {
            **fwd_cov,
            "t20_cutoff_date": (None if cutoff is None else cutoff.strftime("%Y-%m-%d")),
            "usable_t20_events": usable_t20_n,
            "post_cutoff_immature_t20_events": post_cutoff_n,
            "matured_t20_with_return": fwd["directional_return_t20"].notna().sum().item(),
        }
    else:
        # Benzinga arm not built here (no inputs); reported as 0 rows.
        coverage = {"note": "benzinga arm not built in this invocation"}

    report = {
        "snapshot_id": args.snapshot_id,
        "auth_mode": auth_mode,
        "family": args.family,
        "start": args.start,
        "end": args.end,
        "archive_root": args.archive_root,
        "membership_is_point_in_time": False,
        "ledger_rows": ledger_rows,
        "price_rows": int(len(prices)),
        "price_tickers": int(prices["ticker"].nunique()),
        "universe_rows": int(len(uni)),
        "cost_model": ZERO_COST,
        "coverage": coverage,
    }
    print("BUILD_JSON: " + json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
