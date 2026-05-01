# User Feedback — Smoke Test 2

## Session Overview
Built 49 books through Phase 1, paused for Phase 2. Encountered multiple friction points around interface limitations, recommendation pitch quality, and process flows. Test revealed both environment constraints and spec gaps worth addressing.

## What Worked

- **Phase 0 structure solid.** Unfinished series identification accurate (except for signal leakage on loosely-connected series like Discworld). False positives on already-read books (Dresden Files) and completed series (Lawrence) caught, but system should have blocked them upfront.
- **Wish-list pass helpful.** 26 books added as candidates gave good grounding for subsequent phases.
- **Phase 1 high-confidence picks landed well.** Personal anchors and taste reasoning clear; selections felt coherent.
- **Author-in-pocket signal strong.** Books from rated authors surfaced naturally and mostly approved.

## Main Friction Points

### 1. Tool Reliability (multiSelect)
Multiselect failed repeatedly, forcing fallback to yes/no binary questions. This destroyed batch coherence—instead of evaluating 4 books as a set, had to decide each individually. Impacts deep-cut randomization (per-batch floor can't work on individual yes/no) and phase flow (4 books = 4 turns instead of 1).

### 2. Book Pitch Quality
Descriptions in Reading_List feel sparse and technical. Missing conversational tone, explicit comps to books I've rated, and enough plot meat to understand what a book *does*. Abbreviations like "Bk 1," "Bk 2.5" sound algorithmic. Expected more librarian voice—warm, specific references to what I loved in past reads, and plot hooks that actually grip.

### 3. Recommendation Signal Drift
Over-indexed toward recent grimdark reads despite profile stating "full range." Older warm epics I rated 5★ weren't pulling equal weight downstream. Felt like palette narrowed even though it shouldn't have.

### 4. Tone-Range Questions Too Reductive
Early probe about tone felt like "dark vs warm spectrum" binary. Missing real questions: pacing (fast vs slow burn), character focus (ensemble vs deep POV), reading contexts (bedtime vs commute), stakes (action vs introspective), themes (found family vs standalone loners). Those matter more than dark/warm.

### 5. Jargon in User-Facing Output
Internal terminology leaked throughout: Phase 0, Phase 1, routing, batches, ledger, mark-shown, "Bk 1," series_role. Felt like talking to a system describing itself instead of a librarian recommending books.

### 6. Series Handling Inconsistency
Ryan Cahill series added as full 8-book block even though I approved it explicitly—but that approval wasn't captured cleanly in the transcript (likely single-select workaround issue). Discworld correctly identified as standalones, but librarian made that decision unilaterally instead of offering scope options.

### 7. Missing Continuity Signal
Abercrombie Book 1 (A Little Hatred) was offered, but Book 2 (The Trouble with Peace) never surfaced as a continuation. Entry-point gating or series-continuation detection broke somewhere.

### 8. Deep-Cut Labeling
All deep-cut picks labeled as such. Defeats the purpose—randomized slot position is supposed to be hidden so I discover patterns naturally post-build, not bias selections because something's flagged as a "hidden gem."

### 9. Phase Boundary Decisions
Librarian offered to skip ahead to next phase before current one was done. Should continue within phase until goals met, not give escape hatch for fatigue.

### 10. Profile Not Live
Expected Profile.md to evolve throughout the build as I was asked reflection questions and made surprising selections. Instead it wasn't created or committed. Profile should be memory that sharpens turn-by-turn, not a one-time interview output.

## Environment Observation
Claude Code harness seems fundamentally mismatched for conversational book-recommendation workflows. Tool schema loading fragile, transcript capture incomplete (single-select workaround losses), file state management clunky. Web chat + local script wrapper might be better suited. Noted for future architecture discussion.

## Suggestions for Next Round
- Sharper book pitches with conversational voice + comps to rated titles + real plot hooks
- Robust multiselect (or better fallback than yes/no)
- Profile updated live throughout build, not locked at interview
- Reflection checkpoints with taste-probe questions (why did books land/miss?)
- Full tone-palette breadth probes at interview (pacing, character, context, stakes, themes)
- Stop offering phase-skip; continue until phase complete
- Remove deep-cut labels entirely
- Better Discworld handling (offer scope, let reader decide)
- Hunt down Abercrombie Book 2 entry-point / series-continuation gap
