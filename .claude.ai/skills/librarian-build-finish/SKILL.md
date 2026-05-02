---
name: librarian-build-finish
description: >
  Phases 3-5 of a reading-list build on the claude.ai surface — upcoming
  releases via web search across four parallel pools, final review with
  borderline removals + missed picks + distribution check, and the Top 5
  "Start Here" capstone.  Triggers on "wrap it up", "let's finish the
  build", "next phase" when the build state shows core ≥ 100, or any
  build-shaped opener with `current_phase: "phase-3"` or later in the
  picker artifact's window.storage.  Final-flushes profile + reading-list
  artifacts via per-edit storage writes, clears the build state, optionally
  offers a session-log paragraph the reader can paste anywhere.
---

# librarian-build-finish — Phases 3 + 4 + 5

You = the librarian closing out the build.  Reader has 100+ books in
their list.  Three more passes: upcoming-release stretch picks,
full-list walkthrough, Top 5 capstone.

## Hard invariants

All eleven from build-batches carry over.  Two more specific to this
phase:

12. **Phase 4 gate refuses to fire below 100.**  If
    `current_count < 100`, hand back to build-batches.
13. **Phase 3 candidates are NOT in the catalog yet.**  Web search is
    the primary data source.  Every candidate must be backed by recent
    web search confirming a future release date.

## Inputs at session start

Triage handed off because `buildState.current_phase >= "phase-3"`.

```javascript
let buildState = JSON.parse((await window.storage.get("build:" + buildId)).value);
let profileObj = JSON.parse((await window.storage.get("profile")).value);
let listObj    = JSON.parse((await window.storage.get("reading_list")).value);
```

Mirror reading-list content to `/tmp/Reading_List.md`.

Project-file paths from triage:
- `PROJECT_LOG` (required)

Decoded SQLite at `/tmp/Library_Catalog.sqlite`.

Confirm orientation:

> "We're at 100 + <n stretch> books.  Two more passes: upcoming
> releases for the next year, then a full walk-through of the list,
> then five to start with.  Ready?"

## Phase 3 — new and upcoming releases (10-15)

**Phase 3 fires before Phase 4.**  Reader can't make good swap
decisions in final review without seeing stretch picks first.

### Step 1 — wish-list pass for upcoming releases

Open prose:

> "Any books or sequels coming out in the next 12 months that you
> already have on your radar — things you've seen announced, been
> hyped about, or heard recommended?"

For each named release, **run verification searches**:

- Run at least two fresh web searches: publisher announcement, genre
  blog, aggregator.
- Vague "soon" or "next year" → drop.
- Verified date in past → not upcoming, drop.
- Reader-named that's already out and unread → regular catalog
  candidate, not Phase 3 stretch — flag and offer different path.

For confirmed: pull plot/comp details, run `is-read` against
`PROJECT_LOG`, fit-check against profile.  Series sequel → confirm
prior books read in log; series-scope follow-up if ambiguous.  Add to
stretch.

### Step 2 — librarian-suggested upcoming releases

**Anchor to today's date** before searching.

Source from **four parallel pools — not a priority list:**

1. **Author backlist hits.**  Upcoming books by authors in `five_star`
   and `all_favorites`.
   - Search: `<author> new book <current year>`,
     `<author> upcoming` (filter by date).
2. **Sequels in unfinished sequential series.**  Pull from
   `librarian_query.py unfinished-series`; search for announced
   next-book dates.
3. **Comp-driven.**  For 5-star benchmarks, search "books like X" /
   "<author> influence" within upcoming-release roundups.
4. **Genre-anticipated debuts and breakouts.**

**Per stretch batch, at least one pick from pools 3 or 4.**  Pool 1
alone is the smoke-test bug — author-only sourcing misses
genre-anticipated debuts the reader actually wants.

### Web search rules

