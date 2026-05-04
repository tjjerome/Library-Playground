#!/usr/bin/env python3
"""Librarian query helper — claude.ai port, post-recomposition rewrite.

Four subcommands plus `norm`:

    recommend          constraint-satisfaction candidate generation,
                       vector-spread sampling, returns 12-18 candidates
    status             actionable signals only — no dashboard
    series-fit         scope-aware series navigation
    unfinished-series  Phase 0 gate
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
import json
import random
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

try:
    from .sqlite_export import norm  # type: ignore
except (ImportError, ValueError):
    try:
        from sqlite_export import norm  # type: ignore  # noqa: E402
    except ImportError:
        sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
        from webhelper.sqlite_export import norm  # noqa: E402


# ---------------------------------------------------------------------------
# Defaults / paths
# ---------------------------------------------------------------------------

DEFAULT_CATALOG = "Library_Catalog.sqlite"
DEFAULT_LOG = "Reading_Log.csv"
DEFAULT_LIST = "Reading_List.md"
DEFAULT_PROFILE = "Profile.md"
DEFAULT_BUILD_STATE = "build_state.json"

VARIANCE_MODES = ("balanced", "focused", "surprising")
QUALITY_FLOOR = 3.8
DEFAULT_N = 15
MIN_N = 12
MAX_N = 18

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
    return data


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


def lookup_by_pair(conn: sqlite3.Connection, title: str, author: str) -> dict | None:
    tn = norm(title)
    an = norm(author)
    for sql in (
        "SELECT * FROM books WHERE title_normalized = ? AND author_normalized = ?",
        "SELECT * FROM books WHERE title_short = ? AND author_normalized = ?",
    ):
        row = conn.execute(sql, (tn, an)).fetchone()
        if row is not None:
            return row_to_entry(row)
    return None


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
        return "3+yrs"
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
    counts = {"<=12mo": 0, "12-36mo": 0, "3+yrs": 0}
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
                       list_pairs: set[tuple[str, str]]) -> list[dict]:
    """Look up each (title_norm, author_norm) pair in the catalog.
    Returns a list of resolved entries with their signals/themes
    attached (unresolved pairs drop out)."""
    out = []
    for tn, an in list_pairs:
        row = conn.execute(
            "SELECT * FROM books WHERE title_normalized = ? "
            "AND author_normalized = ?", (tn, an)).fetchone()
        if not row:
            row = conn.execute(
                "SELECT * FROM books WHERE title_short = ? "
                "AND author_normalized = ?", (tn, an)).fetchone()
        if not row:
            continue
        e = row_to_entry(row)
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


def commitment_load_warning(state: dict) -> dict | None:
    cl = state.get("commitment_load") or {}
    cap = cl.get("long_series_cap")
    used = cl.get("long_series_slots_used", 0)
    if cap is None:
        return None
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
                require_relevance: bool = True) -> list[dict]:
    """Build the quality-floor pool.  Filters in SQL where cheap,
    finishes in Python for the entry-point gate and exclusions.

    When `require_relevance` is False, the canonical-signal/theme
    relevance gate drops — used by `surprising` variance mode to
    surface quality-floor candidates that match no active vector
    ("books I almost didn't show you").
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
        sql += " AND (LOWER(primary_genre) = ? OR LOWER(secondary_genre) = ?) "
        params.append(genre.lower())
        params.append(genre.lower())

    pool: list[dict] = []
    for row in conn.execute(sql, params):
        e = row_to_entry(row)
        pair = (norm(e.get("title", "")), norm(e.get("author", "")))
        if pair in read_pairs or pair in list_pairs:
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


def assign_strata(pool: list[dict], underused: list[dict],
                  at_risk_floors: list[dict],
                  active_vectors: list[dict]) -> dict[str, list[dict]]:
    """Each candidate goes into every matching stratum (vector or
    floor), and into 'residual' if it matches neither.  A candidate
    can appear in multiple strata; the allocator handles dedup."""
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


def quality_score(c: dict, anchors: list[dict],
                  bucket_weight: dict[str, float],
                  comp_overlap_count: int) -> tuple[float, list[dict]]:
    base = float(c.get("goodreads_rating") or 0)
    anchor, matched_anchors = anchor_strength_for(
        c.get("_signals", set()), c.get("_themes", set()),
        anchors, bucket_weight)
    comp = min(comp_overlap_count, 3) * 0.6
    return base + anchor + comp, matched_anchors


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
    elif mode == "surprising":
        # Residual gets a guaranteed slot or two; vectors weighted
        # inverse to their pool size (rarer = more coverage needed).
        for s in stratum_names:
            weights[s] = 1.0
        if "residual" in stratum_names:
            weights["residual"] = 2.0
    else:
        # balanced
        for s in stratum_names:
            weights[s] = 1.0

    if lean:
        try:
            kind, name = lean.split(":", 1)
            target = (_stratum_label_vector(name) if kind == "vector"
                      else _stratum_label_floor(name) if kind == "floor"
                      else None)
            if target and target in weights:
                weights[target] *= 2.0
        except ValueError:
            pass

    # Light per-call jitter — ±20% for balanced, less for others.
    jitter = 0.20 if mode == "balanced" else 0.10
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
    return floors


