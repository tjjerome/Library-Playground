#!/usr/bin/env python3
"""Sanity checks for the taste-vector tables exported by
`webhelper/sqlite_export` (RECOMPOSITION_PLAN §6.4).

Verifies:

  1. The `CANONICAL_TASTE_VECTORS` vocabulary references only IDs that
     exist in `CANONICAL_TASTE_SIGNALS` / `CANONICAL_THEMES`.
  2. Every defined vector is exported into the `taste_vectors` table
     with its full membership in `taste_vector_members`.
  3. The per-book derivation in `book_taste_vectors` matches what
     `book_taste_vector_matches()` produces directly from the JSON.
  4. Tagging is sparse — most books exemplify 2-4 vectors, in line
     with the design target.

Run via:
    python3 tests/taste_vectors_export.py
    python3 tests/taste_vectors_export.py --catalog Library_Catalog.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from catalogue_vocab import (  # noqa: E402
    CANONICAL_TASTE_SIGNALS,
    CANONICAL_TASTE_VECTORS,
    CANONICAL_THEMES,
    book_taste_vector_matches,
    validate_vectors,
)
from webhelper.sqlite_export import export  # noqa: E402


def _check_vocab() -> list[str]:
    errs = validate_vectors()
    if errs:
        return [f"vocab: {e}" for e in errs]
    return []


def _check_definitions(conn: sqlite3.Connection) -> list[str]:
    errs: list[str] = []
    rows = {r[0]: (r[1], r[2]) for r in conn.execute(
        "SELECT vector_id, label, description FROM taste_vectors")}
    if set(rows) != set(CANONICAL_TASTE_VECTORS):
        missing = set(CANONICAL_TASTE_VECTORS) - set(rows)
        extra = set(rows) - set(CANONICAL_TASTE_VECTORS)
        errs.append(
            f"taste_vectors id mismatch: missing={sorted(missing)!r}, "
            f"extra={sorted(extra)!r}"
        )

    members: dict[str, dict[str, set[str]]] = {}
    for vid, kind, mid in conn.execute(
        "SELECT vector_id, kind, member_id FROM taste_vector_members"
    ):
        members.setdefault(vid, {"signal": set(), "theme": set()})
        members[vid].setdefault(kind, set()).add(mid)

    for vid, vec in CANONICAL_TASTE_VECTORS.items():
        want_sigs = set(vec.get("signals") or [])
        want_themes = set(vec.get("themes") or [])
        got = members.get(vid, {"signal": set(), "theme": set()})
        if got.get("signal", set()) != want_sigs:
            errs.append(
                f"{vid}: signals mismatch — "
                f"want {sorted(want_sigs)!r}, got {sorted(got.get('signal') or [])!r}"
            )
        if got.get("theme", set()) != want_themes:
            errs.append(
                f"{vid}: themes mismatch — "
                f"want {sorted(want_themes)!r}, got {sorted(got.get('theme') or [])!r}"
            )
    return errs


def _check_per_book(conn: sqlite3.Connection, catalog: dict) -> list[str]:
    """Compare every book's exported tags against the in-Python derivation."""
    errs: list[str] = []
    sample_mismatches = 0
    book_tags: dict[str, set[tuple[str, int]]] = {}
    for r in conn.execute(
        "SELECT book_key, vector_id, overlap FROM book_taste_vectors"
    ):
        book_tags.setdefault(r[0], set()).add((r[1], r[2]))

    for key, entry in catalog["entries"].items():
        ts = entry.get("taste_signals") or {}
        positive = list((ts.get("positive") or [])) if isinstance(ts, dict) else []
        themes = list(entry.get("themes") or [])
        want = set(book_taste_vector_matches(positive, themes))
        got = book_tags.get(key, set())
        if want != got:
            sample_mismatches += 1
            if sample_mismatches <= 3:
                errs.append(
                    f"{key}: tag mismatch — want {sorted(want)!r}, got {sorted(got)!r}"
                )

    if sample_mismatches:
        errs.append(f"{sample_mismatches} books had mismatched vector tags")
    return errs


def _check_sparsity(conn: sqlite3.Connection) -> list[str]:
    """Soft-bound: average vector tags per book should land in [2, 5].

    A very low average means the threshold is too strict (the recommender
    won't get useful coverage signal); a very high average means tagging
    is too noisy and `status.vectors_underused` becomes meaningless.
    """
    errs: list[str] = []
    n = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
    if n == 0:
        return ["no books in catalog"]
    total = conn.execute("SELECT COUNT(*) FROM book_taste_vectors").fetchone()[0]
    avg = total / n
    if avg < 2.0 or avg > 5.0:
        errs.append(
            f"sparsity off-target: avg vectors/book = {avg:.2f} "
            f"(expected 2.0-5.0); tune TASTE_VECTOR_MIN_* or vector membership."
        )

    # No single vector should swallow >50% of the catalog (too generic).
    too_broad = conn.execute(
        "SELECT vector_id, COUNT(*) c FROM book_taste_vectors GROUP BY vector_id "
        "HAVING c > ? ORDER BY c DESC", (n // 2,)
    ).fetchall()
    if too_broad:
        bits = ", ".join(f"{vid}={c}" for vid, c in too_broad)
        errs.append(f"vector(s) match >50% of catalog ({n}): {bits}")
    return errs


def run(catalog_path: Path) -> int:
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    all_errs: list[str] = []
    all_errs += _check_vocab()

    with tempfile.TemporaryDirectory() as tmp:
        sqlite_path = Path(tmp) / "Library_Catalog.sqlite"
        export(catalog, sqlite_path)

        conn = sqlite3.connect(str(sqlite_path))
        try:
            all_errs += _check_definitions(conn)
            all_errs += _check_per_book(conn, catalog)
            all_errs += _check_sparsity(conn)
        finally:
            conn.close()

    if all_errs:
        print("FAIL:")
        for e in all_errs:
            print(f"  - {e}")
        return 1
    print(
        f"OK: {len(CANONICAL_TASTE_VECTORS)} vectors against "
        f"{len(CANONICAL_TASTE_SIGNALS)} signals + "
        f"{len(CANONICAL_THEMES)} themes; "
        f"{len(catalog['entries'])} books tagged."
    )
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", default="Library_Catalog.json")
    args = p.parse_args()
    return run(Path(args.catalog))


if __name__ == "__main__":
    sys.exit(main())
