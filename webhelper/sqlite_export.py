#!/usr/bin/env python3
"""Export `Library_Catalog.json` to a queryable SQLite database.

Schema preserves every per-entry field (24 documented in
`library-cataloguer/SKILL.md` plus 5 metadata columns surfaced by
inspection of the live catalog) and catalog-level metadata.

All cataloguer-side fields end up in one of these tables:

  catalog_meta    – single-row catalog metadata (version, dates, totals)
  books           – per-entry scalar columns
  taste_signals   – (book_key, polarity, canonical) per signal
  comparable_books– (book_key, comp_key) per comp link
  content_flags   – (book_key, flag) per flag
  themes          – (book_key, canonical) per theme
  audit_flags     – per-flag audit record (field/severity/reason/...)

Notes on schema choices:

* `title_normalized`, `title_short`, `author_normalized` are populated
  at export time so the runtime helper can index by them via SQL JOINs
  rather than re-running `norm()` per row in Python. `title_short` is
  the pre-colon prefix of the title, normalised — solves the
  Side Jobs subtitle-truncation case in the reading log.

* `audit_json` stores the raw `audit` value as a JSON string (or NULL
  when audit was JSON null / absent).  This is the authoritative
  round-trip form because the original catalog uses five distinct
  audit shapes (dict-passed-True/False/None × flags-empty/non-empty,
  legacy free-form string, and explicit null).  `audit_flags` is a
  queryable projection of the flag rows for SQL convenience; it is
  not used during reconstruction.

* `pub_year` is in the schema for forward compatibility; current
  catalog entries do not populate it.  Stays NULL for all rows.

* `genre_legacy` and `pacing_notes` carry vestigial fields present
  on a small number of entries (72 and 1 respectively).  Preserved
  for byte-for-byte JSON round-trip parity; not queried by any
  skill.
"""

from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path
from typing import Any

# ---------------------------------------------------------------------------
# Normalisation — kept in lock-step with webhelper/librarian_query.py:norm()
# (Step 2 will import this module rather than duplicating the function.)
# ---------------------------------------------------------------------------

_QUOTE_NORMALIZE = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-",
    "​": "", "‌": "", "‍": "", "﻿": "",
})
_LEAD_PUNCT = re.compile(r"^[^\w]+", flags=re.UNICODE)
_LEAD_ARTICLE = re.compile(r"^(the|a|an)\s+", flags=re.IGNORECASE)
_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")
_MULTI_AUTHOR = re.compile(r"\s*(?:&|;|/|\band\b|\bwith\b)\s*", flags=re.IGNORECASE)


def _swap_lastfirst(s: str) -> str:
    """`Last, First` → `First Last`.  Conservative: a single comma,
    no multi-author delimiter, no role/parenthetical markup, and each
    side ≤2 word tokens — so genuine author lists and pen names with
    stylistic commas are left alone."""
    if s.count(",") != 1 or _MULTI_AUTHOR.search(s) or "(" in s:
        return s
    last, first = (p.strip() for p in s.split(","))
    if not (last and first):
        return s
    if len(last.split()) > 2 or len(first.split()) > 2:
        return s
    return f"{first} {last}"


def _collapse_initials(tokens: list[str]) -> list[str]:
    """Merge runs of single-character tokens so `k j parker`,
    `k.j. parker`, and `kj parker` all converge."""
    out: list[str] = []
    buf: list[str] = []
    for t in tokens:
        if len(t) == 1 and t.isalpha():
            buf.append(t)
            continue
        if buf:
            out.append("".join(buf))
            buf = []
        out.append(t)
    if buf:
        out.append("".join(buf))
    return out


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = s.translate(_QUOTE_NORMALIZE)
    s = _swap_lastfirst(s)
    s = s.replace("&", " and ")
    s = _TRAILING_PAREN.sub("", s)
    s = _LEAD_PUNCT.sub("", s)
    s = s.lower()
    s = _LEAD_ARTICLE.sub("", s)
    # Drop subtitle drift: `Title: A Novel` ≡ `Title`.
    s = s.split(":", 1)[0]
    s = re.sub(r"\.", " ", s)
    return " ".join(_collapse_initials(s.split()))


