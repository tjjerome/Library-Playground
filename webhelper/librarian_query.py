#!/usr/bin/env python3
"""Librarian query helper — claude.ai port, post-recomposition rewrite.

Subcommands plus `norm`:

    recommend          constraint-satisfaction candidate generation,
                       vector-spread sampling, returns 12-18 candidates
    status             actionable signals only — no dashboard
    series-fit         scope-aware series navigation
    unfinished-series  Phase 0 gate
    compare            swap analysis for a reader-proposed add
    author-history     log-side read/rating history for an author
    reconcile          log ↔ catalog match audit; --reading-list adds list audit
    bootstrap-state    derive build_state.json from Profile.md taste vectors
    normalize-catalog  rewrite stored normalized columns with live norm()
    norm               shared normaliser (used by library-cataloguer)

The recommender returns *material*, not a turn shape. The skill
chooses how many of the 12-18 candidates to surface and in what
shape (one pick / A-B / scan / deep dive). See
RECOMPOSITION_PLAN.md §4 for the design intent.

Input layout (override via flags):

    Library_Catalog.sqlite      catalog
    Reading_Log.csv             history
    Reading_List.md             current picks (source of truth)
    Profile.md                  free-form preference notes (optional)
    build_state.json            vectors, floors, events, n_target

Output: JSON to stdout. Diagnostics to stderr. Exit codes:
    0 success / 2 malformed input / 3 no candidates after filtering.
"""

from __future__ import annotations

import argparse
import difflib
import json
import math
import random
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    from .book_identity import (  # type: ignore
        norm, title_short, title_fold, title_keys, author_parts,
        authors_match, same_book, _swap_lastfirst)
except (ImportError, ValueError):
    try:
        from book_identity import (  # type: ignore  # noqa: E402
            norm, title_short, title_fold, title_keys, author_parts,
            authors_match, same_book, _swap_lastfirst)
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from webhelper.book_identity import (  # noqa: E402
            norm, title_short, title_fold, title_keys, author_parts,
            authors_match, same_book, _swap_lastfirst)

# Back-compat local aliases for the older underscored names still
# referenced below; one implementation, in book_identity.
_author_matches = authors_match
_title_fold = title_fold


# ---------------------------------------------------------------------------
# Defaults / paths
# ---------------------------------------------------------------------------

DEFAULT_CATALOG = "Library_Catalog.sqlite"
DEFAULT_LOG = "Reading_Log.csv"
DEFAULT_LIST = "Reading_List.md"
DEFAULT_PROFILE = "Profile.md"
DEFAULT_BUILD_STATE = "build_state.json"

VARIANCE_MODES = ("similar", "balanced", "broad", "adjacent", "focused")

# Structural discovery floor.  `balanced` (the new default) and
# `broad` reserve a fixed fraction of the result for residual
# (outside-vector) picks so breadth is guaranteed by construction
# rather than left to caller judgement.  `similar`, `adjacent`, and
# `focused` carry no forced residual quota.
RESIDUAL_QUOTA = {"balanced": 0.20, "broad": 0.375}

# Reader expansion appetite (build_state.preferences.expansion_appetite)
# maps to the implicit --variance default when the caller doesn't pass
# one explicitly.
APPETITE_VARIANCE = {"high": "broad", "moderate": "balanced",
                     "low": "similar"}

QUALITY_FLOOR = 3.8

# Goodreads as a ranking input (Plan C Issues 3 & 4).  GR is one
# weighted signal among many — never the headline.  The score term is
# GR_RANK_WEIGHT * clamp(effective_gr_signal - GR_RANK_PIVOT, ±1).
# Pivot ≈ the catalog-wide median rating above the quality floor, so
# the term is centred (it reorders rather than uniformly shifting) and
# small enough that a strong vector/comp match still outranks a
# mediocre rating.  Nothing is filtered for a low rating — no floor.
GR_RANK_PIVOT = 4.1
GR_RANK_WEIGHT = 1.0
GR_RANK_CLAMP = 1.0

# Selection-bias series-rating correction (Plan C Issue 4).
SERIES_TIGHT_STATUS = ("Short Series", "Long Series")
SERIES_TIGHT_ROLES = ("first", "mid", "late")
# Drop an entry from the retention curve when its review count is an
# anomalous fraction of the series median (mis-scraped rows, e.g. a
# Red Rising book with 278 reviews against siblings in the hundred-
# thousands).
SERIES_OUTLIER_FRAC = 0.05
# Heckman blend: mostly the corrected series baseline, lightly the
# book's own rating.  The 0.75 lets a corrected series carry a weak
# opener; the 0.25 keeps the book's own rating from being discarded.
SERIES_BLEND_SERIES = 0.75
SERIES_BLEND_OWN = 0.25
# Domain-knowledge default when fewer than 3 mainline entries make an
# OLS regression impossible (rho ≈ 0.6, sigma ≈ 1.0 ⇒ beta ≈ 0.6).
SERIES_BETA_DEFAULT = 0.6

DEFAULT_N = 15
MIN_N = 12
MAX_N = 18

# Commitment-load thresholds (used to derive load from the current
# Reading_List, not from a stale build_state field).
LONG_SERIES_THRESHOLD = 3       # ≥3 picks from one series = real commitment
DOORSTOP_PAGES = 600

# Adjacency-mode tuning.  See partial_vector_match / _assign_strata_adjacent
# for how these get used.  Central match = candidate sits inside a
# vector's cluster (covers ≥CENTRAL_MIN_FRAC of the vector OR
# ≥CENTRAL_MIN_ABS overlap, whichever is smaller).  Adjacent = shares
# one axis (signals OR themes) with the vector while pulling outside on
# the other axis.
ADJACENT_CENTRAL_MIN_FRAC = 0.50
ADJACENT_CENTRAL_MIN_ABS = 3

_BOOK1 = re.compile(r"^book\s*1(?![\d.])", flags=re.IGNORECASE)
_ENTRY_ROLES = {"standalone", "first", "loose-entry"}


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


def row_to_entry(row: sqlite3.Row) -> dict:
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


def is_book_one(series_position: str | None) -> bool:
    if not series_position:
        return False
    return bool(_BOOK1.match(series_position.strip()))


_SERIES_NUM = re.compile(r"(\d+(?:\.\d+)?)")


def _series_book_number(series_position: str | None) -> float | None:
    """First numeric token in a series_position string as a float.
    `Book 1` → 1.0, `Book 2.5` → 2.5, `Prequel`/None → None.  A
    non-integer value marks a novella / side entry — excluded from the
    mainline retention curve (Plan C Issue 4)."""
    if not series_position:
        return None
    m = _SERIES_NUM.search(series_position)
    return float(m.group(1)) if m else None


# ---------------------------------------------------------------------------
# Standard normal distribution (Plan C Issue 4 — Heckman correction).
# scipy is not a project dependency and is not worth adding for three
# small functions; implement directly.
# ---------------------------------------------------------------------------

_SQRT_2PI = math.sqrt(2.0 * math.pi)


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / _SQRT_2PI


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# Acklam's rational approximation to the inverse normal CDF.
# Relative error < 1.15e-9 across (0, 1).
_PPF_A = (-3.969683028665376e+01, 2.209460984245205e+02,
          -2.759285104469687e+02, 1.383577518672690e+02,
          -3.066479806614716e+01, 2.506628277459239e+00)
_PPF_B = (-5.447609879822406e+01, 1.615858368580409e+02,
          -1.556989798598866e+02, 6.680131188771972e+01,
          -1.328068155288572e+01)
_PPF_C = (-7.784894002430293e-03, -3.223964580411365e-01,
          -2.400758277161838e+00, -2.549732539343734e+00,
          4.374664141464968e+00, 2.938163982698783e+00)
_PPF_D = (7.784695709041462e-03, 3.224671290700398e-01,
          2.445134137142996e+00, 3.754408661907416e+00)
_PPF_PLOW = 0.02425


def _norm_ppf(p: float) -> float:
    if not 0.0 < p < 1.0:
        raise ValueError(f"_norm_ppf domain: {p}")
    if p < _PPF_PLOW:
        q = math.sqrt(-2.0 * math.log(p))
        return ((((((_PPF_C[0] * q + _PPF_C[1]) * q + _PPF_C[2]) * q
                    + _PPF_C[3]) * q + _PPF_C[4]) * q + _PPF_C[5])
                / ((((_PPF_D[0] * q + _PPF_D[1]) * q + _PPF_D[2]) * q
                    + _PPF_D[3]) * q + 1.0))
    if p > 1.0 - _PPF_PLOW:
        q = math.sqrt(-2.0 * math.log(1.0 - p))
        return -((((((_PPF_C[0] * q + _PPF_C[1]) * q + _PPF_C[2]) * q
                     + _PPF_C[3]) * q + _PPF_C[4]) * q + _PPF_C[5])
                 / ((((_PPF_D[0] * q + _PPF_D[1]) * q + _PPF_D[2]) * q
                     + _PPF_D[3]) * q + 1.0))
    q = p - 0.5
    r = q * q
    return ((((((_PPF_A[0] * r + _PPF_A[1]) * r + _PPF_A[2]) * r
               + _PPF_A[3]) * r + _PPF_A[4]) * r + _PPF_A[5]) * q
            / (((((_PPF_B[0] * r + _PPF_B[1]) * r + _PPF_B[2]) * r
                 + _PPF_B[3]) * r + _PPF_B[4]) * r + 1.0))


# ---------------------------------------------------------------------------
# Log / list / profile loaders
# ---------------------------------------------------------------------------

def load_log(path: str) -> list[dict]:
    import csv
    p = Path(path)
    if not p.exists():
        die(f"missing reading log: {p}", code=2)
    with p.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def already_read_set(log: list[dict]) -> set[tuple[str, str]]:
    return {(norm(r.get("title", "")), norm(r.get("authors", "")))
            for r in log if r.get("title")}


def _strip_md_emphasis(s: str) -> str:
    """Remove surrounding markdown emphasis (*, _, **, __, `) from a
    table cell.  Reading_List.md writes titles as *italic*; the catalog
    stores them plain.  Without this, norm("*Red Country*") leaves a
    trailing "*" (norm strips leading punctuation only) and the row
    matches nothing — see Plan C Issue 1."""
    s = s.strip()
    for _ in range(2):  # handle ** and __ as well as * and _
        for mark in ("**", "__", "*", "_", "`"):
            if (len(s) > len(mark) * 2
                    and s.startswith(mark) and s.endswith(mark)):
                s = s[len(mark):-len(mark)].strip()
    return s


def list_set(path: str) -> set[tuple[str, str]]:
    p = Path(path)
    if not p.exists():
        return set()
    out: set[tuple[str, str]] = set()
    text = p.read_text(encoding="utf-8")
    # D-2: only parse rows belonging to a table whose header carries
    # *both* a `title` and an `author` column.  This covers the main
    # list and the "Upcoming & recent releases" table while excluding
    # the three-column Goals / Series-balance / Floors pipe tables,
    # whose rows would otherwise become phantom (title, author) pairs.
    ti: int | None = None
    ai: int | None = None
    pending: list[str] | None = None  # row preceding a potential separator
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            ti = ai = None  # blank line / prose ends the table
            pending = None
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 2:
            pending = None
            continue
        # A separator row resolves the row before it: if that header
        # carried both columns this is a book table, else it isn't.
        if all(c and set(c) <= set("-: ") for c in cells):
            if pending is not None:
                low = [c.lower() for c in pending]
                if "title" in low and "author" in low:
                    ti, ai = low.index("title"), low.index("author")
                else:
                    ti = ai = None
            pending = None
            continue
        if ti is not None and ai is not None and max(ti, ai) < len(cells):
            title = _strip_md_emphasis(cells[ti])
            author = _strip_md_emphasis(cells[ai])
            if title and not set(title) <= set("- :"):
                out.add((norm(title), norm(author)))
        pending = cells  # may be the header of the next table
    return out


def list_key_map(path: str) -> dict[tuple[str, str], str]:
    """Parse Reading_List.md and return {(title_norm, author_norm): catalog_key}
    for rows that carry a <!-- key:... --> HTML comment.  Rows without the
    comment are absent from the map; callers fall back to fuzzy resolution."""
    p = Path(path)
    if not p.exists():
        return {}
    out: dict[tuple[str, str], str] = {}
    text = p.read_text(encoding="utf-8")
    ti: int | None = None
    ai: int | None = None
    pending: list[str] | None = None
    for line in text.splitlines():
        line_s = line.strip()
        if not line_s.startswith("|"):
            ti = ai = None
            pending = None
            continue
        cells = [c.strip() for c in line_s.strip("|").split("|")]
        if len(cells) < 2:
            pending = None
            continue
        if all(c and set(c) <= set("-: ") for c in cells):
            if pending is not None:
                low = [c.lower() for c in pending]
                if "title" in low and "author" in low:
                    ti, ai = low.index("title"), low.index("author")
                else:
                    ti = ai = None
            pending = None
            continue
        if ti is not None and ai is not None and max(ti, ai) < len(cells):
            title = _strip_md_emphasis(cells[ti])
            author = _strip_md_emphasis(cells[ai])
            if title and not set(title) <= set("- :"):
                # Search all cells for a key comment
                raw_row = line_s
                km = re.search(r"<!--\s*key:\s*(.+?)\s*-->", raw_row)
                if km:
                    out[(norm(title), norm(author))] = km.group(1).strip()
        pending = cells
    return out


