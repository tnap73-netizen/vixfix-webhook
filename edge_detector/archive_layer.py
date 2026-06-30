"""Curated parquet archive layer for the BMCMC edge detector.

Datasets live under an archive root split by ``kind``::

    <root>/curated/<dataset>/data.parquet
    <root>/curated/<dataset>/manifest.json
    <root>/raw/<dataset>/data.parquet
    <root>/raw/<dataset>/manifest.json

Each ``manifest.json`` carries the SHA-256 of the parquet bytes plus row and
column metadata so downstream probes can verify integrity (``hash_ok``).

Event families
--------------
UVOL (unusual volume) is a *separate* event family from the Benzinga
catalyst ledger (see ``BMCMC_UVOL_SEPARATE_EVENT_FAMILY.md``). It shares the
universe, prices, factor matrix and costs, but has its own event keyspace,
ledger and forward-return tables. ``load_for_backtest(family=...)`` selects
the matching ledger/forward-return pair. The default family is ``benzinga``
so existing call sites keep their behavior unchanged.
"""

from __future__ import annotations

import os
import json
import hashlib
import datetime as _dt
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Dataset registry
# ---------------------------------------------------------------------------

# Curated (derived, PIT-gated) datasets written with manifests + SHA-256.
CURATED_DATASETS = (
    "universe_members",
    "event_ledger",
    "forward_returns",
    "factor_matrix",
    "costs",
    "event_ledger_uvol",
    "forward_returns_uvol",
)

# Raw, ingested-as-is datasets.
RAW_DATASETS = ("prices",)

# Columns that must be parsed/serialized as dates per dataset.
_DATE_COLS: dict[str, tuple[str, ...]] = {
    "event_ledger": ("event_ts",),
    "forward_returns": ("event_ts",),
    "event_ledger_uvol": ("event_ts",),
    "forward_returns_uvol": ("event_ts",),
    "prices": ("date",),
}

# Family -> (ledger dataset, forward-return dataset, event key, primary horizon)
FAMILY_DATASETS: dict[str, dict[str, Any]] = {
    "benzinga": {
        "ledger": "event_ledger",
        "forward_returns": "forward_returns",
        "event_key": ("ticker", "earnings_event"),
        "primary_horizon": "t5",
    },
    "uvol": {
        "ledger": "event_ledger_uvol",
        "forward_returns": "forward_returns_uvol",
        "event_key": ("ticker", "uvol_event"),
        "primary_horizon": "t20",
    },
}

VALID_FAMILIES = tuple(FAMILY_DATASETS.keys())

# Non-PIT membership placeholder. v0 universe is survivorship-biased
# (current SPY/QQQ survivors); it must not be promoted to PIT membership.
DERIVED_NON_PIT_PLACEHOLDER = "DERIVED_NON_PIT_PLACEHOLDER"


def _kind_dir(name: str) -> str:
    return "raw" if name in RAW_DATASETS else "curated"


def _dataset_dir(archive_root: str, name: str, kind: str | None = None) -> str:
    kind = kind or _kind_dir(name)
    return os.path.join(archive_root, kind, name)


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ---------------------------------------------------------------------------
# Write / read
# ---------------------------------------------------------------------------

def write_dataset(archive_root: str, name: str, df: pd.DataFrame,
                  kind: str | None = None, extra_meta: dict | None = None) -> dict:
    """Write ``df`` as parquet plus a manifest with SHA-256.

    Returns the manifest dict.
    """
    kind = kind or _kind_dir(name)
    out_dir = _dataset_dir(archive_root, name, kind)
    os.makedirs(out_dir, exist_ok=True)
    data_path = os.path.join(out_dir, "data.parquet")
    df.to_parquet(data_path, index=False)

    sha = _sha256_file(data_path)
    manifest = {
        "name": name,
        "kind": kind,
        "rows": int(len(df)),
        "columns": list(df.columns),
        "sha256": sha,
        "written_at": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
    }
    if extra_meta:
        manifest.update(extra_meta)
    with open(os.path.join(out_dir, "manifest.json"), "w") as f:
        json.dump(manifest, f, indent=2, sort_keys=True)
    return manifest


def read_manifest(archive_root: str, name: str, kind: str | None = None) -> dict:
    path = os.path.join(_dataset_dir(archive_root, name, kind), "manifest.json")
    with open(path) as f:
        return json.load(f)


def dataset_exists(archive_root: str, name: str, kind: str | None = None) -> bool:
    d = _dataset_dir(archive_root, name, kind)
    return os.path.exists(os.path.join(d, "data.parquet")) and \
        os.path.exists(os.path.join(d, "manifest.json"))


def read_dataset(archive_root: str, name: str, kind: str | None = None) -> pd.DataFrame:
    kind = kind or _kind_dir(name)
    data_path = os.path.join(_dataset_dir(archive_root, name, kind), "data.parquet")
    df = pd.read_parquet(data_path)
    for col in _DATE_COLS.get(name, ()):  # normalize date columns
        if col in df.columns:
            df[col] = pd.to_datetime(df[col])
    return df


def verify_hash(archive_root: str, name: str, kind: str | None = None) -> bool:
    """Return True iff the parquet bytes match the manifest SHA-256."""
    kind = kind or _kind_dir(name)
    out_dir = _dataset_dir(archive_root, name, kind)
    data_path = os.path.join(out_dir, "data.parquet")
    try:
        manifest = read_manifest(archive_root, name, kind)
    except FileNotFoundError:
        return False
    if not os.path.exists(data_path):
        return False
    return _sha256_file(data_path) == manifest.get("sha256")


# ---------------------------------------------------------------------------
# Backtest loader
# ---------------------------------------------------------------------------

@dataclass
class LoadedArchive:
    family: str
    archive_root: str
    members: pd.DataFrame
    ledger: pd.DataFrame
    forward_returns: pd.DataFrame
    event_key: tuple[str, ...]
    primary_horizon: str
    membership_is_point_in_time: bool = False
    meta: dict = field(default_factory=dict)


def load_for_backtest(archive_root: str, family: str = "benzinga") -> LoadedArchive:
    """Load universe members plus the ledger/forward-return pair for ``family``.

    ``family`` defaults to ``benzinga`` so existing callers are unaffected.
    ``family="uvol"`` loads the UVOL ledger and UVOL forward returns.
    """
    if family not in FAMILY_DATASETS:
        raise ValueError("unknown family %r; expected one of %s" % (family, VALID_FAMILIES))

    spec = FAMILY_DATASETS[family]
    members = read_dataset(archive_root, "universe_members")
    ledger = read_dataset(archive_root, spec["ledger"])
    fwd = read_dataset(archive_root, spec["forward_returns"])

    membership_pit = bool(
        read_manifest(archive_root, "universe_members").get("membership_is_point_in_time", False)
    )

    return LoadedArchive(
        family=family,
        archive_root=archive_root,
        members=members,
        ledger=ledger,
        forward_returns=fwd,
        event_key=tuple(spec["event_key"]),
        primary_horizon=spec["primary_horizon"],
        membership_is_point_in_time=membership_pit,
        meta={"ledger_dataset": spec["ledger"], "forward_dataset": spec["forward_returns"]},
    )
