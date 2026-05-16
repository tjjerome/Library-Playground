#!/usr/bin/env python3
"""Smoke test for `librarian_query.py unfinished-series`.

Asserts:
  - command runs against live catalog without error
  - returns a JSON list
  - each entry carries the required keys: series, author,
    last_book_read, last_position, last_rating,
    max_rating_in_series, avg_rating_in_series,
    next_book_in_catalog, next_position, next_pages, next_key
  - sort order: max_rating descending
  - all returned entries have max_rating ≥ --min-rating

Run via:
    python3 tests/unfinished_series_smoke.py
"""

from __future__ import annotations

import argparse
import io
import json
import sys
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from webhelper import librarian_query as lq  # noqa: E402


REQUIRED_KEYS = {
    "series", "author", "last_book_read", "last_position",
    "last_rating", "max_rating_in_series", "avg_rating_in_series",
    "next_book_in_catalog", "next_position", "next_pages", "next_key",
}


def _capture(args_ns) -> list:
    buf = io.StringIO()
    saved = sys.stdout
    sys.stdout = buf
    try:
        conn = lq.open_catalog(args_ns.catalog)
        try:
            lq.cmd_unfinished_series(args_ns, conn)
        finally:
            conn.close()
    finally:
        sys.stdout = saved
    return json.loads(buf.getvalue())


def run(catalog: str, log: str) -> int:
    failures: list[str] = []
    args = SimpleNamespace(
        catalog=catalog, log=log,
        reading_list="/dev/null",
        min_rating=4.0, min_avg=3.5, min_last=3.0,
    )
    out = _capture(args)
    if not isinstance(out, list):
        failures.append(f"output is not a list: {type(out).__name__}")
        print("FAIL"); [print(" ", f) for f in failures]; return 1

    for i, entry in enumerate(out):
        missing = REQUIRED_KEYS - set(entry)
        if missing:
            failures.append(f"entry[{i}] missing keys: {missing}")
        if entry.get("max_rating_in_series") is not None:
            if entry["max_rating_in_series"] < args.min_rating:
                failures.append(
                    f"entry[{i}] max_rating "
                    f"{entry['max_rating_in_series']} < min_rating "
                    f"{args.min_rating}")

    # Sort order check.
    ratings = [e["max_rating_in_series"] for e in out
               if e.get("max_rating_in_series") is not None]
    if ratings != sorted(ratings, reverse=True):
        failures.append("not sorted by max_rating_in_series desc")

    if failures:
        print("FAIL")
        for f in failures:
            print(" ", f)
        return 1
    print("OK")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", default=str(REPO / "Library_Catalog.sqlite"))
    p.add_argument("--log", default=str(REPO / "Reading_Log.csv"))
    args = p.parse_args()
    if not Path(args.catalog).exists():
        print(f"FAIL: catalog not found: {args.catalog}")
        return 2
    if not Path(args.log).exists():
        print(f"FAIL: log not found: {args.log}")
        return 2
    return run(args.catalog, args.log)


if __name__ == "__main__":
    sys.exit(main())