def _normalize_preferences(prefs) -> dict:
    """Normalize build_state.preferences to v2 shape.  Missing or
    out-of-range fields fall back to the corrected reader defaults:
    series_commitment=binary, curiosity_targets=[],
    expansion_appetite=moderate.  The audio flag is accepted under
    either `audio_flagged` or `audio_preference` and mirrored to both
    so downstream checks need not branch on the key name."""
    if not isinstance(prefs, dict):
        prefs = {}
    out = dict(prefs)
    sc = prefs.get("series_commitment")
    out["series_commitment"] = sc if sc in ("binary", "test-first") else "binary"
    ct = prefs.get("curiosity_targets")
    out["curiosity_targets"] = ct if isinstance(ct, list) else []
    ea = prefs.get("expansion_appetite")
    out["expansion_appetite"] = (ea if ea in ("high", "moderate", "low")
                                 else "moderate")
    audio = bool(prefs.get("audio_flagged") or prefs.get("audio_preference"))
    out["audio_flagged"] = audio
    out["audio_preference"] = audio
    return out


def load_build_state(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        die(f"missing build state: {p}", code=2)
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        die(f"bad build state at {p}: {e}", code=2)
    if not isinstance(data, dict):
        die("build state must be a JSON object", code=2)
    data.setdefault("n_target", 100)
    data.setdefault("taste_vectors", [])
    data.setdefault("floors", {})
    data.setdefault("events", [])
    data.setdefault("page_budget", None)
    data.setdefault("commitment_load", {})
    data.setdefault("session_notes", [])
    # v1 → v2 normalization.  v1 inputs carry no `version`, no
    # `preferences` block, and no defended/session_lock events; v2
    # carries all three.  Absences normalize to the corrected-default
    # shape so callers never branch on version.  `defended`/
    # `session_lock` events coexist with v1 events untouched.
    data["preferences"] = _normalize_preferences(data.get("preferences"))
    data["version"] = 2
    return data


def collect_locks(state: dict) -> tuple[dict[str, int], set[str]]:
    """Read the locks ledger from build_state.

    Returns ``(defended_counts, session_lock_keys)`` where
    ``defended_counts`` maps a book key to the number of times the
    reader defended it against a proposed cut, and
    ``session_lock_keys`` is the set of keys the reader has explicitly
    locked (unprompted declarations of intent).  Session locks are
    read from ``events[]`` (``type: session_lock``) and, for
    Plan-A-written notes, from ``session_notes[]``
    (``kind: session_lock``)."""
    defended: dict[str, int] = {}
    locks: set[str] = set()
    for ev in state.get("events", []) or []:
        key = ev.get("key")
        if not key:
            continue
        t = ev.get("type")
        if t == "defended":
            defended[key] = defended.get(key, 0) + 1
        elif t == "session_lock":
            locks.add(key)
    for note in state.get("session_notes", []) or []:
        if note.get("kind") == "session_lock" and note.get("key"):
            locks.add(note["key"])
    return defended, locks


def parse_profile_preferences(path: str) -> list[dict]:
    """Parse Profile.md for free-form preference notes that drive
    candidate warnings.  Looks for bullet lines under sections named
    'Preferences', 'Avoid', or 'Constraints' and extracts simple
    keyword-based rules:

        - "no doorstops" / "avoid 600+ pages" / "under 500 pages"
        - "more indie" / "less classic"
        - genre / signal / theme keyword mentions

    Returns a list of {kind, predicate, raw} dicts the recommender
    can apply per candidate.  Best-effort only — the model is the
    primary surface for nuance.
    """
    p = Path(path)
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8")
    notes = []
    in_pref = False
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            heading = s[3:].strip().lower()
            in_pref = any(k in heading for k in ("preference", "avoid", "constraint"))
            continue
        if not in_pref:
            continue
        if not s.startswith("- "):
            continue
        bullet = s[2:].strip()
        bullet_lc = bullet.lower()
        # Page constraints.
        m = re.search(r"(?:under|below|<\s*)(\d{2,4})\s*pages?", bullet_lc)
        if m:
            notes.append({"kind": "page_cap", "limit": int(m.group(1)), "raw": bullet})
            continue
        m = re.search(r"(?:over|above|>\s*|no\s+more\s+than\s+)(\d{2,4})\+?\s*pages?", bullet_lc)
        if m:
            notes.append({"kind": "page_cap", "limit": int(m.group(1)), "raw": bullet})
            continue
        if "doorstop" in bullet_lc or "long book" in bullet_lc:
            if "no " in bullet_lc or "avoid" in bullet_lc or "less" in bullet_lc:
                notes.append({"kind": "page_cap", "limit": 500, "raw": bullet})
                continue
        # Indie/classic preference.
        if "indie" in bullet_lc:
            if "more" in bullet_lc or "prefer" in bullet_lc:
                notes.append({"kind": "prefer", "tag": "indie", "raw": bullet})
            elif "less" in bullet_lc or "fewer" in bullet_lc:
                notes.append({"kind": "avoid", "tag": "indie", "raw": bullet})
        if "classic" in bullet_lc:
            if "more" in bullet_lc or "prefer" in bullet_lc:
                notes.append({"kind": "prefer", "tag": "classic", "raw": bullet})
            elif "less" in bullet_lc or "fewer" in bullet_lc:
                notes.append({"kind": "avoid", "tag": "classic", "raw": bullet})
    return notes


def parse_profile_taste_vectors(path: str) -> list[dict]:
    """Parse Profile.md's '## Taste vectors' section into a list of
    {name, example_titles, status} dicts.  Used by bootstrap-state to
    derive build_state vectors from an existing Profile without
    re-running full cartography."""
    p = Path(path)
    if not p.exists():
        return []
    text = p.read_text(encoding="utf-8")
    vectors: list[dict] = []
    in_section = False
    current: dict | None = None
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("## "):
            heading = s[3:].strip().lower()
            new_in = heading == "taste vectors"
            if not new_in and current is not None:
                vectors.append(current)
                current = None
            in_section = new_in
            continue
        if not in_section:
            continue
        # New vector: "- **Name**" or "- **Name** (prose tags):"
        m = re.match(r"^-\s+\*\*(.+?)\*\*", s)
        if m:
            if current is not None:
                vectors.append(current)
            current = {"name": m.group(1).strip(),
                       "example_titles": [], "status": "active"}
            continue
        if current is None:
            continue
        # Status line: "- Status: active|demoted"
        ms = re.match(r"^-\s+[Ss]tatus:\s*(\w+)", s)
        if ms:
            current["status"] = ms.group(1).lower()
            continue
        # Example-title line: "- *Title* by Author" or "- *Title* (Author)"
        mt = re.match(r"^-\s+\*(.+?)\*\s+(?:by\s+|[\(\[]?)(.+)", s)
        if mt:
            current["example_titles"].append({
                "title": mt.group(1).strip(),
                "author": mt.group(2).rstrip(") ]").strip(),
            })
    if current is not None:
        vectors.append(current)
    return vectors


# ---------------------------------------------------------------------------
# Entry-point gate (port verbatim from prior implementation)
# ---------------------------------------------------------------------------

def passes_entry_point_gate(entry: dict, log_authors: set[str]) -> bool:
    """Two-layer rule:
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


# ---------------------------------------------------------------------------
# Series-position helpers (port verbatim)
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
    if not series_position:
        return None
    m = re.search(r"\(([^)]+)\)", series_position)
    if not m:
        return None
    inner = m.group(1).strip()
    inner_lc = inner.lower()
    if any(tok in inner_lc for tok in _SUBSERIES_SKIP_TOKENS):
        return None
    mm = re.match(r"^Book\s+([\d.]+)\s+in\s+(.+?)(?:\s+subseries)?$",
                  inner, flags=re.IGNORECASE)
    if mm:
        try:
            return (norm(mm.group(2)), float(mm.group(1)))
        except ValueError:
            pass
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
    parsed = _parse_subseries(entry.get("series_position"))
    if parsed:
        return (parsed[1], entry.get("title") or "")
    return _series_order_key(entry)


_NORM_INDEX_CACHE: dict[int, dict[tuple[str, str], dict]] = {}
_SERIES_SIGNAL_CACHE: dict[int, dict[str, float]] = {}
_TITLE_INDEX_CACHE: dict[int, tuple[dict, dict]] = {}


def _norm_index(conn: sqlite3.Connection) -> dict[tuple[str, str], dict]:
    """Catalog index keyed by the *current* norm() of (title, author),
    built once per connection.  Stored title_normalized /
    author_normalized columns reflect whatever norm() was in force
    when each row was written; this recomputes with the live function
    so a hardened norm doesn't silently lose matches until
    `normalize-catalog` runs.  Also keys the pre-colon title prefix."""
    cached = _NORM_INDEX_CACHE.get(id(conn))
    if cached is not None:
        return cached
    idx: dict[tuple[str, str], dict] = {}
    for r in conn.execute("SELECT * FROM books"):
        e = row_to_entry(r)
        an = norm(e.get("author", ""))
        title = e.get("title", "") or ""
        full = norm(title)
        idx.setdefault((full, an), e)
        if ":" in title:
            idx.setdefault((norm(title.split(":", 1)[0]), an), e)
    _NORM_INDEX_CACHE[id(conn)] = idx
    return idx


# ---------------------------------------------------------------------------
# THE resolver.  Every catalog lookup — list resolution, pool/audit
# exclusion, series-fit, cataloguer add — routes through `resolve_book`
# so the "same book?" decision lives in exactly one place
# (book_identity.same_book / authors_match / title_keys) and can never
# fork per call site again.  `lookup_by_pair` is kept as a thin
# back-compat alias over it.
# ---------------------------------------------------------------------------

def _title_index(conn: sqlite3.Connection) -> tuple[dict, dict]:
    """Catalog rows bucketed by title key, recomputed with the live
    norm() so stored-column drift never silently loses a match (the
    `normalize-catalog` command repairs the drift in the data; this is
    the read-side safety net).  Returns ``(exact, folded)``: ``exact``
    keys on norm(title) + pre-colon short title, ``folded`` on the
    spelling-folded forms.  Values are ``(entry, author_norm)`` lists.
    The fold bucket stays separate so D-1c spelling tolerance is only a
    gated fallback, never pollutes an exact title match."""
    cached = _TITLE_INDEX_CACHE.get(id(conn))
    if cached is not None:
        return cached
    exact: dict[str, list[tuple[dict, str]]] = {}
    folded: dict[str, list[tuple[dict, str]]] = {}
    for r in conn.execute("SELECT * FROM books"):
        e = row_to_entry(r)
        an = norm(e.get("author", ""))
        title = e.get("title", "") or ""
        keys = {k for k in (norm(title), title_short(title)) if k}
        for k in keys:
            exact.setdefault(k, []).append((e, an))
            fk = title_fold(k)
            if fk:
                folded.setdefault(fk, []).append((e, an))
    _TITLE_INDEX_CACHE[id(conn)] = (exact, folded)
    return exact, folded


def _pick_best(cands: list[tuple[dict, str]], author_norm: str) -> dict | None:
    """Among title-matched rows, keep those whose author passes the
    tolerant matcher; prefer an exact author equality, then break ties
    deterministically by highest goodreads_reviews then key."""
    matched = [(e, an) for e, an in cands if _author_matches(author_norm, an)]
    if not matched:
        return None
    matched.sort(key=lambda ea: (
        ea[1] != author_norm,                       # exact author first
        -(ea[0].get("goodreads_reviews") or 0),     # then most-reviewed
        ea[0].get("key") or "",                     # stable final tiebreak
    ))
    return matched[0][0]


def resolve_book(conn: sqlite3.Connection,
                 title_norm: str, author_norm: str) -> dict | None:
    """Resolve one (title_norm, author_norm) pair to a catalog entry
    with tolerance for author name-order / co-author / multi-author
    drift (D-1a) and, as a gated fallback, British/American title
    spelling (D-1c).  The spelling fold is tried only after the exact
    title key fails, and still requires an author match."""
    exact, folded = _title_index(conn)
    hit = _pick_best(exact.get(title_norm, []), author_norm)
    if hit is not None:
        return hit
    # Spelling-fold fallback (D-1c).  Run even when the folded form
    # equals the query: the *catalog* side may be the variant
    # ("Valor" in catalog, list wrote "Valour", or vice versa).
    ft = title_fold(title_norm)
    if ft:
        hit = _pick_best(folded.get(ft, []), author_norm)
        if hit is not None:
            return hit
    return None


def lookup_by_pair(conn: sqlite3.Connection,
                   title: str, author: str) -> dict | None:
    """Back-compat alias.  Was an exact (title_normalized,
    author_normalized) SQL lookup with a recompute-index fallback —
    the exact-only path that kept regressing the Cixin-Liu /
    Strugatsky author-variant class at every caller (reconcile,
    series-fit, unfinished-series, cataloguer add).  Now delegates to
    the one tolerant resolver so those callers inherit the fix."""
    return resolve_book(conn, norm(title), norm(author))


def _list_membership(list_pairs: set[tuple[str, str]]):
    """Closure deciding whether a catalog entry is already on the
    reading list, using the same tolerant matcher as `resolve_book`
    (D-1b) so resolved-but-variant on-list books are excluded from the
    candidate pool."""
    by_title: dict[str, list[str]] = {}
    by_fold: dict[str, list[str]] = {}
    for tn, an in list_pairs:
        by_title.setdefault(tn, []).append(an)
        ft = _title_fold(tn)
        if ft:
            by_fold.setdefault(ft, []).append(an)

    def on_list(title: str, author: str) -> bool:
        an = norm(author)
        keys = [norm(title)]
        ts = title_short(title)
        if ts:
            keys.append(ts)
        for k in keys:
            for la in by_title.get(k, []):
                if _author_matches(an, la):
                    return True
        for k in keys:
            fk = _title_fold(k)
            if not fk:
                continue
            for la in by_fold.get(fk, []):
                if _author_matches(an, la):
                    return True
        return False

    return on_list


# ---------------------------------------------------------------------------
# Selection-bias-corrected series rating (Plan C Issue 4).
#
# A per-book Goodreads rating is a noisy ranking input for a tight
# series: a weak opener gets ranked by one bad number, and later
# entries inflate because the audience self-selects.  For tight series
# only, replace the raw number fed to Issue 3's ranking weight with a
# Heckman-style selection-bias-corrected series baseline blended lightly
# with the book's own rating.  The corrected signal and every
# intermediate (p_k, lambda_k, beta) are internal scoring inputs only —
# never projected, never surfaced to the skill.
# ---------------------------------------------------------------------------

def _corrected_series_baseline(entries: list[dict]) -> float | None:
    """Selection-bias-corrected baseline rating for one tight series.

    `entries` is a list of {number, role, rating, reviews} dicts for a
    single series.  Returns the corrected baseline, or None when the
    correction's assumptions don't hold (caller falls back to the
    candidate's own rating):

      - no identifiable book one (anchorless series)
      - review counts not roughly monotone decaying (recency/noise
        dominating rather than selection)

    Method (Heckman two-step; the project methodology doc is
    authoritative, this mirrors its summary):

      1. retention ratio   p_k    = n_k / n_1            (p_1 = 1)
      2. selection thresh. alpha_k = invNormCDF(1 - p_k) (alpha_1 = 0)
      3. inverse Mills     lambda_k = normPDF(alpha_k)/p_k (lambda_1=0)
      4. bias coeff beta:  ≥3 mainline entries → OLS of mu_k on
         lambda_k; the intercept estimates the selection-free
         baseline.  <3 → beta cannot be regressed; the baseline is the
         corrected book-one score (= mu_1, since lambda_1 = 0).
      5. corrected score   mu_k_corrected = mu_k - beta*lambda_k
    """
    # Mainline = tight role + integer book number + usable numbers.
    # Novellas / side stories carry fractional positions (Book 2.5)
    # and are excluded from the retention curve so their low review
    # counts don't masquerade as audience dropout.
    by_number: dict[float, dict] = {}
    for e in entries:
        num = e.get("number")
        if (e.get("role") not in SERIES_TIGHT_ROLES
                or num is None or num != int(num)
                or e.get("rating") is None
                or e.get("reviews") is None or e["reviews"] <= 0):
            continue
        prev = by_number.get(num)
        if prev is None or e["reviews"] > prev["reviews"]:
            by_number[num] = e
    mains = sorted(by_number.values(), key=lambda x: x["number"])
    if not mains:
        return None

    b1 = next((e for e in mains if e["number"] == 1.0), None)
    if b1 is None:
        return None  # anchorless — no n_1, no retention ratio
    n1 = float(b1["reviews"])
    mu1 = float(b1["rating"])

    # Drop mis-scraped rows: an entry whose review count is an
    # anomalous fraction of the series median.  Book one is the
    # anchor and is never dropped.
    revs = sorted(e["reviews"] for e in mains)
    mid = len(revs) // 2
    median = (revs[mid] if len(revs) % 2
              else (revs[mid - 1] + revs[mid]) / 2.0)
    floor = SERIES_OUTLIER_FRAC * median
    retained = [e for e in mains
                if e["number"] == 1.0 or e["reviews"] >= floor]

    # Monotone/domain check: every non-first retained entry needs
    # 0 < n_k < n_1 so p_k ∈ (0,1) and invNormCDF is defined.  A
    # later entry with ≥ n_1 reviews means recency/noise is dominating
    # — the model is unsafe; fall back to own rating.
    rest = [e for e in retained if e["number"] != 1.0]
    for e in rest:
        if not 0 < e["reviews"] < n1:
            return None

    if len(retained) < 3:
        # beta ≈ 0.6 (domain default); baseline = corrected book-one
        # score = mu_1 - beta*lambda_1, and lambda_1 = 0.
        return mu1

    lambdas: list[float] = []
    mus: list[float] = []
    for e in retained:
        if e["number"] == 1.0:
            lambdas.append(0.0)
        else:
            p_k = e["reviews"] / n1
            alpha_k = _norm_ppf(1.0 - p_k)
            lambdas.append(_norm_pdf(alpha_k) / p_k)
        mus.append(float(e["rating"]))

    m = len(lambdas)
    mean_l = sum(lambdas) / m
    mean_mu = sum(mus) / m
    var_l = sum((x - mean_l) ** 2 for x in lambdas) / m
    if var_l < 1e-9:
        return mu1  # degenerate — no usable slope
    cov = sum((lambdas[i] - mean_l) * (mus[i] - mean_mu)
              for i in range(m)) / m
    beta = cov / var_l
    intercept = mean_mu - beta * mean_l  # selection-free baseline
    # The correction's job is to *remove* upward selection inflation,
    # never to manufacture a higher number.  When the OLS slope is
    # non-positive (no inflation in the data, or inverted), the
    # intercept can extrapolate above the observed mean — that is the
    # model's assumption failing, not real signal.  Cap at the
    # mainline mean so the corrected baseline is downward-only.  This
    # keeps the worked-example reproduction (intercept already below
    # the mean).  The "corrected <= plain mean" invariant holds *only
    # on this >=3-mainline OLS path*: the <3-mainline fallback above
    # returns mu_1 (book one's rating) un-capped by design, so a short
    # series whose opener outscored its mainline mean keeps a corrected
    # baseline marginally above that mean — expected, and exempt.
    return min(intercept, mean_mu)


def _series_signal_index(conn: sqlite3.Connection) -> dict[str, float]:
    """`series` value → corrected baseline, built once per connection.
    Only series that yield a valid correction get an entry; everything
    else is absent and the caller uses the book's own rating."""
    cached = _SERIES_SIGNAL_CACHE.get(id(conn))
    if cached is not None:
        return cached
    grouped: dict[str, list[dict]] = {}
    for r in conn.execute(
            "SELECT series, series_status, series_role, series_position, "
            "goodreads_rating, goodreads_reviews FROM books"):
        series = r["series"]
        if not series or r["series_status"] not in SERIES_TIGHT_STATUS:
            continue
        grouped.setdefault(series, []).append({
            "number": _series_book_number(r["series_position"]),
            "role": r["series_role"],
            "rating": r["goodreads_rating"],
            "reviews": r["goodreads_reviews"],
        })
    idx: dict[str, float] = {}
    for series, entries in grouped.items():
        sig = _corrected_series_baseline(entries)
        if sig is not None:
            idx[series] = sig
    _SERIES_SIGNAL_CACHE[id(conn)] = idx
    return idx


def effective_gr_signal(conn: sqlite3.Connection,
                        book: dict) -> float | None:
    """The Goodreads value Issue 3's ranking weight consumes.

      - tight-series book, correction valid →
        0.75*corrected_series_signal + 0.25*own_rating
      - everything else (standalone, loose-series, every fallback) →
        own_rating
      - missing own rating → the corrected series signal alone
      - neither available → None (Issue 3 contributes nothing; no
        penalty)

    Internal scoring input only — never projected."""
    own = parse_rating(book.get("goodreads_rating"))
    status = book.get("series_status")
    role = book.get("series_role")
    series = book.get("series")
    tight = (status in SERIES_TIGHT_STATUS
             and role in SERIES_TIGHT_ROLES)
    if tight and series:
        sig = _series_signal_index(conn).get(series)
        if sig is not None:
            if own is None:
                return sig
            return (SERIES_BLEND_SERIES * sig
                    + SERIES_BLEND_OWN * own)
    return own


# ---------------------------------------------------------------------------
# Per-book signals/themes loaders
# ---------------------------------------------------------------------------

def positive_signals_for(conn: sqlite3.Connection, key: str) -> set[str]:
    return {r["canonical"] for r in conn.execute(
        "SELECT canonical FROM taste_signals "
        "WHERE book_key = ? AND polarity = 'positive'",
        (key,))}


def themes_for(conn: sqlite3.Connection, key: str) -> set[str]:
    return {r["canonical"] for r in conn.execute(
        "SELECT canonical FROM themes WHERE book_key = ?", (key,))}


def comp_keys_for(conn: sqlite3.Connection, key: str) -> list[str]:
    return [r["comp_key"] for r in conn.execute(
        "SELECT comp_key FROM comparable_books WHERE book_key = ?", (key,))]


# ---------------------------------------------------------------------------
# Vector model
# ---------------------------------------------------------------------------

def vector_is_active(v: dict) -> bool:
    return v.get("status", "active") != "demoted"


def active_vectors_of(state: dict) -> list[dict]:
    return [v for v in state.get("taste_vectors", []) if vector_is_active(v)]


def demoted_vectors_of(state: dict) -> list[dict]:
    return [v for v in state.get("taste_vectors", []) if not vector_is_active(v)]


def vector_signal_set(v: dict) -> set[str]:
    return set(v.get("canonical_signals", []) or [])


def vector_theme_set(v: dict) -> set[str]:
    return set(v.get("themes", []) or [])


def vectors_matched(signals: set[str], themes: set[str], vectors: list[dict]) -> list[str]:
    """Names of vectors the (signals, themes) pair matches via any
    canonical-signal or theme overlap."""
    out = []
    for v in vectors:
        if (signals & vector_signal_set(v)) or (themes & vector_theme_set(v)):
            out.append(v["name"])
    return out


def vector_overlap_count(signals: set[str], themes: set[str], v: dict) -> int:
    """Total signal+theme intersection size between a candidate and one
    vector."""
    return len(signals & vector_signal_set(v)) + len(themes & vector_theme_set(v))


def vector_central_threshold(v: dict) -> int:
    """Minimum overlap for a candidate to count as 'central' to vector v.

    Proportional to vector size, capped between 2 and the absolute
    floor — so a 3-signal vector counts overlap=2 as central while
    an 8-signal vector requires 4.  The earlier hardcoded
    ADJACENT_MIN_OVERLAP=1 / MAX_OVERLAP=2 produced misfires on
    large vectors (a single signal hit looked adjacent) and
    starvation on small ones (2 of 3 signals counted as edge, not
    centre)."""
    size = max(1, len(vector_signal_set(v)) + len(vector_theme_set(v)))
    half = (size + 1) // 2  # ceil(size / 2)
    return max(2, min(half, ADJACENT_CENTRAL_MIN_ABS))


def candidate_adjacency(signals: set[str], themes: set[str],
                         active_vectors: list[dict]) -> dict | None:
    """Decide whether a candidate is *adjacent* to the reader's taste.

    Adjacency-as-shape: the candidate must be **central** to its
    strongest-matching vector (overlap ≥ vector_central_threshold)
    AND must carry at least one signal or theme that pulls outside
    that vector — either matching a different active vector (a
    bridge) or matching no active vector at all (a new direction).

    Returns ``{vector, overlap_count, divergence, bridges_to}`` when
    adjacent, else None.  ``divergence`` is ``"bridge"`` or
    ``"new-direction"``; ``bridges_to`` names the bridge vector when
    relevant.

    Replaces the prior ``partial_vector_match`` (which counted any
    1-2 overlap as adjacent regardless of shape — that surfaced thin
    misfires rather than 'just outside my comfort zone' picks)."""
    if not signals and not themes:
        return None
    if not active_vectors:
        return None

    best = None
    best_overlap = 0
    for v in active_vectors:
        overlap = vector_overlap_count(signals, themes, v)
        if overlap >= vector_central_threshold(v) and overlap > best_overlap:
            best = v
            best_overlap = overlap
    if best is None:
        return None

    central_sigs = vector_signal_set(best)
    central_thms = vector_theme_set(best)
    outside_sigs = signals - central_sigs
    outside_thms = themes - central_thms
    if not outside_sigs and not outside_thms:
        return None  # purely central; no divergence

    bridges_to = None
    for v in active_vectors:
        if v["name"] == best["name"]:
            continue
        if (outside_sigs & vector_signal_set(v)) or \
           (outside_thms & vector_theme_set(v)):
            bridges_to = v["name"]
            break

    return {
        "vector": best["name"],
        "overlap_count": best_overlap,
        "divergence": "bridge" if bridges_to else "new-direction",
        "bridges_to": bridges_to,
    }


# ---------------------------------------------------------------------------
# Time-bucketed log anchors
# ---------------------------------------------------------------------------

_DATE_PATTERNS = (
    "%m/%d/%Y", "%Y-%m-%d", "%m/%d/%y", "%Y/%m/%d",
)


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    for pat in _DATE_PATTERNS:
        try:
            return datetime.strptime(s, pat)
        except ValueError:
            continue
    return None


def _bucket_for(d: datetime | None, now: datetime) -> str:
    if d is None:
        return "undated"
    delta_days = (now - d).days
    if delta_days <= 365:
        return "<=12mo"
    if delta_days <= 365 * 3:
        return "12-36mo"
    return "3+yrs"


def compute_log_anchors(log: list[dict], conn: sqlite3.Connection,
                         active_signal_pool: set[str],
                         active_theme_pool: set[str],
                         now: datetime | None = None
                         ) -> tuple[list[dict], dict[str, float]]:
    """Resolve 4★+ log entries to catalog signals/themes (intersected
    with the active vector pool — demoted-only matches drop out) and
    bucket by date.  Returns (anchors, bucket_weight) where each
    anchor is {key, title, rating, signals, themes, bucket} and
    bucket_weight maps bucket → normalized weight (sum=3.0)."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    anchors = []
    counts = {"<=12mo": 0, "12-36mo": 0, "3+yrs": 0, "undated": 0}
    for r in log:
        rating = parse_rating(r.get("My Rating"))
        if rating is None or rating < 4.0:
            continue
        title = r.get("title", "")
        author = r.get("authors", "")
        ce = lookup_by_pair(conn, title, author)
        if not ce:
            continue
        sigs = positive_signals_for(conn, ce["key"]) & active_signal_pool
        thms = themes_for(conn, ce["key"]) & active_theme_pool
        if not sigs and not thms:
            continue
        bucket = _bucket_for(_parse_date(r.get("Last Date Read", "")), now)
        anchors.append({
            "key": ce["key"],
            "title": ce.get("title"),
            "rating": rating,
            "signals": sigs,
            "themes": thms,
            "bucket": bucket,
        })
        counts[bucket] += 1
    inv = {b: 1.0 / max(c, 1) for b, c in counts.items()}
    total = sum(inv.values()) or 1.0
    bucket_weight = {b: round((inv[b] / total) * 3.0, 4) for b in counts}
    return anchors, bucket_weight


def anchor_strength_for(candidate_signals: set[str],
                        candidate_themes: set[str],
                        anchors: list[dict],
                        bucket_weight: dict[str, float]) -> tuple[float, list[dict]]:
    """Sum of bucket weights across log anchors that share at least
    one canonical signal or theme with the candidate.  Capped at 1.5
    per the plan's anti-recency-correction.  Returns (strength,
    matched_anchors)."""
    matched = []
    total = 0.0
    for a in anchors:
        if (candidate_signals & a["signals"]) or (candidate_themes & a["themes"]):
            total += bucket_weight[a["bucket"]]
            matched.append({
                "title": a["title"],
                "rating": a["rating"],
                "bucket": a["bucket"],
            })
    return min(total, 1.5), matched


# ---------------------------------------------------------------------------
# Vector coverage / floor / rejection-cluster computation
# ---------------------------------------------------------------------------

def resolve_list_picks(conn: sqlite3.Connection,
                       list_pairs: set[tuple[str, str]],
                       *,
                       key_map: dict[tuple[str, str], str] | None = None
                       ) -> list[dict]:
    """Look up each (title_norm, author_norm) pair in the catalog.
    Returns a list of resolved entries with their signals/themes
    attached (unresolved pairs drop out).  Resolution is tolerant of
    author name-order / co-author / spelling drift (D-1) via the shared
    `resolve_book`.  Deduped by catalog key so variant list entries
    that collapse onto one catalog row don't double-count.

    When `key_map` is provided (from `list_key_map()`), rows that carry
    a catalog key comment bypass fuzzy title matching and are resolved
    directly by key — eliminating false-positive matches on common titles.
    """
    out = []
    seen: set[str] = set()
    for tn, an in list_pairs:
        # Prefer key-based lookup when the row carries a persisted key.
        direct_key = (key_map or {}).get((tn, an))
        if direct_key:
            row = conn.execute("SELECT * FROM books WHERE key = ?",
                               (direct_key,)).fetchone()
            e = row_to_entry(row) if row else None
        else:
            e = resolve_book(conn, tn, an)
        if e is None or e["key"] in seen:
            continue
        seen.add(e["key"])
        e = dict(e)
        e["_signals"] = positive_signals_for(conn, e["key"])
        e["_themes"] = themes_for(conn, e["key"])
        out.append(e)
    return out


def vector_coverage(picks: list[dict], vectors: list[dict]) -> dict[str, int]:
    cov = {v["name"]: 0 for v in vectors}
    for p in picks:
        sigs = p.get("_signals", set())
        thms = p.get("_themes", set())
        for v in vectors:
            if (sigs & vector_signal_set(v)) or (thms & vector_theme_set(v)):
                cov[v["name"]] += 1
    return cov


def underused_vectors(vectors: list[dict], coverage: dict[str, int],
                      n_target: int) -> list[dict]:
    if not vectors:
        return []
    weight_sum = sum((v.get("weight") or 1.0) for v in vectors) or 1.0
    out = []
    for v in vectors:
        share = (v.get("weight") or 1.0) / weight_sum * n_target
        if coverage.get(v["name"], 0) < share:
            out.append(v)
    return out


def floors_at_risk(floors: dict, picks: list[dict],
                   list_size: int, n_target: int) -> list[dict]:
    """Floor 'remaining' counts.  floors = {indie: N, classic: N,
    genres: {fantasy: N, ...}}.  Returns one record per floor with
    remaining > 0."""
    out = []
    indie_now = sum(1 for p in picks if p.get("indie"))
    classic_now = sum(1 for p in picks if p.get("classic"))
    genre_now: dict[str, int] = {}
    for p in picks:
        g = (p.get("primary_genre") or "").strip()
        if g:
            genre_now[g.lower()] = genre_now.get(g.lower(), 0) + 1

    if "indie" in floors:
        rem = floors["indie"] - indie_now
        if rem > 0:
            out.append({"name": "indie", "kind": "tag",
                        "remaining": rem,
                        "books_left": max(n_target - list_size, 0)})
    if "classic" in floors:
        rem = floors["classic"] - classic_now
        if rem > 0:
            out.append({"name": "classic", "kind": "tag",
                        "remaining": rem,
                        "books_left": max(n_target - list_size, 0)})
    for g, target in (floors.get("genres") or {}).items():
        rem = target - genre_now.get(g.lower(), 0)
        if rem > 0:
            out.append({"name": g, "kind": "genre",
                        "remaining": rem,
                        "books_left": max(n_target - list_size, 0)})
    return out


def rejection_clusters(events: list[dict]) -> list[dict]:
    """Find same-cluster rejection runs from the *tail* of events.
    A run is ≥3 rejections of the same cluster_value with no
    intervening accepts.  Cluster value is taken from the event's
    `vector` field (or `genre` fallback).  Returns one record per
    active cluster (typically 0 or 1)."""
    if not events:
        return []
    runs: list[dict] = []
    current_value = None
    current_kind = None
    current_count = 0
    current_keys: list[str] = []
    for ev in reversed(events):
        if ev.get("type") == "accepted":
            break
        if ev.get("type") != "rejected":
            continue
        kind = "vector" if ev.get("vector") else "genre"
        value = ev.get("vector") or ev.get("genre")
        if not value:
            continue
        if current_value is None:
            current_value, current_kind = value, kind
            current_count = 1
            current_keys = [ev.get("key")]
        elif value == current_value:
            current_count += 1
            current_keys.append(ev.get("key"))
        else:
            break
    if current_count >= 3:
        runs.append({
            "kind": current_kind,
            "value": current_value,
            "count": current_count,
            "keys": [k for k in current_keys if k],
        })
    return runs


def page_budget_warning(picks: list[dict], page_budget: dict | None) -> dict | None:
    if not page_budget:
        return None
    target = page_budget.get("target_avg") or page_budget.get("cap")
    if not target or not picks:
        return None
    pages = [p.get("pages") for p in picks if p.get("pages")]
    if not pages:
        return None
    avg = sum(pages) / len(pages)
    if avg <= target * 1.10:
        return None
    return {"target_avg": target, "current_avg": round(avg, 1),
            "n_picks_with_pages": len(pages)}


def derive_commitment_load(picks: list[dict]) -> dict:
    """Commitment load read off the current Reading_List, not a
    persisted counter.  Build-state used to carry
    `long_series_slots_used`, but nothing in the build flow updated
    it as series got committed; derivation from picks keeps the
    signal honest.

    A long-series slot is consumed when ≥LONG_SERIES_THRESHOLD picks
    share a series — partial scope counts (committing to all six
    matters; trying just Book 1 doesn't).  Doorstops are picks with
    pages ≥ DOORSTOP_PAGES.
    """
    series_counts: dict[str, int] = {}
    for p in picks:
        s = (p.get("series") or "").strip()
        if not s or s.lower() == "standalone":
            continue
        series_counts[s] = series_counts.get(s, 0) + 1
    long_used = sum(1 for n in series_counts.values()
                    if n >= LONG_SERIES_THRESHOLD)
    doorstops = sum(1 for p in picks
                    if (p.get("pages") or 0) >= DOORSTOP_PAGES)
    return {"long_series_slots_used": long_used,
            "doorstop_count": doorstops}


def commitment_load_warning(state: dict,
                             picks: list[dict]) -> dict | None:
    cl = state.get("commitment_load") or {}
    cap = cl.get("long_series_cap")
    if cap is None:
        return None
    used = derive_commitment_load(picks)["long_series_slots_used"]
    if used >= cap:
        return {"long_series_slots_used": used, "long_series_cap": cap,
                "status": "at_cap"}
    if used >= cap - 1:
        return {"long_series_slots_used": used, "long_series_cap": cap,
                "status": "near_cap"}
    return None


# ---------------------------------------------------------------------------
# Stage 1 — quality-floor candidate pool
# ---------------------------------------------------------------------------

def _placeholders(n: int) -> str:
    return ",".join("?" * n) if n else "''"


def stage1_pool(conn: sqlite3.Connection, *,
                active_signals: set[str], active_themes: set[str],
                read_pairs: set, list_pairs: set,
                rejected_keys: set, log_authors: set,
                genre: str | None,
                require_indie: bool = False,
                series_status: list[str] | None = None,
                require_relevance: bool = True) -> list[dict]:
    """Build the quality-floor pool.  Filters in SQL where cheap,
    finishes in Python for the entry-point gate and exclusions.

    When `require_relevance` is False, the canonical-signal/theme
    relevance gate drops — used by the `balanced`/`broad` residual
    quota to surface quality-floor candidates that match no active vector
    ("books I almost didn't show you").

    `require_indie` and `series_status` are hard SQL filters applied
    before all other logic so they can't be soft-biased away.
    `series_status` accepts user-facing aliases: 'standalone',
    'short' (→ 'Short Series'), 'long' (→ 'Long Series').
    """
    if require_relevance and not active_signals and not active_themes:
        return []

    sql = (
        "SELECT DISTINCT b.* FROM books b "
        "WHERE b.title IS NOT NULL "
        "AND b.goodreads_rating >= ? "
    )
    params: list = [QUALITY_FLOOR]

    if require_relevance:
        sql += (
            "AND ("
            "  EXISTS (SELECT 1 FROM taste_signals ts "
            "          WHERE ts.book_key = b.key "
            "            AND ts.polarity = 'positive' "
            f"            AND ts.canonical IN ({_placeholders(len(active_signals))})) "
            "  OR EXISTS (SELECT 1 FROM themes th "
            "             WHERE th.book_key = b.key "
            f"             AND th.canonical IN ({_placeholders(len(active_themes))})) "
            ") "
        )
        params.extend(sorted(active_signals))
        params.extend(sorted(active_themes))

    if genre:
        sql += " AND (LOWER(b.primary_genre) = ? OR LOWER(b.secondary_genre) = ?) "
        params.append(genre.lower())
        params.append(genre.lower())

    if require_indie:
        sql += " AND b.indie = 1 "

    if series_status:
        _status_map = {"standalone": "Standalone",
                       "short": "Short Series",
                       "long": "Long Series"}
        allowed = [_status_map[s] for s in series_status if s in _status_map]
        if allowed:
            sql += f" AND b.series_status IN ({_placeholders(len(allowed))}) "
            params.extend(allowed)

    on_list = _list_membership(list_pairs)
    pool: list[dict] = []
    for row in conn.execute(sql, params):
        e = row_to_entry(row)
        title = e.get("title", "") or ""
        author = e.get("author", "") or ""
        if (norm(title), norm(author)) in read_pairs:
            continue
        if on_list(title, author):
            continue
        if e["key"] in rejected_keys:
            continue
        if not passes_entry_point_gate(e, log_authors):
            continue
        e["_signals"] = positive_signals_for(conn, e["key"])
        e["_themes"] = themes_for(conn, e["key"])
        pool.append(e)
    return pool


# ---------------------------------------------------------------------------
# Stage 2 — vector-spread sampling
# ---------------------------------------------------------------------------

def _stratum_label_vector(name: str) -> str:
    return f"vector:{name}"


def _stratum_label_floor(name: str) -> str:
    return f"floor:{name}"


def _candidate_matched_floors(c: dict, floors: list[dict]) -> list[str]:
    out = []
    for f in floors:
        if f["kind"] == "tag" and c.get(f["name"]):
            out.append(f["name"])
        elif f["kind"] == "genre":
            g = (c.get("primary_genre") or "").lower()
            sg = (c.get("secondary_genre") or "").lower()
            if g == f["name"].lower() or sg == f["name"].lower():
                out.append(f["name"])
    return out


def _stratum_label_adjacent(name: str) -> str:
    return f"adjacent:{name}"


def assign_strata(pool: list[dict], underused: list[dict],
                  at_risk_floors: list[dict],
                  active_vectors: list[dict],
                  variance: str = "balanced") -> dict[str, list[dict]]:
    """Each candidate goes into every matching stratum (vector or
    floor), and into 'residual' if it matches neither.  A candidate
    can appear in multiple strata; the allocator handles dedup.

    Adjacent mode overrides this layout: candidates that are central
    to one active vector AND have signals/themes pulling outside that
    vector (either bridging to another active vector or in a
    no-active-vector direction) go into 'adjacent:<central-vector>'
    strata.  Pure-central matches and pure misses fall through to
    residual.  No underused/floor strata in adjacent mode — the goal
    is shape-aware edge picks, not gap-fillers."""
    if variance == "adjacent":
        return _assign_strata_adjacent(pool, active_vectors)

    strata: dict[str, list[dict]] = {
        _stratum_label_vector(v["name"]): [] for v in underused
    }
    for f in at_risk_floors:
        strata[_stratum_label_floor(f["name"])] = []
    strata["residual"] = []

    underused_names = {v["name"] for v in underused}
    for c in pool:
        sigs = c.get("_signals", set())
        thms = c.get("_themes", set())
        c["_matched_vectors"] = vectors_matched(sigs, thms, active_vectors)
        c["_matched_underused"] = [n for n in c["_matched_vectors"]
                                   if n in underused_names]
        c["_matched_floors"] = _candidate_matched_floors(c, at_risk_floors)
        forced = bool(c.get("_force_residual"))
        c["_is_residual"] = forced or not c["_matched_vectors"]

        if forced:
            strata["residual"].append(c)
            continue

        placed = False
        for vn in c["_matched_underused"]:
            strata[_stratum_label_vector(vn)].append(c)
            placed = True
        for fn in c["_matched_floors"]:
            strata[_stratum_label_floor(fn)].append(c)
            placed = True
        if not placed:
            strata["residual"].append(c)
    return strata


def _assign_strata_adjacent(pool: list[dict],
                             active_vectors: list[dict]) -> dict[str, list[dict]]:
    """Adjacency-mode strata: per-vector buckets keyed by the
    candidate's *central* vector.  Candidates with no central match,
    or central matches that don't diverge anywhere, drop to residual
    so the slot allocator only fills from there when adjacency
    strata are starved."""
    strata: dict[str, list[dict]] = {
        _stratum_label_adjacent(v["name"]): [] for v in active_vectors
    }
    strata["residual"] = []

    for c in pool:
        sigs = c.get("_signals", set())
        thms = c.get("_themes", set())
        c["_matched_vectors"] = vectors_matched(sigs, thms, active_vectors)
        c["_matched_underused"] = []
        c["_matched_floors"] = []

        forced = bool(c.get("_force_residual"))
        adj = None if forced else candidate_adjacency(sigs, thms,
                                                       active_vectors)

        if adj is None or forced:
            c["_is_residual"] = True
            c["_adjacency"] = None
            if forced or not c["_matched_vectors"]:
                strata["residual"].append(c)
            continue

        c["_is_residual"] = False
        c["_adjacency"] = adj
        strata[_stratum_label_adjacent(adj["vector"])].append(c)
    return strata


def quality_score(c: dict, anchors: list[dict],
                  bucket_weight: dict[str, float],
                  comp_overlap_count: int,
                  conn: sqlite3.Connection) -> tuple[float, list[dict]]:
    # Goodreads as one weighted input among many (Plan C Issues 3 & 4):
    # the series-aware effective signal, centred on the catalog median
    # and clamped, so a low rating gently pulls down and a high one
    # gently nudges up — never gating, never the headline.  A strong
    # vector/comp match still outranks a mediocre rating.
    eff = effective_gr_signal(conn, c)
    if eff is None:
        gr = 0.0
    else:
        delta = eff - GR_RANK_PIVOT
        delta = max(-GR_RANK_CLAMP, min(GR_RANK_CLAMP, delta))
        gr = GR_RANK_WEIGHT * delta
    anchor, matched_anchors = anchor_strength_for(
        c.get("_signals", set()), c.get("_themes", set()),
        anchors, bucket_weight)
    comp = min(comp_overlap_count, 3) * 0.6
    return gr + anchor + comp, matched_anchors


def _comp_overlap_count(conn: sqlite3.Connection, key: str,
                        favorite_keys: set[str]) -> int:
    if not favorite_keys:
        return 0
    return sum(1 for c in comp_keys_for(conn, key) if c in favorite_keys)


def favorite_log_keys(conn: sqlite3.Connection, log: list[dict]) -> set[str]:
    out = set()
    for r in log:
        rating = parse_rating(r.get("My Rating"))
        if rating is None or rating < 4.0:
            continue
        ce = lookup_by_pair(conn, r.get("title", ""), r.get("authors", ""))
        if ce:
            out.add(ce["key"])
    return out


def _allocate_slots(stratum_names: list[str], n: int, mode: str,
                    lean: str | None, rng: random.Random) -> dict[str, int]:
    """Returns {stratum_name: slot_count} summing to n.  Honours
    variance mode and --lean.  Empty stratum list → all slots into
    'residual' if present, else equal share across whatever's left."""
    if not stratum_names:
        return {"residual": n}

    weights: dict[str, float] = {}

    if mode == "focused" and any(s.startswith("vector:") for s in stratum_names):
        vec_names = [s for s in stratum_names if s.startswith("vector:")]
        chosen = rng.choice(vec_names)
        for s in stratum_names:
            weights[s] = 1.0
        weights[chosen] = 6.0  # ~60% if 4 strata; scales naturally
    elif mode == "adjacent":
        # Adjacency strata share weight evenly; residual stays low
        # so it only fills slots when adjacency strata are thin.
        for s in stratum_names:
            weights[s] = 1.5 if s.startswith("adjacent:") else 0.5
    else:
        # similar / balanced / broad share the same even-weight base
        # (the old `balanced` behaviour, i.e. similarity-heavy).  For
        # `balanced` and `broad` the structural residual quota is
        # applied as a post-step below so breadth is guaranteed by
        # construction rather than by stratum weighting.
        for s in stratum_names:
            weights[s] = 1.0

    if lean:
        try:
            kind, name = lean.split(":", 1)
            if kind == "vector" and mode == "adjacent":
                # In adjacent mode, "lean vector:X" means
                # "central-to-X plus a new direction" — translate to
                # the adjacency stratum keyed on X.
                target = _stratum_label_adjacent(name)
            elif kind == "vector":
                target = _stratum_label_vector(name)
            elif kind == "floor":
                target = _stratum_label_floor(name)
            else:
                target = None
            if target and target in weights:
                weights[target] *= 2.0
        except ValueError:
            pass

    # Light per-call jitter — wider for the residual-quota modes so
    # consecutive calls vary; tighter elsewhere.
    jitter = 0.20 if mode in ("balanced", "broad") else 0.10
    for s in list(weights):
        weights[s] *= 1.0 + (rng.random() * 2 - 1) * jitter

    total = sum(weights.values()) or 1.0
    raw = {s: weights[s] / total * n for s in stratum_names}
    floors = {s: int(raw[s]) for s in stratum_names}
    used = sum(floors.values())
    remainders = sorted(stratum_names, key=lambda s: -(raw[s] - floors[s]))
    i = 0
    while used < n and i < len(remainders) * 4:
        floors[remainders[i % len(remainders)]] += 1
        used += 1
        i += 1

    # Structural residual quota for balanced / broad.  Pin the
    # residual stratum to ~quota·n and reflow the remaining slots
    # across the other strata in proportion to their current
    # allocation (so --lean / focused skew is preserved among them).
    quota = RESIDUAL_QUOTA.get(mode)
    others = [s for s in stratum_names if s != "residual"]
    if quota and "residual" in floors and others:
        target = min(n, max(1, round(n * quota)))
        if floors["residual"] != target:
            floors["residual"] = target
            rem = n - target
            base = {s: floors[s] for s in others}
            bsum = sum(base.values())
            newf: dict[str, int] = {}
            if bsum > 0:
                for s in others:
                    newf[s] = int(rem * base[s] / bsum)
            else:
                for s in others:
                    newf[s] = 0
            used2 = sum(newf.values())
            order = sorted(others, key=lambda s: -base[s])
            j = 0
            while used2 < rem and order:
                newf[order[j % len(order)]] += 1
                used2 += 1
                j += 1
            for s in others:
                floors[s] = newf[s]
    return floors


def _rank_within_stratum(candidates: list[dict], conn: sqlite3.Connection,
                          anchors: list[dict],
                          bucket_weight: dict[str, float],
                          favorite_keys: set[str],
                          rng: random.Random) -> list[dict]:
    scored = []
    for c in candidates:
        comp_n = _comp_overlap_count(conn, c["key"], favorite_keys)
        score, matched_anchors = quality_score(
            c, anchors, bucket_weight, comp_n, conn)
        c["_score"] = round(score, 3)
        c["_resonance_titles"] = matched_anchors
        c["_comp_overlap_count"] = comp_n
        scored.append(c)
    scored.sort(key=lambda x: (-x["_score"], x.get("title", "")))
    # Light shuffle within roughly-tied scores so consecutive calls
    # don't lock to the same ordering.
    chunks: list[list[dict]] = []
    cur: list[dict] = []
    last = None
    for c in scored:
        if last is not None and abs(c["_score"] - last) > 0.15:
            chunks.append(cur)
            cur = []
        cur.append(c)
        last = c["_score"]
    if cur:
        chunks.append(cur)
    out: list[dict] = []
    for chunk in chunks:
        rng.shuffle(chunk)
        out.extend(chunk)
    return out


def stage2_sample(pool: list[dict], conn: sqlite3.Connection, *,
                  state: dict, log: list[dict],
                  active_vectors: list[dict],
                  underused: list[dict], at_risk: list[dict],
                  n: int, variance: str, lean: str | None,
                  rng: random.Random) -> tuple[list[dict], dict]:
    """Stratified sample.  Returns (selected, stratum_breakdown)."""
    strata = assign_strata(pool, underused, at_risk, active_vectors,
                            variance=variance)
    stratum_names = list(strata.keys())

    # Compute anchor scoring inputs.
    active_signal_pool = {s for v in active_vectors for s in vector_signal_set(v)}
    active_theme_pool = {t for v in active_vectors for t in vector_theme_set(v)}
    anchors, bucket_weight = compute_log_anchors(
        log, conn, active_signal_pool, active_theme_pool)
    favorite_keys = favorite_log_keys(conn, log)

    allocation = _allocate_slots(stratum_names, n, variance, lean, rng)

    selected: list[dict] = []
    selected_keys: set[str] = set()
    breakdown: dict[str, int] = {s: 0 for s in stratum_names}

    # Drop empty strata from allocation by reflowing slots.
    nonempty = [s for s in stratum_names if strata[s]]
    if not nonempty:
        return [], {}
    if set(nonempty) != set(stratum_names):
        allocation = _allocate_slots(nonempty, n, variance, lean, rng)
        breakdown = {s: 0 for s in nonempty}

    # Rank inside each stratum.
    for s in nonempty:
        strata[s] = _rank_within_stratum(strata[s], conn, anchors,
                                          bucket_weight, favorite_keys, rng)

    # Greedy pass: take from each stratum up to its allocation,
    # skipping already-selected.
    for s in nonempty:
        k = allocation.get(s, 0)
        for c in strata[s]:
            if breakdown[s] >= k:
                break
            if c["key"] in selected_keys:
                continue
            c["_stratum"] = s
            selected.append(c)
            selected_keys.add(c["key"])
            breakdown[s] += 1

    # Top-up: if some strata couldn't fill (small pool / heavy
    # overlap), refill from the largest remaining strata.
    if len(selected) < n:
        for s in sorted(nonempty, key=lambda x: -len(strata[x])):
            for c in strata[s]:
                if len(selected) >= n:
                    break
                if c["key"] in selected_keys:
                    continue
                c["_stratum"] = s
                selected.append(c)
                selected_keys.add(c["key"])
                breakdown[s] += 1
            if len(selected) >= n:
                break

    rng.shuffle(selected)
    return selected, {k: v for k, v in breakdown.items() if v > 0}


# ---------------------------------------------------------------------------
# Probe payload
# ---------------------------------------------------------------------------

def _shared_attributes(conn: sqlite3.Connection, keys: list[str]) -> dict:
    if not keys:
        return {}
    pages: list[int] = []
    sig_sets = []
    theme_sets = []
    for k in keys:
        row = conn.execute("SELECT pages FROM books WHERE key = ?", (k,)).fetchone()
        if row and row["pages"]:
            pages.append(row["pages"])
        sig_sets.append(positive_signals_for(conn, k))
        theme_sets.append(themes_for(conn, k))
    out: dict = {}
    if pages:
        out["page_range"] = f"{min(pages)}-{max(pages)}"
    if sig_sets:
        common = set.intersection(*sig_sets) if all(sig_sets) else set()
        if common:
            out["common_signals"] = sorted(common)
    if theme_sets:
        common = set.intersection(*theme_sets) if all(theme_sets) else set()
        if common:
            out["common_themes"] = sorted(common)
    return out


def build_probe(events: list[dict], conn: sqlite3.Connection) -> dict | None:
    clusters = rejection_clusters(events)
    if not clusters:
        return None
    cl = clusters[0]
    shared = _shared_attributes(conn, cl["keys"])
    parts = []
    if shared.get("common_signals"):
        parts.append(", ".join(shared["common_signals"][:2]))
    if shared.get("page_range"):
        parts.append(f"{shared['page_range']} pages")
    if shared.get("common_themes"):
        parts.append(", ".join(shared["common_themes"][:2]))
    if parts:
        suggested = (f"the rejections share {' and '.join(parts)} — "
                     f"is the issue the {cl['kind']} match itself or "
                     f"something else?")
    else:
        suggested = (f"three rejections in a row in {cl['value']} — "
                     f"what's not landing?")
    return {
        "trigger": "rejection_cluster",
        "cluster_kind": cl["kind"],
        "cluster_value": cl["value"],
        "rejected_keys": cl["keys"],
        "shared_attributes": shared,
        "suggested_question": suggested,
    }


# ---------------------------------------------------------------------------
# Render candidate
# ---------------------------------------------------------------------------

def _apply_warnings(c: dict, profile_notes: list[dict]) -> list[str]:
    out = []
    for note in profile_notes:
        if note["kind"] == "page_cap":
            limit = note["limit"]
            if c.get("pages") and c["pages"] > limit:
                out.append(f"page count {c['pages']} exceeds preference ({note['raw']})")
        elif note["kind"] == "avoid":
            if c.get(note["tag"]):
                out.append(f"reader noted: {note['raw']}")
    return out


def render_candidate(c: dict, underused_names: set[str],
                     at_risk_names: set[str],
                     profile_notes: list[dict],
                     show_gr: bool = False,
                     show_audio: bool = False,
                     compact: bool = False) -> dict:
    matched_vectors = c.get("_matched_vectors") or []
    matched_themes = sorted(c.get("_themes", set()))
    matched_floors = c.get("_matched_floors") or []
    fills_vectors = [n for n in matched_vectors if n in underused_names]
    fills_floors = [n for n in matched_floors if n in at_risk_names]
    # Cap resonance_titles to 5 anchors (already ranked by weight);
    # full list with 100+ titles floods context at no benefit.
    resonance = c.get("_resonance_titles", [])[:5]
    if compact:
        return {
            "key": c.get("key"),
            "title": c.get("title"),
            "author": c.get("author"),
            "indie": c.get("indie"),
            "series": c.get("series"),
            "series_position": c.get("series_position"),
            "pages": c.get("pages"),
            "match_reasoning": {
                "matched_vectors": matched_vectors,
                "resonance_titles": resonance[:3],
            },
        }
    out = {
        "key": c.get("key"),
        "title": c.get("title"),
        "author": c.get("author"),
        "pages": c.get("pages"),
        "primary_genre": c.get("primary_genre"),
        "indie": c.get("indie"),
        "classic": c.get("classic"),
        "match_reasoning": {
            "resonance_titles": resonance,
            "matched_vectors": matched_vectors,
            "matched_themes": matched_themes,
            "comp_overlap_count": c.get("_comp_overlap_count", 0),
            "entry_point_ok": True,
        },
        "fills_gap": {
            "vectors": fills_vectors,
            "floors": fills_floors,
            "is_residual": bool(c.get("_is_residual")),
            "adjacency": c.get("_adjacency"),
        },
        "warnings": _apply_warnings(c, profile_notes),
    }
    # goodreads_rating and audio_suitability are dropped from the
    # default projection — they were being used reflexively as cut
    # criteria.  Opt back in via --show-gr / --show-audio or (audio
    # only) the reader's profile-flagged audio preference.
    if show_gr:
        out["goodreads_rating"] = c.get("goodreads_rating")
    if show_audio:
        out["audio_suitability"] = c.get("audio_suitability")
    return out


# ---------------------------------------------------------------------------
# Subcommand: recommend
# ---------------------------------------------------------------------------

CURATE_MODE_MESSAGE = (
    "recommend: curate mode does not source new candidates.\n"
    "Use `compare` for swap analysis or `status` for distribution\n"
    "and floor checks. To source new candidates, run with\n"
    "--mode discover."
)


def cmd_recommend(args, conn: sqlite3.Connection) -> None:
    mode = getattr(args, "mode", "discover") or "discover"
    if mode == "curate":
        # Structural guarantee: curate mode never sources new picks.
        # The message is the entire output; exit non-zero.
        print(CURATE_MODE_MESSAGE, file=sys.stderr)
        sys.exit(4)

    n = args.n
    if n < MIN_N or n > MAX_N:
        # Permissive: allow tests to pin n outside the recommended
        # range; just warn on stderr.
        print(f"librarian-query: --n {n} outside default range "
              f"[{MIN_N},{MAX_N}]; honouring as-is",
              file=sys.stderr)

    log = load_log(args.log)
    log_authors = {norm(r.get("authors", "")) for r in log if r.get("title")}
    read_pairs = already_read_set(log)
    list_pairs = list_set(args.reading_list)
    state = load_build_state(args.build_state)
    profile_notes = (parse_profile_preferences(args.profile)
                     if args.profile else [])
    prefs = state.get("preferences", {})

    # Resolve effective variance.  An explicit --variance always
    # wins; otherwise the reader's stated expansion appetite (set in
    # intake) selects the implicit default: high → broad,
    # low → similar, moderate/unset → balanced.
    explicit_variance = getattr(args, "variance", None)
    if explicit_variance:
        variance = explicit_variance
    else:
        variance = APPETITE_VARIANCE.get(
            prefs.get("expansion_appetite", "moderate"), "balanced")

    show_gr = bool(getattr(args, "show_gr", False))
    show_audio = bool(getattr(args, "show_audio", False)
                      or prefs.get("audio_flagged"))

    actives = active_vectors_of(state)
    if not actives:
        die("build_state has no active taste_vectors; nothing to "
            "match against", code=2)

    rejected_keys = {ev.get("key") for ev in state.get("events", [])
                     if ev.get("type") == "rejected" and ev.get("key")}

    active_signals = {s for v in actives for s in vector_signal_set(v)}
    active_themes = {t for v in actives for t in vector_theme_set(v)}

    require_indie = bool(getattr(args, "require_indie", False))
    series_status = getattr(args, "series_status", None) or None

    pool = stage1_pool(
        conn,
        active_signals=active_signals,
        active_themes=active_themes,
        read_pairs=read_pairs,
        list_pairs=list_pairs,
        rejected_keys=rejected_keys,
        log_authors=log_authors,
        genre=args.genre,
        require_indie=require_indie,
        series_status=series_status,
    )
    pool_size = len(pool)

    # balanced / broad: also surface a residual sub-pool of
    # quality-floor candidates that match no active vector, so the
    # structural residual quota has material to draw from
    # ("books I almost didn't show you").
    if variance in ("balanced", "broad"):
        relaxed = stage1_pool(
            conn,
            active_signals=active_signals,
            active_themes=active_themes,
            read_pairs=read_pairs,
            list_pairs=list_pairs,
            rejected_keys=rejected_keys,
            log_authors=log_authors,
            genre=args.genre,
            require_indie=require_indie,
            series_status=series_status,
            require_relevance=False,
        )
        pool_keys = {c["key"] for c in pool}
        for c in relaxed:
            if c["key"] not in pool_keys:
                c["_force_residual"] = True
                pool.append(c)
        pool_size = len(pool)

    if pool_size == 0:
        die("no candidates after pool filter", code=3)

    picks = resolve_list_picks(conn, list_pairs)
    coverage = vector_coverage(picks, actives)
    n_target = state.get("n_target", 100)
    underused = underused_vectors(actives, coverage, n_target)
    at_risk = floors_at_risk(state.get("floors", {}), picks,
                              len(list_pairs), n_target)

    # If no strata to sample (no underused vectors and no at-risk
    # floors), residual carries the load.
    rng = random.Random(args.seed) if args.seed is not None else random.Random()

    selected, breakdown = stage2_sample(
        pool, conn,
        state=state, log=log,
        active_vectors=actives,
        underused=underused,
        at_risk=at_risk,
        n=n, variance=variance, lean=args.lean,
        rng=rng,
    )

    underused_names = {v["name"] for v in underused}
    at_risk_names = {f["name"] for f in at_risk}

    probe = build_probe(state.get("events", []), conn)

    compact = bool(getattr(args, "compact", False))
    output = {
        "candidates": [render_candidate(c, underused_names, at_risk_names,
                                         profile_notes,
                                         show_gr=show_gr,
                                         show_audio=show_audio,
                                         compact=compact)
                       for c in selected],
        "pool_size": pool_size,
        "stratum_breakdown": breakdown,
        "probe": probe,
        "variance_mode": variance,
    }
    if getattr(args, "audit_exclusions", False):
        output["exclusion_audit"] = build_exclusion_audit(conn, log)
    print(json.dumps(output, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Subcommand: status
# ---------------------------------------------------------------------------

def cmd_status(args, conn: sqlite3.Connection) -> None:
    state = load_build_state(args.build_state)
    list_pairs = list_set(args.reading_list)
    actives = active_vectors_of(state)
    demoted = demoted_vectors_of(state)

    picks = resolve_list_picks(conn, list_pairs)
    coverage = vector_coverage(picks, actives)
    n_target = state.get("n_target", 100)
    under = underused_vectors(actives, coverage, n_target)
    at_risk = floors_at_risk(state.get("floors", {}), picks,
                              len(list_pairs), n_target)
    clusters = rejection_clusters(state.get("events", []))

    defended_counts, session_lock_keys = collect_locks(state)
    # Title resolution: prefer the title the skill wrote on the
    # event/note, fall back to the catalog.
    titles: dict[str, str] = {}
    for ev in state.get("events", []) or []:
        if ev.get("key") and ev.get("title"):
            titles.setdefault(ev["key"], ev["title"])
    for note in state.get("session_notes", []) or []:
        if note.get("key") and note.get("title"):
            titles.setdefault(note["key"], note["title"])

    def _title(key: str) -> str | None:
        if key in titles:
            return titles[key]
        row = conn.execute(
            "SELECT title FROM books WHERE key = ?", (key,)).fetchone()
        return row["title"] if row else None

    defended_picks = sorted(
        ({"key": k, "title": _title(k), "defense_count": c}
         for k, c in defended_counts.items()),
        key=lambda d: (-d["defense_count"], d["title"] or ""),
    )
    session_locks = sorted(
        ({"key": k, "title": _title(k)} for k in session_lock_keys),
        key=lambda d: (d["title"] or ""),
    )

    output = {
        "floors_at_risk": [
            {"name": f["name"], "kind": f["kind"],
             "remaining": f["remaining"], "books_left": f["books_left"]}
            for f in at_risk
        ],
        "vectors_underused": [
            {"name": v["name"], "matched_picks": coverage.get(v["name"], 0)}
            for v in under
        ],
        "vectors_demoted": [v["name"] for v in demoted],
        "rejection_clusters": [
            {"kind": c["kind"], "value": c["value"], "count": c["count"]}
            for c in clusters
        ],
        "commitment_load_warning": commitment_load_warning(state, picks),
        "page_budget_warning": page_budget_warning(picks,
                                                   state.get("page_budget")),
        "defended_picks": defended_picks,
        "session_locks": session_locks,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Subcommand: series-fit
# ---------------------------------------------------------------------------

def _series_books(conn: sqlite3.Connection, series: str) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM books WHERE series = ?", (series,)).fetchall()
    return [row_to_entry(r) for r in rows]


def _narrative_shape(books: list[dict]) -> str:
    if any(_parse_subseries(b.get("series_position")) for b in books):
        return "loose-subseries"
    statuses = {b.get("series_status") for b in books}
    roles = {b.get("series_role") for b in books}
    if statuses == {"Standalone"} or roles == {"standalone"}:
        return "dip-in"
    return "one-arc"


def _subseries_groups(books: list[dict]) -> list[dict]:
    groups: dict[str, list[dict]] = {}
    for b in books:
        sub = _series_sub_thread(b.get("series_position"))
        if sub:
            groups.setdefault(sub, []).append(b)
    out = []
    for name, items in groups.items():
        items_sorted = sorted(items, key=_subseries_order_key)
        out.append({
            "name": name,
            "books": [{"title": x.get("title"), "key": x.get("key"),
                       "position": x.get("series_position"),
                       "pages": x.get("pages")}
                      for x in items_sorted],
        })
    return out


def _series_signals(conn: sqlite3.Connection, books: list[dict]) -> tuple[set[str], set[str]]:
    sigs: set[str] = set()
    thms: set[str] = set()
    for b in books:
        sigs |= positive_signals_for(conn, b["key"])
        thms |= themes_for(conn, b["key"])
    return sigs, thms


def _scope_signals(conn: sqlite3.Connection, books: list[dict],
                   state: dict, list_picks: list[dict]) -> dict:
    actives = active_vectors_of(state)
    series_sigs, series_thms = _series_signals(conn, books)

    matched = []
    strength = "none"
    if actives:
        matched = vectors_matched(series_sigs, series_thms, actives)
        if len(matched) >= 3:
            strength = "strong"
        elif len(matched) == 2:
            strength = "moderate"
        elif len(matched) == 1:
            strength = "weak"

    derived = derive_commitment_load(list_picks)
    long_used = derived["long_series_slots_used"]
    doorstops = derived["doorstop_count"]
    list_size = len(list_picks)
    series_total_pages = sum(b.get("pages") or 0 for b in books)

    n_target = state.get("n_target", 100)
    page_budget = state.get("page_budget") or {}
    target_avg = page_budget.get("target_avg") or 400
    remaining = max(n_target - list_size, 1)
    page_pressure = "low"
    if series_total_pages > remaining * target_avg * 0.4:
        page_pressure = "high"
    elif series_total_pages > remaining * target_avg * 0.2:
        page_pressure = "moderate"

    return {
        "vector_match": {"strength": strength, "matched_vectors": matched},
        "commitment_load": {
            "long_series_slots_used": long_used,
            "doorstop_count_in_list": doorstops,
            "series_total_pages": series_total_pages,
        },
        "page_pressure": page_pressure,
    }


def _scope_recommendation(scope_signals: dict) -> dict:
    strength = scope_signals["vector_match"]["strength"]
    pressure = scope_signals["page_pressure"]
    cl = scope_signals["commitment_load"]
    long_used = cl["long_series_slots_used"]

    if strength == "none":
        return {"scope": "skip", "confidence": "high",
                "rationale": "no overlap with reader's active vectors"}
    if strength == "weak":
        if pressure == "high":
            return {"scope": "skip", "confidence": "medium",
                    "rationale": "weak vector match plus high page pressure"}
        return {"scope": "entry", "confidence": "medium",
                "rationale": "weak vector match — try Book 1 only"}
    if strength == "moderate":
        if pressure == "high" or long_used >= 3:
            return {"scope": "entry", "confidence": "medium",
                    "rationale": ("moderate vector match but reader carries "
                                  f"{long_used} long-series slot(s) and page "
                                  f"pressure is {pressure}")}
        return {"scope": "all", "confidence": "low",
                "rationale": "moderate vector match — full series an option"}
    # strong
    if pressure == "high" or long_used >= 3:
        return {"scope": "entry", "confidence": "medium",
                "rationale": ("strong vector match but reader is committed "
                              f"to {long_used} long series and page pressure "
                              f"is {pressure}")}
    return {"scope": "all", "confidence": "high",
            "rationale": "strong vector match and commitment load is low"}


def cmd_series_fit(args, conn: sqlite3.Connection) -> None:
    if not args.series and not args.series_key:
        die("--series or --series-key required", code=2)
    if args.series_key:
        row = conn.execute("SELECT series FROM books WHERE key = ?",
                            (args.series_key,)).fetchone()
        if not row or not row["series"]:
            die(f"no series for key {args.series_key!r}", code=2)
        series_name = row["series"]
    else:
        series_name = args.series

    books = _series_books(conn, series_name)
    if not books:
        die(f"no books in series {series_name!r}", code=2)
    books_sorted = sorted(books, key=_series_order_key)

    log = load_log(args.log) if Path(args.log).exists() else []
    read_pairs = already_read_set(log)
    list_pairs = list_set(args.reading_list)
    log_ratings: dict[tuple[str, str], float] = {}
    for r in log:
        rating = parse_rating(r.get("My Rating"))
        if rating is None:
            continue
        log_ratings[(norm(r.get("title", "")), norm(r.get("authors", "")))] = rating

    next_unread_key = None
    for b in books_sorted:
        pair = (norm(b.get("title", "")), norm(b.get("author", "")))
        if pair in read_pairs:
            continue
        p = (b.get("series_position") or "").lower()
        m = re.search(r"book\s*([\d.]+)", p)
        if m and float(m.group(1)) < 1:
            continue
        next_unread_key = b["key"]
        break

    rendered_books = []
    for b in books_sorted:
        pair = (norm(b.get("title", "")), norm(b.get("author", "")))
        rendered_books.append({
            "position": b.get("series_position"),
            "title": b.get("title"),
            "key": b.get("key"),
            "pages": b.get("pages"),
            "series_role": b.get("series_role"),
            "in_catalog": True,
            "read": pair in read_pairs,
            "on_list": pair in list_pairs,
            "next_unread": b["key"] == next_unread_key,
            "rating": log_ratings.get(pair),
        })

    state = load_build_state(args.build_state) if Path(args.build_state).exists() else {
        "n_target": 100, "taste_vectors": [], "floors": {},
        "events": [], "commitment_load": {}, "page_budget": None,
    }
    list_picks = resolve_list_picks(conn, list_pairs)
    scope_signals = _scope_signals(conn, books, state, list_picks)

    books_to_add = [b for b in rendered_books if not b["read"] and not b["on_list"]]
    output = {
        "series": series_name,
        "author": books_sorted[0].get("author") if books_sorted else None,
        "books": rendered_books,
        "books_to_add_count": len(books_to_add),
        "books_to_add_pages": sum(b.get("pages") or 0 for b in books_to_add),
        "subseries": _subseries_groups(books_sorted),
        "narrative_shape": _narrative_shape(books_sorted),
        "scope_signals": scope_signals,
        "scope_recommendation": _scope_recommendation(scope_signals),
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Subcommand: unfinished-series (port verbatim, ledger args trimmed)
# ---------------------------------------------------------------------------

def _has_completed_flag(row: dict) -> bool:
    tags = row.get("my_tags") or ""
    return any(t.strip() == "*completed" for t in tags.split(","))


def cmd_unfinished_series(args, conn: sqlite3.Connection) -> None:
    log = load_log(args.log)

    series_books: dict[str, list[dict]] = {}
    rows = conn.execute(
        "SELECT * FROM books WHERE series IS NOT NULL "
        "AND series_status != 'Standalone'"
    ).fetchall()
    for r in rows:
        e = row_to_entry(r)
        s = e["series"]
        series_books.setdefault(s, []).append(e)

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
    for series, rows_log in series_log_rows.items():
        rated = [(r, ce, parse_rating(r.get("My Rating")))
                 for r, ce in rows_log if parse_rating(r.get("My Rating")) is not None]
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
        if any(_has_completed_flag(r) for r, _ in rows_log):
            continue

        ordered = sorted(series_books.get(series, []), key=_series_order_key)
        read_pairs = {(norm(ce.get("title", "")), norm(ce.get("author", "")))
                      for _, ce in rows_log}
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

        last_read = max(rows_log, key=lambda pair: _series_order_key(pair[1]))
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


# ---------------------------------------------------------------------------
# Subcommand: compare
# ---------------------------------------------------------------------------

def _fit_verdict(anchor_strength: float) -> str:
    """anchor_strength_for caps at 1.5.  Map the spread to three
    coarse verdicts the model can quote in chat."""
    if anchor_strength >= 0.9:
        return "strong"
    if anchor_strength >= 0.4:
        return "medium"
    return "weak"


def _shared_overlap(a_sigs: set[str], a_thms: set[str],
                     b_sigs: set[str], b_thms: set[str]) -> dict:
    shared_sigs = sorted(a_sigs & b_sigs)
    shared_thms = sorted(a_thms & b_thms)
    union = (a_sigs | a_thms) | (b_sigs | b_thms)
    overlap = (a_sigs & b_sigs) | (a_thms & b_thms)
    jaccard = (len(overlap) / len(union)) if union else 0.0
    return {
        "shared_signals": shared_sigs,
        "shared_themes": shared_thms,
        "overlap_count": len(overlap),
        "jaccard": round(jaccard, 4),
    }


def cmd_compare(args, conn: sqlite3.Connection) -> None:
    add_entry = lookup_by_pair(conn, args.add, args.add_author or "")
    if not add_entry:
        die(f"add candidate not found in catalog: "
            f"{args.add!r} by {args.add_author!r}", code=3)

    add_sigs = positive_signals_for(conn, add_entry["key"])
    add_thms = themes_for(conn, add_entry["key"])

    list_pairs = list_set(args.reading_list)
    list_picks = resolve_list_picks(conn, list_pairs)
    if not list_picks:
        die("reading list resolved to zero catalog entries; nothing "
            "to compare against", code=3)

    state = load_build_state(args.build_state)
    defended_counts, session_lock_keys = collect_locks(state)
    # Hard lock: a pick defended ≥2× this session, or explicitly
    # session-locked, is removed from cut-candidate sampling
    # entirely.  A single defense (count == 1) still surfaces but
    # carries defended_count so the skill can escalate justification.
    hard_locked = {k for k, c in defended_counts.items() if c >= 2}
    hard_locked |= session_lock_keys

    actives = active_vectors_of(state)
    active_signal_pool = {s for v in actives for s in vector_signal_set(v)}
    active_theme_pool = {t for v in actives for t in vector_theme_set(v)}

    log = load_log(args.log)
    log_authors = {norm(r.get("authors", "")) for r in log if r.get("title")}
    anchors, bucket_weight = compute_log_anchors(
        log, conn, active_signal_pool, active_theme_pool)
    favorite_keys = favorite_log_keys(conn, log)

    # Add candidate's own match reasoning + fit verdict.
    add_anchor_strength, add_matched_anchors = anchor_strength_for(
        add_sigs, add_thms, anchors, bucket_weight)
    add_comp_n = _comp_overlap_count(conn, add_entry["key"], favorite_keys)
    add_match = {
        "resonance_titles": add_matched_anchors,
        "matched_vectors": vectors_matched(add_sigs, add_thms, actives),
        "matched_themes": sorted(add_thms),
        "comp_overlap_count": add_comp_n,
        "entry_point_ok": passes_entry_point_gate(add_entry, log_authors),
        "anchor_strength": round(add_anchor_strength, 3),
    }

    # Score each list pick on two axes.
    scored_picks = []
    for p in list_picks:
        p_sigs = p.get("_signals", set())
        p_thms = p.get("_themes", set())
        overlap = _shared_overlap(add_sigs, add_thms, p_sigs, p_thms)
        p_anchor, _ = anchor_strength_for(
            p_sigs, p_thms, anchors, bucket_weight)
        scored_picks.append({
            "key": p["key"],
            "title": p.get("title"),
            "author": p.get("author"),
            "pages": p.get("pages"),
            "primary_genre": p.get("primary_genre"),
            "shared_signals": overlap["shared_signals"],
            "shared_themes": overlap["shared_themes"],
            "add_candidate_overlap": overlap["jaccard"],
            "_overlap_count": overlap["overlap_count"],
            "anchor_strength": round(p_anchor, 3),
        })

    # High-overlap rank: thematically redundant with the add candidate.
    high_overlap = sorted(
        [p for p in scored_picks if p["_overlap_count"] > 0],
        key=lambda p: (-p["_overlap_count"], -p["add_candidate_overlap"],
                       p["anchor_strength"]),
    )
    # Low-confidence rank: weakest log-anchor resonance, gated by the
    # median so a pick with strong anchors never surfaces as "weak fit".
    if scored_picks:
        anchor_vals = sorted(p["anchor_strength"] for p in scored_picks)
        mid = anchor_vals[len(anchor_vals) // 2]
    else:
        mid = 0.0
    low_confidence = sorted(
        [p for p in scored_picks if p["anchor_strength"] < mid],
        key=lambda p: p["anchor_strength"],
    )

    n = max(args.n, 1)
    half_high = (n + 1) // 2  # at least one of each when both have material
    half_low = n - half_high

    seen: set[str] = set()
    out: list[dict] = []
    # Keys filtered by the lock check that were otherwise eligible
    # swap targets — surfaced so the skill can see what's protected.
    locked_picks_excluded = sorted(
        {p["key"] for p in scored_picks if p["key"] in hard_locked})

    def take(pool: list[dict], reason: str, slots: int) -> None:
        for p in pool:
            if slots <= 0:
                break
            if p["key"] in seen or p["key"] == add_entry["key"]:
                continue
            if p["key"] in hard_locked:
                continue
            seen.add(p["key"])
            entry = {k: v for k, v in p.items() if not k.startswith("_")}
            entry["reason"] = reason
            entry["defended_count"] = defended_counts.get(p["key"], 0)
            out.append(entry)
            slots -= 1

    take(high_overlap, "high_overlap", half_high)
    take(low_confidence, "low_confidence", half_low)

    # Reflow leftover slots: if one axis was thin, fill from the other.
    remaining = n - len(out)
    if remaining > 0:
        for pool, reason in ((low_confidence, "low_confidence"),
                              (high_overlap, "high_overlap")):
            take(pool, reason, remaining)
            remaining = n - len(out)
            if remaining <= 0:
                break

    output = {
        "add_candidate": {
            "key": add_entry["key"],
            "title": add_entry.get("title"),
            "author": add_entry.get("author"),
            "pages": add_entry.get("pages"),
            "primary_genre": add_entry.get("primary_genre"),
            "indie": add_entry.get("indie"),
            "classic": add_entry.get("classic"),
            "match_reasoning": add_match,
            "fit_verdict": _fit_verdict(add_anchor_strength),
        },
        "swap_suggestions": out,
        "list_size": len(list_picks),
        "locked_picks_excluded": locked_picks_excluded,
    }
    print(json.dumps(output, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# Subcommand: norm
# ---------------------------------------------------------------------------

def cmd_norm(args, _conn=None) -> None:
    print(norm(args.text))


# ---------------------------------------------------------------------------
# Addendum B — author history, exclusion audit, reconcile, normalize
# ---------------------------------------------------------------------------

def _log_author_field(row: dict) -> str:
    return row.get("authors") or row.get("author") or ""


def _log_date(row: dict) -> str | None:
    for k in ("Last Date Read", "Date Read", "date", "Date"):
        v = row.get(k)
        if v:
            return v.strip()
    return None


def cmd_author_history(args, _conn=None) -> None:
    log = load_log(args.log)
    qn = norm(args.author)
    reads = []
    matched_author = None
    for r in log:
        if not r.get("title"):
            continue
        raw = _log_author_field(r)
        if qn and qn in author_parts(raw):
            if matched_author is None:
                matched_author = raw
            reads.append({
                "title": r.get("title"),
                "rating": parse_rating(r.get("My Rating")),
                "date": _log_date(r),
            })
    rated_4plus = sum(1 for x in reads
                      if x["rating"] is not None and x["rating"] >= 4.0)
    print(json.dumps({
        "author_query": args.author,
        "matched_author": matched_author,
        "reads": reads,
        "read_count": len(reads),
        "rated_4plus_count": rated_4plus,
    }, ensure_ascii=False, indent=2))


def _norm_distance(a: str, b: str) -> float:
    """1 − similarity ratio on two normalized strings (0 == identical)."""
    if not a and not b:
        return 0.0
    return round(1.0 - difflib.SequenceMatcher(None, a, b).ratio(), 4)


def build_exclusion_audit(conn: sqlite3.Connection,
                          log: list[dict]) -> dict:
    """Reconcile every log entry against the catalog.  Surfaces
    orphans (no catalog match at all) and near-misses (a catalog row
    that *almost* matched — the silent exclusion-gate failures)."""
    idx = _norm_index(conn)
    by_title: dict[str, list[tuple[str, dict]]] = {}
    by_author: dict[str, list[tuple[str, dict]]] = {}
    for (tn, an), e in idx.items():
        by_title.setdefault(tn, []).append((an, e))
        by_author.setdefault(an, []).append((tn, e))

    total = 0
    matched = 0
    orphans: list[dict] = []
    near: list[dict] = []
    for r in log:
        if not r.get("title"):
            continue
        total += 1
        ltn = norm(r.get("title", ""))
        lan = norm(_log_author_field(r))
        # Match decision goes through the one tolerant resolver, not a
        # private exact index — so the audit's "matched" count agrees
        # with what the exclusion gate actually excludes.  The norm
        # index below is kept only to bucket near-miss reporting.
        if resolve_book(conn, ltn, lan) is not None:
            matched += 1
            continue
        # Look for the closest catalog row: same title (author drift)
        # or same author (title drift).
        best = None
        for cand_an, e in by_title.get(ltn, []):
            d = _norm_distance(lan, cand_an)
            if best is None or d < best[0]:
                best = (d, e, "author")
        for cand_tn, e in by_author.get(lan, []):
            d = _norm_distance(ltn, cand_tn)
            if best is None or d < best[0]:
                best = (d, e, "title")
        if best is not None and best[0] <= 0.34:
            e = best[1]
            near.append({
                "log_title": r.get("title"),
                "catalog_title": e.get("title"),
                "log_author": _log_author_field(r),
                "catalog_author": e.get("author"),
                "normalized_distance": best[0],
            })
        else:
            orphans.append({
                "title": r.get("title"),
                "author": _log_author_field(r),
                "reason": "no catalog match",
            })
    return {
        "log_entries_total": total,
        "log_entries_matched_to_catalog": matched,
        "orphan_log_entries": orphans,
        "near_miss_matches": near,
    }


def cmd_reconcile(args, conn: sqlite3.Connection) -> None:
    log = load_log(args.log)
    result = build_exclusion_audit(conn, log)
    reading_list_path = getattr(args, "reading_list", None)
    if reading_list_path:
        result["reading_list_audit"] = _reading_list_audit(conn, reading_list_path)
    print(json.dumps(result, ensure_ascii=False, indent=2))


def _reading_list_audit(conn: sqlite3.Connection, path: str) -> dict:
    """Reconcile Reading_List.md rows against the catalog.

    Reports rows that already carry a catalog key comment (and whether
    the key exists in the catalog), rows without a key but with a
    suggested resolution, and rows that couldn't be resolved at all.
    """
    km = list_key_map(path)
    lp = list_set(path)
    rows_with_key: list[dict] = []
    suggested_keys: list[dict] = []
    unmatched: list[dict] = []
    ambiguous: list[dict] = []

    for tn, an in sorted(lp):
        if (tn, an) in km:
            key = km[(tn, an)]
            exists = (conn.execute(
                "SELECT 1 FROM books WHERE key = ?", (key,)).fetchone()
                      is not None)
            rows_with_key.append({"title_norm": tn, "author_norm": an,
                                  "key": key, "key_valid": exists})
        else:
            entry = resolve_book(conn, tn, an)
            if entry is not None:
                suggested_keys.append({
                    "title_norm": tn, "author_norm": an,
                    "suggested_key": entry["key"],
                    "title": entry.get("title"),
                    "author": entry.get("author"),
                })
            else:
                unmatched.append({"title_norm": tn, "author_norm": an})

    return {
        "rows_with_key": rows_with_key,
        "rows_without_key_count": len(suggested_keys) + len(unmatched),
        "suggested_keys": suggested_keys,
        "unmatched": unmatched,
    }


def cmd_bootstrap_state(args, conn: sqlite3.Connection) -> None:
    """Derive a minimal build_state.json from Profile.md taste vectors.

    For each active vector, resolves example titles against the catalog
    and unions their canonical_signals and themes into the vector schema
    that `recommend` expects.  Writes the result to --out.
    """
    raw_vectors = parse_profile_taste_vectors(args.profile)
    if not raw_vectors:
        die("no taste vectors found in Profile.md — "
            "check that '## Taste vectors' section exists and is populated",
            code=2)

    taste_vectors: list[dict] = []
    for vec in raw_vectors:
        if vec["status"] == "demoted":
            continue
        signals: set[str] = set()
        themes: set[str] = set()
        unresolved: list[str] = []
        for ex in vec["example_titles"]:
            entry = resolve_book(conn, norm(ex["title"]), norm(ex["author"]))
            if entry is None:
                unresolved.append(ex["title"])
                continue
            signals |= positive_signals_for(conn, entry["key"])
            themes |= themes_for(conn, entry["key"])
        if not signals and not themes:
            print(f"bootstrap-state: vector '{vec['name']}' — no catalog matches "
                  f"({', '.join(unresolved) or 'no examples listed'}); skipping",
                  file=sys.stderr)
            continue
        if unresolved:
            print(f"bootstrap-state: vector '{vec['name']}' — "
                  f"unresolved titles: {', '.join(unresolved)}",
                  file=sys.stderr)
        taste_vectors.append({
            "name": vec["name"],
            "canonical_signals": sorted(signals),
            "themes": sorted(themes),
            "status": "active",
        })

    if not taste_vectors:
        die("no vectors could be resolved from catalog — "
            "check that example titles in Profile.md match catalog entries",
            code=2)

    state = {
        "version": 2,
        "mode": "refine",
        "taste_vectors": taste_vectors,
        "floors": {},
        "events": [],
        "preferences": {},
        "session_notes": [],
    }
    out_path = Path(args.out)
    out_path.write_text(json.dumps(state, ensure_ascii=False, indent=2),
                        encoding="utf-8")
    print(f"bootstrap-state: wrote {len(taste_vectors)} vector(s) to {out_path}",
          file=sys.stderr)


def cmd_normalize_catalog(args, conn: sqlite3.Connection) -> None:
    rows = list(conn.execute("SELECT * FROM books"))
    updates: list[tuple] = []
    author_format_changes: list[dict] = []
    malformed: list[dict] = []
    seen: dict[tuple[str, str], list[str]] = {}

    for r in rows:
        e = row_to_entry(r)
        key = e["key"]
        old_title_n = e.get("title_normalized") or ""
        old_author_n = e.get("author_normalized") or ""
        old_short = e.get("title_short") or ""
        old_author = e.get("author") or ""

        new_author = _swap_lastfirst(old_author)
        new_title_n = norm(e.get("title", ""))
        new_author_n = norm(new_author)
        new_short = title_short(e.get("title"))

        if not new_title_n or not new_author_n:
            malformed.append({"key": key, "title": e.get("title"),
                              "author": old_author})

        seen.setdefault((new_title_n, new_author_n), []).append(key)

        if new_author != old_author:
            author_format_changes.append(
                {"key": key, "old": old_author, "new": new_author})

        if (new_title_n != old_title_n or new_author_n != old_author_n
                or new_short != old_short or new_author != old_author):
            updates.append((new_title_n, new_short, new_author,
                            new_author_n, key))

    duplicates = [{"normalized": list(k), "keys": v}
                  for k, v in seen.items() if len(v) > 1]

    summary = {
        "rows_total": len(rows),
        "rows_to_update": len(updates),
        "author_format_changes": author_format_changes,
        "duplicate_groups": duplicates,
        "malformed_rows": malformed,
        "dry_run": bool(args.dry_run),
        "written": False,
    }

    if not args.dry_run and updates:
        conn.executemany(
            "UPDATE books SET title_normalized = ?, title_short = ?, "
            "author = ?, author_normalized = ? WHERE key = ?", updates)
        conn.commit()
        summary["written"] = True
        encoded = Path(args.catalog + ".encoded")
        if args.emit_encoded or encoded.exists():
            try:
                from .encoded_codec import encode_file  # type: ignore
            except (ImportError, ValueError):
                try:
                    from encoded_codec import encode_file  # type: ignore
                except ImportError:
                    from webhelper.encoded_codec import encode_file
            conn.execute("VACUUM")
            encode_file(Path(args.catalog), encoded)
            summary["encoded_path"] = str(encoded)

    print(json.dumps(summary, ensure_ascii=False, indent=2))


# ---------------------------------------------------------------------------
# CLI wiring
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="librarian_query.py")
    sub = p.add_subparsers(dest="cmd", required=True)

    sp = sub.add_parser("norm")
    sp.add_argument("text")
    sp.set_defaults(func=cmd_norm, needs_catalog=False)

    sp = sub.add_parser("recommend")
    sp.add_argument("--catalog", default=DEFAULT_CATALOG)
    sp.add_argument("--log", default=DEFAULT_LOG)
    sp.add_argument("--profile", default=None)
    sp.add_argument("--reading-list", default=DEFAULT_LIST)
    sp.add_argument("--build-state", required=True)
    sp.add_argument("--genre", default=None)
    sp.add_argument("--n", type=int, default=DEFAULT_N)
    sp.add_argument("--lean", default=None,
                    help="vector:NAME or floor:NAME — soft ×2 stratum bias")
    sp.add_argument("--variance", choices=VARIANCE_MODES, default=None,
                    help="sampling spread; default derives from "
                         "build_state.preferences.expansion_appetite "
                         "(high→broad, low→similar, else balanced)")
    sp.add_argument("--show-gr", dest="show_gr", action="store_true",
                    help="include goodreads_rating in candidate projection")
    sp.add_argument("--show-audio", dest="show_audio", action="store_true",
                    help="include audio_suitability in candidate projection")
    sp.add_argument("--mode", choices=("discover", "curate"),
                    default="discover",
                    help="discover (default) sources candidates; "
                         "curate refuses to source new picks")
    sp.add_argument("--audit-exclusions", dest="audit_exclusions",
                    action="store_true",
                    help="also emit an exclusion_audit block "
                         "(orphan + near-miss log↔catalog matches)")
    sp.add_argument("--seed", type=int, default=None)
    sp.add_argument("--compact", action="store_true",
                    help="emit slim per-candidate projection "
                         "(key/title/author/indie/series/pages/"
                         "matched_vectors/top-3-resonance); "
                         "recommended for refine-mode to avoid context floods")
    sp.add_argument("--require-indie", dest="require_indie", action="store_true",
                    help="hard SQL filter: only indie=1 candidates")
    sp.add_argument("--series-status", dest="series_status",
                    choices=("standalone", "short", "long"),
                    action="append", default=None,
                    help="hard SQL filter on series_status: "
                         "'standalone'=Standalone, 'short'=Short Series, "
                         "'long'=Long Series; repeatable")
    sp.set_defaults(func=cmd_recommend, needs_catalog=True)

    sp = sub.add_parser("author-history")
    sp.add_argument("--author", required=True)
    sp.add_argument("--log", default=DEFAULT_LOG)
    sp.add_argument("--catalog", default=DEFAULT_CATALOG)
    sp.set_defaults(func=cmd_author_history, needs_catalog=False)

    sp = sub.add_parser("reconcile")
    sp.add_argument("--catalog", default=DEFAULT_CATALOG)
    sp.add_argument("--log", default=DEFAULT_LOG)
    sp.add_argument("--reading-list", dest="reading_list", default=None,
                    help="if provided, also audit Reading_List.md rows "
                         "for catalog key comments and suggest keys for "
                         "rows that lack them")
    sp.set_defaults(func=cmd_reconcile, needs_catalog=True)

    sp = sub.add_parser("bootstrap-state")
    sp.add_argument("--profile", required=True,
                    help="path to Profile.md (must contain ## Taste vectors)")
    sp.add_argument("--catalog", default=DEFAULT_CATALOG)
    sp.add_argument("--out", required=True,
                    help="path to write the derived build_state.json")
    sp.set_defaults(func=cmd_bootstrap_state, needs_catalog=True)

    sp = sub.add_parser("normalize-catalog")
    sp.add_argument("--catalog", default=DEFAULT_CATALOG)
    sp.add_argument("--dry-run", dest="dry_run", action="store_true",
                    help="report changes without writing")
    sp.add_argument("--emit-encoded", dest="emit_encoded",
                    action="store_true",
                    help="force re-emit of <catalog>.encoded after write")
    sp.set_defaults(func=cmd_normalize_catalog, needs_catalog=True)

    sp = sub.add_parser("status")
    sp.add_argument("--catalog", default=DEFAULT_CATALOG)
    sp.add_argument("--log", default=DEFAULT_LOG)
    sp.add_argument("--reading-list", default=DEFAULT_LIST)
    sp.add_argument("--build-state", required=True)
    sp.set_defaults(func=cmd_status, needs_catalog=True)

    sp = sub.add_parser("series-fit")
    sp.add_argument("--series", default=None)
    sp.add_argument("--series-key", default=None)
    sp.add_argument("--catalog", default=DEFAULT_CATALOG)
    sp.add_argument("--log", default=DEFAULT_LOG)
    sp.add_argument("--reading-list", default=DEFAULT_LIST)
    sp.add_argument("--profile", default=None)
    sp.add_argument("--build-state", default=DEFAULT_BUILD_STATE)
    sp.set_defaults(func=cmd_series_fit, needs_catalog=True)

    sp = sub.add_parser("unfinished-series")
    sp.add_argument("--catalog", default=DEFAULT_CATALOG)
    sp.add_argument("--log", default=DEFAULT_LOG)
    sp.add_argument("--reading-list", default=DEFAULT_LIST)
    sp.add_argument("--min-rating", type=float, default=4.0)
    sp.add_argument("--min-avg", type=float, default=3.5)
    sp.add_argument("--min-last", type=float, default=3.0)
    sp.set_defaults(func=cmd_unfinished_series, needs_catalog=True)

    sp = sub.add_parser("compare")
    sp.add_argument("--catalog", default=DEFAULT_CATALOG)
    sp.add_argument("--log", default=DEFAULT_LOG)
    sp.add_argument("--profile", default=None)
    sp.add_argument("--reading-list", default=DEFAULT_LIST)
    sp.add_argument("--build-state", required=True)
    sp.add_argument("--add", required=True,
                    help="title of the book the reader wants to add")
    sp.add_argument("--add-author", default="",
                    help="author of the add candidate (improves lookup)")
    sp.add_argument("--n", type=int, default=3,
                    help="number of swap suggestions to return")
    sp.set_defaults(func=cmd_compare, needs_catalog=True)

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