def title_short(title: str | None) -> str:
    """Pre-colon prefix of the title, normalised. Empty if title has
    no colon."""
    if not title or ":" not in title:
        return ""
    return norm(title.split(":", 1)[0])


# ---------------------------------------------------------------------------
# Tolerant (title, author) matching (Plan D-1).
#
# norm() reconciles punctuation/case/article drift but not author name
# order, omitted co-authors, or British/American title spelling.  These
# two helpers add a *conservative* tolerance layer, shared by every
# resolution call site so they cannot drift apart.  Deliberately no
# general fuzzy-ratio rule — over-matching resolves the wrong book.
# ---------------------------------------------------------------------------

_AUTHOR_DELIM = re.compile(r"\s*(?:&|\band\b|,)\s*", flags=re.IGNORECASE)


def _author_matches(a: str, b: str) -> bool:
    """True when two norm()'d author strings name the same author(s)
    under name-order swap, co-author omission, or — for genuine
    multi-author lists only — surname overlap.

      - exact equality (current behaviour); or
      - `_swap_lastfirst` on either side yields equality (name order);
        also covers bare two-token order flips via the token-set rule
        below since norm() only swaps on an explicit comma; or
      - the token set of one author is a subset of the other
        (`{ben, r, rich}` ⊆ `{ben, r, rich, leo, janos}`, and the
        order-flip `{cixin, liu}` == `{liu, cixin}`); or
      - both sides are multi-author lists and a surname token is shared
        (`Arkady & Boris Strugatsky` ≡ `Arkady Strugatsky & Boris
        Strugatsky`).  Restricted to multi-author/multi-author so two
        distinct single authors sharing a surname stay distinct.
    """
    if not a or not b:
        return a == b
    if a == b:
        return True
    if _swap_lastfirst(a) == b or a == _swap_lastfirst(b):
        return True
    ta, tb = set(a.split()), set(b.split())
    if ta and tb and (ta <= tb or tb <= ta):
        return True
    pa = [p for p in _AUTHOR_DELIM.split(a) if p.split()]
    pb = [p for p in _AUTHOR_DELIM.split(b) if p.split()]
    if len(pa) > 1 and len(pb) > 1:
        sa = {p.split()[-1] for p in pa}
        sb = {p.split()[-1] for p in pb}
        if sa & sb:
            return True
    return False


# British → American spelling fold, applied per word as an *additional*
# title-variant key (D-1c), never as a general fuzzy match.  Length
# guards keep common non-variant words out (four/hour/tour, noise/raise,
# rise/wise).  -re→-er is intentionally omitted: it mangles
# nature/future/feature far more often than it folds centre/theatre.
_FOLD_WORD_RULES = [
    ("isations", "izations", 9),
    ("isation", "ization", 8),
    ("ising", "izing", 7),
    ("ised", "ized", 6),
    ("ise", "ize", 6),
    ("ours", "ors", 6),
    ("our", "or", 5),
]


def _fold_word(w: str) -> str:
    for suf, repl, minlen in _FOLD_WORD_RULES:
        if len(w) >= minlen and w.endswith(suf):
            return w[: -len(suf)] + repl
    return w


def _title_fold(t: str) -> str:
    """Spelling-folded form of a norm()'d title.  Compare folded↔folded
    and only when an exact title key already failed."""
    if not t:
        return ""
    return " ".join(_fold_word(w) for w in t.split())


# ---------------------------------------------------------------------------
# Schema
# ---------------------------------------------------------------------------

