"""Catalog audits — review-queue generators for the maintainer.

These audits are deterministic SQL/Python passes over the SQLite catalog;
they produce review queues (markdown reports), never auto-fix.  Each
audit narrows to a suspect-shaped subset rather than scanning the full
catalog so the resulting queue is actually reviewable by hand.

Implemented:

* `audit_entry_points_consistency` — flags `author_entry_point=true`
  rows that look wrong against series_role / series_position / pub_year
  signals.  Implements RECOMPOSITION_PLAN §6.5 (the maintainer-side
  review queue the existing `--audit-entry-points` backfill never
  surfaced).

* `audit_comparables` — flags `comparable_books` links with zero
  overlap on taste vectors AND zero combined signal/theme overlap.
  Uses the `book_taste_vectors` table populated by §6.4.  Implements
  RECOMPOSITION_PLAN §6.7.

Both write to `docs/`; they assume `Library_Catalog.sqlite` already
exists (regenerate via `catalogue.py --export-sqlite` first).
"""

from __future__ import annotations

import re
import sqlite3
from datetime import date
from pathlib import Path

# series_role values that legitimately mark a book as "you can start here."
ENTRY_POINT_ROLES = {"standalone", "first", "loose-entry", "entry-point"}


# ---------------------------------------------------------------------------
# 6.5 — author_entry_point consistency audit
# ---------------------------------------------------------------------------

def _parse_book_number(series_position: str | None) -> float | None:
    if not series_position:
        return None
    m = re.search(r"book\s*([\d.]+)", series_position, flags=re.IGNORECASE)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


def _series_misalignment_flag(row: sqlite3.Row) -> str | None:
    """Return a short reason string if this entry-point looks misaligned
    with its series_role / series_position; None when it looks fine.

    Logic by `series_role`:

    - `mid` / `late` / `loose-mid`: entry-point on a clearly non-entry
      slot — always flag.
    - `first` / `standalone`: position should be Book 1 or absent.  Flag
      when position parses to Book ≥ 2.
    - `loose-entry` / `entry-point`: position is allowed anywhere by
      design (loose series have no fixed start) — don't flag on
      position > 1.  Still flag prequel-shaped positions (sub-1 numbers
      or "prequel" in the string), since those are rarely good on-ramps
      regardless of role.
    - role NULL: fall back to position-only checks.
    """
    role = row["series_role"]
    sp = (row["series_position"] or "").lower()
    n = _parse_book_number(sp)
    is_prequel_str = "prequel" in sp
    is_subone = n is not None and 0 < n < 1
    is_above_one = n is not None and n > 1

    bits: list[str] = []

    if role in {"mid", "late", "loose-mid"}:
        bits.append(f"series_role={role!r} (mid-series — not a sensible entry)")
    elif role in {"first", "standalone"}:
        if is_above_one:
            bits.append(f"series_role={role!r} but series_position parses to Book {n:g}")
    # loose-entry / entry-point / None: skip the >1 position check.

    if is_prequel_str:
        bits.append("series_position contains 'prequel'")
    elif is_subone:
        bits.append(f"series_position parses to Book {n:g} (sub-1, likely prequel)")
    elif role is None and is_above_one:
        bits.append(f"series_role unset and series_position parses to Book {n:g}")

    return "; ".join(bits) if bits else None


