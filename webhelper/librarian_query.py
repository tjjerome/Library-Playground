#!/usr/bin/env python3
"""Librarian query helper — claude.ai port.

Single chokepoint for candidate generation, exclusion checks, and the
shown-this-session ledger.  Ports the Code-side `librarian-query.py`
to a SQLite-backed catalog and a stateless ledger that travels via
stdin/stdout — the model owns ledger persistence in `window.storage`,
the helper just transforms.

Defaults assume the sandbox layout the librarian-triage skill sets up
at session start:

    /tmp/Library-Playground/Library_Catalog.sqlite
    /tmp/Library-Playground/Reading_Log.csv
    /tmp/Library-Playground/Profile.md
    /tmp/Library-Playground/Reading_List.md

…but every path is overridable via CLI flags so the skills can place
files wherever they like.

Output: JSON to stdout.  Diagnostics to stderr.  Exit codes:
    0 success / 1 boolean-false (e.g. is-read on an unread book)
    2 malformed input / 3 no candidates after filtering.

Subcommand surface matches the Code helper:
  norm, is-read, is-on-list, is-shown, exclusion-set,
  unfinished-series, candidates, mark-shown, weight,
  distribution, series-continuation, lookup, profile-append,
  session-reset
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

# ---------------------------------------------------------------------------
# Shared normaliser (also used at SQLite export time).  Importing here keeps
# norm() in lock-step with the export-time precomputed columns.
# ---------------------------------------------------------------------------

try:
    # Package-relative (when imported as part of webhelper.*).
    from .sqlite_export import norm  # type: ignore
except (ImportError, ValueError):
    try:
        # Direct invocation: webhelper/librarian_query.py from repo root.
        # Python adds the script dir to sys.path[0], so sibling import works.
        from sqlite_export import norm  # type: ignore  # noqa: E402
    except ImportError:
        # Fallback for tests / out-of-tree invocation.
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from webhelper.sqlite_export import norm  # noqa: E402

REJECTION_PENALTIES = (0.5, 1.5, 3.5, 6.0)  # cumulative-by-count
_BOOK1 = re.compile(r"^book\s*1(?![\d.])", flags=re.IGNORECASE)


# ---------------------------------------------------------------------------
# Defaults / paths
# ---------------------------------------------------------------------------

DEFAULT_CATALOG = "Library_Catalog.sqlite"
DEFAULT_LOG = "Reading_Log.csv"
DEFAULT_LIST = "Reading_List.md"
DEFAULT_PROFILE = "Profile.md"


def die(msg: str, code: int = 2) -> None:
    print(f"librarian-query: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------------------
# Catalog I/O
# ---------------------------------------------------------------------------

def open_catalog(path: str) -> sqlite3.Connection:
    p = Path(path)
    if not p.exists():
        die(f"missing catalog: {p}", code=2)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    return conn


def load_log(path: str) -> list[dict]:
    p = Path(path)
    if not p.exists():
        die(f"missing reading log: {p}", code=2)
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------------------------------------------------------------------------
# Reading list (Reading_List.md) — parse table rows for (title, author) pairs
# ---------------------------------------------------------------------------

def list_set(path: str) -> set[tuple[str, str]]:
    p = Path(path)
    if not p.exists():
        return set()
    out: set[tuple[str, str]] = set()
    text = p.read_text(encoding="utf-8")
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            continue
        if cells[0].lower() in ("title", "---") or set(cells[0]) <= set("- :"):
            continue
        title, author = cells[0], cells[1]
        if not title or set(title) <= set("- :"):
            continue
        out.add((norm(title), norm(author)))
    return out


def already_read_set(log: list[dict]) -> set[tuple[str, str]]:
    return {(norm(r.get("title", "")), norm(r.get("authors", "")))
            for r in log if r.get("title")}


# ---------------------------------------------------------------------------
# Ledger — stateless: stdin JSON in, stdout JSON out.
# Ledger format: list of records, each shaped:
#   {"title": str, "author": str, "title_norm": str, "author_norm": str,
#    "batch_id": str, "status": "selected"|"rejected"|"shown",
#    "ts": ISO8601, "primary_genre": str|null, "indie": bool|null,
#    "classic": bool|null, "pages": int|null}
# ---------------------------------------------------------------------------

def load_ledger(arg: str | None) -> list[dict]:
    """Resolve --ledger argument.

    "-"  → read JSON list from stdin
    None → empty ledger
    path → read JSON list from path (legacy / tests)
    """
    if arg is None:
        return []
    if arg == "-":
        raw = sys.stdin.read().strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            die(f"bad ledger on stdin: {e}", code=2)
    else:
        try:
            data = json.loads(Path(arg).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            die(f"bad ledger at {arg}: {e}", code=2)
    if not isinstance(data, list):
        die("ledger must be a JSON list of records", code=2)
    return data


def shown_set(ledger: list[dict]) -> set[tuple[str, str]]:
    out: set[tuple[str, str]] = set()
    for r in ledger:
        tn = r.get("title_norm") or norm(r.get("title", ""))
        an = r.get("author_norm") or norm(r.get("author", ""))
        out.add((tn, an))
    return out


def rejection_count(ledger: list[dict], title: str, author: str) -> int:
    tn, an = norm(title), norm(author)
    return sum(
        1 for r in ledger
        if (r.get("title_norm") or norm(r.get("title", ""))) == tn
        and (r.get("author_norm") or norm(r.get("author", ""))) == an
        and r.get("status") == "rejected"
    )


def rejection_penalty(count: int) -> float:
    if count <= 0:
        return 0.0
    if count - 1 < len(REJECTION_PENALTIES):
        return REJECTION_PENALTIES[count - 1]
    return REJECTION_PENALTIES[-1]


# ---------------------------------------------------------------------------
# Catalog row helpers
# ---------------------------------------------------------------------------

def row_to_entry(row: sqlite3.Row, conn: sqlite3.Connection | None = None) -> dict:
    """Convert a `books` row into a dict mirroring the legacy JSON shape
    (with bool fields as Python bools).  Joined collections (themes,
    comparable_books, taste_signals, content_flags) are NOT loaded by
    default — they require explicit follow-up queries when needed.
    """
    e = dict(row)
    for f in ("indie", "classic"):
        if e.get(f) is not None:
            e[f] = bool(e[f])
    aep = e.get("author_entry_point")
    e["author_entry_point"] = bool(aep) if aep is not None else None
    return e


def parse_rating(raw) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def has_flag(row: dict, flag: str) -> bool:
    return any(t.strip() == flag for t in (row.get("my_tags") or "").split(","))


def is_book_one(series_position: str | None) -> bool:
    if not series_position:
        return False
    return bool(_BOOK1.match(series_position.strip()))


# series_role values that count as a valid entry point for an unread author.
_ENTRY_ROLES = {"standalone", "first", "loose-entry"}


def passes_entry_point_gate(entry: dict, log_authors: set[str]) -> bool:
    """Universal author entry-point gate.  Same two-layer rule as the
    Code helper:

      1. Catalog-driven (preferred): if `series_role` and/or
         `author_entry_point` populated, use them.
      2. Conservative fallback: when both fields null on the entry,
         non-Standalone book by an unread author requires
         `series_position == "Book 1"`.
    """
    if norm(entry.get("author", "")) in log_authors:
        return True

    role = entry.get("series_role")
    aep = entry.get("author_entry_point")

    if role is not None or aep is not None:
        if aep is False:
            return False
        if role is not None and role not in _ENTRY_ROLES:
            return False
        return True

    if (entry.get("series_status") and entry.get("series_status") != "Standalone"
            and not is_book_one(entry.get("series_position"))):
        return False
    return True


def is_deep_cut(entry: dict, batch_genre_keys: Iterable[str] = ()) -> bool:
    gr = entry.get("goodreads_rating") or 0
    rev = entry.get("goodreads_reviews") or 0
    if rev and rev < 1500 and gr >= 4.2:
        return True
    if entry.get("indie"):
        return True
    if entry.get("classic") and rev and rev < 50000:
        return True
    sec = (entry.get("secondary_genre") or "").strip()
    primary = (entry.get("primary_genre") or "").strip()
    if sec and sec != primary and any(k.lower() == sec.lower() for k in batch_genre_keys):
        return True
    return False


def comp_keys_for(conn: sqlite3.Connection, key: str) -> list[str]:
    return [r["comp_key"] for r in conn.execute(
        "SELECT comp_key FROM comparable_books WHERE book_key = ?", (key,)
    )]


def _split_key(key: str) -> tuple[str, str] | None:
    if " - " not in key:
        return None
    title, author = key.rsplit(" - ", 1)
    return (norm(title), norm(author))


# ---------------------------------------------------------------------------
# Scoring (verbatim from the Code helper, adapted for row dicts)
# ---------------------------------------------------------------------------

def build_favorite_pools(log: list[dict]):
    five_star_authors = set()
    favorite_authors = set()
    favorite_titles_norm: set[tuple[str, str]] = set()
    for r in log:
        rating = parse_rating(r.get("My Rating"))
        if rating is None:
            continue
        title = r.get("title", "")
        author = r.get("authors", "")
        if rating >= 5.0:
            five_star_authors.add(norm(author))
        if rating >= 4.5:
            favorite_authors.add(norm(author))
            favorite_titles_norm.add((norm(title), norm(author)))
    return five_star_authors, favorite_authors, favorite_titles_norm


def score_candidate(
    entry: dict,
    *,
    comp_keys: list[str],
    five_star_authors: set[str],
    favorite_authors: set[str],
    favorite_titles_norm: set[tuple[str, str]],
    boost_tags: dict[str, float],
    batch_genre_keys: Iterable[str] = (),
    rej_count: int = 0,
) -> tuple[float, dict]:
    breakdown: dict = {}
    base = float(entry.get("goodreads_rating") or 0)
    breakdown["gr"] = round(base, 2)

    pocket = 0.0
    author = (entry.get("author") or "").strip()
    if author and norm(author) in five_star_authors:
        pocket = 1.5
    elif author and norm(author) in favorite_authors:
        pocket = 0.8
    breakdown["author_pocket"] = pocket

    comp_overlap = 0
    for c in comp_keys:
        c_norm_pair = _split_key(c)
        if c_norm_pair and c_norm_pair in favorite_titles_norm:
            comp_overlap += 1
    comp_bonus = min(comp_overlap, 3) * 0.6
    breakdown["comp_bonus"] = round(comp_bonus, 2)
    breakdown["comp_overlap_count"] = comp_overlap

    boost_bonus = 0.0
    for tag, factor in boost_tags.items():
        if entry.get(tag):
            boost_bonus += factor
    breakdown["boost_bonus"] = round(boost_bonus, 2)

    deep_cut = is_deep_cut(entry, batch_genre_keys=batch_genre_keys)
    breakdown["deep_cut"] = deep_cut

    penalty = rejection_penalty(rej_count)
    breakdown["rejection_penalty"] = round(-penalty, 2)
    breakdown["rejection_count"] = rej_count

    score = base + pocket + comp_bonus + boost_bonus - penalty
    return score, breakdown


# ---------------------------------------------------------------------------
# series-continuation helpers
# ---------------------------------------------------------------------------

def _series_order_key(entry: dict) -> tuple[float, str]:
    p = (entry.get("series_position") or "").lower()
    m = re.search(r"book\s*([\d.]+)", p)
    if m:
        try:
            return (float(m.group(1)), entry.get("title") or "")
        except ValueError:
            pass
    return (999.0, entry.get("title") or "")


# Patterns that look like subseries notation but aren't navigable
# (content / format annotations, not sequential thread membership).
_SUBSERIES_SKIP_TOKENS = (
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


def _parse_subseries(series_position: str | None) -> tuple[str, float] | None:
    """Return (subseries_name_normalised, subseries_position) parsed
    from the parenthetical of a series_position string, or None when
    no recognisable subseries pattern is present.

    Subseries notation lives inside the trailing parens, e.g.
    "Book 29 (City Watch Book 6)" → ("city watch", 6.0).  Recognised
    inner-paren forms (case-insensitive):

      - "<Name> Book N" / "<Name> Book N.M"
      - "<Name>, Book N"
      - "<Name> #N"
      - "<Name> subseries Book N"
      - "<Name> Series Book N"
      - "Book N in <Name>" / "Book N in <Name> subseries"

    Annotations like "(novella)", "(omnibus)", "(prequel)",
    "(chronological order)", "(Books 10-12: ...)" are ignored —
    they're content/format hints, not a sequential subseries.
    """
    if not series_position:
        return None
    m = re.search(r"\(([^)]+)\)", series_position)
    if not m:
        return None
    inner = m.group(1).strip()
    inner_lc = inner.lower()
    if any(tok in inner_lc for tok in _SUBSERIES_SKIP_TOKENS):
        return None

    # "Book N in <Name> [subseries]" — number first.
    mm = re.match(
        r"^Book\s+([\d.]+)\s+in\s+(.+?)(?:\s+subseries)?$",
        inner, flags=re.IGNORECASE,
    )
    if mm:
        try:
            return (norm(mm.group(2)), float(mm.group(1)))
        except ValueError:
            pass

    # "<Name>[,]? [subseries|Series] Book N" / "<Name> #N"
    for pat in (
        r"^(.+?),\s+Book\s+([\d.]+)$",
        r"^(.+?)\s+(?:[Ss]ubseries|[Ss]eries)\s+Book\s+([\d.]+)$",
        r"^(.+?)\s+(?:[Ss]ubseries|[Ss]eries)\s+#([\d.]+)$",
        r"^(.+?)\s+Book\s+([\d.]+)$",
        r"^(.+?)\s+#([\d.]+)$",
    ):
        mm = re.match(pat, inner, flags=re.IGNORECASE)
        if mm:
            try:
                return (norm(mm.group(1)), float(mm.group(2)))
            except ValueError:
                pass
    return None


def _series_sub_thread(series_position: str | None) -> str | None:
    parsed = _parse_subseries(series_position)
    return parsed[0] if parsed else None


def _subseries_order_key(entry: dict) -> tuple[float, str]:
    """Sort key for navigating WITHIN a subseries.  Falls back to
    overall series ordering when no subseries info is present."""
    parsed = _parse_subseries(entry.get("series_position"))
    if parsed:
        return (parsed[1], entry.get("title") or "")
    return _series_order_key(entry)


def lookup_by_pair(conn: sqlite3.Connection, title: str, author: str) -> dict | None:
    """Three-tier lookup mirroring the Code helper's _index_catalog_by_pair:
       full title → key prefix → pre-colon title prefix.
    """
    tn = norm(title)
    an = norm(author)
    for sql in (
        # Full normalised title.
        "SELECT * FROM books WHERE title_normalized = ? AND author_normalized = ?",
        # title_short (pre-colon prefix) — handles subtitle truncation.
        "SELECT * FROM books WHERE title_short = ? AND author_normalized = ?",
    ):
        row = conn.execute(sql, (tn, an)).fetchone()
        if row is not None:
            return row_to_entry(row)
    return None


# ---------------------------------------------------------------------------
# Subcommand handlers
# ---------------------------------------------------------------------------

def cmd_norm(args, _conn=None) -> None:
    print(norm(args.text))


def cmd_is_read(args, conn) -> None:
    log = load_log(args.log)
    s = already_read_set(log)
    hit = (norm(args.title), norm(args.author)) in s
    print(json.dumps({"hit": hit, "title": args.title, "author": args.author}))
    sys.exit(0 if hit else 1)


def cmd_is_on_list(args, _conn) -> None:
    s = list_set(args.reading_list)
    hit = (norm(args.title), norm(args.author)) in s
    print(json.dumps({"hit": hit, "title": args.title, "author": args.author}))
    sys.exit(0 if hit else 1)


def cmd_is_shown(args, _conn) -> None:
    ledger = load_ledger(args.ledger)
    hit = (norm(args.title), norm(args.author)) in shown_set(ledger)
    print(json.dumps({"hit": hit, "title": args.title, "author": args.author}))
    sys.exit(0 if hit else 1)


def cmd_exclusion_set(args, _conn) -> None:
    log = load_log(args.log)
    out = {
        "already_read": [
            {"title_norm": t, "author_norm": a} for t, a in sorted(already_read_set(log))
        ],
        "on_list": [
            {"title_norm": t, "author_norm": a} for t, a in sorted(list_set(args.reading_list))
        ],
    }
    if args.include_shown:
        ledger = load_ledger(args.ledger)
        out["shown_this_session"] = [
            {"title_norm": t, "author_norm": a} for t, a in sorted(shown_set(ledger))
        ]
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_unfinished_series(args, conn) -> None:
    log = load_log(args.log)

    # Series → ordered list of all catalog books in that series.
    series_books: dict[str, list[dict]] = {}
    rows = conn.execute(
        "SELECT * FROM books WHERE series IS NOT NULL "
        "AND series_status != 'Standalone'"
    ).fetchall()
    for r in rows:
        e = row_to_entry(r)
        s = e["series"]
        series_books.setdefault(s, []).append(e)

    # Group log rows by series via a pair-resolved catalog lookup.
    series_log_rows: dict[str, list[tuple[dict, dict]]] = {}
    for r in log:
        if not r.get("title"):
            continue
        ce = lookup_by_pair(conn, r["title"], r.get("authors", ""))
        if not ce:
            continue
        s = ce.get("series")
        if not s or ce.get("series_status") == "Standalone":
            continue
        series_log_rows.setdefault(s, []).append((r, ce))

    out = []
    for series, rows in series_log_rows.items():
        rated = [(r, ce, parse_rating(r.get("My Rating")))
                 for r, ce in rows if parse_rating(r.get("My Rating")) is not None]
        if not rated:
            continue
        ratings = [x for _, _, x in rated]

        if max(ratings) < args.min_rating:
            continue
        avg = sum(ratings) / len(ratings)
        if avg < args.min_avg:
            continue

        rated_by_pos = sorted(rated, key=lambda t: _series_order_key(t[1]))
        last_rating = rated_by_pos[-1][2]
        if last_rating < args.min_last:
            continue

        if any(has_flag(r, "*completed") for r, _ in rows):
            continue

        ordered = sorted(series_books.get(series, []), key=_series_order_key)
        read_pairs = {(norm(ce.get("title", "")), norm(ce.get("author", "")))
                      for _, ce in rows}
        next_book = None
        for book in ordered:
            if (norm(book.get("title", "")), norm(book.get("author", ""))) in read_pairs:
                continue
            p = (book.get("series_position") or "").lower()
            m = re.search(r"book\s*([\d.]+)", p)
            if m and float(m.group(1)) < 1:
                continue
            next_book = book
            break

        last_read = max(rows, key=lambda pair: _series_order_key(pair[1]))
        out.append({
            "series": series,
            "author": last_read[1].get("author"),
            "last_book_read": last_read[1].get("title"),
            "last_position": last_read[1].get("series_position"),
            "last_rating": parse_rating(last_read[0].get("My Rating")),
            "max_rating_in_series": max(ratings),
            "avg_rating_in_series": round(avg, 2),
            "next_book_in_catalog": next_book.get("title") if next_book else None,
            "next_position": next_book.get("series_position") if next_book else None,
            "next_pages": next_book.get("pages") if next_book else None,
            "next_key": next_book.get("key") if next_book else None,
        })

    out.sort(key=lambda r: -r["max_rating_in_series"])
    print(json.dumps(out, ensure_ascii=False, indent=2))


def cmd_series_continuation(args, conn) -> None:
    src = lookup_by_pair(conn, args.title, args.author)
    if not src:
        print(json.dumps({"next": None, "reason": "source book not in catalog"}))
        sys.exit(0)

    series = src.get("series")
    if not series or src.get("series_status") not in ("Short Series", "Long Series"):
        print(json.dumps({"next": None, "reason": "not a sequential series"}))
        sys.exit(0)

    siblings = [row_to_entry(r) for r in conn.execute(
        "SELECT * FROM books WHERE series = ?", (series,)
    )]

    log = load_log(args.log)
    excluded_pairs = already_read_set(log) | list_set(args.reading_list)
    if not args.include_shown:
        excluded_pairs |= shown_set(load_ledger(args.ledger))

    src_pos = src.get("series_position") or ""
    src_n = (norm(src.get("title", "")), norm(src.get("author", "")))
    src_sub = _series_sub_thread(src_pos)

    def _candidate_books(restrict_to_sub):
        # When walking a subseries, sort by SUBSERIES position (not the
        # outer overall-series book number) so City Watch #6 follows
        # City Watch #5 even when the Discworld numbering jumps over
        # other subseries entries.
        sort_key = _subseries_order_key if restrict_to_sub else _series_order_key
        ordered = sorted(siblings, key=sort_key)
        for book in ordered:
            if restrict_to_sub:
                if _series_sub_thread(book.get("series_position")) != restrict_to_sub:
                    continue
            book_pair = (norm(book.get("title", "")), norm(book.get("author", "")))
            yield book, book_pair

    def _next_after_source(books):
        next_book = None
        found_src = False
        for book, book_pair in books:
            if not found_src:
                if book_pair == src_n or book.get("series_position") == src_pos:
                    found_src = True
                continue
            p = (book.get("series_position") or "").lower()
            m = re.search(r"book\s*([\d.]+)", p)
            if m and float(m.group(1)) < 1:
                continue
            if book_pair in excluded_pairs:
                continue
            next_book = book
            break
        return next_book

    next_book = None
    if src_sub:
        next_book = _next_after_source(list(_candidate_books(src_sub)))
    if not next_book:
        next_book = _next_after_source(list(_candidate_books(None)))

    if not next_book:
        print(json.dumps({"next": None, "reason": "no further unread book in series"}))
        sys.exit(0)

    print(json.dumps({
        "next": {
            "key": next_book.get("key"),
            "title": next_book.get("title"),
            "author": next_book.get("author"),
            "series": series,
            "series_position": next_book.get("series_position"),
            "pages": next_book.get("pages"),
            "gr_rating": next_book.get("goodreads_rating"),
            "gr_reviews": next_book.get("goodreads_reviews"),
            "summary": next_book.get("summary"),
        }
    }, ensure_ascii=False, indent=2))


def _split_title_by_author(q: str) -> tuple[str, str | None]:
    """Detect "<title> by <author>" patterns from natural-language queries.
    Returns (title_query, author_filter or None).  Splits on the rightmost
    " by " (case-insensitive) so titles containing "by" still parse cleanly
    ("Stand By Me by Stephen King" → "Stand By Me", "Stephen King").
    Falls back to (q, None) if the split looks implausible (RHS missing,
    too long to be an author name, or LHS empty)."""
    import re
    parts = re.split(r"\s+by\s+", q, flags=re.IGNORECASE)
    if len(parts) < 2:
        return q, None
    # Take the LAST " by " as the title/author boundary.
    title_q = " by ".join(parts[:-1]).strip()
    author_q = parts[-1].strip()
    if not title_q or not author_q or len(author_q) > 60:
        return q, None
    return title_q, author_q


def cmd_lookup(args, conn) -> None:
    """Three-pass fuzzy match: exact key → title substring (incl.
    pre-colon prefix) → series substring.  Pre-parses "<title> by
    <author>" natural-language queries and filters results by author."""
    raw_q = args.query.strip()
    q, author_q = _split_title_by_author(raw_q)
    qn = norm(q)
    author_filter = norm(author_q) if author_q else None

    log = load_log(args.log) if Path(args.log).exists() else []
    read_set = already_read_set(log)
    on_list = list_set(args.reading_list)
    shown = shown_set(load_ledger(args.ledger)) if args.ledger else set()

    matches: list[dict] = []
    seen_keys: set[str] = set()

    def add(row: sqlite3.Row) -> None:
        k = row["key"]
        if k in seen_keys:
            return
        if author_filter and author_filter not in (row["author_normalized"] or ""):
            return
        seen_keys.add(k)
        title = row["title"] or ""
        author = row["author"] or ""
        pair = (norm(title), norm(author))
        matches.append({
            "key": k,
            "title": title,
            "author": author,
            "series": row["series"],
            "series_position": row["series_position"],
            "series_status": row["series_status"],
            "primary_genre": row["primary_genre"],
            "pages": row["pages"],
            "is_already_read": pair in read_set,
            "is_on_list": pair in on_list,
            "is_shown": pair in shown,
        })

    # Pass 1: exact key match.
    row = conn.execute("SELECT * FROM books WHERE LOWER(key) = ?", (q.lower(),)).fetchone()
    if row is not None:
        add(row)
    if matches and not args.all_passes:
        print(json.dumps(matches, ensure_ascii=False, indent=2))
        sys.exit(0)

    # Pass 2: title substring (incl. pre-colon prefix via title_short).
    if qn:
        for row in conn.execute(
            "SELECT * FROM books WHERE INSTR(title_normalized, ?) > 0 "
            "OR INSTR(title_short, ?) > 0",
            (qn, qn),
        ):
            add(row)
    if matches and not args.all_passes:
        print(json.dumps(matches, ensure_ascii=False, indent=2))
        sys.exit(0)

    # Pass 3: series substring.
    if qn:
        for row in conn.execute(
            "SELECT * FROM books WHERE series IS NOT NULL "
            "AND INSTR(LOWER(REPLACE(REPLACE(series, '.', ' '), '  ', ' ')), ?) > 0",
            (qn,),
        ):
            add(row)

    print(json.dumps(matches, ensure_ascii=False, indent=2))
    if not matches:
        sys.exit(1)


