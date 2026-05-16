#!/usr/bin/env python3
"""Plan C regression tests — helper-side fixes.

Covers:
  Issue 1  list_set() strips markdown emphasis (the compare blocker)
  Issue 3  GR is a small weighted ranking input; never projected by
           default; --show-gr surfaces it; nothing gated for low GR
  Issue 4  selection-bias-corrected, series-aware effective_gr_signal:
             - Heckman worked-example reproduction
             - tight monotone-inflating series → corrected < plain mean
             - loose-series member → own rating (no pooling)
             - true standalone → own rating
             - duology → beta≈0.6 path (no regression)
             - non-monotone / anchorless → fall back to own rating
             - intermediates never projected, with or without --show-gr

Prints OK and exits 0 on success; prints failures and exits 1.
"""

import json
import sqlite3
import statistics
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from webhelper import librarian_query as lq  # noqa: E402

CATALOG = str(REPO / "Library_Catalog.sqlite")

SYNTHETIC_LOG = (
    "title,authors,Last Date Read,My Rating,genre,series_type,my_tags\n"
    "Pet Sematary,Stephen King,2/1/2026,5,Horror,Standalone,\n"
    "The Fisherman,John Langan,1/15/2026,5,Horror,Standalone,\n"
)

BUILD_STATE = {
    "version": 2,
    "n_target": 100,
    "taste_vectors": [
        {"name": "v1", "weight": 1.0,
         "canonical_signals": ["unsettling-mood", "atmospheric-dread"],
         "themes": ["grief-and-loss", "isolation"]},
        {"name": "v2", "weight": 1.0,
         "canonical_signals": ["morally-grey-protagonist"],
         "themes": ["loyalty-and-betrayal", "morality-in-extremis"]},
    ],
    "floors": {}, "events": [],
    "preferences": {"expansion_appetite": "moderate"},
}


def _rec_args(wd: Path, *, show_gr=False, seed=1, reading_list="/dev/null"):
    log = wd / "log.csv"
    log.write_text(SYNTHETIC_LOG, encoding="utf-8")
    bs = wd / "bs.json"
    bs.write_text(json.dumps(BUILD_STATE), encoding="utf-8")
    return SimpleNamespace(
        catalog=CATALOG, log=str(log), profile=None,
        reading_list=reading_list, build_state=str(bs), genre=None,
        n=15, lean=None, variance=None, show_gr=show_gr,
        show_audio=False, mode="discover", audit_exclusions=False,
        seed=seed)


def _capture(fn, args):
    import contextlib
    import io
    buf = io.StringIO()
    conn = lq.open_catalog(args.catalog)
    try:
        with contextlib.redirect_stdout(buf):
            fn(args, conn)
    finally:
        conn.close()
    return json.loads(buf.getvalue())


