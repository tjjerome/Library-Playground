#!/usr/bin/env python3
"""Export `Library_Catalog.json` to a queryable SQLite database.

Schema preserves every per-entry field (24 documented in
`library-cataloguer/SKILL.md` plus 5 metadata columns surfaced by
inspection of the live catalog) and catalog-level metadata.

All cataloguer-side fields end up in one of these tables:

  catalog_meta    – single-row catalog metadata (version, dates, totals)
  books           – per-entry scalar columns
  taste_signals   – (book_key, polarity, signal) per signal
  comparable_books– (book_key, comp_key) per comp link
  content_flags   – (book_key, flag) per flag
  themes          – (book_key, theme) per theme
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


def norm(s: str | None) -> str:
    if not s:
        return ""
    s = s.translate(_QUOTE_NORMALIZE)
    s = _TRAILING_PAREN.sub("", s)
    s = _LEAD_PUNCT.sub("", s)
    s = s.lower()
    s = _LEAD_ARTICLE.sub("", s)
    s = re.sub(r"\.", " ", s)
    return " ".join(s.split())


def title_short(title: str | None) -> str:
    """Pre-colon prefix of the title, normalised. Empty if title has
    no colon."""
    if not title or ":" not in title:
        return ""
    return norm(title.split(":", 1)[0])


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
        signal    TEXT NOT NULL,
        canonical TEXT,
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
        theme     TEXT NOT NULL,
        canonical TEXT,
        FOREIGN KEY (book_key) REFERENCES books(key)
    )""",
    """CREATE TABLE related_series (
        book_key       TEXT NOT NULL,
        related_series TEXT NOT NULL,
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
    "CREATE INDEX idx_taste_signals_canonical  ON taste_signals(canonical, polarity)",
    "CREATE INDEX idx_themes_canonical         ON themes(canonical)",
    "CREATE INDEX idx_related_series           ON related_series(related_series)",
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
            ts_canon = entry.get("taste_signals_canonical") or {}
            if isinstance(ts, dict):
                for polarity in ("positive", "negative"):
                    free = ts.get(polarity) or []
                    canon = ts_canon.get(polarity) or [] if isinstance(ts_canon, dict) else []
                    # Pair canonical IDs with free-form strings by list index;
                    # short canonical list -> trailing rows get NULL canonical.
                    for i, sig in enumerate(free):
                        if not sig:
                            continue
                        canon_id = canon[i] if i < len(canon) and canon[i] else None
                        cur.execute(
                            "INSERT INTO taste_signals (book_key, polarity, signal, canonical) "
                            "VALUES (?, ?, ?, ?)",
                            (key, polarity, sig, canon_id),
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

            themes_free = entry.get("themes") or []
            themes_canon = entry.get("themes_canonical") or []
            for i, theme in enumerate(themes_free):
                if not theme:
                    continue
                canon_id = themes_canon[i] if i < len(themes_canon) and themes_canon[i] else None
                cur.execute(
                    "INSERT INTO themes (book_key, theme, canonical) "
                    "VALUES (?, ?, ?)",
                    (key, theme, canon_id),
                )

            for rel in entry.get("related_series") or []:
                if rel:
                    cur.execute(
                        "INSERT INTO related_series (book_key, related_series) "
                        "VALUES (?, ?)",
                        (key, rel),
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

    pos_rows = list(cur.execute(
        "SELECT signal, canonical FROM taste_signals "
        "WHERE book_key = ? AND polarity = 'positive'",
        (key,),
    ))
    neg_rows = list(cur.execute(
        "SELECT signal, canonical FROM taste_signals "
        "WHERE book_key = ? AND polarity = 'negative'",
        (key,),
    ))
    entry["taste_signals"] = {
        "positive": [r["signal"] for r in pos_rows],
        "negative": [r["signal"] for r in neg_rows],
    }
    pos_canon = [r["canonical"] for r in pos_rows if r["canonical"]]
    neg_canon = [r["canonical"] for r in neg_rows if r["canonical"]]
    if pos_canon or neg_canon:
        # Mirror polarity buckets; only emit when at least one canonical
        # was populated, so legacy entries round-trip without acquiring
        # an empty `taste_signals_canonical` block they didn't have.
        entry["taste_signals_canonical"] = {
            "positive": pos_canon,
            "negative": neg_canon,
        }

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
    theme_rows = list(cur.execute(
        "SELECT theme, canonical FROM themes WHERE book_key = ?",
        (key,),
    ))
    entry["themes"] = [r["theme"] for r in theme_rows]
    themes_canon = [r["canonical"] for r in theme_rows if r["canonical"]]
    if themes_canon:
        entry["themes_canonical"] = themes_canon

    related = [
        r["related_series"] for r in cur.execute(
            "SELECT related_series FROM related_series WHERE book_key = ?",
            (key,),
        )
    ]
    if related:
        entry["related_series"] = related

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
