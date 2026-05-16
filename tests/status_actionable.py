#!/usr/bin/env python3
"""Test that `status` returns ONLY actionable signals — empty arrays
when nothing is at risk, populated when thresholds cross.

Scenarios:
  1. Empty list, all floors > 0 → vectors_underused populated, floors
     populated, rejection_clusters empty, page_budget_warning null.
  2. List that satisfies all floors → floors_at_risk empty.
  3. Three same-vector rejections in a row → rejection_clusters has
     one record with count=3.
  4. Three rejections with one accept between them → rejection_clusters
     empty (run broken).
  5. Demoted vectors surface in `vectors_demoted`.
  6. page_budget configured + picks averaging too long → warning fires.

Run via:
    python3 tests/status_actionable.py
"""

from __future__ import annotations

import argparse
import io
import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from webhelper import librarian_query as lq  # noqa: E402

EMPTY_LOG = "title,authors,Last Date Read,My Rating\n"

BASE_VECTORS = [
    {"name": "vec-A", "weight": 1.0,
     "canonical_signals": ["unsettling-mood"], "themes": ["isolation"]},
    {"name": "vec-B", "weight": 1.0,
     "canonical_signals": ["morally-grey-protagonist"],
     "themes": ["loyalty-and-betrayal"]},
]


def _capture_status(args_ns) -> dict:
    buf = io.StringIO()
    saved = sys.stdout
    sys.stdout = buf
    try:
        conn = lq.open_catalog(args_ns.catalog)
        try:
            lq.cmd_status(args_ns, conn)
        finally:
            conn.close()
    finally:
        sys.stdout = saved
    return json.loads(buf.getvalue())


def _make_args(workdir: Path, catalog: str, *, build_state: dict,
               reading_list: str = "/dev/null",
               log: str | None = None) -> SimpleNamespace:
    log_path = log
    if log_path is None:
        p = workdir / "log.csv"
        p.write_text(EMPTY_LOG, encoding="utf-8")
        log_path = str(p)
    bs_path = workdir / "build_state.json"
    bs_path.write_text(json.dumps(build_state), encoding="utf-8")
    return SimpleNamespace(
        catalog=catalog, log=log_path,
        reading_list=reading_list,
        build_state=str(bs_path),
    )


def _write_list(workdir: Path, rows: list[tuple[str, str]]) -> str:
    p = workdir / "list.md"
    lines = ["| Title | Author |", "| --- | --- |"]
    for t, a in rows:
        lines.append(f"| {t} | {a} |")
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(p)


