#!/usr/bin/env python3
"""Test that `--lean vector:NAME` increases the named vector's
allocation vs an unleant baseline (same seed, same fixtures).

Run via:
    python3 tests/recommend_lean.py
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

BUILD_STATE = {
    "n_target": 100,
    "taste_vectors": [
        {"name": "grief-rooted horror", "weight": 1.0,
         "canonical_signals": ["unsettling-mood", "lyrical-prose",
                               "atmospheric-dread"],
         "themes": ["grief-and-loss", "isolation"]},
        {"name": "morally-grey leads", "weight": 1.0,
         "canonical_signals": ["morally-grey-protagonist"],
         "themes": ["morality-in-extremis"]},
        {"name": "structural cleverness", "weight": 1.0,
         "canonical_signals": ["unconventional-structure",
                               "metafictional"],
         "themes": ["identity-and-self"]},
    ],
    "floors": {"indie": 5},
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


def _make_args(workdir: Path, catalog: str, lean: str | None) -> SimpleNamespace:
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
        genre=None, n=15, lean=lean,
        variance="balanced", seed=7,
    )


def run(catalog: str) -> int:
    failures: list[str] = []
    target_vector = "morally-grey leads"
    target_label = f"vector:{target_vector}"

    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        baseline = _capture(_make_args(wd, catalog, lean=None))
        leaned = _capture(_make_args(wd, catalog, lean=f"vector:{target_vector}"))

    base_n = baseline["stratum_breakdown"].get(target_label, 0)
    lean_n = leaned["stratum_breakdown"].get(target_label, 0)
    if lean_n <= base_n:
        failures.append(
            f"--lean vector:{target_vector!r} did not increase allocation "
            f"(baseline={base_n}, leaned={lean_n})")

    # Floor lean too.
    target_label_f = "floor:indie"
    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        baseline_f = _capture(_make_args(wd, catalog, lean=None))
        leaned_f = _capture(_make_args(wd, catalog, lean="floor:indie"))
    base_f = baseline_f["stratum_breakdown"].get(target_label_f, 0)
    lean_f = leaned_f["stratum_breakdown"].get(target_label_f, 0)
    if lean_f <= base_f:
        failures.append(
            f"--lean floor:indie did not increase allocation "
            f"(baseline={base_f}, leaned={lean_f})")

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
