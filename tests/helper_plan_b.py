#!/usr/bin/env python3
"""Plan B acceptance tests for `webhelper/librarian_query.py`.

Covers the helper-side migration:

  - Test 1  field rename complete (`anchor_log_entries` → `resonance_titles`)
  - Test 2  default projection omits goodreads_rating / audio_suitability
  - Test 3  --show-gr / --show-audio expose the fields
  - Test 4  --mode curate refuses to source (exit non-zero, no JSON)
  - Test 5  variance default responds to expansion_appetite
  - Test 6  defended ≥2 excluded from swap_suggestions + locked list
  - Test 7  one defense exposes defended_count: 1 (still surfaced)
  - Test 8  session_lock excludes immediately
  - Test 9  v1 build_state loads with normalized v2 defaults

Run via:
    python3 tests/helper_plan_b.py
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
    ],
    "floors": {"indie": 8, "classic": 5},
    "events": [],
}


def _write(workdir: Path, build_state: dict) -> tuple[str, str]:
    log_path = workdir / "log.csv"
    log_path.write_text(SYNTHETIC_LOG, encoding="utf-8")
    bs_path = workdir / "build_state.json"
    bs_path.write_text(json.dumps(build_state), encoding="utf-8")
    return str(log_path), str(bs_path)


def _rec_args(catalog: str, log: str, bs: str, **over) -> SimpleNamespace:
    base = dict(
        catalog=catalog, log=log, profile=None, reading_list="/dev/null",
        build_state=bs, genre=None, n=15, lean=None, variance=None,
        seed=42, show_gr=False, show_audio=False, mode="discover",
    )
    base.update(over)
    return SimpleNamespace(**base)


def _capture_recommend(args_ns) -> dict:
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


def _capture_compare(args_ns) -> dict:
    buf = io.StringIO()
    saved = sys.stdout
    sys.stdout = buf
    try:
        conn = lq.open_catalog(args_ns.catalog)
        try:
            lq.cmd_compare(args_ns, conn)
        finally:
            conn.close()
    finally:
        sys.stdout = saved
    return json.loads(buf.getvalue())


def run(catalog: str) -> int:  # noqa: C901
    failures: list[str] = []

    # ---- Test 1: rename complete in source ----------------------------
    src = (REPO / "webhelper" / "librarian_query.py").read_text("utf-8")
    if "anchor_log_entries" in src:
        failures.append("(1) 'anchor_log_entries' still present in source")

    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        log, bs = _write(wd, BUILD_STATE)

        # ---- Test 2: default projection omits gr/audio ----------------
        out = _capture_recommend(_rec_args(catalog, log, bs, seed=1))
        cand = out["candidates"][0]
        if "goodreads_rating" in cand or "audio_suitability" in cand:
            failures.append("(2) default projection leaks gr/audio")
        if "rating" in cand["match_reasoning"]:
            failures.append("(2) match_reasoning still carries 'rating'")
        if "resonance_titles" not in cand["match_reasoning"]:
            failures.append("(2) match_reasoning missing 'resonance_titles'")
        if "anchor_log_entries" in cand["match_reasoning"]:
            failures.append("(1) output still emits 'anchor_log_entries'")

        # ---- Test 3: opt-in flags expose fields -----------------------
        out3 = _capture_recommend(
            _rec_args(catalog, log, bs, seed=1,
                      show_gr=True, show_audio=True))
        c3 = out3["candidates"][0]
        if "goodreads_rating" not in c3 or "audio_suitability" not in c3:
            failures.append("(3) --show-gr/--show-audio did not expose fields")

        # ---- Test 4: curate mode refuses to source --------------------
        try:
            _capture_recommend(_rec_args(catalog, log, bs, mode="curate"))
            failures.append("(4) curate mode did not exit non-zero")
        except SystemExit as e:
            if e.code in (0, None):
                failures.append(f"(4) curate mode exit code {e.code} == 0")

        # ---- Test 5: variance default tracks expansion_appetite -------
        expect = {"high": "broad", "low": "similar",
                  "moderate": "balanced", None: "balanced"}
        for appetite, mode in expect.items():
            st = json.loads(json.dumps(BUILD_STATE))
            if appetite is not None:
                st["preferences"] = {"expansion_appetite": appetite}
            _, bs5 = _write(wd, st)
            o = _capture_recommend(_rec_args(catalog, log, bs5, seed=4))
            if o["variance_mode"] != mode:
                failures.append(
                    f"(5) appetite={appetite!r} → variance_mode "
                    f"{o['variance_mode']!r}, expected {mode!r}")
        # Explicit --variance still wins over appetite.
        st = json.loads(json.dumps(BUILD_STATE))
        st["preferences"] = {"expansion_appetite": "high"}
        _, bs5 = _write(wd, st)
        o = _capture_recommend(
            _rec_args(catalog, log, bs5, seed=4, variance="similar"))
        if o["variance_mode"] != "similar":
            failures.append("(5) explicit --variance overridden by appetite")

    # ---- Tests 6-8: compare lock filtering ----------------------------
    conn = lq.open_catalog(catalog)
    rows = conn.execute(
        "SELECT key, title, author FROM books "
        "WHERE goodreads_rating >= 4.0 LIMIT 5").fetchall()
    conn.close()
    keys = [(r["key"], r["title"], r["author"]) for r in rows]
    if len(keys) < 5:
        failures.append("(6-8) not enough catalog rows for compare test")
    else:
        add_k, add_t, add_a = keys[0]
        twice_k, twice_t, _ = keys[1]
        once_k, once_t, _ = keys[2]
        lock_k, lock_t, _ = keys[3]
        with tempfile.TemporaryDirectory() as tmp:
            wd = Path(tmp)
            log, _ = _write(wd, BUILD_STATE)
            rl = wd / "RL.md"
            lines = ["| Title | Author |", "| --- | --- |"]
            for k, t, a in keys[1:]:
                lines.append(f"| {t} | {a} |")
            rl.write_text("\n".join(lines) + "\n", encoding="utf-8")
            st = json.loads(json.dumps(BUILD_STATE))
            st["events"] = [
                {"type": "defended", "key": twice_k, "title": twice_t},
                {"type": "defended", "key": twice_k, "title": twice_t},
                {"type": "defended", "key": once_k, "title": once_t},
                {"type": "session_lock", "key": lock_k, "title": lock_t},
            ]
            bs_path = wd / "bs.json"
            bs_path.write_text(json.dumps(st), encoding="utf-8")
            cargs = SimpleNamespace(
                catalog=catalog, log=log, profile=None,
                reading_list=str(rl), build_state=str(bs_path),
                add=add_t, add_author=add_a, n=10)
            cout = _capture_compare(cargs)
            swap_keys = {s["key"] for s in cout["swap_suggestions"]}
            excluded = set(cout["locked_picks_excluded"])

            # Test 6: defended ≥2 excluded + listed.
            if twice_k in swap_keys:
                failures.append("(6) defended≥2 pick still in swaps")
            if twice_k not in excluded:
                failures.append("(6) defended≥2 pick not in "
                                 "locked_picks_excluded")
            # Test 7: one defense still surfaces with defended_count 1.
            once_entry = next((s for s in cout["swap_suggestions"]
                               if s["key"] == once_k), None)
            if once_entry is None:
                failures.append("(7) singly-defended pick dropped from swaps")
            elif once_entry.get("defended_count") != 1:
                failures.append(
                    f"(7) defended_count {once_entry.get('defended_count')} "
                    f"!= 1 for singly-defended pick")
            # Test 8: session_lock excluded immediately.
            if lock_k in swap_keys:
                failures.append("(8) session_lock pick still in swaps")
            if lock_k not in excluded:
                failures.append("(8) session_lock pick not in "
                                 "locked_picks_excluded")
            if "anchor_log_entries" in json.dumps(cout):
                failures.append("(1) compare output emits anchor_log_entries")

    # ---- Test 9: v1 backward compat -----------------------------------
    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        v1 = {"n_target": 100, "taste_vectors": [], "floors": {},
              "events": [{"type": "rejected", "key": "x"}]}
        p = wd / "v1.json"
        p.write_text(json.dumps(v1), encoding="utf-8")
        st = lq.load_build_state(str(p))
        if st.get("version") != 2:
            failures.append(f"(9) version not normalized to 2: "
                            f"{st.get('version')}")
        pr = st.get("preferences", {})
        if pr.get("series_commitment") != "binary":
            failures.append("(9) series_commitment default != binary")
        if pr.get("curiosity_targets") != []:
            failures.append("(9) curiosity_targets default != []")
        if pr.get("expansion_appetite") != "moderate":
            failures.append("(9) expansion_appetite default != moderate")
        if st["events"] != v1["events"]:
            failures.append("(9) v1 events mutated on load")

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
