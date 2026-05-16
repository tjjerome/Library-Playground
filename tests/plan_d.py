#!/usr/bin/env python3
"""Plan D regression tests — reading-list resolution fixes.

Self-contained: builds a small synthetic in-memory catalog (no
dependency on the gitignored Library_Catalog.sqlite) and checks:

  D-1a  _author_matches tolerance (name order / co-author / multi-
        author) and the title-collision guard (same title, different
        author stays distinct).
  D-1c  _title_fold British/American spelling fold, narrow.
  D-1   resolve_list_picks resolves all six variant classes, deduped,
        and a same-title/different-author candidate resolves to the
        right row.
  D-1b  stage1_pool on-list exclusion uses the same tolerant matcher,
        so resolved-but-variant on-list books leave the pool while a
        same-title/different-author book stays.
  D-2   list_set parses only book tables (title+author header),
        ignoring Goals / Series-balance / Floors pipe tables.

Prints OK and exits 0 on success; prints failures and exits 1.
"""

import sqlite3
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from webhelper import librarian_query as lq  # noqa: E402
from webhelper import sqlite_export as se  # noqa: E402
from webhelper.sqlite_export import (  # noqa: E402
    norm, title_short, _author_matches, _title_fold)

# (title, author, key, reviews) — list/catalog variant pairs plus the
# title-collision guard (two distinct "Wrath" authors).
CATALOG = [
    ("The Three-Body Problem", "Liu Cixin", "ttbp", 900000),
    ("The Dark Forest", "Liu Cixin", "tdf", 200000),
    ("Death's End", "Liu Cixin", "de", 150000),
    ("Skunk Works", "Ben R. Rich & Leo Janos", "sw", 60000),
    ("Roadside Picnic", "Arkady Strugatsky & Boris Strugatsky", "rp", 80000),
    ("Valor", "John Gwynne", "valor", 40000),
    ("Wrath", "John Gwynne", "wrath_g", 30000),
    ("Wrath", "Alex Raizman", "wrath_r", 1500),
    ("Mistborn: The Final Empire", "Brandon Sanderson", "mb", 1200000),
]

# What the reader actually wrote on Reading_List.md.
LIST_ENTRIES = [
    ("The Three-Body Problem", "Cixin Liu"),
    ("The Dark Forest", "Cixin Liu"),
    ("Death's End", "Cixin Liu"),
    ("Skunk Works", "Ben R. Rich"),
    ("Roadside Picnic", "Arkady & Boris Strugatsky"),
    ("Valour", "John Gwynne"),
    ("Wrath", "John Gwynne"),
    ("Mistborn", "Brandon Sanderson"),
]

READING_LIST_MD = """\
# Reading list

## Goals

| goal | target | notes |
|---|---|---|
| fantasy | 35 | keep variety |
| indie | keep indie deliberately in rotation | |

### Series balance

| series | status | notes |
|---|---|---|
| balance | open | rotate openers |

### Floors

| floor | count | notes |
|---|---|---|
| indie | 12 | floor |
| classic | 8 | floor |

## The list

| Title | Author | Notes |
|---|---|---|
| The Three-Body Problem | Cixin Liu | sci-fi |
| The Dark Forest | Cixin Liu | |
| Death's End | Cixin Liu | |
| Skunk Works | Ben R. Rich | memoir |
| Roadside Picnic | Arkady & Boris Strugatsky | |
| *Valour* | John Gwynne | **epic** |
| Wrath | John Gwynne | |
| Mistborn | Brandon Sanderson | |

## Upcoming & recent releases

| Title | Author | Expected |
|---|---|---|
| The Imperator's Hand | Some Author | 2026 |
"""


def _build_catalog() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    for stmt in se.SCHEMA:
        conn.execute(stmt)
    for title, author, key, reviews in CATALOG:
        conn.execute(
            "INSERT INTO books (key, title, title_normalized, title_short, "
            "author, author_normalized, goodreads_rating, goodreads_reviews) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (key, title, norm(title), title_short(title),
             author, norm(author), 4.3, reviews))
    conn.commit()
    return conn