def audit_entry_points_consistency(conn: sqlite3.Connection) -> dict:
    """Three-criterion audit. Returns {misaligned, pub_year_regression,
    zero_entry_point} — each a list of dicts ready for markdown render."""
    conn.row_factory = sqlite3.Row

    # --- Criterion 1: series misalignment on author_entry_point=true rows ---
    misaligned = []
    for r in conn.execute(
        "SELECT key, title, author, series, series_position, series_role, "
        "pub_year, primary_genre "
        "FROM books WHERE author_entry_point = 1"
    ):
        reason = _series_misalignment_flag(r)
        if reason:
            misaligned.append({
                "key": r["key"], "title": r["title"], "author": r["author"],
                "series": r["series"], "series_position": r["series_position"],
                "series_role": r["series_role"], "pub_year": r["pub_year"],
                "primary_genre": r["primary_genre"], "reason": reason,
            })
    misaligned.sort(key=lambda d: (d["author"] or "", d["title"] or ""))

    # --- Criteria 2 & 3 require per-author iteration over ≥2-book authors ---
    authors = [r[0] for r in conn.execute(
        "SELECT author_normalized FROM books "
        "GROUP BY author_normalized HAVING COUNT(*) >= 2"
    )]

    pub_year_regression = []
    zero_entry_point = []

    for an in authors:
        rows = list(conn.execute(
            "SELECT key, title, author, pub_year, series, series_status, "
            "series_position, series_role, author_entry_point, primary_genre "
            "FROM books WHERE author_normalized = ?", (an,)
        ))

        # --- Criterion 2: pub_year regression on standalone-only authors ---
        standalones = [r for r in rows if r["series_status"] in (None, "Standalone")]
        eps_in_standalones = [r for r in standalones if r["author_entry_point"] == 1]
        dated_standalones = [r for r in standalones if r["pub_year"] is not None]
        if (len(standalones) >= 2 and eps_in_standalones and dated_standalones):
            earliest_year = min(r["pub_year"] for r in dated_standalones)
            earliest_titles = [r["title"] for r in dated_standalones
                               if r["pub_year"] == earliest_year]
            for ep in eps_in_standalones:
                if ep["pub_year"] is not None and ep["pub_year"] > earliest_year:
                    pub_year_regression.append({
                        "key": ep["key"],
                        "title": ep["title"],
                        "author": ep["author"],
                        "ep_year": ep["pub_year"],
                        "earliest_year": earliest_year,
                        "earliest_title": earliest_titles[0] if earliest_titles else None,
                        "gap_years": ep["pub_year"] - earliest_year,
                        "primary_genre": ep["primary_genre"],
                    })

        # --- Criterion 3: zero entry point AND no first/standalone role ---
        if len(rows) >= 3 \
                and not any(r["author_entry_point"] == 1 for r in rows) \
                and not any(r["series_role"] in ENTRY_POINT_ROLES for r in rows):
            zero_entry_point.append({
                "author": rows[0]["author"],
                "n_books": len(rows),
                "roles": sorted({r["series_role"] for r in rows if r["series_role"]}),
                "sample_titles": [r["title"] for r in rows[:3]],
            })

    pub_year_regression.sort(key=lambda d: (-(d["gap_years"] or 0),
                                            d["author"] or ""))
    zero_entry_point.sort(key=lambda d: (-(d["n_books"] or 0),
                                         d["author"] or ""))

    return {
        "misaligned": misaligned,
        "pub_year_regression": pub_year_regression,
        "zero_entry_point": zero_entry_point,
    }