# ---------------------------------------------------------------------------
# profile-append — stdin/stdout style for skill-driven Drive flushes.
# Default behaviour: read --profile, write back --profile.  Pass --stdio to
# read from stdin and write the new content to stdout (the model captures
# stdout and writes back to Drive itself).
# ---------------------------------------------------------------------------

def _profile_append_text(text: str, section: str, bullet: str) -> tuple[str, dict]:
    """Pure-text version of the Code helper's profile-append.  Returns
    (new_text, info_dict)."""
    lines = text.splitlines()
    target = f"## {section.strip()}"
    section_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip().lower() == target.lower()),
        None,
    )

    if section_idx is None:
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(target)
        lines.append("")
        lines.append(f"- {bullet}")
        lines.append("")
        return ("\n".join(lines) + "\n",
                {"appended": True, "section": section, "bullet": bullet,
                 "created_section": True})

    end_idx = len(lines)
    for j in range(section_idx + 1, len(lines)):
        if lines[j].startswith("## "):
            end_idx = j
            break

    existing = [ln.strip() for ln in lines[section_idx + 1:end_idx]]
    if any(ln.lstrip("- ").strip() == bullet for ln in existing if ln.startswith("- ")):
        return (text, {"appended": False, "section": section, "bullet": bullet,
                       "reason": "duplicate"})

    insert_at = end_idx
    while insert_at > section_idx + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, f"- {bullet}")
    return ("\n".join(lines) + "\n",
            {"appended": True, "section": section, "bullet": bullet,
             "created_section": False})