def main() -> int:
    failures: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            failures.append(msg)

    # D-1a — author tolerance.
    check(_author_matches(norm("Cixin Liu"), norm("Liu Cixin")),
          "name-order: Cixin Liu vs Liu Cixin")
    check(_author_matches(norm("Ben R. Rich"),
                          norm("Ben R. Rich & Leo Janos")),
          "co-author omission: Ben R. Rich subset")
    check(_author_matches(norm("Arkady & Boris Strugatsky"),
                          norm("Arkady Strugatsky & Boris Strugatsky")),
          "multi-author formatting: Strugatsky")
    check(not _author_matches(norm("Alex Raizman"), norm("John Gwynne")),
          "collision guard: Raizman must not match Gwynne")
    check(not _author_matches(norm("John Smith"), norm("Jane Smith")),
          "single-author shared surname must stay distinct")

    # D-1c — narrow spelling fold.
    check(_title_fold(norm("Valour")) == norm("Valor"),
          "fold: valour -> valor")
    check(_title_fold(norm("Colour of Magic"))
          == _title_fold(norm("Color of Magic")),
          "fold: colour == color")
    check(_title_fold(norm("Four")) == norm("Four"),
          "fold: 'four' unchanged (length guard)")
    check(_title_fold(norm("Recognise")) == norm("Recognize"),
          "fold: recognise -> recognize")

    conn = _build_catalog()

    # D-1 — resolution of every variant class, deduped.
    list_pairs = {(norm(t), norm(a)) for t, a in LIST_ENTRIES}
    picks = lq.resolve_list_picks(conn, list_pairs)
    keys = sorted(p["key"] for p in picks)
    for want in ("ttbp", "tdf", "de", "sw", "rp", "valor", "mb"):
        check(want in keys, f"resolve: expected catalog key {want!r} "
                            f"(got {keys})")
    # "Wrath" appears for John Gwynne on the list -> must resolve to the
    # Gwynne row, never the Raizman one.
    check("wrath_g" in keys and "wrath_r" not in keys,
          f"resolve: Wrath must bind to Gwynne not Raizman (got {keys})")
    check(len(keys) == len(set(keys)),
          f"resolve: results must be deduped by key (got {keys})")
    check(len(picks) <= len(LIST_ENTRIES),
          f"resolve: count must not balloon ({len(picks)} > "
          f"{len(LIST_ENTRIES)})")

    # D-1b — pool exclusion via the same tolerant matcher.
    on_list = lq._list_membership(list_pairs)
    check(on_list("The Three-Body Problem", "Liu Cixin"),
          "pool: variant on-list book must be excluded (Liu Cixin)")
    check(on_list("Skunk Works", "Ben R. Rich & Leo Janos"),
          "pool: co-authored on-list book must be excluded")
    check(on_list("Roadside Picnic",
                  "Arkady Strugatsky & Boris Strugatsky"),
          "pool: multi-author on-list book must be excluded")
    check(on_list("Valor", "John Gwynne"),
          "pool: spelling-variant on-list book must be excluded")
    check(on_list("Wrath", "John Gwynne"),
          "pool: Gwynne's Wrath is on the list -> excluded")
    check(not on_list("Wrath", "Alex Raizman"),
          "pool: Raizman's Wrath is NOT on the list -> stays eligible")

    # D-2 — list_set scopes to book tables only.
    with tempfile.TemporaryDirectory() as d:
        rl = Path(d) / "Reading_List.md"
        rl.write_text(READING_LIST_MD, encoding="utf-8")
        pairs = lq.list_set(str(rl))
    titles = {t for t, _ in pairs}
    # Phantom rows from Goals / Series-balance / Floors must be absent.
    for phantom in ("fantasy", "indie", "classic", "balance", "goal",
                    "floor", "series"):
        check(phantom not in titles,
              f"D-2: phantom row {phantom!r} leaked into list_set "
              f"({sorted(titles)})")
    # Real book rows (incl. the Upcoming table) must be present.
    check((norm("Valour"), norm("John Gwynne")) in pairs,
          "D-2: emphasis-wrapped book row must parse")
    check((norm("The Imperator's Hand"), norm("Some Author")) in pairs,
          "D-2: Upcoming & recent releases table must still parse")
    check(len(pairs) == 9,
          f"D-2: expected 9 real book pairs, got {len(pairs)}: "
          f"{sorted(pairs)}")

    if failures:
        print("FAILURES:")
        for f in failures:
            print("  -", f)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
