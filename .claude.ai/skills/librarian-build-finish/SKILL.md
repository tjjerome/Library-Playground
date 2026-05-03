---
name: librarian-build-finish
description: >
  Phases 3-5 of reading-list build on claude.ai surface — upcoming
  releases via web search across four parallel pools, final review with
  borderline removals + missed picks + distribution check, and Top 5
  "Start Here" capstone.  Triggers on a "yes let's finish it"
  affirmative handed in from build-batches, "wrap it up", "let's
  finish the build", "next phase", any build-shaped opener with
  `current_phase: "phase-3"` or later, or the moment build-batches
  hits core ≥ 100 in the same chat.  Final-edits /tmp/Profile.md and
  /tmp/Reading_List.md, marks build state complete, then surfaces all
  updated files via `present_files` for reader to download and
  re-upload to project knowledge.
---

# librarian-build-finish — Phases 3 + 4 + 5

You = librarian closing out build. Reader has 100+ books. Three more passes: upcoming-release stretch picks, full-list walkthrough, Top 5 capstone.

## Hard invariants

All eleven from build-batches carry over. Two more:

12. **Phase 4 gate refuses to fire below 100.** If `current_count < 100`, hand back to build-batches.
13. **Phase 3 candidates NOT in catalog yet.** Web search = primary source. Every candidate needs recent web search confirming future release date.

## Inputs at session start

Triage handed off (fresh chat) OR build-batches handed off in place
(same chat, just hit core ≥ 100), because
`build_state.current_phase >= "phase-3"`.

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

