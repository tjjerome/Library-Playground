#!/usr/bin/env python3
"""Addendum B acceptance tests.

  - author-history resolves an initial-spacing-drifted author
  - norm() collapses initial-spacing / subtitle / leading-article
  - an author-format-drifted read is excluded from recommend
  - recommend --audit-exclusions surfaces a near-miss drift pair
  - a quoted comma inside a CSV field doesn't corrupt `authors`
  - normalize-catalog dry-run reports without writing; a real run
    persists and the re-run dry-run is clean

Run via:
    python3 tests/addendum_b.py
"""

from __future__ import annotations

import argparse
import io
import json
import shutil
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from webhelper import librarian_query as lq  # noqa: E402
from webhelper.sqlite_export import norm  # noqa: E402

BUILD_STATE = {
    "n_target": 100,
    "taste_vectors": [
        {"name": "grief-rooted horror", "weight": 1.0,
         "canonical_signals": ["unsettling-mood", "lyrical-prose",
                               "atmospheric-dread"],
         "themes": ["grief-and-loss", "isolation"]},
    ],
    "floors": {},
    "events": [],
}


def _capture(fn, args_ns, conn=None) -> str:
    buf = io.StringIO()
    saved = sys.stdout
    sys.stdout = buf
    try:
        fn(args_ns, conn)
    finally:
        sys.stdout = saved
    return buf.getvalue()