SCHEMA = [
    """CREATE TABLE catalog_meta (
        catalog_version  INTEGER NOT NULL,
        last_updated     TEXT NOT NULL,
        total_in_library INTEGER,
        total_catalogued INTEGER,
        total_pending    INTEGER
    )""",
    """CREATE TABLE books (
        key                  TEXT PRIMARY KEY,
        title                TEXT NOT NULL,
        title_normalized     TEXT NOT NULL,
        title_short          TEXT,
        author               TEXT NOT NULL,
        author_normalized    TEXT NOT NULL,
        series               TEXT,
        series_position      TEXT,
        series_status        TEXT,
        series_role          TEXT,
        author_entry_point   INTEGER,
        primary_genre        TEXT,
        secondary_genre      TEXT,
        genre_legacy         TEXT,
        indie                INTEGER,
        classic              INTEGER,
        pages                INTEGER,
        goodreads_rating     REAL,
        goodreads_reviews    INTEGER,
        pub_year             INTEGER,
        summary              TEXT,
        tone                 TEXT,
        pacing               TEXT,
        pacing_notes         TEXT,
        setting              TEXT,
        audio_suitability    TEXT,
        audio_notes          TEXT,
        confidence           TEXT,
        research_source      TEXT,
        status               TEXT,
        audit_json           TEXT
    )""",
    """CREATE TABLE taste_signals (
        book_key  TEXT NOT NULL,
        polarity  TEXT NOT NULL,
        canonical TEXT NOT NULL,
        FOREIGN KEY (book_key) REFERENCES books(key)
    )""",
    """CREATE TABLE comparable_books (
        book_key TEXT NOT NULL,
        comp_key TEXT NOT NULL,
        FOREIGN KEY (book_key) REFERENCES books(key)
    )""",
    """CREATE TABLE content_flags (
        book_key TEXT NOT NULL,
        flag     TEXT NOT NULL,
        FOREIGN KEY (book_key) REFERENCES books(key)
    )""",
    """CREATE TABLE themes (
        book_key  TEXT NOT NULL,
        canonical TEXT NOT NULL,
        FOREIGN KEY (book_key) REFERENCES books(key)
    )""",
    """CREATE TABLE audit_flags (
        book_key       TEXT NOT NULL,
        field          TEXT,
        severity       TEXT,
        reason         TEXT,
        csv_value      TEXT,
        expected_value TEXT,
        FOREIGN KEY (book_key) REFERENCES books(key)
    )""",
    "CREATE INDEX idx_books_genre              ON books(primary_genre)",
    "CREATE INDEX idx_books_secondary_genre    ON books(secondary_genre)",
    "CREATE INDEX idx_books_series             ON books(series, series_position)",
    "CREATE INDEX idx_books_title_normalized   ON books(title_normalized)",
    "CREATE INDEX idx_books_title_short        ON books(title_short)",
    "CREATE INDEX idx_books_author_normalized  ON books(author_normalized)",
    "CREATE INDEX idx_books_indie              ON books(indie)",
    "CREATE INDEX idx_books_classic            ON books(classic)",
    "CREATE INDEX idx_books_status             ON books(status)",
]


BOOK_SCALAR_FIELDS = (
    # JSON field name → SQL column. Order tracks the CREATE TABLE.
    ("series", "series"),
    ("series_position", "series_position"),
    ("series_status", "series_status"),
    ("series_role", "series_role"),
    ("primary_genre", "primary_genre"),
    ("secondary_genre", "secondary_genre"),
    ("genre", "genre_legacy"),
    ("pages", "pages"),
    ("goodreads_rating", "goodreads_rating"),
    ("goodreads_reviews", "goodreads_reviews"),
    ("pub_year", "pub_year"),
    ("summary", "summary"),
    ("tone", "tone"),
    ("pacing", "pacing"),
    ("pacing_notes", "pacing_notes"),
    ("setting", "setting"),
    ("audio_suitability", "audio_suitability"),
    ("audio_notes", "audio_notes"),
    ("confidence", "confidence"),
    ("research_source", "research_source"),
    ("status", "status"),
)


def _bool_to_int(v: Any) -> int | None:
    if v is None:
        return None
    if isinstance(v, bool):
        return 1 if v else 0
    if isinstance(v, int):
        return 1 if v else 0
    return None


