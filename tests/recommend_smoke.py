#!/usr/bin/env python3
"""Smoke test for `librarian_query.py recommend`.

Runs the recommender against the live SQLite catalog and a synthetic
log/list/build_state set, then verifies the output contract:

  (a) pool_size > 0
  (b) every candidate passes exclusion + entry-point gate
  (c) no `goodreads_reviews` field appears anywhere in output
  (d) at least one candidate matches an underused vector
  (e) `--genre Horror` restricts the pool
  (f) a rejected key in build_state.events does not appear in candidates
  (g) a known non-Book-1 by an unread author is excluded
  (h) default --n returns 12-18 candidates
  (i) stratum_breakdown sums to candidate count

Run via:
    python3 tests/recommend_roundtrip.py            # default: live catalog
    python3 tests/recommend_smoke.py --catalog X    # alternative
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
    "The Fisherman,John Langan,1/15/2026,5,Horror,Standalone,\n"
    "House of Leaves,Mark Z. Danielewski,3/1/2024,4.5,Horror,Standalone,\n"
    "The Lions of Al-Rassan,Guy Gavriel Kay,11/1/2025,4.5,Fantasy,Standalone,\n"
    "Blood Over Bright Haven,M.L. Wang,12/1/2025,5,Fantasy,Standalone,\n"
)

SYNTHETIC_BUILD_STATE = {
    "n_target": 100,
    "taste_vectors": [
        {"name": "grief-rooted horror", "weight": 1.0,
         "canonical_signals": ["unsettling-mood", "lyrical-prose",
                               "atmospheric-dread"],
         "themes": ["grief-and-loss", "isolation"]},
        {"name": "morally-grey leads", "weight": 1.0,
         "canonical_signals": ["morally-grey-protagonist"],
         "themes": ["morality-in-extremis", "loyalty-and-betrayal"]},
    ],
    "floors": {"indie": 8, "classic": 5},
    "events": [],
    "commitment_load": {"long_series_slots_used": 0},
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


def _make_args(workdir: Path, *, catalog: str, build_state: dict,
               n: int = 15, genre: str | None = None,
               variance: str = "balanced",
               seed: int = 42, lean: str | None = None,
               reading_list: str | None = None) -> SimpleNamespace:
    log_path = workdir / "log.csv"
    log_path.write_text(SYNTHETIC_LOG, encoding="utf-8")
    bs_path = workdir / "build_state.json"
    bs_path.write_text(json.dumps(build_state), encoding="utf-8")
    list_path = reading_list or "/dev/null"
    return SimpleNamespace(
        catalog=catalog,
        log=str(log_path),
        profile=None,
        reading_list=list_path,
        build_state=str(bs_path),
        genre=genre,
        n=n,
        lean=lean,
        variance=variance,
        seed=seed,
    )


def run(catalog: str) -> int:
    failures: list[str] = []
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)

        # Baseline call.
        args = _make_args(workdir, catalog=catalog,
                          build_state=SYNTHETIC_BUILD_STATE)
        out = _capture(args)

        # (a) pool_size > 0
        if out["pool_size"] <= 0:
            failures.append(f"(a) pool_size = {out['pool_size']}")

        # (h) default --n returns 12-18
        n_cands = len(out["candidates"])
        if not (12 <= n_cands <= 18):
            failures.append(f"(h) candidate count {n_cands} outside [12,18]")

        # (i) breakdown sums to candidate count
        if sum(out["stratum_breakdown"].values()) != n_cands:
            failures.append(
                f"(i) breakdown sum {sum(out['stratum_breakdown'].values())} "
                f"!= candidate count {n_cands}")

        # (c) no goodreads_reviews anywhere
        if "goodreads_reviews" in json.dumps(out):
            failures.append("(c) goodreads_reviews leaked into output")

        # (b) every candidate passes exclusion (synthetic log titles
        # are not in candidates).
        log_titles = {"pet sematary", "the fisherman", "house of leaves",
                      "the lions of al-rassan", "blood over bright haven"}
        for c in out["candidates"]:
            if (c.get("title") or "").lower() in log_titles:
                failures.append(f"(b) excluded title resurfaced: {c['title']}")
                break

        # (d) ≥1 candidate matches an underused vector
        any_match = any(c["match_reasoning"]["matched_vectors"]
                        for c in out["candidates"])
        if not any_match:
            failures.append("(d) no candidate matched any underused vector")

        # (e) genre filter restricts pool
        args_horror = _make_args(workdir, catalog=catalog,
                                  build_state=SYNTHETIC_BUILD_STATE,
                                  genre="Horror")
        out_horror = _capture(args_horror)
        if out_horror["pool_size"] >= out["pool_size"]:
            failures.append(
                f"(e) Horror pool {out_horror['pool_size']} not smaller "
                f"than baseline {out['pool_size']}")
        non_horror = [c for c in out_horror["candidates"]
                      if (c.get("primary_genre") or "").lower() != "horror"]
        # secondary genre matches are valid; just check ≥1 horror present
        horror_count = len(out_horror["candidates"]) - len(non_horror)
        if horror_count == 0:
            failures.append("(e) Horror filter returned no horror picks")

        # (f) rejected key excluded
        first_key = out["candidates"][0]["key"]
        rejected_state = {**SYNTHETIC_BUILD_STATE,
                          "events": [{"type": "rejected", "key": first_key,
                                      "vector": "grief-rooted horror"}]}
        args_rej = _make_args(workdir, catalog=catalog,
                               build_state=rejected_state)
        out_rej = _capture(args_rej)
        if any(c["key"] == first_key for c in out_rej["candidates"]):
            failures.append(f"(f) rejected key {first_key!r} still in output")

        # (g) entry-point gate excludes a known non-Book-1 by unread author.
        # Find a non-Book-1 candidate in the catalog whose author is NOT in
        # the synthetic log; assert it's not in any candidate output.
        import sqlite3
        conn = sqlite3.connect(catalog)
        conn.row_factory = sqlite3.Row
        log_authors_norm = {lq.norm("Stephen King"), lq.norm("John Langan"),
                            lq.norm("Mark Z. Danielewski"),
                            lq.norm("Guy Gavriel Kay"), lq.norm("M.L. Wang")}
        bad_row = None
        for r in conn.execute(
            "SELECT * FROM books WHERE series_status IN ('Long Series','Short Series') "
            "AND series_position NOT LIKE 'Book 1%' "
            "AND series_role IS NOT 'standalone' "
            "AND series_role IS NOT 'first' "
            "AND author_entry_point IS NOT 1 "
            "AND goodreads_rating >= 4.0 LIMIT 100"
        ):
            if lq.norm(r["author"]) not in log_authors_norm:
                bad_row = r
                break
        conn.close()
        if bad_row is not None:
            bad_key = bad_row["key"]
            if any(c["key"] == bad_key for c in out["candidates"]):
                failures.append(
                    f"(g) entry-point violator {bad_key!r} surfaced")

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