def cmd_profile_append(args, _conn) -> None:
    section = args.section.strip()
    bullet = args.bullet.strip()

    if args.stdio:
        text = sys.stdin.read()
        if not text:
            text = ("# Reader Profile\n\n"
                    "_Living memory — updated throughout reading-list builds._\n\n")
        new_text, info = _profile_append_text(text, section, bullet)
        sys.stdout.write(new_text)
        print(json.dumps(info), file=sys.stderr)
        return

    p = Path(args.profile)
    if not p.exists():
        text = ("# Reader Profile\n\n"
                "_Living memory — updated throughout reading-list builds._\n\n")
    else:
        text = p.read_text(encoding="utf-8")

    new_text, info = _profile_append_text(text, section, bullet)
    p.write_text(new_text, encoding="utf-8")
    print(json.dumps(info))


# ---------------------------------------------------------------------------
# candidates — the big one.
# ---------------------------------------------------------------------------

def cmd_candidates(args, conn) -> None:
    log = load_log(args.log)
    excluded = already_read_set(log) | list_set(args.reading_list)
    ledger = load_ledger(args.ledger)
    if not args.include_shown:
        excluded |= shown_set(ledger)

    five_star_authors, favorite_authors, favorite_titles_norm = build_favorite_pools(log)

    boost_tags: dict[str, float] = {}
    for spec in args.boost_tag or []:
        try:
            tag, factor = spec.split(":", 1)
            boost_tags[tag] = float(factor)
        except ValueError:
            die(f"bad --boost-tag {spec!r}; expected tag:factor", code=2)

    cross_cut_floor: dict[str, int] = {}
    for spec in args.cross_cut_floor or []:
        try:
            tag, n = spec.split(":", 1)
            cross_cut_floor[tag] = int(n)
        except ValueError:
            die(f"bad --cross-cut-floor {spec!r}; expected tag:n", code=2)

    require_tags = set(args.require_tag or [])
    genres = list(args.genre or [])
    log_authors = {norm(r.get("authors", "")) for r in log if r.get("title")}

    # Pre-filter pool with SQL where possible, finish in Python.
    sql = "SELECT * FROM books WHERE title IS NOT NULL "
    params: list = []
    if genres:
        wanted = [g.lower() for g in genres]
        if args.include_secondary:
            sql += " AND (LOWER(primary_genre) IN (" \
                   + ",".join("?" * len(wanted)) + ") " \
                   "OR LOWER(secondary_genre) IN (" \
                   + ",".join("?" * len(wanted)) + ")) "
            params.extend(wanted)
            params.extend(wanted)
        else:
            sql += " AND LOWER(primary_genre) IN (" \
                   + ",".join("?" * len(wanted)) + ") "
            params.extend(wanted)
    if args.min_gr:
        sql += " AND IFNULL(goodreads_rating, 0) >= ? "
        params.append(args.min_gr)
    if args.min_reviews:
        sql += " AND IFNULL(goodreads_reviews, 0) >= ? "
        params.append(args.min_reviews)
    if args.page_cap:
        sql += " AND (pages IS NULL OR pages <= ?) "
        params.append(args.page_cap)
    if args.page_floor:
        sql += " AND (pages IS NULL OR pages >= ?) "
        params.append(args.page_floor)

    pool: list[dict] = []
    for row in conn.execute(sql, params):
        e = row_to_entry(row)
        if (norm(e.get("title", "")), norm(e.get("author", ""))) in excluded:
            continue
        ok = True
        for tag in require_tags:
            if not e.get(tag):
                ok = False
                break
        if not ok:
            continue
        if args.author_entry_point_strict and not passes_entry_point_gate(e, log_authors):
            continue

        comps = comp_keys_for(conn, e["key"])
        rej = rejection_count(ledger, e.get("title", ""), e.get("author", ""))
        score, breakdown = score_candidate(
            e,
            comp_keys=comps,
            five_star_authors=five_star_authors,
            favorite_authors=favorite_authors,
            favorite_titles_norm=favorite_titles_norm,
            boost_tags=boost_tags,
            batch_genre_keys=genres,
            rej_count=rej,
        )
        pool.append({
            "key": e["key"],
            "entry": e,
            "score": score,
            "breakdown": breakdown,
            "is_deep_cut": is_deep_cut(e, batch_genre_keys=genres),
        })

    if not pool:
        die("no candidates after filtering", code=3)

    pool.sort(key=lambda x: -x["score"])

    selected: list[dict] = []
    selected_keys: set[str] = set()

    # cross-cut-floor: pre-fill required tag minima.
    for tag, n in cross_cut_floor.items():
        have = sum(1 for s in selected if s["entry"].get(tag))
        for cand in pool:
            if have >= n:
                break
            if cand["key"] in selected_keys:
                continue
            if cand["entry"].get(tag):
                selected.append(cand)
                selected_keys.add(cand["key"])
                have += 1

    # deep-cut slot.
    if args.deep_cut_slot and not any(s["is_deep_cut"] for s in selected):
        for cand in pool:
            if cand["key"] in selected_keys:
                continue
            if cand["is_deep_cut"]:
                selected.append(cand)
                selected_keys.add(cand["key"])
                break

    # fill the rest with top-ranked.
    for cand in pool:
        if len(selected) >= args.batch_size:
            break
        if cand["key"] in selected_keys:
            continue
        selected.append(cand)
        selected_keys.add(cand["key"])

    rng = random.Random(args.seed)
    rng.shuffle(selected)

    deep_cut_index = next((i for i, s in enumerate(selected) if s["is_deep_cut"]), None)

    # Rejection-cluster escalation.
    cluster_genres = set(g.lower() for g in (args.genre or []))
    require_indie = "indie" in require_tags or "indie" in boost_tags
    require_classic = "classic" in require_tags or "classic" in boost_tags
    page_bucket = None
    if args.page_cap:
        page_bucket = "short" if args.page_cap <= 350 else "medium" if args.page_cap <= 600 else "long"

    cluster_rejections = 0
    for r in ledger:
        if r.get("status") != "rejected":
            continue
        rec_genre = (r.get("primary_genre") or "").lower() if r.get("primary_genre") else None
        rec_indie = bool(r.get("indie"))
        rec_classic = bool(r.get("classic"))
        rec_pages = r.get("pages") or 0
        rec_bucket = None
        if rec_pages:
            rec_bucket = "short" if rec_pages <= 350 else "medium" if rec_pages <= 600 else "long"

        if cluster_genres and rec_genre and rec_genre not in cluster_genres:
            continue
        if require_indie and not rec_indie:
            continue
        if require_classic and not rec_classic:
            continue
        if page_bucket and rec_bucket and rec_bucket != page_bucket:
            continue
        cluster_rejections += 1

    probe_recommended = cluster_rejections >= args.probe_threshold
    probe_reason = None
    if probe_recommended:
        cluster_descr = []
        if cluster_genres:
            cluster_descr.append("/".join(sorted(cluster_genres)))
        if require_indie:
            cluster_descr.append("indie")
        if require_classic:
            cluster_descr.append("classic")
        if page_bucket:
            cluster_descr.append(f"{page_bucket} pages")
        cluster_label = "+".join(cluster_descr) or "this cluster"
        probe_reason = (
            f"{cluster_rejections} rejections in {cluster_label} this session — "
            "likely a framing miss, not candidate quality. Pause and probe before next batch."
        )

    batch_id = args.batch_id or f"{(args.genre or ['mixed'])[0]}-{int(time.time())}"
    payload = {
        "batch_id": batch_id,
        "deep_cut_index": deep_cut_index,
        "probe_recommended": probe_recommended,
        "probe_reason": probe_reason,
        "cluster_rejection_count": cluster_rejections,
        "filters_applied": {
            "genre": args.genre,
            "min_gr": args.min_gr,
            "min_reviews": args.min_reviews,
            "page_cap": args.page_cap,
            "page_floor": args.page_floor,
            "require_tag": list(require_tags),
            "boost_tag": boost_tags,
            "cross_cut_floor": cross_cut_floor,
            "author_entry_point_strict": args.author_entry_point_strict,
            "include_shown": args.include_shown,
        },
        "candidates": [
            {
                "key": s["key"],
                "title": s["entry"].get("title"),
                "author": s["entry"].get("author"),
                "primary_genre": s["entry"].get("primary_genre"),
                "secondary_genre": s["entry"].get("secondary_genre"),
                "series": s["entry"].get("series"),
                "series_status": s["entry"].get("series_status"),
                "series_position": s["entry"].get("series_position"),
                "pages": s["entry"].get("pages"),
                "gr_rating": s["entry"].get("goodreads_rating"),
                "gr_reviews": s["entry"].get("goodreads_reviews"),
                "indie": s["entry"].get("indie"),
                "classic": s["entry"].get("classic"),
                "is_deep_cut": s["is_deep_cut"],
                "score": round(s["score"], 3),
                **({"score_breakdown": s["breakdown"]} if args.explain else {}),
            }
            for s in selected
        ],
    }
    print(json.dumps(payload, ensure_ascii=False, indent=2))


