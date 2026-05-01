# Overseer Assessment — Smoke Test 2

## Summary

Fixes from the prior smoke test held under fresh use, but session exposed 15 new structural gaps spanning tool reliability, UX/tone, specification ambiguities, and environment constraints. Librarian logic remains sound (Phase 0 series detection, author-in-pocket signaling, Phase 1 high-confidence picks all functioned correctly), but implementation accumulated friction at conversational UX, candidate pitch quality, and decision-gate boundaries. Most critical issues: multiselect tool failure (recurring, forces degraded fallback), book-pitch tone/depth (affects reader engagement downstream), and profile fluidity (profile locked at interview instead of evolving throughout build). One systemic finding: Claude Code environment appears unsuited for conversational workflows; web chat + local script wrapper recommended for future work.

## Prior Group Regression Check (A–D + false positives)

**GROUP A–D (prior root causes):** Not explicitly re-tested. Phase 0 false positives (Dresden Files Side Jobs, Library Trilogy) surfaced despite prior fixes, suggesting exclusion-gate issues persist or edge cases still slip through. Both books caught by reader manually, not system.

**Phase 0 false positives:**
- Dresden Files: Side Jobs (Bk 12.5) marked as unread continuation but reader already read it (9/2/2021, 3.75★). Exclusion gate should have blocked it.
- Library Trilogy (Mark Lawrence): marked as unfinished but reader completed all three books. False positive.
Implication: `librarian-query.py is-read` may have normalization misses, or Reading_Log.csv dates/flags miscoded. Severity: Medium (reader catches them, but shouldn't require manual audit).

## New Gaps Surfaced (Groups E–U)

### GROUP E: multiSelect Tool Failure (Recurring)
**Symptom:** AskUserQuestion multiSelect option failed in Phase 2, forcing fallback to yes/no binary questions.
**Impact:** 
- Batch coherence lost (4 books = 4 separate decisions, not 1 evaluated set)
- Comparison impossible (can't weigh options against each other)
- Deep-cut randomization broken (per-batch ≥1 floor can't work on individual decisions)
- Rejection ledger fragmented (unclear which picks rejected vs. deferred)
- Phase flow inflated (4 books = 4 turns instead of 1)

**Root cause:** Tool schema loading issue in Claude Code environment. Likely environment constraint, not librarian-side bug.
**Fix angle:** Investigate tool schema load timing in Claude Code. If unfixable, consider web + local wrapper. Fallback (if multiSelect unavailable) should be single-select "which of these 4?" not yes/no binary per pick.
**Severity:** High — breaks core Phase 2 mechanism.

---

### GROUP H: Phase 0 Loosely-Connected Series Signal Leakage
**Symptom:** Discworld flagged as "will surface as standalones during Fantasy batches," but reader's highly-rated Pratchett entries never influenced downstream candidate generation. Librarian made scope decision unilaterally (standalones, not series) instead of routing via AskUserQuestion.
**Impact:** Pratchett 5★ signal absent from Fantasy batch scoring. Recommended picks should comp to Discworld tone (warm grimdark, comedic, ensemble) but didn't.
**Root cause:** Phase 0 note correct (loosely-connected = surface as individual standalones per spec), but librarian didn't mine Pratchett entries for taste_signals downstream. Candidate generation should use log-based taste signal independently of phase-0 routing.
**Fix angle:** In Phase 1/2 candidate generation, pull taste signals from all reader-rated series entries regardless of phase-0 scope decision. Pratchett 5★ should influence Fantasy batch comps even if Discworld books surface as individuals.
**Severity:** Medium — reader misses genre-matched picks aligned with proven taste.

---

### GROUP I: Librarian Tone / Internal Jargon Leakage
**Symptom:** Chat and Reading_List descriptions use internal terminology: "Phase 0," "routing," "batches," "mark-shown ledger," "Bk 1," "Bk 0.5," series_role references. User feedback: "feels like talking to a system describing itself, not a librarian."
**Impact:** Reduces conversational warmth, breaks immersion, reader aware of infrastructure instead of experience.
**Root cause:** Skill prompt allows technical language in user-facing context. No explicit guardrail to filter internal terminology.
**Fix angle:** Audit all user-facing strings in librarian skill for jargon. Rewrite descriptions in conversational prose. Series numbering: spell out "Book 1," "Book 2.5" or embed in prose ("first in the series," "companion novella") instead of abbreviations.
**Severity:** Medium — UX friction, not logic error.

---

### GROUP J: Series Continuation Finding Gap (Abercrombie Book 2)
**Symptom:** Phase 1 offered *A Little Hatred* (Age of Madness Bk 1) but *The Trouble with Peace* (Bk 2) never surfaced, despite being in catalog.
**Impact:** Reader missing natural continuation of highly-fit entry.
**Root cause:** Entry-point gating or series-continuation detection. If Abercrombie rated in log (Best Served Cold 5★) with unread Book 2 in catalog, should surface in Phase 1/2. Possible causes:
  1. Catalog series_role/author_entry_point prevents Book 2 (if marked "mid" and author in log but only for different series)
  2. Series-continuation query (`librarian-query.py unfinished-series`) missed it
  3. Candidate generation didn't check for Book 2 after Book 1 offered
**Fix angle:** Verify `librarian-query.py unfinished-series` includes Abercrombie Age of Madness. Check catalog series_role for Bk 2. If logic correct, problem is in Phase 1/2 candidate generation not surfacing Book 2 post-Book 1-offer.
**Severity:** Medium — findability gap, not blocking.

---

### GROUP K: Profile.md Missing / Not Committed
**Symptom:** Profile.md not created after Step 2 taste interview, and no live updates throughout build (reflection checkpoints, batch feedback).
**Impact:** 
- No persistent taste memory across phases
- Candidate generation uses only Step 2 interview data, doesn't adapt to build-phase signals
- Reader corrections / surprising selections not captured
- No evidence profile evolved (required per spec: "Profile.md is live — written throughout the build")

**Root cause:** Either (1) librarian didn't create after interview, or (2) created but never committed. File friction in Claude Code workflow likely factor.
**Fix angle:** Enforce profile creation immediately post-interview. Add reflection-checkpoint writes to Profile.md same turn (Edit in-place). Commit after every 2–3 batches (bundle with Reading_List updates). Make Profile commits visible in git log as evidence of live evolution.
**Severity:** High — breaks profile-as-memory concept and adaptive candidate generation.

---

### GROUP L: Deep-Cut Labeling Violation
**Symptom:** All deep-cut picks labeled as deep cuts in Reading_List / batch descriptions. Spec: "never label the deep cut in user-facing output."
**Impact:** Reader biased toward/away from picks flagged as "hidden gems." Defeats purpose of randomized-slot mechanism.
**Root cause:** Librarian misinterpreting "note which is deep cut" (for ledger) as "label for reader visibility."
**Fix angle:** Remove all deep-cut labels from user-facing descriptions. Pass `--deep-cut-slot` to helper; let randomization + unlabeled position work. Reader discovers deep-cut picks naturally through selection patterns, not through labels.
**Severity:** High — corrupts anti-bias mechanism.

---

### GROUP M: Book Pitch Quality / Depth
**Symptom:** Reading_List descriptions sparse, jargon-heavy, missing conversational tone. Example: "Bk 1, grimdark moral rot, same world decades later" instead of "You loved Best Served Cold — same author, same grimdark rot, set decades later in that world. This time the cynicism spreads across three POVs playing politics."
**Impact:** Reader disengaged from list; descriptions don't evoke why book fits.
**Root cause:** Descriptions rely on ≤140-char format without rich chat prelude. Spec demands prelude (2–4 sentences per book before AskUserQuestion), but Reading_List prose should be richer than mobile-safe bullets.
**Fix angle:**
  1. Rewrite Reading_List descriptions conversational (complete sentences, not fragments)
  2. Lead with strongest signal: explicit comp (if strong fit) OR profile flag OR author-in-pocket OR theme anchor
  3. Include plot hook (what happens, stakes, character arc shape)
  4. Note tone/pace/audio if relevant
  5. Format: 3–4 sentences per book, not bullet-point abbreviations
**Severity:** Medium — affects reader engagement with final list.

---

### GROUP N: Yes/No Fallback Breaks Batching
**Symptom:** When multiSelect failed, librarian fell back to yes/no binary per-pick decisions instead of single-select "which of these 4?" or "add all/some/none."
**Impact:** Same as GROUP E (batching destroyed, comparison impossible, deep-cut floor breaks, ledger fragmenting).
**Root cause:** Yes/no felt like "safe" fallback but destroys core mechanism.
**Fix angle:** If multiSelect unavailable, use single-select: "Which of these four appeals most?" Still allows book comparison, maintains batch coherence, preserves ledger. Or offer "add all of these / add some / skip all" with follow-up checklist if "some."
**Severity:** High — yes/no fallback worse than single-select.

---

### GROUP O: Premature Phase-Skip Offers
**Symptom:** Librarian offered to advance to next phase before current phase complete.
**Impact:** 
- Genre balance broken (skip Horror phase early = Horror under-target 110)
- Indie/classic floors stuck (skip to next genre = goals unmet)
- Phase purpose defeated (each phase designed for signal stacking + distribution)

**Root cause:** Spec boundary beat says "commit before Phase N+1?" but librarian interpreted as "skip to Phase N+1?"
**Fix angle:** 
  1. Remove skip option from phase-boundary questions
  2. Only offer: "commit progress before continuing Phase N?"
  3. Advance when reader satisficed OR goals met, not on reader whim
  4. Phase 4 gate: core ≥100 before advancing; if not, return to Phase 2
**Severity:** Medium — impacts final distribution but reader can adjust.

---

### GROUP P: Phase 3 Wish-List Auto-Add
**Symptom:** Librarian auto-added upcoming releases reader mentioned without explicit selection. Wish-list items should guide search, not auto-populate stretch.
**Impact:** Reader surprised by stretch inclusions; no explicit buy-in.
**Root cause:** Spec Step 1 says "add confirmed picks to stretch" ambiguously. Librarian read as "auto-add"; should read as "add to pool for review."
**Fix angle:**
  1. Ask reader: "Anything coming soon you're excited about?"
  2. Verify release window for each
  3. Add to pool (alongside librarian-searched picks) for Phase 3 batches
  4. Reader selects from pooled options, not auto-approved stretch additions
**Severity:** Low — reader catches it, can remove.

---

### GROUP Q: Phase 3 Cap Logic / Composition Clarity
**Symptom:** Spec lacks clarity on Phase 3 cap transitions and composition bias.
**Current spec gaps:**
  1. Phase 2→3 boundary: when core >110, should trim before Phase 3? (Yes, per user clarification)
  2. Phase 3 cap: 110 or 125? (Should be 125 per user intent: 100 core + 10 grace + 15 stretch)
  3. Composition: "four parallel pools" listed but debut bias not explicit
**Impact:** Librarian may over-fill core or miss debut emphasis.
**Fix angle:**
  1. Explicit: "If core >110 at end Phase 2, trim to 110 before Phase 3 fires"
  2. Explicit: "Phase 3 cap = 125 (100 core + 10 grace + 15 stretch)"
  3. Composition: "Four pools (author backlist, sequels, comp-driven, debuts) with explicit debut bias — prioritize breakout debuts as voice-discovery mechanism"
**Severity:** Low — clarification issue, not broken logic.

---

### GROUP R: Phase 3 Taste-Matching
**Symptom:** Upcoming-books pool should filter to reader taste before offering, but spec doesn't mandate it.
**Impact:** Librarian may surface "widely anticipated" debuts unmoored from reader's profile (e.g., anticipated dark sci-fi when reader's recent pattern is warm epic).
**Fix angle:** Filter Phase 3 upcoming-books pool to reader taste signals:
  - Author signal (new books by 5-star-rated authors)
  - Genre goals (debuts in Fantasy/Crime/etc from Step 3)
  - Tone palette (dark vs warm, pacing, character focus from evolved profile)
  - Theme signals (found family, heist structure, moral ambiguity from taste_signals)
**Severity:** Low — enhancement, not error.

---

### GROUP S: Tone-Palette Over-Weighting Recent Reads
**Symptom:** Despite profile stating "full range (dark grimdark + warm epic)," candidate generation skewed toward recent grimdark reads. Older 5★ warm epics didn't pull equal weight.
**Impact:** Palette narrowed mid-build despite spec guidance to capture breadth.
**Root cause:** Candidate ranking defaults to recency for tie-breaking, unintentionally narrows tone.
**Fix angle:** Weight old + recent favorites equally for tone signal. If reader rated warm epics 5★ two years ago + recent grimdark 5★, candidate generation should pull from both pools proportionally, not just recent.
**Severity:** Medium — reduces genre diversity, but reader can course-correct.

---

### GROUP T: Tone-Range Probe Reductive
**Symptom:** Step 2 tone-breadth question offered "dark vs warm spectrum" binary. Insufficient for actual taste granularity.
**Impact:** Profile captures only tone extremes; misses pacing, character scope, context, stakes, themes.
**Current spec guidance:** "Tone span" probe exists but boils down to dark/warm.
**Fix angle:** Minimum 3 probes (open-ended, not MC) on:
  1. **Pacing:** Fast-paced thriller vs slow-burn character study?
  2. **Character focus:** Ensemble cast vs deep single POV?
  3. **Reading context:** Bedtime wind-down vs commute vs dedicated time?
  4. **Stakes:** High action vs introspective psychological?
  5. **Themes:** Found family vs loner protagonists? Heist vs survival?
Keep probing until librarian has sharp read. Don't cap at arbitrary count.
**Severity:** Medium — profile lacks dimensionality for downstream signal matching.

---

### GROUP U: Profile-Locking at Step 2
**Symptom:** Profile treated as one-time interview output, not evolved throughout build. Spec says "live — written throughout," but no reflection checkpoints, batch-skip probes, or surprising-selection follow-ups committed to Profile.md.
**Impact:** Candidate generation runs against stale taste data. Reader signals mid-build (picking grimdark x3 but skipping grimdark x2 = taste shift) not captured. Profile doesn't reflect actual trajectory.
**Root cause:** Specification emphasizes profile as interview artifact; doesn't mandate ongoing writes. Implementation locked profile instead of evolving it.
**Fix angle:** Reframe profile as **fluid memory, not contract**. Librarian updates Profile.md:
  - After every reflection checkpoint (observation + prose question + reader answer)
  - After whole-batch skips (why didn't those land? → profile note)
  - After surprising selections (what drew you to that? → profile note)
  - After reader corrections (taste shifts, content flags, new themes)
Commit Profile updates every 2–3 batches bundled with Reading_List commits. Git log should show Profile evolving turn-by-turn.
**Severity:** High — breaks adaptive recommendation premise.

---

## Environment Constraint

**Claude Code harness mismatch:** Conversational book-recommendation workflows require stable tool execution, clean transcript capture, persistent multi-file state. Claude Code optimized for code editing + bash. Observed friction:
- Tool schema loading unreliable (multiSelect failures)
- Single-select fallback breaks transcript capture (reader selections lost)
- File state management clunky (Profile.md creation/commit delayed/skipped)
- Jargon naturally leaks from dev-facing context

**Recommendation:** Consider web chat + local script wrapper for future librarian work. Chat (web) provides conversational UX + reliable tool execution; local wrapper (`librarian-query.py` calls) handles catalog isolation. Hybrid architecture preserves large-catalog design without environment friction.

---

## What Worked Well

1. **Phase 0 unfinished-series detection:** Accurate identification of reader-rated series with unread continuations (Red Rising, Murderbot, Sprawl, etc.). Falsely-positive entries (Dresden, Lawrence) caught by reader.
2. **Author-in-pocket signal:** Books from highly-rated authors surfaced naturally and landed well (Abercrombie, Lynch, Buehlman, etc.).
3. **Wish-list pass:** 26-book wish-list integration smooth; grounded candidate pool effectively.
4. **Phase 1 high-confidence picks:** Personal anchors clear; selections felt coherent and well-justified.
5. **Spec structure sound:** Phase gates, deep-cut mechanism, rejection weighting, exclusion logic all functionally correct (issues are implementation + UX, not architecture).

---

## Top-3 Recommendations (Leverage-Ranked)

### 1. Fix multiSelect tool or ship robust single-select fallback
**Leverage:** Highest. multiSelect failures cascade to yes/no batching, breaking Phase 2 core mechanism. If Claude Code tool unreliable, migrate to web + wrapper or ship single-select default. Unblocks Phases 2–5.

### 2. Rewrite librarian voice for conversational tone + richer pitch
**Leverage:** High. Book pitches are reader's engagement point. Current sparse + jargon-heavy descriptions kill enthusiasm. Richer conversational prose (comps + themes + plot hooks + tone anchors) downstream from tone/jargon cleanup (GROUP I). Impacts every batch forward.

### 3. Make Profile.md live throughout build
**Leverage:** High. Profile-locking defeats adaptive recommendation premise. Implement reflection checkpoints with taste probes (why did picks land/miss?) + Profile writes every 2–3 batches. Sharpens downstream candidate generation + unblocks GROUP S/T issues (palette narrowing).

### 4. Enforce phase boundaries (no skip offers, core ≥100 before Phase 4)
**Leverage:** Medium. Prevents premature phase exits that break genre/indie/classic balances. Simple spec clarification + implementation gate-check.

### 5. Audit and fix Phase 0 false positives
**Leverage:** Medium. Dresden / Lawrence false positives suggest `librarian-query.py is-read` normalization issues or Reading_Log.csv data quality gaps. Verify exclusion gate on edge cases.

---

## Interface Accessibility Requirement

**Critical constraint:** Next interface must be accessible to users with Claude Pro subscription only. No additional usage-based costs, no separate API credits, no extra fees. 

Web chat (claude.ai) with Pro access satisfies constraint. Local wrapper (librarian-query.py on user's machine) has no cost. This combination preserves accessibility while avoiding Claude Code environment friction.

If migrating to custom interface (Cursor, custom IDE extension, standalone app), must remain within Claude Pro tier — no API calls beyond what Pro covers, no external service costs.

---

## Conclusion

Librarian skill architecture remains sound. Session exposed 15 new UX/specification/environment issues, not logic flaws. Most critical: tool reliability (multiSelect), conversational tone (pitch quality), and profile fluidity (live evolution, not interview lock-in). Environment (Claude Code) appears structurally mismatched for conversational workflows; web + wrapper recommended for future iterations. Fixes above unblock full Phase 2–5 build and improve downstream recommendation quality substantially.
