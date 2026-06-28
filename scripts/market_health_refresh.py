#!/usr/bin/env python3
"""Railway/native-cron entrypoint for BMCMC market health refresh."""

from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from edgar_speed_feeds.scrapers.market_health import main  # noqa: E402


if __name__ == "__main__":
    raise SystemExit(main())