def run(catalog: str) -> int:  # noqa: C901
    failures: list[str] = []

    # ---- norm() unit cases ------------------------------------------
    norm_cases = [
        ("K.J. Parker", "K. J. Parker"),       # initial spacing
        ("KJ Parker", "K. J. Parker"),
        ("Prosper's Demon: A Novella", "Prosper's Demon"),  # subtitle
        ("The Hunter", "Hunter"),              # leading article
        ("Stang, Morgan", "Morgan Stang"),     # last,first drift
        ("Smith & Jones", "Smith and Jones"),  # ampersand
    ]
    for a, b in norm_cases:
        if norm(a) != norm(b):
            failures.append(
                f"norm: {a!r} ({norm(a)!r}) != {b!r} ({norm(b)!r})")

    # ---- author-history --------------------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        log = wd / "log.csv"
        log.write_text(
            'title,authors,My Rating,Last Date Read,my_tags\n'
            '"Prosper\'s Demon","K. J. Parker",4.25,2023/12/27,'
            '"sci-fi, owned, favorite"\n',
            encoding="utf-8")
        ah = SimpleNamespace(author="K.J. Parker", log=str(log),
                             catalog=catalog)
        out = json.loads(_capture(lq.cmd_author_history, ah))
        if out["read_count"] != 1 or not out["reads"]:
            failures.append(f"author-history: read_count {out['read_count']}")
        elif out["reads"][0]["title"] != "Prosper's Demon":
            failures.append(f"author-history: wrong title {out['reads'][0]}")
        if out["matched_author"] != "K. J. Parker":
            failures.append(
                f"author-history: matched_author {out['matched_author']!r}")
        if out["rated_4plus_count"] != 1:
            failures.append("author-history: rated_4plus_count != 1")

        # ---- CSV quoted-comma parse --------------------------------
        rows = lq.load_log(str(log))
        if rows[0]["authors"] != "K. J. Parker":
            failures.append(
                f"CSV: authors corrupted -> {rows[0]['authors']!r}")
        if rows[0]["my_tags"] != "sci-fi, owned, favorite":
            failures.append(f"CSV: my_tags -> {rows[0]['my_tags']!r}")

    # ---- pick a real catalog book for drift tests ------------------
    conn = lq.open_catalog(catalog)
    r = conn.execute(
        "SELECT key, title, author FROM books "
        "WHERE author LIKE '% %' AND title NOT LIKE '%:%' "
        "AND goodreads_rating >= 4.0 LIMIT 1").fetchone()
    book_key, book_title, book_author = r["key"], r["title"], r["author"]
    parts = book_author.split(" ")
    drift_author = f"{parts[-1]}, {' '.join(parts[:-1])}"  # Last, First
    conn.close()

    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        bs = wd / "bs.json"
        bs.write_text(json.dumps(BUILD_STATE), encoding="utf-8")

        # Exclusion gate: book logged with "Last, First" author drift
        # must not be recommended.
        log2 = wd / "log2.csv"
        log2.write_text(
            "title,authors,My Rating,Last Date Read\n"
            f'"{book_title}","{drift_author}",5,2024/01/01\n',
            encoding="utf-8")
        rec = SimpleNamespace(
            catalog=catalog, log=str(log2), profile=None,
            reading_list="/dev/null", build_state=str(bs), genre=None,
            n=15, lean=None, variance="balanced", seed=1,
            show_gr=False, show_audio=False, mode="discover",
            audit_exclusions=True)
        conn = lq.open_catalog(catalog)
        out = json.loads(_capture(lq.cmd_recommend, rec, conn))
        conn.close()
        if any(c["key"] == book_key for c in out["candidates"]):
            failures.append(
                f"exclusion: drifted read {book_key!r} still recommended")
        audit = out.get("exclusion_audit")
        if not audit:
            failures.append("recommend --audit-exclusions: no audit block")
        elif audit["log_entries_matched_to_catalog"] < 1:
            failures.append(
                "exclusion audit: drifted read not matched to catalog")

        # Near-miss: same title, author with a 1-char typo → should
        # land in near_miss_matches, not orphan.
        typo_author = book_author[:-1] if len(book_author) > 4 \
            else book_author + "x"
        log3 = wd / "log3.csv"
        log3.write_text(
            "title,authors,My Rating,Last Date Read\n"
            f'"{book_title}","{typo_author}",5,2024/01/01\n',
            encoding="utf-8")
        rec3 = SimpleNamespace(**{**vars(rec), "log": str(log3)})
        conn = lq.open_catalog(catalog)
        out3 = json.loads(_capture(lq.cmd_recommend, rec3, conn))
        conn.close()
        near = out3["exclusion_audit"]["near_miss_matches"]
        if not any(n["catalog_title"] == book_title for n in near):
            failures.append(
                f"near-miss: typo author not surfaced (near={near[:1]})")

    # ---- normalize-catalog dry / real / re-dry ----------------------
    with tempfile.TemporaryDirectory() as tmp:
        nc = Path(tmp) / "nc.sqlite"
        shutil.copy(catalog, nc)
        # The shipped catalog may already be normalized at rest, so
        # inject guaranteed drift: clobber one row's normalized
        # columns and put its author in `Last, First` form.
        seed = sqlite3.connect(nc)
        k = seed.execute(
            "SELECT key FROM books WHERE author LIKE '% %' LIMIT 1"
        ).fetchone()[0]
        seed.execute(
            "UPDATE books SET title_normalized='zzz drift', "
            "author_normalized='zzz drift', author='Drifted, Author' "
            "WHERE key=?", (k,))
        seed.commit()
        seed.close()

        a_dry = SimpleNamespace(catalog=str(nc), dry_run=True,
                                emit_encoded=False)
        conn = lq.open_catalog(str(nc))
        d1 = json.loads(_capture(lq.cmd_normalize_catalog, a_dry, conn))
        conn.close()
        if d1["written"] or d1["rows_to_update"] <= 0:
            failures.append(
                f"normalize dry-run: written={d1['written']} "
                f"to_update={d1['rows_to_update']}")
        if not d1["author_format_changes"]:
            failures.append("normalize dry-run: no author_format_changes")

        a_real = SimpleNamespace(catalog=str(nc), dry_run=False,
                                 emit_encoded=False)
        conn = lq.open_catalog(str(nc))
        d2 = json.loads(_capture(lq.cmd_normalize_catalog, a_real, conn))
        conn.close()
        if not d2["written"]:
            failures.append("normalize real run: written=False")

        conn = lq.open_catalog(str(nc))
        d3 = json.loads(_capture(lq.cmd_normalize_catalog, a_dry, conn))
        conn.close()
        if d3["rows_to_update"] != 0:
            failures.append(
                f"normalize re-dry-run not clean: "
                f"{d3['rows_to_update']} still pending")

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
    args = p.parse_args()
    if not Path(args.catalog).exists():
        print(f"FAIL: catalog not found: {args.catalog}")
        return 2
    return run(args.catalog)


if __name__ == "__main__":
    sys.exit(main())
