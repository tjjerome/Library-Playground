#!/usr/bin/env python3
"""Book-identity contract — the guardrail that stops author/title
matching being a moving target.

`webhelper/book_identity.same_book` is the ONE predicate every
resolution call site uses (resolve_book / lookup_by_pair /
_list_membership / reconcile audit).  A new mismatch class is a new
row in MUST_MATCH here, a new false-positive risk a row in
MUST_NOT_MATCH — not another per-site band-aid.

Also asserts the unification holds: `lookup_by_pair` (reconcile,
series-fit, unfinished-series, cataloguer add) resolves the same
variant classes as list resolution, against a synthetic catalog.

Prints OK / exits 0 on success; prints failures / exits 1.
"""

import sqlite3
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from webhelper import librarian_query as lq  # noqa: E402
from webhelper import sqlite_export as se  # noqa: E402
from webhelper.book_identity import same_book, norm, title_short  # noqa: E402

# (label, title_a, author_a, title_b, author_b) — every pair the
# system has ever had to treat as the same book.  Add a row when a
# new class appears; never patch a call site.
MUST_MATCH = [
    ("identical", "The Hobbit", "J.R.R. Tolkien",
     "The Hobbit", "J.R.R. Tolkien"),
    ("author name order", "The Three-Body Problem", "Cixin Liu",
     "The Three-Body Problem", "Liu Cixin"),
    ("co-author omitted", "Skunk Works", "Ben R. Rich",
     "Skunk Works", "Ben R. Rich & Leo Janos"),
    ("multi-author formatting", "Roadside Picnic",
     "Arkady & Boris Strugatsky",
     "Roadside Picnic", "Arkady Strugatsky & Boris Strugatsky"),
    ("british/american title", "Valour", "John Gwynne",
     "Valor", "John Gwynne"),
    ("initials spacing", "Red Country", "K. J. Parker",
     "Red Country", "KJ Parker"),
    ("subtitle drift", "Side Jobs: Stories from the Dresden Files",
     "Jim Butcher", "Side Jobs", "Jim Butcher"),
    ("leading article", "The Name of the Wind", "Patrick Rothfuss",
     "Name of the Wind", "Patrick Rothfuss"),
    ("smart punctuation", "Salem’s Lot", "Stephen King",
     "Salem's Lot", "Stephen King"),
]

# Pairs that must stay DISTINCT — the over-matching guard.
MUST_NOT_MATCH = [
    ("same title diff author", "Wrath", "John Gwynne",
     "Wrath", "Alex Raizman"),
    ("shared surname single authors", "The Road", "John Smith",
     "The Road", "Jane Smith"),
    ("same author diff book", "The Hobbit", "J.R.R. Tolkien",
     "The Silmarillion", "J.R.R. Tolkien"),
    ("different everything", "Dune", "Frank Herbert",
     "Neuromancer", "William Gibson"),
]

# Catalog rows for the unification round-trip.
CATALOG = [
    ("The Three-Body Problem", "Liu Cixin", "ttbp"),
    ("Skunk Works", "Ben R. Rich & Leo Janos", "sw"),
    ("Roadside Picnic", "Arkady Strugatsky & Boris Strugatsky", "rp"),
    ("Valor", "John Gwynne", "valor"),
    ("Wrath", "John Gwynne", "wrath_g"),
    ("Wrath", "Alex Raizman", "wrath_r"),
    ("Side Jobs: Stories from the Dresden Files", "Jim Butcher", "sj"),
]
# (query_title, query_author, expected_key | None)
LOOKUPS = [
    ("The Three-Body Problem", "Cixin Liu", "ttbp"),
    ("Skunk Works", "Ben R. Rich", "sw"),
    ("Roadside Picnic", "Arkady & Boris Strugatsky", "rp"),
    ("Valour", "John Gwynne", "valor"),
    ("Wrath", "John Gwynne", "wrath_g"),
    ("Wrath", "Alex Raizman", "wrath_r"),
    ("Side Jobs", "Jim Butcher", "sj"),
    ("Nonexistent Book", "Nobody", None),
]


def _catalog() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    for stmt in se.SCHEMA:
        conn.execute(stmt)
    for title, author, key in CATALOG:
        conn.execute(
            "INSERT INTO books (key, title, title_normalized, "
            "title_short, author, author_normalized, goodreads_rating, "
            "goodreads_reviews) VALUES (?,?,?,?,?,?,?,?)",
            (key, title, norm(title), title_short(title),
             author, norm(author), 4.2, 1000))
    conn.commit()
    return conn


def main() -> int:
    fails: list[str] = []

    for label, ta, aa, tb, ab in MUST_MATCH:
        if not same_book(ta, aa, tb, ab):
            fails.append(f"MUST_MATCH failed [{label}]: "
                         f"({ta!r},{aa!r}) vs ({tb!r},{ab!r})")
    for label, ta, aa, tb, ab in MUST_NOT_MATCH:
        if same_book(ta, aa, tb, ab):
            fails.append(f"MUST_NOT_MATCH failed [{label}]: "
                         f"({ta!r},{aa!r}) vs ({tb!r},{ab!r})")

    # same_book must be symmetric (resolution direction must not matter).
    for label, ta, aa, tb, ab in MUST_MATCH + MUST_NOT_MATCH:
        if same_book(ta, aa, tb, ab) != same_book(tb, ab, ta, aa):
            fails.append(f"asymmetry [{label}]")

    # Unification: lookup_by_pair (the 4 previously exact-only callers)
    # now resolves every variant class through the one resolver.
    conn = _catalog()
    for qt, qa, want in LOOKUPS:
        got = lq.lookup_by_pair(conn, qt, qa)
        got_key = got["key"] if got else None
        if got_key != want:
            fails.append(f"lookup_by_pair({qt!r},{qa!r}) -> "
                         f"{got_key!r}, want {want!r}")

    if fails:
        print("FAILURES:")
        for f in fails:
            print("  -", f)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
