#!/usr/bin/env python3
"""Library.csv-side audits — propose corrections to Library_new.csv.

LLM-driven audits that walk Library.csv and propose updates to genre,
series_type, pub_year, or indie flags.  Output goes to Library_new.csv
(never Library.csv directly) so the maintainer can diff before
overwriting.

Usage:
    python audit_library.py --series-type
    python audit_library.py --genres                 # report only
    python audit_library.py --genres --apply
    python audit_library.py --pub-years --apply
    python audit_library.py --indie-flags --apply

All audits read Library.csv by default.  --apply commits the proposed
changes to Library_new.csv; without it, only a diff report is printed.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import catalogue as _c


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--library", default="Library.csv",
                   help="Input CSV (default: Library.csv)")
    p.add_argument("--library-out", default=_c.LIBRARY_NEW_PATH,
                   help=f"Output CSV (default: {_c.LIBRARY_NEW_PATH})")
    p.add_argument("--catalog", default=_c.CATALOG_FILE,
                   help="JSON catalog (used by pub-years / indie-flags)")
    p.add_argument("--index", default=_c.INDEX_FILE)
    p.add_argument("--chunk-size", type=int, default=0,
                   help="Override default chunk size (0 = audit-specific default)")
    p.add_argument("--apply", dest="apply_changes", action="store_true",
                   help="Write proposed changes to --library-out (default: dry-run report only)")

    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--series-type", action="store_true",
                   help="Re-audit Library.csv #series_type via the page-count rule (deterministic).")
    g.add_argument("--genres", action="store_true",
                   help="LLM proposes a primary genre per row.")
    g.add_argument("--pub-years", action="store_true",
                   help="LLM verifies first-publication year per catalog entry.")
    g.add_argument("--indie-flags", action="store_true",
                   help=f"LLM promotes verified self-pub origins to indie=True for entries with "
                        f"<={_c.INDIE_REVIEW_THRESHOLD} reviews.")

    args = p.parse_args()

    if args.series_type:
        stats = _c.audit_library_series_type(Path(args.library), Path(args.library_out))
        print(f"\nLibrary series-type audit complete.")
        print(f"  rows total    : {stats['rows_total']}")
        print(f"  rows changed  : {stats['rows_changed']}")
        print(f"  series flipped: {stats['series_changed']}")
        return 0

    if args.genres:
        client = _c.authenticate_anthropic_client()
        stats = _c.audit_library_genres(
            Path(args.library), Path(args.library_out), client,
            chunk_size=args.chunk_size or _c.DEFAULT_CHUNK_SIZE,
            apply_changes=args.apply_changes,
        )
        print(f"\nLibrary genre audit complete.")
        for k in ("rows_audited", "responses_received", "proposed_changes", "applied"):
            print(f"  {k:18s}: {stats[k]}")
        if not args.apply_changes and stats["proposed_changes"]:
            print(f"  (review report; rerun with --apply to write {args.library_out}.)")
        return 0

    catalog = _c.load_catalog(args.catalog)

    if args.pub_years:
        # Refresh CSV-authoritative fields before LLM pass — keeps the
        # prompt anchored on current CSV.
        books = _c.load_library(args.library)
        _c.sync_library_to_catalog(books, catalog)
        client = _c.authenticate_anthropic_client()
        stats = _c.audit_pub_years(
            catalog, Path(args.library), Path(args.library_out), client,
            chunk_size=args.chunk_size or _c.PUB_YEAR_CHUNK_SIZE,
            apply_changes=args.apply_changes,
        )
        print(f"\npub_year audit complete.")
        for k in ("entries_audited", "responses_received", "proposed_changes",
                  "applied", "library_new_csv_changes"):
            print(f"  {k:24s}: {stats[k]}")
        if args.apply_changes:
            _c.save_catalog(catalog, args.catalog)
            _c.save_index(catalog, args.index)
            print(f"  Wrote → {args.catalog} (+ {args.index})")
        return 0

    if args.indie_flags:
        books = _c.load_library(args.library)
        _c.sync_library_to_catalog(books, catalog)
        client = _c.authenticate_anthropic_client()
        stats = _c.audit_indie_flags(
            catalog, client,
            chunk_size=args.chunk_size or _c.INDIE_AUDIT_CHUNK_SIZE,
            apply_changes=args.apply_changes,
        )
        print(f"\nindie backfill audit complete.")
        for k in ("candidates", "responses_received", "proposed_promotions", "applied"):
            print(f"  {k:22s}: {stats[k]}")
        if args.apply_changes:
            _c.save_catalog(catalog, args.catalog)
            _c.save_index(catalog, args.index)
            print(f"  Wrote → {args.catalog} (+ {args.index})")
        return 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