def _row_for_book(key: str, entry: dict) -> tuple:
    title = entry.get("title", "")
    author = entry.get("author", "")
    audit = entry.get("audit")
    if "audit" in entry and audit is None:
        # explicit JSON null on the entry — round-trip preserves null,
        # not "missing".
        audit_json = "null"
    elif audit is None:
        audit_json = None
    else:
        audit_json = json.dumps(audit, ensure_ascii=False, sort_keys=True)

    scalars = {json_name: entry.get(json_name) for json_name, _ in BOOK_SCALAR_FIELDS}
    return (
        key,
        title,
        norm(title),
        title_short(title),
        author,
        norm(author),
        scalars["series"],
        scalars["series_position"],
        scalars["series_status"],
        scalars["series_role"],
        _bool_to_int(entry.get("author_entry_point")),
        scalars["primary_genre"],
        scalars["secondary_genre"],
        scalars["genre"],
        _bool_to_int(entry.get("indie")),
        _bool_to_int(entry.get("classic")),
        scalars["pages"],
        scalars["goodreads_rating"],
        scalars["goodreads_reviews"],
        scalars["pub_year"],
        scalars["summary"],
        scalars["tone"],
        scalars["pacing"],
        scalars["pacing_notes"],
        scalars["setting"],
        scalars["audio_suitability"],
        scalars["audio_notes"],
        scalars["confidence"],
        scalars["research_source"],
        scalars["status"],
        audit_json,
    )


def _audit_flag_rows(key: str, entry: dict) -> list[tuple]:
    audit = entry.get("audit")
    if not isinstance(audit, dict):
        return []
    out: list[tuple] = []
    for f in audit.get("flags") or []:
        if not isinstance(f, dict):
            continue
        out.append((
            key,
            f.get("field"),
            f.get("severity"),
            f.get("reason"),
            f.get("csv_value"),
            f.get("expected_value"),
        ))
    return out


def export(catalog: dict, sqlite_path: Path) -> None:
    """Build a fresh SQLite at `sqlite_path` from the `catalog` dict.

    Overwrites any existing file at that path.
    """
    if sqlite_path.exists():
        sqlite_path.unlink()
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(str(sqlite_path))
    try:
        cur = conn.cursor()
        for stmt in SCHEMA:
            cur.execute(stmt)

        cur.execute(
            "INSERT INTO catalog_meta (catalog_version, last_updated, "
            "total_in_library, total_catalogued, total_pending) "
            "VALUES (?, ?, ?, ?, ?)",
            (
                int(catalog.get("catalog_version") or 1),
                str(catalog.get("last_updated") or ""),
                catalog.get("total_in_library"),
                catalog.get("total_catalogued"),
                catalog.get("total_pending"),
            ),
        )

        book_cols = (
            "key, title, title_normalized, title_short, author, "
            "author_normalized, series, series_position, series_status, "
            "series_role, author_entry_point, primary_genre, "
            "secondary_genre, genre_legacy, indie, classic, pages, "
            "goodreads_rating, goodreads_reviews, pub_year, summary, "
            "tone, pacing, pacing_notes, setting, audio_suitability, "
            "audio_notes, confidence, research_source, status, audit_json"
        )
        placeholders = ", ".join("?" * 31)
        book_sql = f"INSERT INTO books ({book_cols}) VALUES ({placeholders})"

        for key, entry in catalog["entries"].items():
            cur.execute(book_sql, _row_for_book(key, entry))

            ts = entry.get("taste_signals") or {}
            if isinstance(ts, dict):
                for sig in ts.get("positive") or []:
                    if sig:
                        cur.execute(
                            "INSERT INTO taste_signals (book_key, polarity, canonical) "
                            "VALUES (?, 'positive', ?)",
                            (key, sig),
                        )
                for sig in ts.get("negative") or []:
                    if sig:
                        cur.execute(
                            "INSERT INTO taste_signals (book_key, polarity, canonical) "
                            "VALUES (?, 'negative', ?)",
                            (key, sig),
                        )

            for comp in entry.get("comparable_books") or []:
                if comp:
                    cur.execute(
                        "INSERT INTO comparable_books (book_key, comp_key) "
                        "VALUES (?, ?)",
                        (key, comp),
                    )

            for flag in entry.get("content_flags") or []:
                if flag:
                    cur.execute(
                        "INSERT INTO content_flags (book_key, flag) "
                        "VALUES (?, ?)",
                        (key, flag),
                    )

            for theme in entry.get("themes") or []:
                if theme:
                    cur.execute(
                        "INSERT INTO themes (book_key, canonical) VALUES (?, ?)",
                        (key, theme),
                    )

            for row in _audit_flag_rows(key, entry):
                cur.execute(
                    "INSERT INTO audit_flags (book_key, field, severity, "
                    "reason, csv_value, expected_value) VALUES (?, ?, ?, ?, ?, ?)",
                    row,
                )

        conn.commit()
        cur.execute("VACUUM")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Reverse — used by tests/sqlite_roundtrip.py
