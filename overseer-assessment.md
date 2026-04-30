# Overseer Assessment — Recommended Fixes

Distilled fix recommendations across the 19 reader-reported issues. Issues cluster into 7 root-cause groups; fixing the groups is more efficient than item-by-item.

---

## Group A — Universal exclusion gate

Covers issues **4, 8, 15**.

Promote the `is_already_read` check from a Phase-2-local step to a session-level invariant: no candidate enters any `AskUserQuestion` checklist — wishlist pass, batch construction, ad-hoc reader requests, refinements, stretch picks — without clearing both `is_already_read` (against `Reading_Log.csv`) and a new `is_on_list` check (against `Reading_List.md`). Add a redundant pre-write check on every `Edit` to `Reading_List.md`. Extend `norm()` to strip leading punctuation/articles ("'Salem's Lot", "The Book of the New Sun"), collapse multi-period initials, and drop trailing series-suffix parens. Run a one-time diagnostic over current `Reading_List.md` to identify which failures are gate-placement vs. fuzzy-match.

---

## Group B — Author/series metadata + enforcement gates

Covers issues **6, 7, 14, 18**.

Three mechanisms together:

1. **Pre-write series-scope gate.** Before any `Edit` to `Reading_List.md`, every non-Standalone entry must have an answered scope `AskUserQuestion` on record. Single canonical rule; both existing mentions in the spec become cross-references.
2. **Author entry-point check.** When a candidate's author is not in `Reading_Log.csv`, verify entry-point status: book 1 of the chosen series, *and* the chosen series is a sensible starting series for that author; for standalones and "series of standalones" (Connelly, Christie, Reacher), verify the specific book is a recommended starting point and doesn't rely on accumulated context.
3. **Unfinished-series enforcement gate.** Before Phase 1 fires, produce an in-chat "unfinished series check": every series in the log with ≥4.0 average rating gets surfaced at least once as a continuation pick. Reader can decline; agent must offer.

Catalog-side companion work for the cataloguer skill: add `series_role` (`first` / `mid` / `late` / `loose-entry` / `loose-mid` / `standalone`) and `author_entry_point` flags, audit existing series openers (Hobb, Wolfe, Liu, Martine), and verify completeness for unfinished-series next-books.

---

## Group C — Conversational tone + signal capture during build

Covers issues **3, 9, 11**.

Replace the current "one chat line" between-batch summary and "respect the silence" rejection rule with a tiered, conversational pattern:

- **Between-batch beat.** Brief reflection on what selections + skips imply, then a direction question (continue / pivot / pause). 1–3 sentences, librarian-at-the-shelf voice.
- **Description template.** Personal-first, named-anchor required. Structure: `[why you specifically — named anchor: a rated title, stated signal, profile flag] — [one phrase on what the book is] — [page count].` Demote plot/themes/comps fully to `preview`. Rewrite the canonical example.
- **Rejection weighting.** Each skip adds soft, escalating negative weight to a candidate. Model retains authority to resurface, but must overcome accumulated weight (i.e., new framing/signal). High-confidence picks that get rejected trigger a probe with the named anchor as the subject — answer can update `Profile.md` via the cataloguer skill. Full-batch skip = immediate pause-and-probe; no new batch fires until answered.
- **Tone section addition.** "Conversational during build, terse during deliverable handoff. Willing to swing when personal fit is there."

---

## Group D — Interview hygiene

Covers issues **1, 2**.

After any open-ended prose question, do not issue another `AskUserQuestion` until the reader has replied. Open answers are turn-ending. Cut Step 2 Q7 ("genres you want more of") — Step 3 owns genre collection. For partially-stale `Profile.md`, only ask MC questions whose answers aren't covered by the existing profile. Add a session-level "asked already" ledger so headers don't repeat.

---

## Group E — Candidate composition + goal shape

Covers issues **10, 12, 16**.

- **Per-batch deep cut slot.** At least 1 of every 4-pick batch is a deep cut (small-press, cult favorite, genre adjacency, deep backlist of canonical authors, translated lit, mid-list literary, out-of-print recovery — independent of `indie:true`). No reader-visible label. Slot position randomized per batch.
- **Indie/classic interspersion.** Treat as cross-cutting axes considered during every genre batch's candidate sourcing, not as separate batch types. At session start, surface catalog-distribution warnings ("most indie in your catalog is fantasy — pull indie while building fantasy, not after").
- **Goal-shape change.** Indie and classics are floor-only minimums, not ranges. No upper tolerance. Series-status buckets keep their range-with-tolerance shape (different goal type — one bucket starves another).
- **Phase 4 candidate sourcing.** Treat author-backlist, sequel, comp-driven, and genre-anticipated as parallel pools, not a priority list. Per stretch batch, at least one pick must come from the discovery-leaning sources (comp-driven or genre-anticipated). Genre-anticipated picks from new-to-reader authors must clear the entry-point check from Group B.

---

## Group F — Phase structure + finale

Covers issues **13, 17, 19**.

Reorder phases:

1. Phase 1 — highest-confidence picks (unchanged).
2. Phase 2 — batch building (unchanged).
3. Phase 3 — new & upcoming releases (was Phase 4).
4. Phase 4 — final review: borderline removals, missed-pick additions, distribution tolerance check, series-scope right-sizing. Reader sees both core and stretch, considers them holistically.
5. **Phase 5 (new) — Top 5 "Start Here" capstone.** Librarian's prescriptive call, with reader veto via `AskUserQuestion`. Diversity across the 5 (mix of pace, length, genre, tone). Strongest personal pitches in the entire workflow. Lives at the top of `Reading_List.md` in its own section, distinct from the mood-driven pool below.

Invariants:

- **Core target = 100 is fixed.** Phase 3 goal reductions trigger an immediate redistribution `AskUserQuestion` ("those 6 freed slots: where do they go?"). Goal cuts redistribute slots, never reduce the total.
- **Phase 3 (stretch) gate.** Core count ≥ 100 *or* explicit reader approval to ship below target. No swap-discussion preamble required to cross the gate.
- **Phase 4 (final review) gate.** Stretch picks complete.

---

## Group G — Mobile rendering

Covers issue **5**.

Author the questions to survive `AskUserQuestion` truncation:

- `description` ≤ ~140 chars, personal-first hook + page count up front.
- `preview` carries plot/themes/comps.
- `label` packs one extra signal where useful ("Title — Author (432pp, cosmic horror)").
- Frame each batch in chat *before* firing the question — context lives in chat, options become a confirmation interface.

The underlying truncation is a Claude Code mobile-UI constraint, not a skill bug. Worth a separate Claude Code feedback issue if severity warrants.
