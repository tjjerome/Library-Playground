#!/usr/bin/env python3
"""Test that vectors marked `status: "demoted"` are excluded from
the recommender's output:

  - No candidate's `matched_vectors` includes the demoted vector
  - No candidate is sampled into a stratum named after the demoted
    vector
  - Anchor weighting drops to zero when the only matching log entries
    point at signals/themes exclusive to demoted vectors

Run via:
    python3 tests/recommend_demoted.py
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

SYNTHETIC_LOG = (
    "title,authors,Last Date Read,My Rating,genre,series_type,my_tags\n"
    "Pet Sematary,Stephen King,2/1/2026,5,Horror,Standalone,\n"
)

DEMOTED_VECTOR = "epic fantasy doorstops"
ACTIVE_VECTOR = "grief-rooted horror"

BUILD_STATE = {
    "n_target": 100,
    "taste_vectors": [
        {"name": ACTIVE_VECTOR, "weight": 1.0, "status": "active",
         "canonical_signals": ["unsettling-mood", "lyrical-prose"],
         "themes": ["grief-and-loss", "isolation"]},
        {"name": DEMOTED_VECTOR, "status": "demoted",
         "demoted_reason": "phase",
         "canonical_signals": ["sweeping-scope", "richly-built-world"],
         "themes": ["power-and-authority"]},
    ],
    "floors": {"indie": 4},
    "events": [],
}


def _capture(args_ns) -> dict:
    buf = io.StringIO()
    saved = sys.stdout
    sys.stdout = buf
    try:
        conn = lq.open_catalog(args_ns.catalog)
        try:
            lq.cmd_recommend(args_ns, conn)
        finally:
            conn.close()
    finally:
        sys.stdout = saved
    return json.loads(buf.getvalue())


def _make_args(workdir: Path, catalog: str) -> SimpleNamespace:
    log_path = workdir / "log.csv"
    log_path.write_text(SYNTHETIC_LOG, encoding="utf-8")
    bs_path = workdir / "build_state.json"
    bs_path.write_text(json.dumps(BUILD_STATE), encoding="utf-8")
    return SimpleNamespace(
        catalog=catalog,
        log=str(log_path),
        profile=None,
        reading_list="/dev/null",
        build_state=str(bs_path),
        genre=None, n=15, lean=None,
        variance="balanced", seed=21,
    )


def run(catalog: str) -> int:
    failures: list[str] = []

    with tempfile.TemporaryDirectory() as tmp:
        out = _capture(_make_args(Path(tmp), catalog))

    # No candidate should list the demoted vector.
    for c in out["candidates"]:
        mv = c["match_reasoning"]["matched_vectors"]
        if DEMOTED_VECTOR in mv:
            failures.append(
                f"candidate {c['key']!r} matched_vectors includes "
                f"demoted {DEMOTED_VECTOR!r}: {mv}")

    # No stratum named after the demoted vector.
    demoted_label = f"vector:{DEMOTED_VECTOR}"
    if demoted_label in out["stratum_breakdown"]:
        failures.append(
            f"stratum_breakdown contains demoted-vector stratum "
            f"{demoted_label!r}: {out['stratum_breakdown']}")

    # Anchor inputs: when only the demoted vector's signals/themes
    # match a log entry, that entry should NOT contribute to anchor
    # weighting.  Test the helper directly: build an isolated
    # situation where active_signal_pool excludes demoted-only signals.
    import sqlite3
    conn = sqlite3.connect(catalog)
    conn.row_factory = sqlite3.Row
    try:
        active_signals = {"unsettling-mood", "lyrical-prose"}
        active_themes = {"grief-and-loss", "isolation"}
        # Pick a 4★+ log row whose catalog signals/themes intersect
        # ONLY the demoted vector's vocabulary.
        log = [{
            "title": "Pet Sematary", "authors": "Stephen King",
            "Last Date Read": "2/1/2026", "My Rating": "5",
        }]
        anchors_a, _ = lq.compute_log_anchors(log, conn, active_signals, active_themes)
        # Now restrict to demoted-only vocab; should yield no anchors.
        demoted_signals = {"sweeping-scope", "richly-built-world"}
        demoted_themes = {"power-and-authority"}
        anchors_b, _ = lq.compute_log_anchors(log, conn,
                                              demoted_signals, demoted_themes)
        # Pet Sematary has grief-and-loss / unsettling-mood — should
        # produce anchors against active vocab.
        if not anchors_a:
            failures.append(
                "compute_log_anchors returned 0 anchors against active "
                "vocab — fixture invalid (Pet Sematary should match "
                "grief-and-loss / unsettling-mood)")
        # …and should produce zero anchors when the active vocab is
        # confined to the demoted vector's signals (Pet Sematary
        # doesn't match power-and-authority etc).
        if anchors_b:
            failures.append(
                f"anchors with demoted-only vocab returned "
                f"{len(anchors_b)} (should be 0)")
    finally:
        conn.close()

    # vectors_demoted exposed via status (cross-check).
    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        bs_path = wd / "build_state.json"
        bs_path.write_text(json.dumps(BUILD_STATE), encoding="utf-8")
        log_path = wd / "log.csv"
        log_path.write_text(SYNTHETIC_LOG, encoding="utf-8")
        args_status = SimpleNamespace(
            catalog=catalog, log=str(log_path),
            reading_list="/dev/null",
            build_state=str(bs_path),
        )
        buf = io.StringIO()
        saved = sys.stdout
        sys.stdout = buf
        try:
            conn = lq.open_catalog(catalog)
            try:
                lq.cmd_status(args_status, conn)
            finally:
                conn.close()
        finally:
            sys.stdout = saved
        status_out = json.loads(buf.getvalue())
        if DEMOTED_VECTOR not in status_out["vectors_demoted"]:
            failures.append(
                f"status vectors_demoted missing {DEMOTED_VECTOR!r}: "
                f"{status_out['vectors_demoted']}")

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