def cmd_mark_shown(args, conn) -> None:
    if args.picks.startswith("@"):
        path = args.picks[1:]
        try:
            picks = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            die(f"bad --picks file {path}: {e}", code=2)
    else:
        try:
            picks = json.loads(args.picks)
        except json.JSONDecodeError as e:
            die(f"bad --picks JSON: {e}", code=2)

    if not isinstance(picks, list):
        die("--picks must be a JSON list of {title, author, status} records", code=2)

    ledger = load_ledger(args.ledger)
    ts = datetime.now(timezone.utc).isoformat()
    for p in picks:
        title = p.get("title", "")
        author = p.get("author", "")
        status = p.get("status", "shown")
        ce = lookup_by_pair(conn, title, author)
        rec = {
            "title": title,
            "author": author,
            "title_norm": norm(title),
            "author_norm": norm(author),
            "batch_id": args.batch_id,
            "status": status,
            "ts": ts,
            "primary_genre": p.get("primary_genre") or (ce.get("primary_genre") if ce else None),
            "indie": p.get("indie") if "indie" in p else (ce.get("indie") if ce else None),
            "classic": p.get("classic") if "classic" in p else (ce.get("classic") if ce else None),
            "pages": p.get("pages") or (ce.get("pages") if ce else None),
        }
        ledger.append(rec)

    if args.ledger == "-":
        # Write the *updated* ledger to stdout (model captures + persists).
        sys.stdout.write(json.dumps(ledger, ensure_ascii=False))
        print(json.dumps({"appended": len(picks), "batch_id": args.batch_id}),
              file=sys.stderr)
    else:
        # Legacy file mode (tests).
        Path(args.ledger).write_text(json.dumps(ledger, ensure_ascii=False),
                                     encoding="utf-8") if args.ledger else None
        print(json.dumps({"appended": len(picks), "batch_id": args.batch_id}))