def run(catalog: str) -> int:
    failures: list[str] = []

    # --- Scenario 1: empty list, all floors open.
    state1 = {
        "n_target": 100,
        "taste_vectors": BASE_VECTORS,
        "floors": {"indie": 5, "classic": 3, "genres": {"horror": 4}},
        "events": [],
    }
    with tempfile.TemporaryDirectory() as tmp:
        out = _capture_status(_make_args(Path(tmp), catalog, build_state=state1))
    floors_names = {f["name"] for f in out["floors_at_risk"]}
    if not {"indie", "classic", "horror"} <= floors_names:
        failures.append(f"(1) floors_at_risk missing: {floors_names}")
    if not out["vectors_underused"]:
        failures.append("(1) vectors_underused empty for empty list")
    if out["rejection_clusters"]:
        failures.append("(1) rejection_clusters non-empty without events")
    if out["page_budget_warning"] is not None:
        failures.append("(1) page_budget_warning fired without budget")

    # --- Scenario 2: large enough list satisfies floors.
    # We're using synthetic catalog rows; for floors, we need the
    # resolve_list_picks call to actually find them.  Use real
    # catalog book titles (Pet Sematary etc.).
    import sqlite3
    conn = sqlite3.connect(catalog)
    conn.row_factory = sqlite3.Row
    indie_rows = list(conn.execute(
        "SELECT title, author FROM books WHERE indie = 1 LIMIT 5").fetchall())
    classic_rows = list(conn.execute(
        "SELECT title, author FROM books WHERE classic = 1 LIMIT 3").fetchall())
    conn.close()
    big_list = [(r["title"], r["author"]) for r in indie_rows + classic_rows]
    state2 = {
        "n_target": 100,
        "taste_vectors": BASE_VECTORS,
        "floors": {"indie": 5, "classic": 3},
        "events": [],
    }
    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        list_path = _write_list(wd, big_list)
        out2 = _capture_status(_make_args(
            wd, catalog, build_state=state2, reading_list=list_path))
    if any(f["name"] == "indie" for f in out2["floors_at_risk"]):
        failures.append("(2) indie floor still at-risk after 5 indie picks")
    if any(f["name"] == "classic" for f in out2["floors_at_risk"]):
        failures.append("(2) classic floor still at-risk after 3 classic picks")

    # --- Scenario 3: three same-vector rejections in a row → cluster.
    state3 = {
        "n_target": 100, "taste_vectors": BASE_VECTORS,
        "floors": {}, "events": [
            {"type": "rejected", "key": "X1", "vector": "vec-A", "ts": "1"},
            {"type": "rejected", "key": "X2", "vector": "vec-A", "ts": "2"},
            {"type": "rejected", "key": "X3", "vector": "vec-A", "ts": "3"},
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        out3 = _capture_status(_make_args(Path(tmp), catalog,
                                           build_state=state3))
    if not out3["rejection_clusters"]:
        failures.append("(3) no rejection_cluster after 3 same-vector rejects")
    elif (out3["rejection_clusters"][0]["value"] != "vec-A"
          or out3["rejection_clusters"][0]["count"] != 3):
        failures.append(
            f"(3) cluster shape wrong: {out3['rejection_clusters']}")

    # --- Scenario 4: accept breaks the run.
    state4 = {
        "n_target": 100, "taste_vectors": BASE_VECTORS,
        "floors": {}, "events": [
            {"type": "rejected", "key": "X1", "vector": "vec-A", "ts": "1"},
            {"type": "rejected", "key": "X2", "vector": "vec-A", "ts": "2"},
            {"type": "accepted", "key": "Y", "vector": "vec-A", "ts": "3"},
            {"type": "rejected", "key": "X3", "vector": "vec-A", "ts": "4"},
        ],
    }
    with tempfile.TemporaryDirectory() as tmp:
        out4 = _capture_status(_make_args(Path(tmp), catalog,
                                           build_state=state4))
    if out4["rejection_clusters"]:
        failures.append(
            f"(4) cluster fired through intervening accept: "
            f"{out4['rejection_clusters']}")

    # --- Scenario 5: demoted vectors surface.
    state5 = {
        "n_target": 100,
        "taste_vectors": [
            {"name": "active-1", "canonical_signals": ["unsettling-mood"],
             "themes": ["isolation"]},
            {"name": "old-phase", "status": "demoted",
             "canonical_signals": ["sweeping-scope"],
             "themes": ["power-and-authority"]},
        ],
        "floors": {}, "events": [],
    }
    with tempfile.TemporaryDirectory() as tmp:
        out5 = _capture_status(_make_args(Path(tmp), catalog,
                                           build_state=state5))
    if "old-phase" not in out5["vectors_demoted"]:
        failures.append(
            f"(5) demoted vector missing from vectors_demoted: "
            f"{out5['vectors_demoted']}")

    # --- Scenario 6: page-budget warning when avg exceeds target.
    big_list_pages = []
    conn = sqlite3.connect(catalog)
    conn.row_factory = sqlite3.Row
    for r in conn.execute(
        "SELECT title, author, pages FROM books WHERE pages > 700 LIMIT 4"
    ):
        big_list_pages.append((r["title"], r["author"]))
    conn.close()
    state6 = {
        "n_target": 100, "taste_vectors": BASE_VECTORS,
        "floors": {}, "events": [],
        "page_budget": {"target_avg": 350},
    }
    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        list_path = _write_list(wd, big_list_pages)
        out6 = _capture_status(_make_args(
            wd, catalog, build_state=state6, reading_list=list_path))
    if out6["page_budget_warning"] is None:
        failures.append("(6) page_budget_warning did not fire on long list")

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
