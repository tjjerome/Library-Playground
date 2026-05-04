#!/usr/bin/env python3
"""LLM backfills against the existing catalog (no CSV diff).

One-off maintenance passes that walk Library_Catalog.json, fill or
correct fields on entries that already exist, save the catalog.
Distinct from `catalogue.py`, which is the CSV-driven incremental
build flow.

Usage:
    python backfill.py --entry-points              # series_role + author_entry_point
    python backfill.py --entry-points --dry-run    # phase-1 derivation only, no LLM

Phase 1 of the entry-points backfill is deterministic (auto-derives
trivial cases from series_status / series_position).  Phase 2 is the
LLM pass for ambiguous cases (loose-connected, cross-author judgement).
"""

from __future__ import annotations

import argparse
import sys

import catalogue as _c


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--catalog", default=_c.CATALOG_FILE)
    p.add_argument("--index", default=_c.INDEX_FILE)
    p.add_argument("--chunk-size", type=int, default=_c.DEFAULT_CHUNK_SIZE)
    p.add_argument("--dry-run", action="store_true",
                   help="Phase 1 only; skip LLM pass and don't write the catalog.")
    p.add_argument("--entry-points", action="store_true",
                   help="Backfill series_role + author_entry_point.")
    args = p.parse_args()

    if not args.entry_points:
        p.error("pick a backfill: --entry-points")

    catalog = _c.load_catalog(args.catalog)

    client = None
    if not args.dry_run:
        client = _c.authenticate_anthropic_client()

    stats = _c.audit_entry_points(
        catalog,
        client=client,
        chunk_size=args.chunk_size,
        dry_run=args.dry_run,
        catalog_path=None if args.dry_run else args.catalog,
        index_path=None if args.dry_run else args.index,
    )

    print(f"\nEntry-point backfill complete.")
    for k in ("auto_filled", "llm_chunks", "llm_filled", "still_null"):
        print(f"  {k:12s}: {stats[k]}")

    if args.dry_run:
        print("  --dry-run: catalog NOT written.")
    else:
        _c.save_catalog(catalog, args.catalog)
        _c.save_index(catalog, args.index)
        print(f"  Wrote → {args.catalog} (+ {args.index})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
