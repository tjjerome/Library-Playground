#!/usr/bin/env python3
"""Smoke test for `librarian_query.py series-fit`.

  - One-arc series via live catalog (Red Rising): all books returned
    in series_position order, narrative_shape=`one-arc`,
    scope_signals + scope_recommendation populated.
  - Loose-subseries via synthetic SQLite fixture with parens
    subseries notation: narrative_shape=`loose-subseries`, subseries
    groups detected.
  - Commitment-load differential: same series + same vector match,
    different reading-list contents (empty vs. ≥3 series each with
    ≥3 picks), produces different `scope_recommendation.scope`.
    Commitment load is *derived* from the list, not read from state.

Run via:
    python3 tests/series_fit_smoke.py
"""

from __future__ import annotations

import argparse
import io
import json
import sqlite3
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from webhelper import librarian_query as lq  # noqa: E402
from webhelper import sqlite_export as se  # noqa: E402


def _capture(args_ns) -> dict:
    buf = io.StringIO()
    saved = sys.stdout
    sys.stdout = buf
    try:
        conn = lq.open_catalog(args_ns.catalog)
        try:
            lq.cmd_series_fit(args_ns, conn)
        finally:
            conn.close()
    finally:
        sys.stdout = saved
    return json.loads(buf.getvalue())


def _make_args(workdir: Path, catalog: str, *, series: str,
               build_state: dict, log: str = "/dev/null",
               reading_list: str | None = None) -> SimpleNamespace:
    if reading_list is None:
        reading_list = "/dev/null"
    bs_path = workdir / "build_state.json"
    bs_path.write_text(json.dumps(build_state), encoding="utf-8")
    return SimpleNamespace(
        catalog=catalog,
        log=log,
        profile=None,
        reading_list=reading_list,
        build_state=str(bs_path),
        series=series, series_key=None,
    )


def _strong_match_state() -> dict:
    return {
        "n_target": 100,
        "taste_vectors": [
            {"name": "epic political fantasy",
             "canonical_signals": ["sweeping-scope", "morally-grey-protagonist",
                                    "richly-built-world"],
             "themes": ["power-and-authority", "loyalty-and-betrayal",
                        "morality-in-extremis"]},
            {"name": "world-building immersion",
             "canonical_signals": ["richly-built-world"],
             "themes": ["power-and-authority"]},
            {"name": "character-driven epic",
             "canonical_signals": ["deep-character-study",
                                    "morally-grey-protagonist"],
             "themes": ["loyalty-and-betrayal"]},
        ],
        "floors": {}, "events": [],
        "commitment_load": {},
        "page_budget": {"target_avg": 500},
    }


def _high_commitment_list_for(catalog_path: str) -> str:
    """Build a markdown reading-list with ≥3 distinct series, each
    with ≥3 books, drawn from the live catalog so resolve_list_picks
    actually finds them.  Picks the first three series that have
    ≥3 books in the catalog."""
    conn = sqlite3.connect(catalog_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT series, COUNT(*) AS n FROM books "
        "WHERE series IS NOT NULL AND series != '' "
        "AND series != 'Standalone' "
        "GROUP BY series HAVING n >= 3 "
        "ORDER BY n DESC LIMIT 4"
    ).fetchall()
    series_names = [r["series"] for r in rows]
    if len(series_names) < 3:
        conn.close()
        raise RuntimeError(
            f"live catalog lacks 3+ series with ≥3 books "
            f"(found {len(series_names)})")
    lines = ["| Title | Author |", "|---|---|"]
    for s in series_names[:4]:
        books = conn.execute(
            "SELECT title, author FROM books WHERE series = ? LIMIT 3",
            (s,)).fetchall()
        for b in books:
            lines.append(f"| {b['title']} | {b['author']} |")
    conn.close()
    return "\n".join(lines) + "\n"