def _rank_within_stratum(candidates: list[dict], conn: sqlite3.Connection,
                          anchors: list[dict],
                          bucket_weight: dict[str, float],
                          favorite_keys: set[str],
                          rng: random.Random) -> list[dict]:
    scored = []
    for c in candidates:
        comp_n = _comp_overlap_count(conn, c["key"], favorite_keys)
        score, matched_anchors = quality_score(c, anchors, bucket_weight, comp_n)
        c["_score"] = round(score, 3)
        c["_anchor_log_entries"] = matched_anchors
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
    strata = assign_strata(pool, underused, at_risk, active_vectors)
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
                     profile_notes: list[dict]) -> dict:
    matched_vectors = c.get("_matched_vectors") or []
    matched_themes = sorted(c.get("_themes", set()))
    matched_floors = c.get("_matched_floors") or []
    fills_vectors = [n for n in matched_vectors if n in underused_names]
    fills_floors = [n for n in matched_floors if n in at_risk_names]
    return {
        "key": c.get("key"),
        "title": c.get("title"),
        "author": c.get("author"),
        "pages": c.get("pages"),
        "primary_genre": c.get("primary_genre"),
        "indie": c.get("indie"),
        "classic": c.get("classic"),
        "match_reasoning": {
            "anchor_log_entries": c.get("_anchor_log_entries", []),
            "matched_vectors": matched_vectors,
            "matched_themes": matched_themes,
            "comp_overlap_count": c.get("_comp_overlap_count", 0),
            "entry_point_ok": True,
            "rating": c.get("goodreads_rating"),
        },
        "fills_gap": {
            "vectors": fills_vectors,
            "floors": fills_floors,
            "is_residual": bool(c.get("_is_residual")),
        },
        "warnings": _apply_warnings(c, profile_notes),
    }


# ---------------------------------------------------------------------------
# Subcommand: recommend
# ---------------------------------------------------------------------------

def cmd_recommend(args, conn: sqlite3.Connection) -> None:
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

    actives = active_vectors_of(state)
    if not actives:
        die("build_state has no active taste_vectors; nothing to "
            "match against", code=2)

    rejected_keys = {ev.get("key") for ev in state.get("events", [])
                     if ev.get("type") == "rejected" and ev.get("key")}

    active_signals = {s for v in actives for s in vector_signal_set(v)}
    active_themes = {t for v in actives for t in vector_theme_set(v)}

    pool = stage1_pool(
        conn,
        active_signals=active_signals,
        active_themes=active_themes,
        read_pairs=read_pairs,
        list_pairs=list_pairs,
        rejected_keys=rejected_keys,
        log_authors=log_authors,
        genre=args.genre,
    )
    pool_size = len(pool)

    # Surprising mode: also surface a residual sub-pool of
    # quality-floor candidates that match no active vector.
    if args.variance == "surprising":
        relaxed = stage1_pool(
            conn,
            active_signals=active_signals,
            active_themes=active_themes,
            read_pairs=read_pairs,
            list_pairs=list_pairs,
            rejected_keys=rejected_keys,
            log_authors=log_authors,
            genre=args.genre,
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
        n=n, variance=args.variance, lean=args.lean,
        rng=rng,
    )

    underused_names = {v["name"] for v in underused}
    at_risk_names = {f["name"] for f in at_risk}

    probe = build_probe(state.get("events", []), conn)

    output = {
        "candidates": [render_candidate(c, underused_names, at_risk_names,
                                         profile_notes)
                       for c in selected],
        "pool_size": pool_size,
        "stratum_breakdown": breakdown,
        "probe": probe,
        "variance_mode": args.variance,
    }
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
        "commitment_load_warning": commitment_load_warning(state),
        "page_budget_warning": page_budget_warning(picks,
                                                   state.get("page_budget")),
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
                   state: dict, list_size: int) -> dict:
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

    cl = state.get("commitment_load") or {}
    long_used = cl.get("long_series_slots_used", 0)
    doorstops = cl.get("doorstop_count", 0)
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
    scope_signals = _scope_signals(conn, books, state, len(list_pairs))

    output = {
        "series": series_name,
        "author": books_sorted[0].get("author") if books_sorted else None,
        "books": rendered_books,
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
# Subcommand: norm
# ---------------------------------------------------------------------------

def cmd_norm(args, _conn=None) -> None:
    print(norm(args.text))


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
    sp.add_argument("--variance", choices=VARIANCE_MODES, default="balanced")
    sp.add_argument("--seed", type=int, default=None)
    sp.set_defaults(func=cmd_recommend, needs_catalog=True)

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
