#!/usr/bin/env python3
"""Round-trip parity test for `webhelper/sqlite_export`.

Reads `Library_Catalog.json` (or the file passed in `--catalog`),
exports it to a temporary SQLite file, then reconstructs each entry
from SQLite and compares structurally to the original.

Run via:
    python3 tests/sqlite_roundtrip.py
    python3 tests/sqlite_roundtrip.py --catalog Library_Catalog.json --verbose
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webhelper.sqlite_export import (  # noqa: E402
    export,
    reconstruct_entry,
    load_meta,
)


# JSON fields that the new schema doesn't round-trip — drop on both
# sides before comparing. `taste_signals_canonical` and `themes_canonical`
# were the legacy paired-list shape; the closed-vocab schema folds those
# IDs into `taste_signals` and `themes` directly, so the export does not
# reconstruct them.
IGNORE_FIELDS: set[str] = {"taste_signals_canonical", "themes_canonical"}


_LIST_FIELDS = ("comparable_books", "content_flags", "themes")
_OPTIONAL_LIST_FIELDS = ("related_series",)


def _normalise_for_compare(entry: dict) -> dict:
    """Normalise both original and reconstructed entries to a shape where
    they should compare equal if the SQLite export preserved every
    meaningful field.

    - Drop None values; absent-vs-None treated as equal.
    - Drop `IGNORE_FIELDS` (legacy paired-list canonical fields).
    - Default `taste_signals` and the list-fields to empty values on both
      sides (catalogues vary between key-absent and empty).
    - Optional fields (related_series) round-trip only when populated.
    """
    out = {}
    for k, v in entry.items():
        if k in IGNORE_FIELDS:
            continue
        if v is None:
            continue
        if k == "taste_signals" and isinstance(v, dict):
            out[k] = {
                "positive": list(v.get("positive") or []),
                "negative": list(v.get("negative") or []),
            }
            continue
        if k in _LIST_FIELDS:
            out[k] = list(v or [])
            continue
        if k in _OPTIONAL_LIST_FIELDS:
            lst = list(v or [])
            if lst:
                out[k] = lst
            continue
        out[k] = v

    if "taste_signals" not in out:
        out["taste_signals"] = {"positive": [], "negative": []}
    for k in _LIST_FIELDS:
        if k not in out:
            out[k] = []

    return out


def diff_entries(orig: dict, recon: dict) -> list[str]:
    """Return a list of human-readable diff lines; empty list = match."""
    a = _normalise_for_compare(orig)
    b = _normalise_for_compare(recon)
    diffs: list[str] = []
    keys = sorted(set(a) | set(b))
    for k in keys:
        if k not in a:
            diffs.append(f"  + only in reconstructed: {k} = {b[k]!r}")
        elif k not in b:
            diffs.append(f"  - only in original: {k} = {a[k]!r}")
        elif a[k] != b[k]:
            diffs.append(f"  ! differ at {k}:")
            diffs.append(f"      orig:  {a[k]!r}")
            diffs.append(f"      recon: {b[k]!r}")
    return diffs


def run(catalog_path: Path, verbose: bool = False) -> int:
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    with tempfile.TemporaryDirectory() as tmp:
        sqlite_path = Path(tmp) / "Library_Catalog.sqlite"
        export(catalog, sqlite_path)

        conn = sqlite3.connect(str(sqlite_path))
        try:
            meta = load_meta(conn)
            assert meta["catalog_version"] == catalog.get("catalog_version"), (
                f"catalog_version mismatch: meta={meta['catalog_version']}, "
                f"json={catalog.get('catalog_version')}"
            )
            assert meta["last_updated"] == str(catalog.get("last_updated") or ""), (
                "last_updated mismatch"
            )

            book_count = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
            json_count = len(catalog["entries"])
            assert book_count == json_count, (
                f"books count mismatch: sqlite={book_count}, json={json_count}"
            )

            mismatches = 0
            for key, orig in catalog["entries"].items():
                recon = reconstruct_entry(conn, key)
                diffs = diff_entries(orig, recon)
                if diffs:
                    mismatches += 1
                    if verbose or mismatches <= 5:
                        print(f"DIFF for {key}:")
                        for d in diffs:
                            print(d)
        finally:
            conn.close()

    if mismatches:
        print(f"\nFAIL: {mismatches}/{json_count} entries differ.")
        return 1
    print(f"OK: {json_count} entries round-trip cleanly.")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", default="Library_Catalog.json")
    p.add_argument("--verbose", action="store_true")
    args = p.parse_args()
    return run(Path(args.catalog), verbose=args.verbose)


if __name__ == "__main__":
    sys.exit(main())