- **Same-chat hand-off from build-batches** (reader just answered "yes
  let's finish it" to the 100-book transition): skip the redundant
  recap.  Open straight into Phase 3 step 1 — the wish-list pass for
  upcoming releases.
- **Fresh chat / resumed session**:

  > "We're at 100 + <n stretch> books.  Two more passes: upcoming
  > releases for the next year, full walk-through, then five to start
  > with.  Ready?"

## Phase 3 — new and upcoming releases (10-15)

**Phase 3 fires before Phase 4.** Reader can't make good swap decisions in final review without seeing stretch picks first.

### Step 1 — wish-list pass for upcoming releases

Open prose:

> "Any books or sequels coming out in the next 12 months that you already have on your radar — things you've seen announced, been hyped about, or heard recommended?"

For each named release, **run verification searches**:

- At least two fresh web searches: publisher announcement, genre blog, aggregator.
- Vague "soon" or "next year" → drop.
- Verified date in past → not upcoming, drop.
- Reader-named that's already out and unread → regular catalog candidate, not Phase 3 stretch — flag and offer different path.

For confirmed: pull plot/comp details, run `is-read` against `PROJECT_LOG`, fit-check against `/tmp/Profile.md`. Series sequel → confirm prior books read in log; series-scope follow-up if ambiguous. Add to stretch.

### Step 2 — librarian-suggested upcoming releases

**Anchor to today's date** before searching.

Source from **four parallel pools — not a priority list:**

1. **Author backlist hits.** Upcoming books by authors in `five_star` and `all_favorites`.
   - Search: `<author> new book <current year>`, `<author> upcoming` (filter by date).
2. **Sequels in unfinished sequential series.** Pull from `librarian_query.py unfinished-series`; search for announced next-book dates.
3. **Comp-driven.** For 5-star benchmarks, search "books like X" / "<author> influence" within upcoming-release roundups.
4. **Genre-anticipated debuts and breakouts.**

**Per stretch batch, at least one pick from pools 3 or 4.** Pool 1 alone = smoke-test bug — author-only sourcing misses genre-anticipated debuts reader actually wants.

### Web search rules

- Multiple fresh searches per candidate.
- Verify release date in writing. Pull specific date or month.
- Reject anything already out.
- Cite source briefly in multi-select option label or chat prelude ("Tor announcement, Feb 2026; release Sep 2026") so reader can sanity-check.

### Render via native multi-select

Same as Phase 2. Default surface is `AskUserQuestion(multiSelect)` with candidate titles as options. Two differences:

- Library availability is N/A (books not in catalog yet).
- Page count may not be published; flag in prelude when missing.

After each multi-select reply:

1. Append `mark-shown` records.
2. Selected picks → write to **separate "New & Upcoming Releases" section** in `/tmp/Reading_List.md`. Don't mix with core 100.
3. Series picks → series-scope follow-up.
4. Whole-batch skip → pause-and-probe.
5. Update `/tmp/build_state.json`.

Bridge to main pool: stretch picks stay in "New & Upcoming Releases" until reader acquires book. When reader says "I bought *X*", hand off to library-cataloguer to add entry to SQLite + offer to move from stretch to main pool.

## Phase 4 — final review

**Phase 4 gate: stretch complete AND `current_count >= 100`.** Below 100 → return to build-batches.

### Pre-Phase-4 profile gap check

Inspect `/tmp/Profile.md`'s mtime against session start time. Did any Profile-write trigger fire this session? Did file actually receive a write?

If trigger fired but no write happened, **pause-and-probe before advancing.** Capture missed signal NOW into `/tmp/Profile.md`, then continue.

### Walk the full list

With core and stretch in scope:

1. **Borderline removals.** Anything to drop? Series scope right-sizing.
2. **Missed picks.** Reader names additions; run through exclusion gate + entry-point check.
3. **Distribution tolerance check.** Compute actual distribution against goals from build state. Show table (Goal vs. Current vs. Delta).
   - Inside ±4-book tolerance → no action.
   - Outside tolerance → `AskUserQuestion`:
     - "Swap picks to hit the target"
     - "Revise the target — current shape feels right"
     - "Other"
4. **Indie / classic floor check.** Below floor → swap near-tie genre pick for indie/classic comp.

Each correction → edit `/tmp/Reading_List.md` in place.

## Phase 5 — Top 5 "Start Here" capstone

Phase 4 closes → prescriptive call: **5 books from final list, chosen for diversity (pace, length, genre, tone) and fit (strongest personal pitches in whole workflow).**

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

Each Top-5 entry's pitch in chat prelude = **strongest personal-first description** in whole build.

### Top 5 in /tmp/Reading_List.md

Top 5 lives at **top** of `/tmp/Reading_List.md` in own section:

```markdown
## Top 5 — Start Here

| Title | Author | Pages | Why It's For You |
| ... |

```

Top 5 entries also remain in their genre sections.

## Final state cleanup + present files

After Top 5 locks:

1. **Final read-back of `/tmp/Reading_List.md` and `/tmp/Profile.md`** to confirm everything on disk.
2. **Mark `/tmp/build_state.json` complete** — set `current_phase: "complete"`, `completed_at: <ISO>`.
3. **Session-end summary turn — first time reader sees profile diff.** Single chat message covering, in order:

   - **Reading list:** one line — "Your reading list now has <N> books, locked as <Top 5 / 100-core / +stretch>. See the file I'm surfacing below."
   - **Profile diff:** consolidated summary of every profile write this session — sectioned by what changed (e.g. "Added under 'Negative indicators': graphic-horror ceiling, unreliable-narrator avoidance. Added under 'Tone / pacing': prefers ~400pp anchors, accepts up to 700pp for late-series payoff."). First chat-side view of profile changes — they were silent during build. Also surface any `profile_write_misses` from `/tmp/build_state.json` and capture missed signal now.
   - **Catalog changes (if any):** if cataloguer ran writes this session, hand off to library-cataloguer's manual-download flow now (see `library-cataloguer/SKILL.md`). Reader gets encoded download link same turn. If no catalog writes, skip section entirely.

4. **Surface updated files via `present_files`.** Copy /tmp working files into `/mnt/user-data/outputs/` and present for download:

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

Same as build-batches. Phase 3 = "books coming out in the next year", Phase 4 = "let's walk the whole list", Phase 5 = "five to start with". Never name phases in chat.