def cmd_weight(args, _conn) -> None:
    ledger = load_ledger(args.ledger)
    rej = rejection_count(ledger, args.title, args.author)
    print(json.dumps({
        "title": args.title,
        "author": args.author,
        "rejection_count": rej,
        "penalty": rejection_penalty(rej),
    }))


def cmd_distribution(args, conn) -> None:
    by_genre: dict[str, dict[str, int]] = {}
    totals: dict[str, int] = {}
    for row in conn.execute(
        "SELECT primary_genre, indie, classic FROM books"
    ):
        g = row["primary_genre"] or "Unknown"
        by_genre.setdefault(g, {"indie": 0, "classic": 0, "total": 0})
        by_genre[g]["total"] += 1
        if row["indie"]:
            by_genre[g]["indie"] += 1
            totals["indie"] = totals.get("indie", 0) + 1
        if row["classic"]:
            by_genre[g]["classic"] += 1
            totals["classic"] = totals.get("classic", 0) + 1

    warnings = []
    for tag in ("indie", "classic"):
        total = totals.get(tag, 0)
        if total == 0:
            continue
        for g, counts in by_genre.items():
            share = counts[tag] / total
            if share > 0.6:
                warnings.append({
                    "tag": tag,
                    "concentrated_in": g,
                    "share": round(share, 2),
                    "n_in_genre": counts[tag],
                    "n_total": total,
                    "message": (
                        f"{int(share * 100)}% of {tag} books in your catalog are in {g}. "
                        f"Pull {tag} picks while building {g}, not after."
                    ),
                })
    print(json.dumps({"warnings": warnings, "by_genre": by_genre, "totals": totals},
                     ensure_ascii=False, indent=2))