def _build_synthetic_catalog(path: Path) -> None:
    """Create a tiny SQLite catalog with two books that carry
    parens-style subseries notation, so `_parse_subseries` fires."""
    conn = sqlite3.connect(str(path))
    for stmt in se.SCHEMA:
        conn.execute(stmt)
    conn.execute("INSERT INTO catalog_meta VALUES (?,?,?,?,?)",
                 (1, "2026-05-04", 4, 4, 0))

    rows = [
        # key, title, title_norm, title_short, author, author_norm, series,
        # series_position, series_status, series_role, author_entry_point,
        # primary_genre, secondary_genre, genre_legacy, indie, classic, pages,
        # gr_rating, gr_reviews, pub_year, summary, tone, pacing, pacing_notes,
        # setting, audio_suitability, audio_notes, confidence, research_source,
        # status, audit_json
        ("Guards! Guards! - Terry Pratchett", "Guards! Guards!",
         "guards guards", "guards guards", "Terry Pratchett",
         "terry pratchett", "Discworld", "Book 8 (City Watch Book 1)",
         "Long Series", "loose-entry", 1, "Fantasy", None, None, 0, 0, 380,
         4.4, 200000, 1989, "...", None, None, None, None, None, None,
         "high", None, "complete", None),
        ("Men at Arms - Terry Pratchett", "Men at Arms",
         "men at arms", "men at arms", "Terry Pratchett", "terry pratchett",
         "Discworld", "Book 15 (City Watch Book 2)", "Long Series", None,
         None, "Fantasy", None, None, 0, 0, 405, 4.4, 100000, 1993, "...",
         None, None, None, None, None, None, "high", None, "complete", None),
        ("Mort - Terry Pratchett", "Mort",
         "mort", "mort", "Terry Pratchett", "terry pratchett",
         "Discworld", "Book 4 (Death Book 1)", "Long Series", None, None,
         "Fantasy", None, None, 0, 0, 272, 4.3, 200000, 1987, "...",
         None, None, None, None, None, None, "high", None, "complete", None),
        ("Reaper Man - Terry Pratchett", "Reaper Man",
         "reaper man", "reaper man", "Terry Pratchett", "terry pratchett",
         "Discworld", "Book 11 (Death Book 2)", "Long Series", None, None,
         "Fantasy", None, None, 0, 0, 290, 4.3, 90000, 1991, "...",
         None, None, None, None, None, None, "high", None, "complete", None),
    ]
    conn.executemany(
        "INSERT INTO books VALUES (" + ",".join("?" * 31) + ")", rows)
    # taste_signals for one of the books so series-fit's _series_signals
    # has something to feed _scope_signals.
    for k in ("Guards! Guards! - Terry Pratchett",
              "Men at Arms - Terry Pratchett"):
        for s in ("morally-grey-protagonist", "richly-built-world"):
            conn.execute("INSERT INTO taste_signals VALUES (?,?,?)",
                         (k, "positive", s))
        for t in ("power-and-authority", "loyalty-and-betrayal"):
            conn.execute("INSERT INTO themes VALUES (?,?)", (k, t))
    conn.commit()
    conn.close()


def run(catalog: str) -> int:
    failures: list[str] = []

    # --- Test 1: live one-arc (Red Rising).
    state = _strong_match_state()
    with tempfile.TemporaryDirectory() as tmp:
        out = _capture(_make_args(Path(tmp), catalog,
                                   series="Red Rising",
                                   build_state=state))
    if len(out["books"]) < 5:
        failures.append(f"(1) Red Rising returned {len(out['books'])} books")
    if out["narrative_shape"] != "one-arc":
        failures.append(f"(1) Red Rising shape={out['narrative_shape']!r}")
    positions = [b["position"] for b in out["books"]]
    expected_first = "Book 1"
    if not positions or positions[0] != expected_first:
        failures.append(
            f"(1) Red Rising first position {positions[:1]!r}, "
            f"expected {expected_first!r}")
    if "vector_match" not in out["scope_signals"]:
        failures.append("(1) scope_signals.vector_match missing")
    if "commitment_load" not in out["scope_signals"]:
        failures.append("(1) scope_signals.commitment_load missing")
    if "scope" not in out["scope_recommendation"]:
        failures.append("(1) scope_recommendation.scope missing")

    # --- Test 2: synthetic loose-subseries.
    with tempfile.TemporaryDirectory() as tmp:
        synth_path = Path(tmp) / "synth.sqlite"
        _build_synthetic_catalog(synth_path)
        out2 = _capture(_make_args(Path(tmp), str(synth_path),
                                    series="Discworld",
                                    build_state=state))
    if out2["narrative_shape"] != "loose-subseries":
        failures.append(
            f"(2) synthetic Discworld shape "
            f"{out2['narrative_shape']!r}, expected loose-subseries")
    sub_names = {s["name"] for s in out2["subseries"]}
    if not {"city watch", "death"} <= sub_names:
        failures.append(
            f"(2) subseries detection: got {sub_names}, "
            f"expected city watch + death")

    # --- Test 3: commitment-load differential changes recommendation.
    # Derived from the reading list: empty list → low load → "all";
    # populated list with ≥3 series carrying ≥3 picks each → high
    # load → "entry".
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        low_list = tmp_path / "list_low.md"
        low_list.write_text("", encoding="utf-8")
        high_list = tmp_path / "list_high.md"
        high_list.write_text(_high_commitment_list_for(catalog),
                              encoding="utf-8")
        low = _capture(_make_args(tmp_path, catalog, series="Red Rising",
                                   build_state=_strong_match_state(),
                                   reading_list=str(low_list)))
        high = _capture(_make_args(tmp_path, catalog, series="Red Rising",
                                    build_state=_strong_match_state(),
                                    reading_list=str(high_list)))
    low_scope = low["scope_recommendation"]["scope"]
    high_scope = high["scope_recommendation"]["scope"]
    low_used = low["scope_signals"]["commitment_load"][
        "long_series_slots_used"]
    high_used = high["scope_signals"]["commitment_load"][
        "long_series_slots_used"]
    if low_used != 0:
        failures.append(
            f"(3) empty list derived long_used={low_used}, expected 0")
    if high_used < 3:
        failures.append(
            f"(3) populated list derived long_used={high_used}, "
            f"expected ≥3")
    if low_scope == high_scope:
        failures.append(
            f"(3) commitment-load did not affect scope "
            f"(low={low_scope!r}, high={high_scope!r})")

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
