#!/usr/bin/env python3
"""Catalog-side audits — deterministic review queues over Library_Catalog.sqlite.

Two read-only audits, both write markdown review queues into docs/.  No
LLM, no catalog mutations.  Implements RECOMPOSITION_PLAN §6.5 and §6.7.

Usage:
    python audit_catalog.py --entry-points
    python audit_catalog.py --comparables
    python audit_catalog.py --all
    python audit_catalog.py --all --sqlite Library_Catalog.sqlite

Regenerate the SQLite catalog first via `python catalogue.py` if the
catalog has changed since the last export.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from audits import (
    write_comparables_review_queue,
    write_entry_points_review_queue,
)


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--sqlite", default="Library_Catalog.sqlite",
                   help="SQLite catalog to read (default: Library_Catalog.sqlite)")
    p.add_argument("--entry-points", action="store_true",
                   help="Write docs/audit_entry_points.md (RECOMPOSITION_PLAN §6.5).")
    p.add_argument("--comparables", action="store_true",
                   help="Write docs/audit_comparables.md (RECOMPOSITION_PLAN §6.7).")
    p.add_argument("--all", action="store_true", help="Run both audits.")
    args = p.parse_args()

    if not (args.entry_points or args.comparables or args.all):
        p.error("pick at least one: --entry-points / --comparables / --all")

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        print(f"  ! {sqlite_path} not found; run `python catalogue.py` to regenerate.")
        return 2

    if args.entry_points or args.all:
        out = Path("docs/audit_entry_points.md")
        report = write_entry_points_review_queue(sqlite_path, out)
        n = (len(report["misaligned"])
             + len(report["pub_year_regression"])
             + len(report["zero_entry_point"]))
        print(f"  Wrote {out} ({n} flags: "
              f"{len(report['misaligned'])} misaligned, "
              f"{len(report['pub_year_regression'])} pub_year regression, "
              f"{len(report['zero_entry_point'])} zero entry point).")

    if args.comparables or args.all:
        out = Path("docs/audit_comparables.md")
        queue = write_comparables_review_queue(sqlite_path, out)
        drops = sum(1 for q in queue if q["suggested_action"] == "drop")
        reviews = sum(1 for q in queue if q["suggested_action"] == "review")
        print(f"  Wrote {out} ({len(queue)} flags: "
              f"{drops} drop-suggested, {reviews} review-suggested).")

    return 0


if __name__ == "__main__":
    sys.exit(main())
