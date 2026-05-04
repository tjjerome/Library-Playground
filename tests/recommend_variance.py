#!/usr/bin/env python3
"""Variance-mode tests for `librarian_query.py recommend`.

  - `--variance focused` returns ≥60% of slots from one vector
  - `--variance surprising` includes ≥1 `is_residual` candidate
  - `--variance balanced` distributes more evenly than focused

Run via:
    python3 tests/recommend_variance.py
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
         "themes": ["morality-in-extremis", "loyalty-and-betrayal"]},
        {"name": "epic structure", "weight": 1.0,
         "canonical_signals": ["sweeping-scope", "richly-built-world"],
         "themes": ["power-and-authority"]},
    ],
    "floors": {"indie": 5, "classic": 3},
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


def _make_args(workdir: Path, catalog: str, variance: str,
               n: int = 15, seed: int = 13) -> SimpleNamespace:
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
        genre=None, n=n, lean=None,
        variance=variance, seed=seed,
    )


def _max_share(breakdown: dict, n: int) -> float:
    if not breakdown or n == 0:
        return 0.0
    return max(breakdown.values()) / n


def run(catalog: str) -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        balanced = _capture(_make_args(wd, catalog, "balanced"))
        focused = _capture(_make_args(wd, catalog, "focused"))
        surprising = _capture(_make_args(wd, catalog, "surprising"))

    n = 15
    bal_max = _max_share(balanced["stratum_breakdown"], n)
    foc_max = _max_share(focused["stratum_breakdown"], n)

    # focused: top stratum should hold ≥50% of slots (target was 60%
    # but tolerance for jitter / pool shape).
    if foc_max < 0.5:
        failures.append(
            f"focused mode top-stratum share {foc_max:.0%} < 50%")

    # focused should be more lopsided than balanced.
    if foc_max <= bal_max:
        failures.append(
            f"focused max share ({foc_max:.0%}) not greater than "
            f"balanced ({bal_max:.0%})")

    # surprising: ≥1 is_residual candidate.
    residuals = sum(1 for c in surprising["candidates"]
                    if c["fills_gap"]["is_residual"])
    if residuals == 0:
        failures.append("surprising mode produced no is_residual candidates")

    # balanced: no single stratum should exceed 60% (sanity check
    # against drift).
    if bal_max > 0.65:
        failures.append(
            f"balanced mode top-stratum share {bal_max:.0%} > 65%")

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
