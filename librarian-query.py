#!/usr/bin/env python3
"""Librarian query helper — single chokepoint for candidate generation, exclusion
checks, and the shown-this-session ledger.

The librarian skill (`.claude/skills/librarian/SKILL.md`) routes every candidate
through this script. Inline Python in chat must not duplicate the gates.

JSON to stdout. Diagnostics to stderr. Exit codes:
  0 success / 1 boolean-false (e.g. `is-read` for an unread book)
  2 malformed input / 3 no candidates after filtering.

Reads: Library_Catalog.json, Library_Index.json, Reading_Log.csv,
       Reading_List.md, .librarian-session/shown.jsonl.
Writes: .librarian-session/shown.jsonl (only).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parent
CATALOG = REPO_ROOT / "Library_Catalog.json"
INDEX = REPO_ROOT / "Library_Index.json"
LOG = REPO_ROOT / "Reading_Log.csv"
LIST = REPO_ROOT / "Reading_List.md"
SESSION_DIR = REPO_ROOT / ".librarian-session"
LEDGER = SESSION_DIR / "shown.jsonl"

REJECTION_PENALTIES = (0.5, 1.5, 3.5, 6.0)  # cumulative-by-count

_QUOTE_NORMALIZE = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-",
    "​": "", "‌": "", "‍": "", "﻿": "",
})
_LEAD_PUNCT = re.compile(r"^[^\w]+", flags=re.UNICODE)
_LEAD_ARTICLE = re.compile(r"^(the|a|an)\s+", flags=re.IGNORECASE)
_TRAILING_PAREN = re.compile(r"\s*\([^)]*\)\s*$")
_BOOK1 = re.compile(r"^book\s*1(?![\d.])", flags=re.IGNORECASE)


def norm(s: str) -> str:
    """Canonical normalization for title/author matching.

    Strips smart quotes, em-dashes, zero-width chars, leading punctuation
    (`'Salem's Lot`), leading articles (`The Book of the New Sun`), trailing
    series-suffix parens, collapses initials (`R.F. Kuang` -> `r f kuang`),
    lowercases, and collapses whitespace.
    """
    if not s:
        return ""
    s = s.translate(_QUOTE_NORMALIZE)
    s = _TRAILING_PAREN.sub("", s)
    s = _LEAD_PUNCT.sub("", s)
    s = s.lower()
    s = _LEAD_ARTICLE.sub("", s)
    s = re.sub(r"\.", " ", s)  # period collapse for initials
    return " ".join(s.split())


# ----------------------- input loaders -----------------------

def _load_json(path: Path) -> dict:
    if not path.exists():
        die(f"missing input: {path}", code=2)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"malformed JSON {path}: {e}", code=2)


def load_catalog() -> dict:
    return _load_json(CATALOG)


def load_index() -> dict:
    return _load_json(INDEX)


def load_log() -> list[dict]:
    if not LOG.exists():
        die(f"missing input: {LOG}", code=2)
    with LOG.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def already_read_set(log: list[dict] | None = None) -> set[tuple[str, str]]:
    log = log if log is not None else load_log()
    return {(norm(r.get("title", "")), norm(r.get("authors", "")))
            for r in log if r.get("title")}


def list_set() -> set[tuple[str, str]]:
    """Parse Reading_List.md for `(norm(title), norm(author))` pairs.

    Recognizes both `| Title | Author | ... |` table rows and the Top-5 capstone
    section. Tolerant of an absent file (returns empty set).
    """
    if not LIST.exists():
        return set()
    out: set[tuple[str, str]] = set()
    text = LIST.read_text(encoding="utf-8")
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


# ----------------------- session ledger -----------------------

def ensure_session():
    SESSION_DIR.mkdir(exist_ok=True)
    if not LEDGER.exists():
        LEDGER.touch()


def ledger_records() -> list[dict]:
    if not LEDGER.exists():
        return []
    out = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def shown_set() -> set[tuple[str, str]]:
    return {(r["title_norm"], r["author_norm"]) for r in ledger_records()}


def rejection_count(title: str, author: str) -> int:
    tn, an = norm(title), norm(author)
    return sum(1 for r in ledger_records()
               if r.get("title_norm") == tn
               and r.get("author_norm") == an
               and r.get("status") == "rejected")


def rejection_penalty(count: int) -> float:
    if count <= 0:
        return 0.0
    if count - 1 < len(REJECTION_PENALTIES):
        return REJECTION_PENALTIES[count - 1]
    return REJECTION_PENALTIES[-1]


def append_ledger(rec: dict):
    ensure_session()
    with LEDGER.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


# ----------------------- candidate scoring -----------------------

def has_flag(row: dict, flag: str) -> bool:
    return any(t.strip() == flag for t in (row.get("my_tags") or "").split(","))


def parse_rating(raw):
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def is_book_one(series_position: str | None) -> bool:
    if not series_position:
        return False
    return bool(_BOOK1.match(series_position.strip()))


# series_role values that count as a valid entry point for an unread author.
_ENTRY_ROLES = {"standalone", "first", "loose-entry"}


def _passes_entry_point_gate(entry: dict, log_authors: set[str]) -> bool:
    """Universal author entry-point gate.

    Two-layer check:

    1. **Catalog-driven** (preferred): when `series_role` and/or
       `author_entry_point` are populated, use them. This is the long-term
       answer once `catalogue.py --audit-entry-points` has run.
    2. **Conservative fallback**: when both fields are null on the entry,
       fall back to the original rule — non-Standalone book by an unread
       author requires `series_position == "Book 1"`.

    Author IS in the log → always passes (reader has read this author and
    can judge whether to start with this book themselves).
    """
    if norm(entry.get("author", "")) in log_authors:
        return True

    role = entry.get("series_role")
    aep = entry.get("author_entry_point")

    # Catalog-driven path
    if role is not None or aep is not None:
        if aep is False:
            return False
        if role is not None and role not in _ENTRY_ROLES:
            # mid / late / loose-mid: drop for unread authors
            return False
        # role in entry-roles, OR role null with aep True/null → allow
        return True

    # Conservative fallback (fields not yet populated by audit)
    if (entry.get("series_status") and entry.get("series_status") != "Standalone"
            and not is_book_one(entry.get("series_position"))):
        return False
    return True


def is_deep_cut(entry: dict, batch_genre_keys: Iterable[str] = ()) -> bool:
    """Helper-internal definition. Never labeled in user-facing output."""
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


def score_candidate(
    entry: dict,
    *,
    log: list[dict],
    five_star_authors: set[str],
    favorite_authors: set[str],
    favorite_titles_norm: set[tuple[str, str]],
    boost_tags: dict[str, float],
    batch_genre_keys: Iterable[str] = (),
    rej_count: int = 0,
) -> tuple[float, dict]:
    breakdown = {}
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
    for c in entry.get("comparable_books") or []:
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


def _split_key(key: str) -> tuple[str, str] | None:
    if " - " not in key:
        return None
    title, author = key.rsplit(" - ", 1)
    return (norm(title), norm(author))


# ----------------------- subcommand handlers -----------------------

def cmd_norm(args):
    print(norm(args.text))


def cmd_is_read(args):
    s = already_read_set()
    hit = (norm(args.title), norm(args.author)) in s
    print(json.dumps({"hit": hit, "title": args.title, "author": args.author}))
    sys.exit(0 if hit else 1)


def cmd_is_on_list(args):
    s = list_set()
    hit = (norm(args.title), norm(args.author)) in s
    print(json.dumps({"hit": hit, "title": args.title, "author": args.author}))
    sys.exit(0 if hit else 1)


def cmd_is_shown(args):
    hit = (norm(args.title), norm(args.author)) in shown_set()
    print(json.dumps({"hit": hit, "title": args.title, "author": args.author}))
    sys.exit(0 if hit else 1)


def cmd_exclusion_set(args):
    out = {
        "already_read": [
            {"title_norm": t, "author_norm": a} for t, a in sorted(already_read_set())
        ],
        "on_list": [
            {"title_norm": t, "author_norm": a} for t, a in sorted(list_set())
        ],
    }
    if args.include_shown:
        out["shown_this_session"] = [
            {"title_norm": t, "author_norm": a} for t, a in sorted(shown_set())
        ]
    print(json.dumps(out, ensure_ascii=False, indent=2))


def _series_order_key(entry: dict) -> tuple[float, str]:
    p = (entry.get("series_position") or "").lower()
    m = re.search(r"book\s*([\d.]+)", p)
    if m:
        try:
            return (float(m.group(1)), entry.get("title") or "")
        except ValueError:
            pass
    return (999.0, entry.get("title") or "")


def _index_catalog_by_pair(entries: dict) -> dict[tuple[str, str], dict]:
    """Index catalog entries by (norm(title), norm(author)).

    Two passes so subtitle-truncated rows in Reading_Log resolve to the right
    catalog entry without shadowing books whose actual title has a colon:

    Pass 1 — full title and full catalog-key prefix (priority).
    Pass 2 — pre-colon prefix of the entry title; pre-` - ` prefix of the
             catalog key. Only fills a slot if Pass 1 left it empty.

    Example: catalog key `Side Jobs - Jim Butcher` with entry title
    `Side Jobs: Stories from the Dresden Files` is indexed under
    `(side jobs stories from the dresden files, jim butcher)` (full title)
    AND `(side jobs, jim butcher)` (key prefix + colon prefix). A
    Reading_Log row `Side Jobs / Jim Butcher` resolves cleanly.
    """
    out: dict[tuple[str, str], dict] = {}

    # Pass 1: full forms (highest priority).
    for k, e in entries.items():
        author_n = norm(e.get("author", ""))
        full_title_n = norm(e.get("title", ""))
        if full_title_n:
            pair = (full_title_n, author_n)
            out.setdefault(pair, {"key": k, **e})
        # Catalog key in form "Title - Author" — index by the title portion
        # of the key in case it differs from entry["title"] (short-titled key).
        if " - " in k:
            key_title = k.rsplit(" - ", 1)[0]
            key_pair = (norm(key_title), author_n)
            out.setdefault(key_pair, {"key": k, **e})

    # Pass 2: subtitle prefixes (only fill empty slots).
    for k, e in entries.items():
        author_n = norm(e.get("author", ""))
        title = e.get("title") or ""
        # Pre-colon prefix of entry title.
        if ":" in title:
            prefix = title.split(":", 1)[0]
            pair = (norm(prefix), author_n)
            if pair not in out:
                out[pair] = {"key": k, **e}

    return out


def cmd_unfinished_series(args):
    """Phase 0 input: series the reader is mid-way through and likely wants
    to continue. Three gates:

      1. max(rating) >= --min-rating (any high point in the series at all)
      2. avg(rating) >= --min-avg     (overall enjoyment held up)
      3. last_rating  >= --min-last   (most recent series read wasn't a clear "I'm done")

    Plus: no `*completed` flag on any entry.

    `last_rating` is the rating on the highest-position read entry — i.e.
    where the reader actually stopped. A series rated 5/5/2 (Book 1, 2, 3)
    is filtered out; the trajectory says they DNF'd. A series rated 5/4/4
    stays; the trajectory says they liked it and just paused.
    """
    log = load_log()
    cat = load_catalog()
    entries = cat["entries"]
    pair_to_entry = _index_catalog_by_pair(entries)

    series_to_books: dict[str, list[dict]] = {}
    for k, e in entries.items():
        s = e.get("series")
        if not s or e.get("series_status") == "Standalone":
            continue
        series_to_books.setdefault(s, []).append({"key": k, **e})

    # group log rows by catalog series_name (resolved via the pair index)
    series_log_rows: dict[str, list[tuple[dict, dict]]] = {}
    for r in log:
        if not r.get("title"):
            continue
        pair = (norm(r["title"]), norm(r.get("authors", "")))
        ce = pair_to_entry.get(pair)
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

        # last_rating = rating on the highest-position read entry the reader rated
        rated_by_pos = sorted(rated, key=lambda t: _series_order_key(t[1]))
        last_rating = rated_by_pos[-1][2]
        if last_rating < args.min_last:
            continue

        if any(has_flag(r, "*completed") for r, _ in rows):
            continue

        ordered = sorted(series_to_books.get(series, []), key=_series_order_key)
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
            "avg_rating_in_series": round(sum(ratings) / len(ratings), 2),
            "next_book_in_catalog": next_book.get("title") if next_book else None,
            "next_position": next_book.get("series_position") if next_book else None,
            "next_pages": next_book.get("pages") if next_book else None,
            "next_key": next_book.get("key") if next_book else None,
        })

    out.sort(key=lambda r: -r["max_rating_in_series"])
    print(json.dumps(out, ensure_ascii=False, indent=2))


# ----------------------- series-continuation -----------------------

def _series_sub_thread(series_position: str | None) -> str | None:
    """Extract sub-thread label from a series_position string.

    Examples:
      "Book 1 of Age of Madness"        -> "age of madness"
      "Book 8 (Age of Madness #2)"      -> "age of madness"
      "Book 34 (City Watch Book 7)"     -> "city watch"
      "Book 5"                          -> None
      "Book 1"                          -> None
    """
    if not series_position:
        return None
    p = series_position.strip()

    # Prefer parens content if present.
    m = re.search(r"\(([^)]+)\)", p)
    if m:
        inner = m.group(1)
    else:
        # Fall back to text after the leading "Book N" or "N.M".
        inner = re.sub(r"^[Bb]ook\s*\d+(\.\d+)?\s*", "", p)
        inner = re.sub(r"^of\s+", "", inner, flags=re.IGNORECASE)

    if not inner:
        return None
    # Strip trailing "Book N" / "#N" / "novella" / etc.
    inner = re.sub(r"\s+Book\s*\d+(\.\d+)?$", "", inner, flags=re.IGNORECASE)
    inner = re.sub(r"\s*#\d+(\.\d+)?$", "", inner)
    inner = re.sub(r"\s+\(?(novella|coda|prequel)\)?$", "", inner, flags=re.IGNORECASE)
    inner = inner.strip().lower()
    return inner or None


def cmd_series_continuation(args):
    """Return next unread book in the same series as the given title.

    Used by Phase 2 after a series book is selected: surface the next book
    as a follow-up checklist option (never auto-add).
    """
    cat = load_catalog()
    entries = cat["entries"]
    pair_to_entry = _index_catalog_by_pair(entries)

    pair = (norm(args.title), norm(args.author))
    src = pair_to_entry.get(pair)
    if not src:
        print(json.dumps({"next": None, "reason": "source book not in catalog"}))
        sys.exit(0)

    series = src.get("series")
    if not series or src.get("series_status") not in ("Short Series", "Long Series"):
        print(json.dumps({"next": None, "reason": "not a sequential series"}))
        sys.exit(0)

    # All catalog entries in this series, ordered.
    siblings = [{"key": k, **e} for k, e in entries.items() if e.get("series") == series]
    siblings.sort(key=_series_order_key)

    # Read / on-list / shown exclusions.
    log = load_log()
    excluded_pairs = already_read_set(log) | list_set()
    if not args.include_shown:
        excluded_pairs |= shown_set()

    src_pos = src.get("series_position") or ""
    src_n = (norm(src.get("title", "")), norm(src.get("author", "")))
    src_sub = _series_sub_thread(src_pos)

    # If the source belongs to a sub-thread (e.g. Age of Madness within
    # First Law World), restrict siblings to that sub-thread first; fall
    # back to the parent series if no sub-thread match.
    def _candidate_books(restrict_to_sub):
        for book in siblings:
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
            # Skip prequels / 0.x entries.
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


# ----------------------- lookup -----------------------

def cmd_lookup(args):
    """Three-pass fuzzy match against the catalog. Replaces inline find().

    Pass 1: exact key match (case-insensitive)
    Pass 2: title substring (full or pre-colon prefix)
    Pass 3: series substring

    Returns each match with its canonical key, identifying fields, and
    exclusion-gate booleans.
    """
    cat = load_catalog()
    entries = cat["entries"]
    q = args.query.strip()
    qn = norm(q)

    matches: list[dict] = []
    seen_keys: set[str] = set()

    def add(k: str):
        if k in seen_keys:
            return
        seen_keys.add(k)
        e = entries[k]
        title = e.get("title") or ""
        author = e.get("author") or ""
        pair = (norm(title), norm(author))
        matches.append({
            "key": k,
            "title": title,
            "author": author,
            "series": e.get("series"),
            "series_position": e.get("series_position"),
            "series_status": e.get("series_status"),
            "primary_genre": e.get("primary_genre"),
            "pages": e.get("pages"),
            "is_already_read": pair in already_read_set(),
            "is_on_list": pair in list_set(),
            "is_shown": pair in shown_set(),
        })

    # Pass 1: exact key match.
    for k in entries:
        if k.lower() == q.lower():
            add(k)
    if matches and not args.all_passes:
        print(json.dumps(matches, ensure_ascii=False, indent=2))
        sys.exit(0)

    # Pass 2: title substring (incl. pre-colon prefix).
    for k, e in entries.items():
        title = (e.get("title") or "").lower()
        if qn and (qn in norm(title) or qn in norm(title.split(":", 1)[0])):
            add(k)
    if matches and not args.all_passes:
        print(json.dumps(matches, ensure_ascii=False, indent=2))
        sys.exit(0)

    # Pass 3: series substring.
    for k, e in entries.items():
        s = (e.get("series") or "").lower()
        if qn and qn in norm(s):
            add(k)

    print(json.dumps(matches, ensure_ascii=False, indent=2))
    if not matches:
        sys.exit(1)


# ----------------------- profile-append -----------------------

PROFILE_PATH = REPO_ROOT / "Profile.md"


def cmd_profile_append(args):
    """Append a bullet to a named section of Profile.md.

    Idempotent on identical bullets (no duplicate). Creates the section
    if missing. Never rewrites the rest of the file.
    """
    section = args.section.strip()
    bullet = args.bullet.strip()

    if not PROFILE_PATH.exists():
        # Bootstrap a minimal Profile.md scaffold.
        PROFILE_PATH.write_text(
            "# Reader Profile\n\n"
            "_Living memory — updated throughout reading-list builds._\n\n",
            encoding="utf-8",
        )

    text = PROFILE_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()

    # Find the section heading (## <section>).
    target = f"## {section}"
    section_idx = next(
        (i for i, ln in enumerate(lines) if ln.strip().lower() == target.lower()),
        None,
    )

    if section_idx is None:
        # Append a new section at end.
        if lines and lines[-1].strip():
            lines.append("")
        lines.append(target)
        lines.append("")
        lines.append(f"- {bullet}")
        lines.append("")
        PROFILE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(json.dumps({"appended": True, "section": section, "bullet": bullet,
                          "created_section": True}))
        return

    # Find the next section boundary.
    end_idx = len(lines)
    for j in range(section_idx + 1, len(lines)):
        if lines[j].startswith("## "):
            end_idx = j
            break

    # Idempotent check inside the section.
    existing = [ln.strip() for ln in lines[section_idx + 1:end_idx]]
    if any(ln.lstrip("- ").strip() == bullet for ln in existing if ln.startswith("- ")):
        print(json.dumps({"appended": False, "section": section, "bullet": bullet,
                          "reason": "duplicate"}))
        return

    # Insert before any trailing blank lines in the section.
    insert_at = end_idx
    while insert_at > section_idx + 1 and not lines[insert_at - 1].strip():
        insert_at -= 1
    lines.insert(insert_at, f"- {bullet}")
    PROFILE_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(json.dumps({"appended": True, "section": section, "bullet": bullet,
                      "created_section": False}))


def _build_favorite_pools(log: list[dict]):
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


def cmd_candidates(args):
    cat = load_catalog()
    log = load_log()
    entries = cat["entries"]

    excluded = already_read_set(log) | list_set()
    if not args.include_shown:
        excluded |= shown_set()

    five_star_authors, favorite_authors, favorite_titles_norm = _build_favorite_pools(log)

    boost_tags = {}
    for spec in args.boost_tag or []:
        try:
            tag, factor = spec.split(":", 1)
            boost_tags[tag] = float(factor)
        except ValueError:
            die(f"bad --boost-tag {spec!r}; expected tag:factor", code=2)

    cross_cut_floor = {}
    for spec in args.cross_cut_floor or []:
        try:
            tag, n = spec.split(":", 1)
            cross_cut_floor[tag] = int(n)
        except ValueError:
            die(f"bad --cross-cut-floor {spec!r}; expected tag:n", code=2)

    require_tags = set(args.require_tag or [])
    genres = [g for g in (args.genre or [])]
    log_authors = {norm(r.get("authors", "")) for r in log if r.get("title")}

    pool = []
    for k, e in entries.items():
        if not e.get("title"):
            continue
        if (norm(e.get("title", "")), norm(e.get("author", ""))) in excluded:
            continue
        # genre filter
        if genres:
            primary = (e.get("primary_genre") or "").lower()
            secondary = (e.get("secondary_genre") or "").lower()
            wanted = {g.lower() for g in genres}
            if not (primary in wanted or (args.include_secondary and secondary in wanted)):
                continue
        # tag floors / requirements
        ok = True
        for tag in require_tags:
            if not e.get(tag):
                ok = False
                break
        if not ok:
            continue
        # gr / reviews / pages floors and caps
        gr = e.get("goodreads_rating") or 0
        if gr < args.min_gr:
            continue
        rev = e.get("goodreads_reviews") or 0
        if rev < args.min_reviews:
            continue
        pages = e.get("pages") or 0
        if args.page_cap and pages and pages > args.page_cap:
            continue
        if args.page_floor and pages and pages < args.page_floor:
            continue
        # author entry-point gate
        if args.author_entry_point_strict and not _passes_entry_point_gate(e, log_authors):
            continue

        rej = rejection_count(e.get("title", ""), e.get("author", ""))
        score, breakdown = score_candidate(
            e,
            log=log,
            five_star_authors=five_star_authors,
            favorite_authors=favorite_authors,
            favorite_titles_norm=favorite_titles_norm,
            boost_tags=boost_tags,
            batch_genre_keys=genres,
            rej_count=rej,
        )
        pool.append({"key": k, "entry": e, "score": score, "breakdown": breakdown,
                     "is_deep_cut": is_deep_cut(e, batch_genre_keys=genres)})

    if not pool:
        die("no candidates after filtering", code=3)

    pool.sort(key=lambda x: -x["score"])

    selected: list[dict] = []
    selected_keys: set[str] = set()

    # cross-cut-floor: pre-fill required tag minima
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

    # deep-cut slot
    if args.deep_cut_slot and not any(s["is_deep_cut"] for s in selected):
        for cand in pool:
            if cand["key"] in selected_keys:
                continue
            if cand["is_deep_cut"]:
                selected.append(cand)
                selected_keys.add(cand["key"])
                break

    # fill the rest with top-ranked
    for cand in pool:
        if len(selected) >= args.batch_size:
            break
        if cand["key"] in selected_keys:
            continue
        selected.append(cand)
        selected_keys.add(cand["key"])

    # shuffle so deep-cut position isn't always the same slot
    rng = random.Random(args.seed)
    rng.shuffle(selected)

    deep_cut_index = next((i for i, s in enumerate(selected) if s["is_deep_cut"]), None)

    # Rejection-cluster escalation. Count rejections in the same cross-cut
    # cluster (genre × indie? × classic? × page-bucket). If at threshold,
    # surface a probe_recommended flag so the librarian fires pause-and-probe
    # instead of generating yet another batch.
    cluster_genres = set(g.lower() for g in (args.genre or []))
    require_indie = "indie" in require_tags or "indie" in boost_tags
    require_classic = "classic" in require_tags or "classic" in boost_tags
    page_bucket = None
    if args.page_cap:
        page_bucket = "short" if args.page_cap <= 350 else "medium" if args.page_cap <= 600 else "long"

    cluster_rejections = 0
    for r in ledger_records():
        if r.get("status") != "rejected":
            continue
        # Match cluster filter dimensions on the original entry if cached.
        # We keep this loose: any rejection in the same genre+indie/classic+page bucket counts.
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


def cmd_mark_shown(args):
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

    # Look up cluster fields from catalog so the ledger records carry enough
    # context for rejection-cluster escalation in `candidates`.
    cat = load_catalog()
    pair_to_entry = _index_catalog_by_pair(cat["entries"])

    ts = datetime.now(timezone.utc).isoformat()
    for p in picks:
        title = p.get("title", "")
        author = p.get("author", "")
        status = p.get("status", "shown")  # selected | rejected | shown
        ce = pair_to_entry.get((norm(title), norm(author)))
        rec = {
            "title": title,
            "author": author,
            "title_norm": norm(title),
            "author_norm": norm(author),
            "batch_id": args.batch_id,
            "status": status,
            "ts": ts,
            # Cluster fields for rejection-cluster escalation. Caller can pass
            # them explicitly (overrides catalog lookup); else inferred from catalog.
            "primary_genre": p.get("primary_genre") or (ce.get("primary_genre") if ce else None),
            "indie": p.get("indie") if "indie" in p else (ce.get("indie") if ce else None),
            "classic": p.get("classic") if "classic" in p else (ce.get("classic") if ce else None),
            "pages": p.get("pages") or (ce.get("pages") if ce else None),
        }
        append_ledger(rec)
    print(json.dumps({"appended": len(picks), "batch_id": args.batch_id}))


def cmd_weight(args):
    rej = rejection_count(args.title, args.author)
    print(json.dumps({
        "title": args.title,
        "author": args.author,
        "rejection_count": rej,
        "penalty": rejection_penalty(rej),
    }))


def cmd_distribution(args):
    cat = load_catalog()
    by_genre: dict[str, dict[str, int]] = {}
    totals: dict[str, int] = {}
    for e in cat["entries"].values():
        g = e.get("primary_genre") or "Unknown"
        by_genre.setdefault(g, {"indie": 0, "classic": 0, "total": 0})
        by_genre[g]["total"] += 1
        if e.get("indie"):
            by_genre[g]["indie"] += 1
            totals["indie"] = totals.get("indie", 0) + 1
        if e.get("classic"):
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
                        f"{int(share*100)}% of {tag} books in your catalog are in {g}. "
                        f"Pull {tag} picks while building {g}, not after."
                    ),
                })
    print(json.dumps({"warnings": warnings, "by_genre": by_genre, "totals": totals},
                     ensure_ascii=False, indent=2))


def cmd_session_reset(args):
    if LEDGER.exists():
        LEDGER.unlink()
    print(json.dumps({"reset": True, "ledger": str(LEDGER)}))


# ----------------------- argparse wiring -----------------------

def die(msg: str, code: int = 2):
    print(f"librarian-query: {msg}", file=sys.stderr)
    sys.exit(code)


def build_parser():
    p = argparse.ArgumentParser(prog="librarian-query.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("norm")
    sp.add_argument("text")
    sp.set_defaults(func=cmd_norm)

    for name, fn in (("is-read", cmd_is_read),
                     ("is-on-list", cmd_is_on_list),
                     ("is-shown", cmd_is_shown)):
        sp = sub.add_parser(name)
        sp.add_argument("--title", required=True)
        sp.add_argument("--author", required=True)
        sp.set_defaults(func=fn)

    sp = sub.add_parser("exclusion-set")
    sp.add_argument("--include-shown", action="store_true")
    sp.set_defaults(func=cmd_exclusion_set)

    sp = sub.add_parser("unfinished-series")
    sp.add_argument("--min-rating", type=float, default=4.0,
                    help="Series must have at least one rating ≥ this (default 4.0)")
    sp.add_argument("--min-avg", type=float, default=3.5,
                    help="Series average rating must be ≥ this (default 3.5) — "
                         "drops series the reader broadly didn't enjoy")
    sp.add_argument("--min-last", type=float, default=3.0,
                    help="Reader's most-recent rating in the series must be ≥ this "
                         "(default 3.0) — drops series with a clear DNF trajectory")
    sp.set_defaults(func=cmd_unfinished_series)

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
    sp.add_argument("--probe-threshold", type=int, default=3,
                    help="Number of cluster-matched rejections that triggers "
                         "probe_recommended=true in the response (default 3).")
    sp.add_argument("--batch-id", default=None)
    sp.add_argument("--explain", action="store_true")
    sp.set_defaults(func=cmd_candidates)

    sp = sub.add_parser("mark-shown")
    sp.add_argument("--batch-id", required=True)
    sp.add_argument("--picks", required=True,
                    help="JSON list, or @file.json, with {title, author, status} records")
    sp.set_defaults(func=cmd_mark_shown)

    sp = sub.add_parser("weight")
    sp.add_argument("--title", required=True)
    sp.add_argument("--author", required=True)
    sp.set_defaults(func=cmd_weight)

    sp = sub.add_parser("distribution")
    sp.set_defaults(func=cmd_distribution)

    sp = sub.add_parser("session-reset")
    sp.set_defaults(func=cmd_session_reset)

    sp = sub.add_parser("series-continuation")
    sp.add_argument("--title", required=True)
    sp.add_argument("--author", required=True)
    sp.add_argument("--include-shown", action="store_true",
                    help="Diagnostic: include books already shown this session")
    sp.set_defaults(func=cmd_series_continuation)

    sp = sub.add_parser("lookup")
    sp.add_argument("--query", required=True,
                    help="Title, partial title, or series name")
    sp.add_argument("--all-passes", action="store_true",
                    help="Run all three match passes and merge results "
                         "(default: stop at first pass with a hit)")
    sp.set_defaults(func=cmd_lookup)

    sp = sub.add_parser("profile-append")
    sp.add_argument("--section", required=True,
                    help='Section header to append under (e.g. "Negative indicators")')
    sp.add_argument("--bullet", required=True,
                    help="Bullet text (no leading dash). Idempotent if identical bullet exists.")
    sp.set_defaults(func=cmd_profile_append)

    return p


def main():
    args = build_parser().parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