- Multiple fresh searches per candidate.
- Verify release date in writing.  Pull specific date or month.
- Reject anything already out.
- Cite source briefly in picker `pitch` field ("Tor announcement, Feb
  2026; release Sep 2026") so reader can sanity-check.

### Render via React picker

Same as Phase 2.  Two differences:

- Library availability is N/A (these books aren't in the catalog yet).
- Page count may not be published; flag in pitch when missing.

After each picker save:

1. Append `mark-shown` records.
2. Selected picks → write to a **separate "New & Upcoming Releases"
   section** in the reading-list artifact.  Don't mix with core 100.
3. Series picks → series-scope follow-up.
4. Whole-batch skip → pause-and-probe.
5. Update build state.

Bridge to main pool: stretch picks stay in "New & Upcoming Releases"
until reader acquires the book.  When reader says "I bought *X*",
hand off to library-cataloguer to add the entry to SQLite + offer to
move it from stretch to main pool.

## Phase 4 — final review

**Phase 4 gate: stretch complete AND `current_count >= 100`.**  Below
100 → return to build-batches.

### Pre-Phase-4 profile gap check

Inspect profile artifact's `updated_at`.  Did any Profile-write
trigger fire this session?  Did the artifact actually receive a
write?

If a trigger fired but no write happened, **pause-and-probe before
advancing.**  Capture the missed signal NOW into the profile artifact,
then continue.

### Walk the full list

With core and stretch in scope:

1. **Borderline removals.**  Anything to drop?  Series scope
   right-sizing.
2. **Missed picks.**  Reader names additions; run through exclusion
   gate + entry-point check.
3. **Distribution tolerance check.**  Compute actual distribution
   against goals from build state.  Show table (Goal vs. Current vs.
   Delta).
   - Inside ±4-book tolerance → no action.
   - Outside tolerance → `AskUserQuestion`:
     - "Swap picks to hit the target"
     - "Revise the target — current shape feels right"
     - "Other"
4. **Indie / classic floor check.**  Below floor → swap a near-tie
   genre pick for an indie/classic comp.

Each correction → edit reading-list artifact content → write back to
`window.storage["reading_list"]`.  Mirror to `/tmp/Reading_List.md`
for the next helper call.

## Phase 5 — Top 5 "Start Here" capstone

Phase 4 closes → prescriptive call: **5 books from the final list,
chosen for diversity (pace, length, genre, tone) and fit (strongest
personal pitches in the whole workflow).**

### Render via React picker

Build a single 5-book picker batch (pass `books` array of length 5).

Surface as a single `AskUserQuestion`:

```
Q: "Lock these 5 as your Start Here?"
Options:
  - "Lock these 5 (Recommended)"
  - "Swap one of them — which?"
  - "Pick 5 myself"
  - "Other"
```

Each Top-5 entry's pitch is the **strongest personal-first description**
in the whole build.

### Top 5 in the reading-list artifact

Top 5 lives at the **top** of the reading-list artifact's content in
its own section:

```markdown
## Top 5 — Start Here

| Title | Author | Pages | Why It's For You |
| ... |
```

Top 5 entries also remain in their genre sections.

## Final flushes + state cleanup

After Top 5 locks:

1. **Final profile artifact write.**  One last read-back to confirm
   `updated_at` is recent.
2. **Final reading-list artifact write.**  Top 5 section + main pool
   + New & Upcoming Releases.
3. **Session-end summary turn — first time the reader sees the
   profile diff.**  Render a single chat message covering, in this
   order:

   - **Reading list:** one line — "Your reading list now has <N>
     books, locked as <Top 5 / 100-core / +stretch>.  See
     <reading-list URL>."  The reader has been watching this evolve
     all session, so this is just a final pointer.
   - **Profile diff:** consolidated summary of every profile write
     that happened this session — sectioned by what changed (e.g.
     "Added under 'Negative indicators': graphic-horror ceiling,
     unreliable-narrator avoidance.  Added under 'Tone / pacing':
     prefers ~400pp anchors, accepts up to 700pp for late-series
     payoff.").  This is the reader's first chat-side view of the
     profile changes — they were silent during the build.  Also
     surface any `profile_write_misses` recorded in picker storage
     and capture the missed signal now.  Link the profile artifact
     URL: "Inspect or edit at <profile URL>."
   - **Catalog changes (if any):** if the cataloguer ran any writes
     this session, hand off to library-cataloguer's manual-download
     flow now (see `library-cataloguer/SKILL.md`).  The reader
     receives the encoded download link in the same turn.  If no
     catalog writes happened, skip this section entirely.

4. **Mark `build:<id>` as complete** — set `current_phase: "complete"`,
   `completed_at: <ISO>`.  Keep for one cycle (so triage can replay
   "you finished a build on <date>"); delete on next session-start if
   reader starts fresh.
5. **Offer a session-log paragraph** the reader can paste anywhere
   (Drive comment, journal, chat with a friend):

   > "Want a one-paragraph summary of this session for your records?"
   > Options: "Yes — show me a summary" / "No, all done"

   On yes, render a paragraph: "Built a 100+15 list across <date
   range>.  <N> Phase 0 series routed (<list>).  Goals: <genres>.  Top
   5 locked: <list>."  Reader-facing language only.

## Hand-offs

- Reader bought a stretch book → library-cataloguer (add to SQLite,
  optionally promote from stretch to main).
- Reader wants a fresh single-book lookup mid-session → librarian-
  quickref.
- Reader hits a problem (e.g. window.storage corruption mid-Phase-3) →
  surface F3 from UX_DESIGN.md and hand back to triage.

## Boundaries — what build-finish does NOT do

- Run Phase 0, Phase 1, or Phase 2.
- Generate genre batches via `candidates --genre <G>`.
- Open new candidate pools beyond stretch.

## Reader-facing language map

Same as build-batches.  Phase 3 = "books coming out in the next
year", Phase 4 = "let's walk the whole list", Phase 5 = "five to
start with".  Never name the phases in chat.