def main() -> int:  # noqa: C901
    fails: list[str] = []

    # ---- Issue 1: markdown emphasis strip --------------------------
    cases = {
        "*Red Country*": "Red Country",
        "**The Will of the Many**": "The Will of the Many",
        "_Tigana_": "Tigana",
        "`Code`": "Code",
        "Plain Title": "Plain Title",
        "*A: B*": "A: B",
    }
    for raw, want in cases.items():
        got = lq._strip_md_emphasis(raw)
        if got != want:
            fails.append(f"(1) _strip_md_emphasis({raw!r})={got!r} != {want!r}")
    # norm() alone leaves the trailing '*' (the original bug); after
    # stripping, the italic title normalizes to the plain catalog form.
    if not lq.norm("*Red Country*").endswith("*"):
        fails.append("(1) baseline assumption wrong: norm strips trailing")
    if lq.norm(lq._strip_md_emphasis("*Red Country*")) != lq.norm("Red Country"):
        fails.append("(1) stripped italic title != plain norm")

    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        conn = sqlite3.connect(CATALOG)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT title, author FROM books "
            "WHERE goodreads_rating >= 4.0 LIMIT 10").fetchall()
        conn.close()
        rl = wd / "RL.md"
        lines = ["| Title | Author |", "| --- | --- |"]
        for r in rows:
            lines.append(f"| *{r['title']}* | {r['author']} |")
        rl.write_text("\n".join(lines) + "\n", encoding="utf-8")
        resolved = lq.list_set(str(rl))
        if len(resolved) != len(rows):
            fails.append(f"(1) italic list resolved {len(resolved)}/"
                         f"{len(rows)} cells")

    # ---- Issue 4: pure-function behavioral checks ------------------
    # Heckman worked-example reproduction (doc: ~7.2, plain avg 7.97).
    ex = [{"number": 1.0, "role": "first", "rating": 7.2, "reviews": 10000},
          {"number": 2.0, "role": "mid", "rating": 8.1, "reviews": 4000},
          {"number": 3.0, "role": "late", "rating": 8.6, "reviews": 1500}]
    base = lq._corrected_series_baseline(ex)
    if base is None or not (7.0 <= base <= 7.4):
        fails.append(f"(4) worked-example baseline {base} not ~7.2")
    if base is not None and base >= statistics.mean([7.2, 8.1, 8.6]):
        fails.append("(4) worked-example corrected not below plain mean")

    # Monotone-inflating tight series → corrected < plain mainline mean.
    inflate = [{"number": float(i), "role": r, "rating": g, "reviews": n}
               for i, r, g, n in (
                   (1, "first", 3.9, 20000), (2, "mid", 4.3, 9000),
                   (3, "mid", 4.6, 4000), (4, "late", 4.8, 1500))]
    bi = lq._corrected_series_baseline(inflate)
    mean_inf = statistics.mean([e["rating"] for e in inflate])
    if bi is None or bi >= mean_inf:
        fails.append(f"(4) inflating series corrected {bi} not < mean "
                     f"{mean_inf}")

    # Duology → beta≈0.6 path (no regression); baseline == book-one mu.
    duo = [{"number": 1.0, "role": "first", "rating": 4.0, "reviews": 5000},
           {"number": 2.0, "role": "late", "rating": 4.7, "reviews": 2000}]
    if lq._corrected_series_baseline(duo) != 4.0:
        fails.append("(4) duology baseline != book-one rating")

    # Non-monotone (a later entry exceeds book one) → None.
    nm = [{"number": 1.0, "role": "first", "rating": 4.0, "reviews": 1000},
          {"number": 2.0, "role": "mid", "rating": 4.5, "reviews": 3000},
          {"number": 3.0, "role": "late", "rating": 4.6, "reviews": 500}]
    if lq._corrected_series_baseline(nm) is not None:
        fails.append("(4) non-monotone series not None")

    # Anchorless (no book one) → None.
    anc = [{"number": 2.0, "role": "mid", "rating": 4.0, "reviews": 1000},
           {"number": 3.0, "role": "late", "rating": 4.5, "reviews": 500}]
    if lq._corrected_series_baseline(anc) is not None:
        fails.append("(4) anchorless series not None")

    # Bad-data outlier dropped: Red Rising Book 5 (n=278) must not
    # break the correction; corrected < plain AVG (inflation removed).
    conn = lq.open_catalog(CATALOG)
    try:
        idx = lq._series_signal_index(conn)
        rr = [r[0] for r in conn.execute(
            "SELECT goodreads_rating FROM books WHERE series='Red Rising'")]
        if "Red Rising" not in idx:
            fails.append("(4) Red Rising has no corrected signal "
                         "(outlier not dropped?)")
        elif idx["Red Rising"] >= statistics.mean(rr):
            fails.append("(4) Red Rising corrected not below plain AVG")

        # Loose-series member → own rating (no pooling, no correction).
        loose = conn.execute(
            "SELECT * FROM books WHERE series_role IN "
            "('loose-mid','loose-entry') LIMIT 1").fetchone()
        if loose:
            b = lq.row_to_entry(loose)
            eff = lq.effective_gr_signal(conn, b)
            if eff != lq.parse_rating(b.get("goodreads_rating")):
                fails.append("(4) loose-series effective != own rating")

        # True standalone → own rating, even with non-empty series.
        std = conn.execute(
            "SELECT * FROM books WHERE series_role='standalone' "
            "AND series IS NOT NULL AND series != '' LIMIT 1").fetchone()
        if std:
            b = lq.row_to_entry(std)
            eff = lq.effective_gr_signal(conn, b)
            if eff != lq.parse_rating(b.get("goodreads_rating")):
                fails.append("(4) standalone effective != own rating")

        # Tight-series book with a valid signal → blended (≠ own,
        # unless own == signal by coincidence).
        tight = conn.execute(
            "SELECT * FROM books WHERE series='Red Rising' "
            "AND series_position='Book 1'").fetchone()
        if tight:
            b = lq.row_to_entry(tight)
            own = lq.parse_rating(b.get("goodreads_rating"))
            eff = lq.effective_gr_signal(conn, b)
            expected = (lq.SERIES_BLEND_SERIES * idx["Red Rising"]
                        + lq.SERIES_BLEND_OWN * own)
            if abs(eff - expected) > 1e-9:
                fails.append("(4) tight-series effective not blended")
    finally:
        conn.close()

    # ---- Issue 3: projection + ranking influence -------------------
    with tempfile.TemporaryDirectory() as tmp:
        wd = Path(tmp)
        out = _capture(lq.cmd_recommend, _rec_args(wd, seed=7))
        cands = out["candidates"]
        if any("goodreads_rating" in c for c in cands):
            fails.append("(3) goodreads_rating in default projection")
        if any("audio_suitability" in c for c in cands):
            fails.append("(3) audio_suitability in default projection")
        blob = json.dumps(out)
        for leak in ("effective_gr_signal", "corrected_series",
                     "goodreads_reviews", "_eff_gr"):
            if leak in blob:
                fails.append(f"(3/4) internal '{leak}' leaked to output")

        out_gr = _capture(lq.cmd_recommend,
                          _rec_args(wd, show_gr=True, seed=7))
        if not all("goodreads_rating" in c for c in out_gr["candidates"]):
            fails.append("(3) --show-gr did not surface goodreads_rating")
        if "effective_gr_signal" in json.dumps(out_gr):
            fails.append("(4) corrected signal leaked under --show-gr")

    # GR influences ordering but never gates: quality_score is
    # monotone in the effective signal, bounded by the ±clamp, and a
    # strong vector/comp match still outranks a pure rating edge.
    conn = lq.open_catalog(CATALOG)
    try:
        hi = {"goodreads_rating": 5.0, "series_role": "standalone",
              "series_status": "Standalone", "series": "X",
              "_signals": set(), "_themes": set()}
        lo = {"goodreads_rating": 3.0, "series_role": "standalone",
              "series_status": "Standalone", "series": "Y",
              "_signals": set(), "_themes": set()}
        s_hi, _ = lq.quality_score(hi, [], {}, 0, conn)
        s_lo, _ = lq.quality_score(lo, [], {}, 0, conn)
        if not s_hi > s_lo:
            fails.append("(3) high GR did not rank above low GR")
        if (s_hi - s_lo) > 2 * lq.GR_RANK_CLAMP + 1e-9:
            fails.append("(3) GR influence exceeds clamp bound")
        # A strong taste match on the low-GR book outranks the pure
        # rating edge of the high-GR book — GR is never the headline.
        anchors = [{"signals": {"sig"}, "themes": set(),
                    "title": "t", "rating": 5, "bucket": "<=12mo"}]
        bw = {"<=12mo": 1.5, "12-36mo": 0, "3+yrs": 0, "undated": 0}
        lo2 = dict(lo)
        lo2["_signals"] = {"sig"}
        s_lo2, _ = lq.quality_score(lo2, anchors, bw, 3, conn)
        if not s_lo2 > s_hi:
            fails.append("(3) strong taste match did not outrank GR edge")
    finally:
        conn.close()

    if fails:
        print("FAILURES:")
        for f in fails:
            print("  -", f)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
