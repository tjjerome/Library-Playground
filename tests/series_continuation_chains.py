#!/usr/bin/env python3
"""Walk every consolidated series chain and assert continuation
succeeds with an empty reading log.

Imports VALIDATION_CHAINS from `webhelper/consolidate_series_tags.py`
and reuses the helper's `validate_chains` runner so the test stays
authoritative as the consolidation table evolves.

Run via:
    python3 tests/series_continuation_chains.py
    python3 tests/series_continuation_chains.py --sqlite Library_Catalog.sqlite
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webhelper.consolidate_series_tags import (  # noqa: E402
    VALIDATION_CHAINS,
    validate_chains,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--sqlite", default="Library_Catalog.sqlite",
                   help="Path to the SQLite catalog to validate against")
    args = p.parse_args()

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        print(f"FAIL: {sqlite_path} not found.  Re-export with:")
        print("  python3 catalogue.py --library Library.csv "
              "--export-sqlite Library_Catalog.sqlite --emit-encoded")
        return 1

    total = len(VALIDATION_CHAINS)
    print(f"Walking {total} consolidated chains against {sqlite_path}…")
    passes, failures = validate_chains(sqlite_path)
    if failures:
        print(f"FAIL: {passes}/{total} pass; {len(failures)} fail:")
        for msg in failures:
            print(msg)
        return 1
    print(f"OK: {passes}/{total} chains continue cleanly.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
