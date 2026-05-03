#!/usr/bin/env python3
"""Normalise series_position subseries notations to a canonical form.

Subseries annotations inside the parenthetical of `series_position` come
in many forms in the live catalog:

    (City Watch #3)
    (City Watch Book 4)
    (Book 5 in City Watch subseries)
    (Death subseries Book 3)
    (Helen Trilogy, Book 2)

This script rewrites every recognised pattern to the canonical form:

    (<Subseries Name> Book <N>)

Annotations that are NOT navigable subseries (omnibus, prequel, novella,
chronological, etc.) are left untouched — see _SUBSERIES_SKIP_TOKENS in
`webhelper/librarian_query.py` for the skip list this script mirrors.

Reads `Library_Catalog.json` in place by default.  Pass --dry-run to
preview without writing.

After running, regenerate the SQLite + .encoded catalog:

    python3 catalogue.py --library Library.csv \\
        --export-sqlite Library_Catalog.sqlite --emit-encoded

then upload the new `.encoded` to your Drive folder.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# Mirror of webhelper/librarian_query.py — keep in sync.
_SKIP_TOKENS = (
    "overall", "publication order", "collects", "novella", "novelette",
    "omnibus", "anthology", "standalone", "prequel", "sequel",
    "companion", "short story", "finale", "chronological",
    "translated", "translation", "audio original", "ebook",
    "middle grade", "final adult", "spin-off", "side-story",
    "or standalone", "set after", "between", "late-career",
    "pre-series", "unpublished", "set in", "in english",
    "collection", "bridge novella", "plus anthology",
    "part of interconnected", "novellas", "phase 1", "phase ii",
    "rogue one prequel", "in publication order", "in chronological",
    "within universe", "short novel", "secret project",
    "or .",
)


def _format_num(n_str: str) -> str:
    """Render numeric position cleanly: drop trailing .0, keep .5 etc."""
    try:
        f = float(n_str)
        return str(int(f)) if f.is_integer() else str(f)
    except ValueError:
        return n_str


def normalise_inner(inner: str) -> str | None:
    """Return the canonical "<Name> Book N" form for `inner`, or None
    if the inner string is not a recognisable subseries pattern (skip
    tokens, or no number found)."""
    inner = inner.strip()
    if any(tok in inner.lower() for tok in _SKIP_TOKENS):
        return None

    # "Book N in <Name> [subseries]" — number first.
    mm = re.match(
        r"^Book\s+([\d.]+)\s+in\s+(.+?)(?:\s+subseries)?$",
        inner, flags=re.IGNORECASE,
    )
    if mm:
        return f"{mm.group(2).strip()} Book {_format_num(mm.group(1))}"

    # Name-first patterns.
    for pat in (
        r"^(.+?),\s+Book\s+([\d.]+)$",
        r"^(.+?)\s+(?:[Ss]ubseries|[Ss]eries)\s+Book\s+([\d.]+)$",
        r"^(.+?)\s+(?:[Ss]ubseries|[Ss]eries)\s+#([\d.]+)$",
        r"^(.+?)\s+Book\s+([\d.]+)$",
        r"^(.+?)\s+#([\d.]+)$",
    ):
        mm = re.match(pat, inner, flags=re.IGNORECASE)
        if mm:
            return f"{mm.group(1).strip()} Book {_format_num(mm.group(2))}"
    return None


def normalise_series_position(sp: str | None) -> str | None:
    """Rewrite the parenthetical of `sp` to canonical form when
    recognised.  Returns the new string, or None when no change."""
    if not sp:
        return None
    m = re.search(r"\(([^)]+)\)", sp)
    if not m:
        return None
    inner = m.group(1)
    canonical_inner = normalise_inner(inner)
    if canonical_inner is None or canonical_inner == inner.strip():
        return None
    return sp[: m.start(1)] + canonical_inner + sp[m.end(1):]


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog", default="Library_Catalog.json",
                   help="Path to Library_Catalog.json")
    p.add_argument("--dry-run", action="store_true",
                   help="Print proposed changes without writing")
    args = p.parse_args()

    path = Path(args.catalog)
    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 1

    with path.open(encoding="utf-8") as f:
        catalog = json.load(f)

    changes: list[tuple[str, str, str]] = []
    for key, entry in catalog["entries"].items():
        old = entry.get("series_position")
        new = normalise_series_position(old)
        if new and new != old:
            changes.append((key, old, new))
            if not args.dry_run:
                entry["series_position"] = new

    if not changes:
        print("No changes — series_position values already canonical.")
        return 0

    print(f"{'Would update' if args.dry_run else 'Updated'} {len(changes)} entries:")
    for key, old, new in changes:
        print(f"  {key}")
        print(f"    - {old}")
        print(f"    + {new}")

    if args.dry_run:
        return 0

    with path.open("w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)
    print(f"\nWrote {path}.  Re-export SQLite + encoded:")
    print("  python3 catalogue.py --library Library.csv "
          "--export-sqlite Library_Catalog.sqlite --emit-encoded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
