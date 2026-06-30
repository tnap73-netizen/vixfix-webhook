#!/usr/bin/env python3
"""Run the Arm A stock event-study backtest for a given family.

Loads the curated archive via ``archive_layer.load_for_backtest(family=...)``
and runs an OLS event study with Newey-West (HAC) standard errors. For UVOL,
factor/market adjustment is required: t20 windows overlap, the v0 short side
appears to be losing to bull-tape beta, so alpha is judged versus the market
rather than as raw directional return.

Primary horizon by family: benzinga -> t5, uvol -> t20 (overridable). The
full horizon curve (t1/t5/t10/t20/t30) is always printed, never just the
primary horizon.

A ``t20 PASS`` means worth a forward paper-trade; it is NOT a validated edge
(n is thin, v0 is survivorship-biased and small-n).

NOTE: this script is intentionally not run during the build/probe step.
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

CURVE = ("t1", "t5", "t10", "t20", "t30")
ALPHA = 0.05


def _hac_lag(n: int) -> int:
    if n <= 1:
        return 0
    return int(np.floor(4 * (n / 100.0) ** (2.0 / 9.0)))


def _factor_returns(arch: al.LoadedArchive) -> pd.DataFrame | None:
    """Load the factor matrix if present (market/factor returns by date)."""
    if al.dataset_exists(arch.archive_root, "factor_matrix"):
        return al.read_dataset(arch.archive_root, "factor_matrix")
    return None


def _event_study(fwd: pd.DataFrame, horizon: str, factors: pd.DataFrame | None) -> dict:
    """OLS of net directional return on a constant (+ factors) with HAC SE."""
    import statsmodels.api as sm

    col = "directional_return_%s" % horizon
    sub = fwd[["event_ts", col]].dropna().copy()
    n = int(len(sub))
    if n == 0:
        return {"horizon": horizon, "n": 0, "mean": None, "alpha": None,
                "t_stat": None, "p_value": None, "win_rate": None, "verdict": "NO_DATA"}

    y = sub[col].to_numpy(dtype=float)
    X = np.ones((n, 1))
    factor_cols: list[str] = []
    if factors is not None and "event_ts" in factors.columns:
        merged = sub.merge(factors, on="event_ts", how="left")
        factor_cols = [c for c in factors.columns if c != "event_ts"]
        if factor_cols:
            fx = merged[factor_cols].to_numpy(dtype=float)
            X = np.column_stack([np.ones(n), fx])

    model = sm.OLS(y, X, missing="drop")
    res = model.fit(cov_type="HAC", cov_kwds={"maxlags": _hac_lag(n)})

    alpha = float(res.params[0])
    t_stat = float(res.tvalues[0])
    p_value = float(res.pvalues[0])
    verdict = "PASS" if (p_value < ALPHA and alpha > 0) else "FAIL"

    return {
        "horizon": horizon,
        "n": n,
        "mean": float(np.mean(y)),
        "alpha": alpha,
        "t_stat": t_stat,
        "p_value": p_value,
        "win_rate": float(np.mean(y > 0)),
        "factor_adjusted": bool(factor_cols),
        "factors": factor_cols,
        "verdict": verdict,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    # --root is Todd's alias for --archive-root; either may be omitted when
    # BMCMC_DATA_ROOT is set. Resolution matches the builder/probe.
    ap.add_argument("--archive-root", "--root", dest="archive_root", default=None)
    ap.add_argument("--universe", default="bmcmc_v1")
    ap.add_argument("--family", choices=al.VALID_FAMILIES, default="benzinga")
    ap.add_argument("--primary-horizon", default=None,
                    help="override family default (benzinga=t5, uvol=t20)")
    args = ap.parse_args()

    args.archive_root = args.archive_root or os.environ.get("BMCMC_DATA_ROOT")
    if not args.archive_root:
        ap.error("archive root required: pass --archive-root/--root or set BMCMC_DATA_ROOT")

    arch = al.load_for_backtest(args.archive_root, family=args.family)
    primary = args.primary_horizon or arch.primary_horizon

    factors = _factor_returns(arch)
    if args.family == "uvol" and factors is None:
        # Factor adjustment is required for UVOL; surface its absence loudly
        # rather than silently reporting raw directional return as alpha.
        print("WARN: factor_matrix missing; UVOL alpha is not market-adjusted")

    curve = {h: _event_study(arch.forward_returns, h, factors) for h in CURVE}

    primary_res = curve.get(primary) or _event_study(arch.forward_returns, primary, factors)

    print("data_source: curated_parquet")
    print("family: %s" % args.family)
    print("primary_horizon: %s" % primary)
    print("membership_is_point_in_time: %s" % arch.membership_is_point_in_time)
    print("HORIZON_CURVE:")
    for h in CURVE:
        r = curve[h]
        print("  %s n=%s mean=%s alpha=%s t=%s p=%s win=%s verdict=%s" % (
            h, r["n"], r["mean"], r["alpha"], r["t_stat"], r["p_value"],
            r["win_rate"], r["verdict"]))
    print("VERDICT: %s (%s)" % (primary_res["verdict"], primary))
    print("SUMMARY_JSON: " + json.dumps({
        "data_source": "curated_parquet",
        "family": args.family,
        "primary_horizon": primary,
        "primary": primary_res,
        "curve": curve,
        "membership_is_point_in_time": arch.membership_is_point_in_time,
    }, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
