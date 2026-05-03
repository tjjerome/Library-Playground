---
name: librarian-build-finish
description: >
  Phases 3-5 of a reading-list build on the claude.ai surface — upcoming
  releases via web search across four parallel pools, final review with
  borderline removals + missed picks + distribution check, and the Top 5
  "Start Here" capstone.  Triggers on "wrap it up", "let's finish the
  build", "next phase" when /tmp/build_state.json shows core ≥ 100, or
  any build-shaped opener with `current_phase: "phase-3"` or later.
  Final-edits /tmp/Profile.md and /tmp/Reading_List.md, marks the build
  state complete, then surfaces all updated files via `present_files`
  for the reader to download and re-upload to project knowledge.
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

Triage handed off because `build_state.current_phase >= "phase-3"`.

```python
import json
build_state = json.load(open("/tmp/build_state.json"))
profile_text = open("/tmp/Profile.md").read()
list_text    = open("/tmp/Reading_List.md").read()
```

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
`PROJECT_LOG`, fit-check against `/tmp/Profile.md`.  Series sequel →
confirm prior books read in log; series-scope follow-up if ambiguous.
Add to stretch.

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
- Cite source briefly in the multi-select option label or chat prelude
  ("Tor announcement, Feb 2026; release Sep 2026") so reader can
  sanity-check.

### Render via native multi-select

Same as Phase 2.  Default surface is `AskUserQuestion(multiSelect)`
with the candidate titles as options.  Two differences:

- Library availability is N/A (these books aren't in the catalog yet).
- Page count may not be published; flag in the prelude when missing.

After each multi-select reply:

1. Append `mark-shown` records.
2. Selected picks → write to a **separate "New & Upcoming Releases"
   section** in `/tmp/Reading_List.md`.  Don't mix with core 100.
3. Series picks → series-scope follow-up.
4. Whole-batch skip → pause-and-probe.
5. Update `/tmp/build_state.json`.

Bridge to main pool: stretch picks stay in "New & Upcoming Releases"
until reader acquires the book.  When reader says "I bought *X*",
hand off to library-cataloguer to add the entry to SQLite + offer to
move it from stretch to main pool.

## Phase 4 — final review

**Phase 4 gate: stretch complete AND `current_count >= 100`.**  Below
100 → return to build-batches.

### Pre-Phase-4 profile gap check

Inspect `/tmp/Profile.md`'s mtime against the session start time.
Did any Profile-write trigger fire this session?  Did the file
actually receive a write?

If a trigger fired but no write happened, **pause-and-probe before
advancing.**  Capture the missed signal NOW into `/tmp/Profile.md`,
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

Each correction → edit `/tmp/Reading_List.md` in place.

## Phase 5 — Top 5 "Start Here" capstone

Phase 4 closes → prescriptive call: **5 books from the final list,
chosen for diversity (pace, length, genre, tone) and fit (strongest
personal pitches in the whole workflow).**

### Render via single AskUserQuestion

Single five-option `AskUserQuestion`:

```
Q: "Lock these 5 as your Start Here?"
Options:
  - "Lock these 5 (Recommended)"
  - "Swap one of them — which?"
  - "Pick 5 myself"
  - "Other"
```

Each Top-5 entry's pitch in the chat prelude is the **strongest
personal-first description** in the whole build.

### Top 5 in /tmp/Reading_List.md

Top 5 lives at the **top** of `/tmp/Reading_List.md` in its own
section:

```markdown
## Top 5 — Start Here

| Title | Author | Pages | Why It's For You |
| ... |

```

Top 5 entries also remain in their genre sections.

## Final state cleanup + present files

After Top 5 locks:

1. **Final read-back of `/tmp/Reading_List.md` and `/tmp/Profile.md`**
   to confirm everything is on disk.
2. **Mark `/tmp/build_state.json` complete** — set
   `current_phase: "complete"`, `completed_at: <ISO>`.
3. **Session-end summary turn — first time the reader sees the
   profile diff.**  Render a single chat message covering, in this
   order:

   - **Reading list:** one line — "Your reading list now has <N>
     books, locked as <Top 5 / 100-core / +stretch>.  See the file
     I'm surfacing below."
   - **Profile diff:** consolidated summary of every profile write
     that happened this session — sectioned by what changed (e.g.
     "Added under 'Negative indicators': graphic-horror ceiling,
     unreliable-narrator avoidance.  Added under 'Tone / pacing':
     prefers ~400pp anchors, accepts up to 700pp for late-series
     payoff.").  This is the reader's first chat-side view of the
     profile changes — they were silent during the build.  Also
     surface any `profile_write_misses` recorded in
     `/tmp/build_state.json` and capture the missed signal now.
   - **Catalog changes (if any):** if the cataloguer ran any writes
     this session, hand off to library-cataloguer's manual-download
     flow now (see `library-cataloguer/SKILL.md`).  The reader
     receives the encoded download link in the same turn.  If no
     catalog writes happened, skip this section entirely.

4. **Surface the updated files via `present_files`.**  Copy the /tmp
   working files into `/mnt/user-data/outputs/` and present them so
   the reader can download:

   ```python
   import shutil
   shutil.copy("/tmp/Reading_List.md", "/mnt/user-data/outputs/Reading_List.md")
   shutil.copy("/tmp/Profile.md",      "/mnt/user-data/outputs/Profile.md")
   shutil.copy("/tmp/build_state.json", "/mnt/user-data/outputs/build_state.json")
   ```

   Then render markdown links so the reader can click + download:

   > "Updated files for you to re-upload to project knowledge:
   >
   > - [`Reading_List.md`](sandbox:/mnt/user-data/outputs/Reading_List.md)
   > - [`Profile.md`](sandbox:/mnt/user-data/outputs/Profile.md)
   > - [`build_state.json`](sandbox:/mnt/user-data/outputs/build_state.json)
   >
   > Replace the matching files in your claude.ai project knowledge so
   > the next session picks up where we left off."

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

## Boundaries — what build-finish does NOT do

- Run Phase 0, Phase 1, or Phase 2.
- Generate genre batches via `candidates --genre <G>`.
- Open new candidate pools beyond stretch.

## Reader-facing language map

Same as build-batches.  Phase 3 = "books coming out in the next
year", Phase 4 = "let's walk the whole list", Phase 5 = "five to
start with".  Never name the phases in chat.
