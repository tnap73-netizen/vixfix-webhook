#!/usr/bin/env python3
"""Validate BMCMC subscription runtime wiring without printing secrets."""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass


@dataclass(frozen=True)
class Check:
    name: str
    env_var: str
    required_for_strict: bool
    note: str


CHECKS = [
    Check("Massive API", "MASSIVE_API_KEY", True, "Sole required trading-feed secret for strict ESS. Unified key for Massive/Benzinga (earnings, guidance, ratings) via api.massive.com."),
    Check("Benzinga API", "BENZINGA_API_KEY", False, "Legacy/informational only. NOT required: Benzinga access is covered by the unified MASSIVE_API_KEY. Optional fallback for old standalone-key paths."),
    Check("Schwab client id", "SCHWAB_CLIENT_ID", False, "Required for Schwab reporting routes on the web service."),
    Check("Schwab client secret", "SCHWAB_CLIENT_SECRET", False, "Required for Schwab OAuth refresh/re-auth."),
    Check("BMCMC EDGAR root", "BMCMC_EDGAR_ROOT", False, "Required for Railway volume-backed market-health output when not using repo-local paths."),
]


def masked_present(value: str | None) -> str:
    if value is None or value == "":
        return "missing"
    return "present"


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate BMCMC subscription environment without exposing secrets.")
    parser.add_argument("--strict", action="store_true", help="Fail if full ESS / Railway trading feed keys are missing.")
    args = parser.parse_args()

    failures: list[str] = []
    print("BMCMC subscription environment check")
    for check in CHECKS:
        value = os.environ.get(check.env_var)
        status = masked_present(value)
        required = "required" if check.required_for_strict else "optional"
        print(f"{check.env_var}: {status} ({required}) - {check.note}")
        if args.strict and check.required_for_strict and status != "present":
            failures.append(check.env_var)

    if failures:
        print("STRICT_FAIL missing=" + ",".join(failures))
        return 1

    print("STRICT_PASS" if args.strict else "REGISTRY_CHECK_COMPLETE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
