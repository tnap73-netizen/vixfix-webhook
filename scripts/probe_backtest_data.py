#!/usr/bin/env python3
"""Probe the curated backtest archive for a given event family.

For ``--family uvol`` it requires ``universe_members``, ``event_ledger_uvol``
and ``forward_returns_uvol``, verifies each dataset's SHA-256 (``hash_ok``),
and checks that the ledger key aligns 1:1 with the forward-return key on
``(ticker, uvol_event)``.

Example::

    python3 scripts/probe_backtest_data.py --family uvol \
        --archive-root uvol_build/archive
"""

from __future__ import annotations

import os
import sys
import json
import argparse

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from edge_detector import archive_layer as al  # noqa: E402

REQUIRED = {
    "benzinga": ("universe_members", "event_ledger", "forward_returns"),
    "uvol": ("universe_members", "event_ledger_uvol", "forward_returns_uvol"),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    # --root is Todd's alias for --archive-root; either may be omitted when
    # BMCMC_DATA_ROOT is set. Resolution matches the builder.
    ap.add_argument("--archive-root", "--root", dest="archive_root", default=None)
    # --universe is accepted for CLI compatibility (snapshot id); the archive
    # root already locates the datasets, so it is informational here.
    ap.add_argument("--universe", default="bmcmc_v1")
    ap.add_argument("--family", choices=al.VALID_FAMILIES, default="benzinga")
    args = ap.parse_args()

    args.archive_root = args.archive_root or os.environ.get("BMCMC_DATA_ROOT")
    if not args.archive_root:
        ap.error("archive root required: pass --archive-root/--root or set BMCMC_DATA_ROOT")

    spec = al.FAMILY_DATASETS[args.family]
    key = list(spec["event_key"])
    required = REQUIRED[args.family]

    checks: dict = {}
    all_ok = True

    # presence + hash for every required dataset
    for name in required:
        present = al.dataset_exists(args.archive_root, name)
        hash_ok = al.verify_hash(args.archive_root, name) if present else False
        checks[name] = {"present": present, "hash_ok": hash_ok}
        all_ok = all_ok and present and hash_ok

    key_alignment = None
    if all([checks[n]["present"] for n in required]):
        ledger = al.read_dataset(args.archive_root, spec["ledger"])
        fwd = al.read_dataset(args.archive_root, spec["forward_returns"])
        lk = set(map(tuple, ledger[key].astype(str).values.tolist()))
        fk = set(map(tuple, fwd[key].astype(str).values.tolist()))
        only_ledger = len(lk - fk)
        only_fwd = len(fk - lk)
        aligned = (only_ledger == 0 and only_fwd == 0 and len(lk) == len(fk))
        key_alignment = {
            "ledger_keys": len(lk),
            "forward_keys": len(fk),
            "only_in_ledger": only_ledger,
            "only_in_forward": only_fwd,
            "aligned": aligned,
        }
        all_ok = all_ok and aligned
    else:
        all_ok = False

    summary = {
        "result": "PASS" if all_ok else "FAIL",
        "family": args.family,
        "universe": args.universe,
        "event_key": key,
        "datasets": checks,
        "key_alignment": key_alignment,
    }

    print("FAMILY: %s" % args.family)
    for name in required:
        c = checks[name]
        print("dataset=%s present=%s hash_ok=%s" % (name, c["present"], c["hash_ok"]))
    if key_alignment is not None:
        print("key_alignment aligned=%s ledger=%d forward=%d only_ledger=%d only_forward=%d" % (
            key_alignment["aligned"], key_alignment["ledger_keys"],
            key_alignment["forward_keys"], key_alignment["only_in_ledger"],
            key_alignment["only_in_forward"]))
    print("RESULT: %s" % summary["result"])
    print("SUMMARY_JSON: " + json.dumps(summary, sort_keys=True))
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