# ---------------------------------------------------------------------------

def reconstruct_entry(conn: sqlite3.Connection, key: str) -> dict:
    """Build a dict that mirrors the JSON entry shape from the SQLite
    rows for `key`.  Used for round-trip parity tests."""
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row

    book = cur.execute("SELECT * FROM books WHERE key = ?", (key,)).fetchone()
    if book is None:
        raise KeyError(key)

    entry: dict = {
        "title": book["title"],
        "author": book["author"],
    }
    for json_name, col in BOOK_SCALAR_FIELDS:
        val = book[col]
        if val is None and json_name in ("pub_year", "genre", "pacing_notes"):
            # forward-compat / vestigial fields: omit when null on the
            # SQLite side so we match the JSON shape (key absent).
            continue
        entry[json_name] = val

    aep = book["author_entry_point"]
    entry["author_entry_point"] = bool(aep) if aep is not None else None
    entry["indie"] = bool(book["indie"]) if book["indie"] is not None else None
    entry["classic"] = bool(book["classic"]) if book["classic"] is not None else None

    pos = [r["canonical"] for r in cur.execute(
        "SELECT canonical FROM taste_signals WHERE book_key = ? AND polarity = 'positive'",
        (key,),
    )]
    neg = [r["canonical"] for r in cur.execute(
        "SELECT canonical FROM taste_signals WHERE book_key = ? AND polarity = 'negative'",
        (key,),
    )]
    entry["taste_signals"] = {"positive": pos, "negative": neg}

    entry["comparable_books"] = [
        r["comp_key"] for r in cur.execute(
            "SELECT comp_key FROM comparable_books WHERE book_key = ?",
            (key,),
        )
    ]
    entry["content_flags"] = [
        r["flag"] for r in cur.execute(
            "SELECT flag FROM content_flags WHERE book_key = ?",
            (key,),
        )
    ]
    entry["themes"] = [
        r["canonical"] for r in cur.execute(
            "SELECT canonical FROM themes WHERE book_key = ?",
            (key,),
        )
    ]

    aj = book["audit_json"]
    if aj is None:
        # Original entry had no `audit` key at all (rare in current
        # catalog — every entry has the key). Omit on reconstruction.
        pass
    else:
        entry["audit"] = json.loads(aj)

    return entry


def load_meta(conn: sqlite3.Connection) -> dict:
    cur = conn.cursor()
    cur.row_factory = sqlite3.Row
    row = cur.execute("SELECT * FROM catalog_meta").fetchone()
    if row is None:
        return {}
    return {
        "catalog_version": row["catalog_version"],
        "last_updated": row["last_updated"],
        "total_in_library": row["total_in_library"],
        "total_catalogued": row["total_catalogued"],
        "total_pending": row["total_pending"],
    }


def export_from_path(json_path: Path, sqlite_path: Path) -> None:
    with open(json_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)
    export(catalog, sqlite_path)