def cmd_session_reset(args, _conn) -> None:
    """No-op in the stateless world.  Returns an empty ledger on stdout
    if --ledger - is set, mirroring the Code helper's "reset" semantics."""
    if args.ledger == "-":
        sys.stdout.write("[]")
    print(json.dumps({"reset": True}), file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def _add_data_paths(p: argparse.ArgumentParser, *, with_ledger: bool = False,
                    with_profile: bool = False) -> None:
    p.add_argument("--catalog", default=DEFAULT_CATALOG,
                   help=f"Path to SQLite catalog (default {DEFAULT_CATALOG})")
    p.add_argument("--log", default=DEFAULT_LOG,
                   help=f"Path to Reading_Log.csv (default {DEFAULT_LOG})")
    p.add_argument("--reading-list", default=DEFAULT_LIST,
                   help=f"Path to Reading_List.md (default {DEFAULT_LIST})")
    if with_ledger:
        p.add_argument("--ledger", default=None,
                       help="`-` reads ledger JSON from stdin (and writes "
                            "updated ledger to stdout for mark-shown). A path "
                            "reads/writes that file instead.")
    if with_profile:
        p.add_argument("--profile", default=DEFAULT_PROFILE,
                       help=f"Path to Profile.md (default {DEFAULT_PROFILE})")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="librarian_query.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("norm")
    sp.add_argument("text")
    sp.set_defaults(func=cmd_norm, needs_catalog=False)

    sp = sub.add_parser("is-read")
    sp.add_argument("--title", required=True)
    sp.add_argument("--author", required=True)
    _add_data_paths(sp)
    sp.set_defaults(func=cmd_is_read, needs_catalog=False)

    sp = sub.add_parser("is-on-list")
    sp.add_argument("--title", required=True)
    sp.add_argument("--author", required=True)
    _add_data_paths(sp)
    sp.set_defaults(func=cmd_is_on_list, needs_catalog=False)

    sp = sub.add_parser("is-shown")
    sp.add_argument("--title", required=True)
    sp.add_argument("--author", required=True)
    _add_data_paths(sp, with_ledger=True)
    sp.set_defaults(func=cmd_is_shown, needs_catalog=False)

    sp = sub.add_parser("exclusion-set")
    sp.add_argument("--include-shown", action="store_true")
    _add_data_paths(sp, with_ledger=True)
    sp.set_defaults(func=cmd_exclusion_set, needs_catalog=False)

    sp = sub.add_parser("unfinished-series")
    sp.add_argument("--min-rating", type=float, default=4.0)
    sp.add_argument("--min-avg", type=float, default=3.5)
    sp.add_argument("--min-last", type=float, default=3.0)
    _add_data_paths(sp)
    sp.set_defaults(func=cmd_unfinished_series, needs_catalog=True)

    sp = sub.add_parser("candidates")
    sp.add_argument("--genre", action="append")
    sp.add_argument("--include-secondary", action="store_true")
    sp.add_argument("--exclude-read", dest="exclude_read", action="store_true", default=True)
    sp.add_argument("--include-shown", action="store_true")
    sp.add_argument("--min-gr", type=float, default=3.8)
    sp.add_argument("--min-reviews", type=int, default=0)
    sp.add_argument("--page-cap", type=int, default=0)
    sp.add_argument("--page-floor", type=int, default=0)
    sp.add_argument("--require-tag", action="append")
    sp.add_argument("--boost-tag", action="append")
    sp.add_argument("--cross-cut-floor", action="append")
    sp.add_argument("--batch-size", type=int, default=4)
    sp.add_argument("--deep-cut-slot", action="store_true")
    sp.add_argument("--seed", type=int, default=None)
    sp.add_argument("--author-entry-point-strict",
                    dest="author_entry_point_strict",
                    action="store_true", default=True)
    sp.add_argument("--no-author-entry-point-strict",
                    dest="author_entry_point_strict", action="store_false")
    sp.add_argument("--probe-threshold", type=int, default=3)
    sp.add_argument("--batch-id", default=None)
    sp.add_argument("--explain", action="store_true")
    _add_data_paths(sp, with_ledger=True)
    sp.set_defaults(func=cmd_candidates, needs_catalog=True)

    sp = sub.add_parser("mark-shown")
    sp.add_argument("--batch-id", required=True)
    sp.add_argument("--picks", required=True,
                    help="JSON list, or @file.json, with {title, author, status} records")
    _add_data_paths(sp, with_ledger=True)
    sp.set_defaults(func=cmd_mark_shown, needs_catalog=True)

    sp = sub.add_parser("weight")
    sp.add_argument("--title", required=True)
    sp.add_argument("--author", required=True)
    _add_data_paths(sp, with_ledger=True)
    sp.set_defaults(func=cmd_weight, needs_catalog=False)

    sp = sub.add_parser("distribution")
    _add_data_paths(sp)
    sp.set_defaults(func=cmd_distribution, needs_catalog=True)

    sp = sub.add_parser("session-reset")
    _add_data_paths(sp, with_ledger=True)
    sp.set_defaults(func=cmd_session_reset, needs_catalog=False)

    sp = sub.add_parser("series-continuation")
    sp.add_argument("--title", required=True)
    sp.add_argument("--author", required=True)
    sp.add_argument("--include-shown", action="store_true")
    _add_data_paths(sp, with_ledger=True)
    sp.set_defaults(func=cmd_series_continuation, needs_catalog=True)

    sp = sub.add_parser("lookup")
    sp.add_argument("--query", required=True)
    sp.add_argument("--all-passes", action="store_true")
    _add_data_paths(sp, with_ledger=True)
    sp.set_defaults(func=cmd_lookup, needs_catalog=True)

    sp = sub.add_parser("profile-append")
    sp.add_argument("--section", required=True)
    sp.add_argument("--bullet", required=True)
    sp.add_argument("--stdio", action="store_true",
                    help="Read profile from stdin, write updated profile to "
                         "stdout (skill-driven Drive flush).  Default: edit "
                         "--profile in place.")
    _add_data_paths(sp, with_profile=True)
    sp.set_defaults(func=cmd_profile_append, needs_catalog=False)

    return p


def main() -> None:
    args = build_parser().parse_args()
    conn = None
    if getattr(args, "needs_catalog", False):
        conn = open_catalog(args.catalog)
    try:
        args.func(args, conn)
    finally:
        if conn is not None:
            conn.close()


if __name__ == "__main__":
    main()