def render_entry_points_markdown(report: dict) -> str:
    """Render the audit report as a maintainer-facing review queue."""
    today = date.today().isoformat()
    lines: list[str] = []
    lines.append("# `author_entry_point` consistency review queue")
    lines.append("")
    lines.append(f"_Generated {today} from `Library_Catalog.sqlite`._")
    lines.append("")
    lines.append("Implements RECOMPOSITION_PLAN §6.5.  Three suspect classes,")
    lines.append("none auto-fixed.  Each row is for the maintainer to confirm")
    lines.append("(keep / change / annotate).")
    lines.append("")
    n_total = (len(report["misaligned"]) + len(report["pub_year_regression"])
               + len(report["zero_entry_point"]))
    lines.append(f"**{n_total} flags total** "
                 f"({len(report['misaligned'])} misaligned, "
                 f"{len(report['pub_year_regression'])} pub_year regression, "
                 f"{len(report['zero_entry_point'])} zero-entry-point authors).")
    lines.append("")

    # --- Section 1 ---
    lines.append("## 1. Series misalignment "
                 f"({len(report['misaligned'])})")
    lines.append("")
    lines.append("`author_entry_point=true` on a book whose `series_role` or")
    lines.append("`series_position` says it's not actually a sensible starting")
    lines.append("point.  These are the Smiley's People / Murder on the Orient")
    lines.append("Express shape — high-confidence flags.")
    lines.append("")
    if report["misaligned"]:
        lines.append("| Title | Author | Series | Position | Role | Reason |")
        lines.append("|---|---|---|---|---|---|")
        for r in report["misaligned"]:
            lines.append(
                f"| {_md_cell(r['title'])} | {_md_cell(r['author'])} "
                f"| {_md_cell(r['series'])} | {_md_cell(r['series_position'])} "
                f"| {_md_cell(r['series_role'])} | {_md_cell(r['reason'])} |"
            )
    else:
        lines.append("_No flags — clean._")
    lines.append("")

    # --- Section 2 ---
    lines.append("## 2. pub_year regression on standalone-only authors "
                 f"({len(report['pub_year_regression'])})")
    lines.append("")
    lines.append("Author has ≥2 standalone books, the entry-point flag is on")
    lines.append("a book published *after* an earlier standalone by the same")
    lines.append("author.  **Soft signal — many flags will be intentional**")
    lines.append("(e.g. \"And Then There Were None\" is a better Christie")
    lines.append("on-ramp than her 1929 obscurity).  Sorted by gap years")
    lines.append("descending; bigger gaps deserve more scrutiny.")
    lines.append("")
    if report["pub_year_regression"]:
        lines.append("| Author | Entry-point title | EP year | Earliest title | Earliest year | Gap |")
        lines.append("|---|---|---|---|---|---|")
        for r in report["pub_year_regression"]:
            lines.append(
                f"| {_md_cell(r['author'])} | {_md_cell(r['title'])} "
                f"| {r['ep_year']} | {_md_cell(r['earliest_title'])} "
                f"| {r['earliest_year']} | {r['gap_years']} |"
            )
    else:
        lines.append("_No flags — clean._")
    lines.append("")

    # --- Section 3 ---
    lines.append("## 3. Zero entry-point authors with ≥3 books "
                 f"({len(report['zero_entry_point'])})")
    lines.append("")
    lines.append("Author has 3+ books in the catalog, none flagged")
    lines.append("`author_entry_point=true`, and no book has a")
    lines.append("`series_role` of standalone/first/loose-entry/entry-point.")
    lines.append("Likely an oversight — pick one as the entry point or")
    lines.append("annotate why none qualifies.")
    lines.append("")
    if report["zero_entry_point"]:
        lines.append("| Author | Book count | series_role values | Sample titles |")
        lines.append("|---|---|---|---|")
        for r in report["zero_entry_point"]:
            samples = "; ".join(r["sample_titles"])
            roles = ", ".join(r["roles"]) or "(none)"
            lines.append(
                f"| {_md_cell(r['author'])} | {r['n_books']} "
                f"| {_md_cell(roles)} | {_md_cell(samples)} |"
            )
    else:
        lines.append("_No flags — clean._")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# 6.7 — comparable_books quality audit
# ---------------------------------------------------------------------------

def audit_comparables(conn: sqlite3.Connection) -> list[dict]:
    """Return the comp-link review queue.

    Pre-filtered to: comp_key resolves to a book in the catalog AND the
    two books share zero `book_taste_vectors`.  Within that suspect set,
    captures combined signal+theme overlap so the rendered queue can
    sort drop-strong cases first.

    Composite is filtered to ≤ 0 (signal_overlap + theme_overlap == 0)
    so the queue stays small and high-signal — that's ~418 rows on the
    live catalog.  Maintainer can re-run with a higher cap if desired.
    """
    conn.row_factory = sqlite3.Row

    rows = conn.execute("""
        SELECT
            cb.book_key  AS a_key,
            cb.comp_key  AS b_key,
            a.title      AS a_title,
            a.author     AS a_author,
            a.primary_genre AS a_genre,
            a.goodreads_rating AS a_rating,
            b.title      AS b_title,
            b.author     AS b_author,
            b.primary_genre AS b_genre,
            b.goodreads_rating AS b_rating,
            (SELECT COUNT(*) FROM taste_signals sa
             JOIN taste_signals sb ON sa.canonical = sb.canonical
                AND sa.polarity='positive' AND sb.polarity='positive'
             WHERE sa.book_key = cb.book_key AND sb.book_key = cb.comp_key) AS sig_overlap,
            (SELECT COUNT(*) FROM themes ta
             JOIN themes tb ON ta.canonical = tb.canonical
             WHERE ta.book_key = cb.book_key AND tb.book_key = cb.comp_key) AS theme_overlap
        FROM comparable_books cb
        JOIN books a ON a.key = cb.book_key
        JOIN books b ON b.key = cb.comp_key
        WHERE NOT EXISTS (
            SELECT 1 FROM book_taste_vectors va
            JOIN book_taste_vectors vb ON va.vector_id = vb.vector_id
            WHERE va.book_key = cb.book_key AND vb.book_key = cb.comp_key
        )
    """).fetchall()

    queue: list[dict] = []
    for r in rows:
        composite = (r["sig_overlap"] or 0) + (r["theme_overlap"] or 0)
        if composite > 0:
            continue
        genre_match = bool(r["a_genre"] and r["b_genre"] and r["a_genre"] == r["b_genre"])
        queue.append({
            "a_key": r["a_key"], "b_key": r["b_key"],
            "a_title": r["a_title"], "a_author": r["a_author"],
            "b_title": r["b_title"], "b_author": r["b_author"],
            "a_genre": r["a_genre"], "b_genre": r["b_genre"],
            "genre_match": genre_match,
            "sig_overlap": r["sig_overlap"] or 0,
            "theme_overlap": r["theme_overlap"] or 0,
            "rating_pair": (r["a_rating"], r["b_rating"]),
            "rating_sum": (r["a_rating"] or 0) + (r["b_rating"] or 0),
            "suggested_action": "drop" if not genre_match else "review",
        })
    # Strongest "drop" cases first: genre mismatch then weakest combined rating.
    queue.sort(key=lambda d: (
        0 if d["suggested_action"] == "drop" else 1,
        d["rating_sum"],
        d["a_author"] or "", d["a_title"] or "",
    ))
    return queue


