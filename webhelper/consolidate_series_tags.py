#!/usr/bin/env python3
"""Consolidate parent/child series-tag splits.

The librarian's series-continuation helper queries
`SELECT * FROM books WHERE series = ?`.  Books split across a
parent tag and a derivative child tag (e.g. "Discworld" +
"Discworld City Watch") can't navigate across the split.

This script merges confirmed parent/child pairs, renames a
handful of parents to canonical umbrella forms, folds the
George Mueller and Jack Ryan one-book offshoots into their
parent series, and normalises the Wilbur Smith "Birds of Prey"
/ Courtney chain.

Discworld subseries (City Watch, Death, Witches, Tiffany
Aching, Industrial Revolution) are intentionally kept split:
the subseries-restricted series walker
(librarian_query._series_sub_thread / _subseries_order_key)
relies on each subseries being its own clean Book-N sequence,
which a single umbrella "Discworld" tag would break.

Reads `Library_Catalog.json` in place by default.  Pass
--dry-run to preview without writing.

After running, regenerate the SQLite + .encoded catalog:

    python3 catalogue.py --library Library.csv \\
        --export-sqlite Library_Catalog.sqlite --emit-encoded

The script is idempotent: a second invocation on an already-
consolidated catalog produces zero changes.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Mapping tables
# ---------------------------------------------------------------------------

# Plain series-tag merges.  Every book whose `series` matches the LHS is
# retagged to the RHS; `series_position` is left alone unless overridden
# below in BOOK_OVERRIDES.
SIMPLE_MERGES: list[tuple[str, str]] = [
    ("6:20 Man (Travis Devine)", "6:20 Man"),
    ("Birds of Prey (Courtney)", "Birds of Prey"),
    ("Detective Galileo Series", "Detective Galileo"),
    ("Gael Song Trilogy", "Gael Song"),
    ("George Mueller / CIA Cold War series", "George Mueller"),
    ("George Smiley / John le Carré", "George Smiley"),
    ("Green Town Trilogy", "Green Town"),
    ("Gunmetal Gods Saga", "Gunmetal Gods"),
    ("Hogwarts Library Books", "Hogwarts Library"),
    ("Jedi Academy Trilogy", "Jedi Academy"),
    ("Night's Dawn / Commonwealth", "Night's Dawn"),
    ("Star Wars Legends (Clone Wars)", "Star Wars Legends"),
    ("The Feyrlands Collection (Ranker's Charge)", "The Feyrlands Collection"),
    ("The High Republic (Phase II)", "The High Republic"),
    ("The Strain Trilogy", "The Strain"),
]

# Umbrella renames.  Every book whose current `series` matches the LHS
# is retagged to the RHS.  Used to canonicalise parent names that
# absorb multiple children (Jack Ryan Universe absorbs Jack Ryan +
# Jack Ryan Universe; Star Wars (Canon) absorbs Star Wars + Star Wars
# (Canon) + Star Wars (Standalone Novels)).
RENAMES: list[tuple[str, str]] = [
    ("Jack Ryan", "Jack Ryan Universe"),
    ("Star Wars", "Star Wars (Canon)"),
    ("Star Wars (Standalone Novels)", "Star Wars (Canon)"),
]

# Per-book (title, author) overrides — applied AFTER the bulk retag
# steps.  Used to inject subseries-name + canonical Discworld
# publication-order numbers, and to normalise the Birds of Prey /
# Courtney bibliography.  An entry of (None, None) means "no change".
BOOK_OVERRIDES: dict[tuple[str, str], tuple[str | None, str | None]] = {
    # ---- George Mueller (Paul Vidich) ----
    # "The Mercenary" and "The Matchmaker: A Spy in Berlin" were
    # catalogued as their own 1-book series; they are Books 3 and 4 of
    # the George Mueller / CIA Cold War sequence (after "An Honorable
    # Man" #1 and "The Good Assassin" #2).
    ("The Mercenary", "Paul Vidich"): ("George Mueller", "Book 3"),
    ("The Matchmaker: A Spy in Berlin", "Paul Vidich"):
        ("George Mueller", "Book 4"),

    # ---- Jack Ryan Universe (Tom Clancy) ----
    # The Jack Ryan books are catalogued in publication order and the
    # parent tag is renamed to "Jack Ryan Universe" via RENAMES.
    # "Rainbow Six" (John Clark offshoot, pub. 1998) was its own
    # 1-book series; folded in as Book 8, after "Executive Orders"
    # (1996), matching real-world publication sequence.
    ("Rainbow Six", "Tom Clancy"): ("Jack Ryan Universe", "Book 8"),

    # ---- Birds of Prey / Courtney chain (Wilbur Smith) ----
    # Birds of Prey is a sub-trilogy expanded into a 7-book branch of
    # the broader Courtney saga.  Outer position = Birds-of-Prey-branch
    # order; inner parens = Courtney saga publication number.
    ("Birds of Prey", "Wilbur Smith"): ("Birds of Prey", "Book 1 (Courtney Series Book 9)"),
    ("Monsoon", "Wilbur Smith"): ("Birds of Prey", "Book 2 (Courtney Series Book 10)"),
    ("Blue Horizon", "Wilbur Smith"): ("Birds of Prey", "Book 3 (Courtney Series Book 11)"),
    ("The Golden Lion", "Wilbur Smith & Giles Kristian"):
        ("Birds of Prey", "Book 3.5 (Courtney Series Book 14)"),
    ("The Tiger's Prey", "Wilbur Smith & Tom Harper"):
        ("Birds of Prey", "Book 4 (Courtney Series Book 16)"),
    ("Storm Tide", "Wilbur Smith"): ("Birds of Prey", "Book 5 (Courtney Series Book 20)"),
    ("Nemesis", "Wilbur Smith & Tom Harper"):
        ("Birds of Prey", "Book 6 (Courtney Series Book 22)"),
    ("Warrior King", "Wilbur Smith & Tom Harper"):
        ("Birds of Prey", "Book 7 (Courtney Series Book 23)"),
}


# Sample chains the script verifies against the post-export SQLite to
# prove every consolidated branch navigates end-to-end.  Each tuple is
# (source_title, author, expected_next_title).
VALIDATION_CHAINS: list[tuple[str, str, str]] = [
    # 6:20 Man
    ("The 6:20 Man", "David Baldacci", "The Edge"),
    ("The Edge", "David Baldacci", "To Die For"),
    # Detective Galileo.  Catalog has both "A Midsummer's Equation" and
    # "Silent Parade" pinned at Book 4 (English-translation order is
    # decoupled from Japanese publication order); the walker breaks the
    # tie by title, so chain order reflects that.
    ("The Devotion of Suspect X", "Keigo Higashino", "Salvation of a Saint"),
    ("Salvation of a Saint", "Keigo Higashino", "A Midsummer's Equation"),
    ("A Midsummer's Equation", "Keigo Higashino", "Silent Parade"),
    ("Silent Parade", "Keigo Higashino", "Invisible Helix"),
    # Discworld City Watch (subseries-aware)
    ("Guards! Guards!", "Terry Pratchett", "Men at Arms"),
    ("Men at Arms", "Terry Pratchett", "Feet of Clay"),
    ("Feet of Clay", "Terry Pratchett", "Jingo"),
    ("Jingo", "Terry Pratchett", "The Fifth Elephant"),
    ("The Fifth Elephant", "Terry Pratchett", "Night Watch"),
    ("Night Watch", "Terry Pratchett", "Thud!"),
    ("Thud!", "Terry Pratchett", "Snuff"),
    # Discworld Death
    ("Mort", "Terry Pratchett", "Reaper Man"),
    ("Reaper Man", "Terry Pratchett", "Soul Music"),
    ("Soul Music", "Terry Pratchett", "Hogfather"),
    # Discworld Witches
    ("Equal Rites", "Terry Pratchett", "Wyrd Sisters"),
    ("Wyrd Sisters", "Terry Pratchett", "Witches Abroad"),
    ("Witches Abroad", "Terry Pratchett", "Lords and Ladies"),
    ("Lords and Ladies", "Terry Pratchett", "Maskerade"),
    ("Maskerade", "Terry Pratchett", "Carpe Jugulum"),
    # Discworld Tiffany Aching
    ("The Wee Free Men", "Terry Pratchett", "A Hat Full of Sky"),
    ("A Hat Full of Sky", "Terry Pratchett", "Wintersmith"),
    ("Wintersmith", "Terry Pratchett", "I Shall Wear Midnight"),
    # Discworld Industrial Revolution / Moist von Lipwig
    ("Going Postal", "Terry Pratchett", "Making Money"),
    ("Making Money", "Terry Pratchett", "Raising Steam"),
    # Gael Song.  "Dreams of Sorrow" is a Book 2.5 interquel novella
    # — the walker's `Book < 1` filter doesn't drop mid-series novellas,
    # so it correctly slots between Books 2 and 3.  Pre-existing walker
    # behaviour, unrelated to this consolidation.
    ("The Children of Gods and Fighting Men", "Shauna Lawless",
     "The Words of Kings and Prophets"),
    ("The Words of Kings and Prophets", "Shauna Lawless",
     "Dreams of Sorrow"),
    ("Dreams of Sorrow", "Shauna Lawless",
     "The Land of the Living and the Dead"),
    # George Mueller
    ("An Honorable Man", "Paul Vidich", "The Good Assassin"),
    ("The Good Assassin", "Paul Vidich", "The Mercenary"),
    ("The Mercenary", "Paul Vidich", "The Matchmaker: A Spy in Berlin"),
    # George Smiley
    ("Call for the Dead", "John le Carré", "A Murder of Quality"),
    ("Tinker, Tailor, Soldier, Spy", "John le Carré", "The Honourable Schoolboy"),
    # Gunmetal Gods
    ("Gunmetal Gods", "Zamil Akhtar", "Conqueror's Blood"),
    # Jedi Academy
    ("Jedi Search", "Kevin J. Anderson", "Dark Apprentice"),
    ("Dark Apprentice", "Kevin J. Anderson", "Champions of the Force"),
    # The High Republic.  Series_position values use Phase notation
    # ("Phase 1, Adult", "Phase II, Book 1", etc.) which contains skip
    # tokens — subseries navigation is intentionally disabled, and
    # Phase ordering doesn't survive the outer Book-N parser.  Just
    # assert the walker returns *something* downstream-of-source for a
    # canonical entry; non-empty result proves the merged series is
    # navigable post-consolidation.
    # (Light → A Test of Courage reflects current alpha-tiebreak walk:
    # Phase tokens collapse to the 999.0 sentinel, so siblings tie on
    # position and the walker breaks the tie by title.)
    ("Light of the Jedi", "Charles Soule", "A Test of Courage"),
    # The Strain
    ("The Strain", "Guillermo del Toro & Chuck Hogan", "The Fall"),
    ("The Fall", "Guillermo Del Toro & Chuck Hogan", "The Night Eternal"),
    # Birds of Prey / Courtney
    ("Birds of Prey", "Wilbur Smith", "Monsoon"),
    ("Monsoon", "Wilbur Smith", "Blue Horizon"),
    ("Blue Horizon", "Wilbur Smith", "The Golden Lion"),
    ("The Golden Lion", "Wilbur Smith & Giles Kristian", "The Tiger's Prey"),
    ("The Tiger's Prey", "Wilbur Smith & Tom Harper", "Storm Tide"),
    ("Storm Tide", "Wilbur Smith", "Nemesis"),
    ("Nemesis", "Wilbur Smith & Tom Harper", "Warrior King"),
    # Jack Ryan Universe.  Catalog is in publication order (the
    # editorial canon for this series); "Jack Ryan" → "Jack Ryan
    # Universe" via RENAMES.  Head of the sequence walks
    # Hunt for Red October (#1) → Patriot Games (#2); the tail
    # confirms the folded "Rainbow Six" offshoot lands as #8 after
    # "Executive Orders" (#7).
    ("The Hunt for Red October", "Tom Clancy", "Patriot Games"),
    ("Executive Orders", "Tom Clancy", "Rainbow Six"),
]


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def _key_index(catalog: dict) -> dict[tuple[str, str], str]:
    """Build a (title, author) → catalog key index."""
    out = {}
    for k, e in catalog["entries"].items():
        out[(e["title"], e["author"])] = k
    return out


def apply_consolidations(catalog: dict) -> list[tuple[str, str, str, str, str]]:
    """Mutate `catalog` in place; return list of
    (key, old_series, new_series, old_pos, new_pos) for each change."""

    changes: list[tuple[str, str, str, str, str]] = []
    simple_merge_map = dict(SIMPLE_MERGES)
    rename_map = dict(RENAMES)

    for key, entry in catalog["entries"].items():
        old_series = entry.get("series")
        old_pos = entry.get("series_position")
        new_series = old_series
        new_pos = old_pos

        # Step 1: simple merges + renames.
        if new_series in simple_merge_map:
            new_series = simple_merge_map[new_series]
        if new_series in rename_map:
            new_series = rename_map[new_series]

        # Step 2: per-book override (takes precedence on both fields).
        override = BOOK_OVERRIDES.get((entry.get("title"), entry.get("author")))
        if override is not None:
            ov_series, ov_pos = override
            if ov_series is not None:
                new_series = ov_series
            if ov_pos is not None:
                new_pos = ov_pos

        if new_series != old_series or new_pos != old_pos:
            entry["series"] = new_series
            entry["series_position"] = new_pos
            changes.append((key, old_series or "", new_series or "",
                            old_pos or "", new_pos or ""))

    return changes


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------

def validate_chains(sqlite_path: Path) -> tuple[int, list[str]]:
    """Walk every chain in VALIDATION_CHAINS via the same logic the
    librarian helper uses (lookup + WHERE series = ? + subseries-aware
    sort).  Return (passes, failure_messages)."""
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from webhelper import librarian_query as lq

    conn = sqlite3.connect(sqlite_path)
    conn.row_factory = sqlite3.Row

    failures: list[str] = []
    passes = 0
    for src_title, author, expected_next in VALIDATION_CHAINS:
        src = lq.lookup_by_pair(conn, src_title, author)
        if not src:
            failures.append(
                f"  [LOOKUP] {src_title!r} by {author!r}: source not in catalog"
            )
            continue
        series = src.get("series")
        siblings = [lq.row_to_entry(r) for r in conn.execute(
            "SELECT * FROM books WHERE series = ?", (series,)
        )]
        src_pos = src.get("series_position") or ""
        src_sub = lq._series_sub_thread(src_pos)
        src_n = (lq.norm(src["title"]), lq.norm(src["author"]))

        def _ordered(restrict):
            key_fn = lq._subseries_order_key if restrict else lq._series_order_key
            for b in sorted(siblings, key=key_fn):
                if restrict and lq._series_sub_thread(b.get("series_position")) != restrict:
                    continue
                yield b

        next_book = None
        for pool in (_ordered(src_sub) if src_sub else [], _ordered(None)):
            found = False
            for b in pool:
                bn = (lq.norm(b["title"]), lq.norm(b["author"]))
                if not found:
                    if bn == src_n or b.get("series_position") == src_pos:
                        found = True
                    continue
                next_book = b
                break
            if next_book:
                break

        actual = next_book["title"] if next_book else None
        if actual == expected_next:
            passes += 1
        else:
            failures.append(
                f"  [{series!r}] {src_title!r} → expected {expected_next!r}, "
                f"got {actual!r}"
            )
    conn.close()
    return passes, failures


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog", default="Library_Catalog.json")
    p.add_argument("--sqlite", default="Library_Catalog.sqlite",
                   help="SQLite catalog used by the post-write validator")
    p.add_argument("--dry-run", action="store_true",
                   help="Print proposed changes without writing the JSON")
    p.add_argument("--skip-validate", action="store_true",
                   help="Skip the SQLite chain validator (faster dry-runs)")
    args = p.parse_args()

    path = Path(args.catalog)
    if not path.exists():
        print(f"error: {path} not found", file=sys.stderr)
        return 1

    with path.open(encoding="utf-8") as f:
        catalog = json.load(f)

    changes = apply_consolidations(catalog)

    if not changes:
        print("No changes — catalog already consolidated.")
    else:
        print(f"{'Would update' if args.dry_run else 'Updated'} "
              f"{len(changes)} entries:")
        for key, os_, ns, op, np_ in changes:
            print(f"  {key}")
            if os_ != ns:
                print(f"    series:   {os_!r} → {ns!r}")
            if op != np_:
                print(f"    position: {op!r} → {np_!r}")

    if not args.dry_run and changes:
        with path.open("w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=2, ensure_ascii=False)
        print(f"\nWrote {path}.  Re-export SQLite + encoded:")
        print("  python3 catalogue.py --library Library.csv "
              "--export-sqlite Library_Catalog.sqlite --emit-encoded")

    if args.skip_validate:
        return 0

    sqlite_path = Path(args.sqlite)
    if not sqlite_path.exists():
        print(f"\nSkipping chain validation — {sqlite_path} not present.")
        print("Re-export the catalog and re-run without --dry-run to validate.")
        return 0

    print(f"\nValidating {len(VALIDATION_CHAINS)} chains against {sqlite_path}…")
    passes, failures = validate_chains(sqlite_path)
    if failures:
        print(f"  {passes}/{len(VALIDATION_CHAINS)} pass; "
              f"{len(failures)} fail:")
        for msg in failures:
            print(msg)
        return 2
    print(f"  {passes}/{len(VALIDATION_CHAINS)} chains OK.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
