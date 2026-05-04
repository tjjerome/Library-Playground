#!/usr/bin/env python3
"""Canonicalise free-form taste_signals / themes to closed-vocab IDs.

LLM-driven mapping pass.  Walks the catalog, collects distinct free-form
phrases, asks Claude to map each to a `catalogue_vocab` canonical ID,
applies the mapping in-place, saves the catalog.  Idempotent.

Usage:
    python canonicalize.py --signals
    python canonicalize.py --themes
    python canonicalize.py --signals --themes
"""

from __future__ import annotations

import argparse
import sys

import catalogue as _c


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--catalog", default=_c.CATALOG_FILE)
    p.add_argument("--index", default=_c.INDEX_FILE)
    p.add_argument("--signals", action="store_true",
                   help="Canonicalise taste_signals.")
    p.add_argument("--themes", action="store_true",
                   help="Canonicalise themes.")
    args = p.parse_args()

    if not (args.signals or args.themes):
        p.error("pick at least one: --signals / --themes")

    catalog = _c.load_catalog(args.catalog)
    client = _c.authenticate_anthropic_client()

    if args.signals:
        print("\nCanonicalising taste_signals…")
        stats = _c.canonicalize_signals(catalog, client)
        for k in ("distinct_phrases", "phrases_mapped", "phrases_unmapped", "entries_changed"):
            print(f"  {k:18s}: {stats[k]}")
        _c.save_catalog(catalog, args.catalog)
        _c.save_index(catalog, args.index)

    if args.themes:
        print("\nCanonicalising themes…")
        stats = _c.canonicalize_themes(catalog, client)
        for k in ("distinct_phrases", "phrases_mapped", "phrases_unmapped", "entries_changed"):
            print(f"  {k:18s}: {stats[k]}")
        _c.save_catalog(catalog, args.catalog)
        _c.save_index(catalog, args.index)

    print(f"\n  Wrote → {args.catalog} (+ {args.index})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