def render_comparables_markdown(queue: list[dict]) -> str:
    today = date.today().isoformat()
    drops = [q for q in queue if q["suggested_action"] == "drop"]
    reviews = [q for q in queue if q["suggested_action"] == "review"]

    lines: list[str] = []
    lines.append("# `comparable_books` quality review queue")
    lines.append("")
    lines.append(f"_Generated {today} from `Library_Catalog.sqlite`._")
    lines.append("")
    lines.append("Implements RECOMPOSITION_PLAN §6.7.  Comp links pre-filtered")
    lines.append("to: comp resolves to a catalog book AND the two books share")
    lines.append("**zero** taste vectors AND **zero** combined signal/theme")
    lines.append("overlap.  Suggested action is rule-based:")
    lines.append("")
    lines.append("- **drop**: zero overlap of any kind AND primary_genre")
    lines.append("  doesn't even match.  Almost certainly the wrong comp.")
    lines.append("- **review**: zero overlap but same primary_genre.  Often a")
    lines.append("  weak genre-only comp — maintainer judgement on whether to")
    lines.append("  drop or revise.")
    lines.append("")
    lines.append(f"**{len(queue)} flags total** "
                 f"({len(drops)} drop-suggested, {len(reviews)} review-suggested).")
    lines.append("")
    lines.append("Sort: drop-suggested first, then by combined Goodreads rating")
    lines.append("ascending (weakest-rated pairs surface first).  Comps where")
    lines.append("the cited book itself isn't catalogued are excluded — those")
    lines.append("can't be quality-scored without per-book signals.")
    lines.append("")

    def _section(title: str, items: list[dict]) -> None:
        lines.append(f"## {title} ({len(items)})")
        lines.append("")
        if not items:
            lines.append("_No flags — clean._")
            lines.append("")
            return
        lines.append("| Source book | Comp | Source genre | Comp genre | Ratings (a/b) |")
        lines.append("|---|---|---|---|---|")
        for q in items:
            ratings = q["rating_pair"]
            rating_str = f"{ratings[0] or '–'} / {ratings[1] or '–'}"
            src = f"{_md_cell(q['a_title'])} — {_md_cell(q['a_author'])}"
            comp = f"{_md_cell(q['b_title'])} — {_md_cell(q['b_author'])}"
            lines.append(
                f"| {src} | {comp} | {_md_cell(q['a_genre'])} "
                f"| {_md_cell(q['b_genre'])} | {rating_str} |"
            )
        lines.append("")

    _section("Drop-suggested (genre mismatch + zero overlap)", drops)
    _section("Review-suggested (same genre, zero overlap)", reviews)

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _md_cell(s) -> str:
    """Markdown-table-safe cell value."""
    if s is None:
        return ""
    return str(s).replace("|", "\\|").replace("\n", " ")


# ---------------------------------------------------------------------------
# CLI entry points used by catalogue.py
# ---------------------------------------------------------------------------

def write_entry_points_review_queue(sqlite_path: Path, out_path: Path) -> dict:
    conn = sqlite3.connect(str(sqlite_path))
    try:
        report = audit_entry_points_consistency(conn)
    finally:
        conn.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_entry_points_markdown(report), encoding="utf-8")
    return report


def write_comparables_review_queue(sqlite_path: Path, out_path: Path) -> list[dict]:
    conn = sqlite3.connect(str(sqlite_path))
    try:
        queue = audit_comparables(conn)
    finally:
        conn.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render_comparables_markdown(queue), encoding="utf-8")
    return queue
