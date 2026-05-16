#!/usr/bin/env python3
"""Variance-mode tests for `librarian_query.py recommend`.

  - `--variance focused` concentrates ≥50% of slots on one vector
  - `--variance similar` carries no structural residual quota
  - `--variance balanced` reserves a ~20% residual quota
  - `--variance broad` reserves a heavier (~35-40%) residual quota
  - residual share ordering: similar < balanced < broad
  - focused stays more lopsided than balanced

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


def _residual_share(breakdown: dict, n: int) -> float:
    if not breakdown or n == 0:
        return 0.0
    total = sum(breakdown.values()) or n
    return breakdown.get("residual", 0) / total


def run(catalog: str) -> int:
    failures: list[str] = []
    n = 15
    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        similar = _capture(_make_args(wd, catalog, "similar", n=n))
        balanced = _capture(_make_args(wd, catalog, "balanced", n=n))
        broad = _capture(_make_args(wd, catalog, "broad", n=n))
        focused = _capture(_make_args(wd, catalog, "focused", n=n))

    bal_max = _max_share(balanced["stratum_breakdown"], n)
    foc_max = _max_share(focused["stratum_breakdown"], n)

    sim_res = _residual_share(similar["stratum_breakdown"], n)
    bal_res = _residual_share(balanced["stratum_breakdown"], n)
    brd_res = _residual_share(broad["stratum_breakdown"], n)

    # focused: top stratum should hold ≥50% of slots.
    if foc_max < 0.5:
        failures.append(
            f"focused mode top-stratum share {foc_max:.0%} < 50%")
    if foc_max <= bal_max:
        failures.append(
            f"focused max share ({foc_max:.0%}) not greater than "
            f"balanced ({bal_max:.0%})")

    # similar: no structural residual quota (similarity-heavy).  A
    # stray residual match is tolerable but it must stay well under
    # the balanced quota.
    if sim_res >= 0.15:
        failures.append(
            f"similar mode residual share {sim_res:.0%} ≥ 15% "
            f"(should carry no structural quota)")

    # balanced: ~20% residual quota (allow jitter band).
    if not (0.10 <= bal_res <= 0.30):
        failures.append(
            f"balanced mode residual share {bal_res:.0%} outside "
            f"[10%,30%] (expected ~20%)")

    # broad: heavier residual quota (~35-40%).
    if brd_res < 0.30:
        failures.append(
            f"broad mode residual share {brd_res:.0%} < 30% "
            f"(expected ~35-40%)")

    # Ordering: similar < balanced < broad.
    if not (sim_res < bal_res < brd_res):
        failures.append(
            f"residual share not ordered similar<balanced<broad "
            f"({sim_res:.0%} / {bal_res:.0%} / {brd_res:.0%})")

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
