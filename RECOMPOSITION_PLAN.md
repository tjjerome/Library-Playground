# Skill Recomposition Plan

Response to the post-smoke-test feedback. Goal: shift the librarian from
*"don't miss anything"* to *"put the right book in the reader's hands."*
Different objective, different shape.

This plan covers (1) skill recomposition, (2) recommender redesign,
(3) script pruning, (4) state separation, and (5) a pitch list for
catalog-side cleanup that would unblock the redesign.  Catalog cleanup
items 6.3-6.7 are out of scope to implement here, but item 6.1
(canonicalize taste signals) is sequenced as the first phase of
implementation rather than parallel — see §7.

## Design stance: principles over templates

Several places in an earlier draft of this plan reached for
structural solutions when the actual fix was *less* structure.  The
revisions below preserve that learning and call it out where
relevant:

- **Pitch shape is a principle, not a menu.**  Earlier draft listed
  four pitch shapes with selection rules ("if reader's last reply
  was specific → shape 1 or 4").  That's mechanical scaffolding in
  a different costume — the model picks "shape 2" instead of
  "shape 1" and the output stays mechanical.  Revised §2 states the
  principle and trusts the model.
- **Recommendation is portfolio construction, not ranking.**
  Earlier draft proposed a multiplicative score formula
  (`rating × overlap × theme × ...`).  That collapses to "match as
  many of your current vectors as possible" — same recency-drift
  problem, new costume.  Revised §4 replaces the score with
  constraint-satisfaction + vector-spread sampling.
- **Reflection is trigger-based, not counter-based.**  Earlier
  draft revised reflection cadence from "every 2-3 batches" to
  "every ~10 picks."  Both are clocks.  Revised §2 names explicit
  triggers (rejection cluster, floor near saturation, reader
  pivots twice in same direction) with a long-stretch backstop.
- **Process narration removed structurally, not by rule.**  Telling
  the model "have a status tool but don't print it" is a hard ask.
  Revised §4 fixes this by making `status` return *only* what's
  actionable for the next decision — less to leak.
- **Taste cartography is living, not frozen at setup.**  Earlier
  draft had vectors derived once and persisted.  Revised §3 adds
  light re-derivation on rejection clusters, reader corrections,
  positive surprises, and reflection beats.
- **Reader-correction-as-feedback is an explicit primitive.**  The
  earlier draft missed this entirely.  When the reader pushes back,
  the model names what was wrong and revises its stance for the
  rest of the build, not just the next turn.  See §2.

---

## 1. Diagnosis — why the build felt like a form

Five structural causes, mapped to the feedback:

| Symptom (from feedback) | Structural cause |
|---|---|
| Every turn is `AskUserQuestion` | `librarian-build-batches` mandates "fire the multi-select question" after every prelude.  Prose-pitch + question is the only documented turn shape. |
| Pitches all four-up, identical format | Skill prescribes a 4-pick "three-part book pitch" template per batch.  No alternative shape documented. |
| Process narration ("73 of 100", "pivoting to horror", "reflection beat") | Skill **mandates** a one-line summary after every batch ("Added 3 to your list — 14 of 100, 4 of 15 indie, 7 of 12 classic") and surfaces a `where are we` phrase. |
| Recency drift onto recent 5★s | `score_candidate()` ranks by `goodreads_rating + author_pocket + comp_overlap`.  Author pockets / comp overlap derive from the log without time-bucketing, so recent-heavy logs produce recent-heavy pools. |
| Popularity-as-quality | `--min-reviews` filter and the implicit "more reviews → safer pick" assumption show up in the candidates query surface. |
| Smiley's People as a le Carré entry point | Helper has `passes_entry_point_gate()`, but it's only enforced when `--author-entry-point-strict` is passed, and the build skills never pass it. |
| Candidates errored on first call | `cmd_candidates` reads ledger entries assuming dict shape (`r.get("status")`, `r.get("primary_genre")`); `build_state.json` writes string keys. |
| Duplicate pick state | Picks live in both `/tmp/Reading_List.md` AND `build_state.json.ledger` (via `mark-shown`).  Two sources of truth. |

The **AskUserQuestion-as-default** and **batch-as-unit** are the load-
bearing structural problems.  Everything else cascades from those.

---

## 2. Skill set after recomposition

### Drop / collapse

- **`librarian-build-batches` → `librarian-build`.**  Rename and
  rewrite.  "Batches" is the wrong primitive — picks accumulate
  conversationally, not in fixed-size chunks.
- **`librarian-build-finish` stays as a separate skill** but loses
  its phase numbering.  It owns three responsibilities (upcoming
  releases, full-list walk-through, Top-5 capstone) that are
  genuinely distinct from the open-pitch loop, so the split is
  worth keeping; the *vocabulary* changes (no more "Phase 3/4/5"
  internally either).
- **`librarian-build-setup` stays**, but its job narrows: Phase 0
  unfinished-series gate, taste cartography pass (new — see §3),
  goals-as-floors conversation, wishlist.  It no longer establishes
  "Phase 1 highest-confidence picks" — those just happen in `build`.

Final skill set:

```
librarian-triage          (router; mostly unchanged)
librarian-quickref        (single-book; mostly unchanged)
librarian-build-setup     (intake; adds taste cartography)
librarian-build           (was -batches; conversational, not batched)
librarian-build-finish    (closing passes; vocabulary cleanup)
library-cataloguer        (unchanged scope; benefits from script prune)
```

### `librarian-build` — new conversation grammar

The skill specifies principles, not templates.  Anywhere we'd be
tempted to enumerate options for the model to pick from, we instead
state the principle and trust the model to vary within it.  This is
the load-bearing change: the previous version's "four pitch shapes
with selection rules" was the same form-feel problem in a different
costume — the model would just announce internally "deploying shape
2."  Looser guardrails produce more conversational output than
finer-grained scaffolding.

**Pitch principles (not a menu):**

- **Vary the pitch shape.**  Default *away* from four-up parallel
  pitches.  Sometimes one book pushed hard, sometimes A/B tension on
  a real tradeoff, sometimes a handful to scan, sometimes "here's
  what I almost didn't show you."  No fixed cadence; the moment
  picks the shape.
- **`AskUserQuestion` is for genuine multi-axis decisions** (scope,
  goals, distribution tradeoffs, swap-vs-revise-target) — *not* for
  every pitch.  When pitching one or two books, prose is the surface;
  reader replies in chat.
- **Conviction over coverage.**  A single pick written with care
  does more than four parallel paragraphs.  When the right move is
  one book, pitch one book.

**Reader-correction-as-feedback.**  This is the missing primitive.
When the reader pushes back ("don't max fantasy before indie",
"too many doorstops", "Smiley's People is Book 5, not an entry
point"), the model:

1. Names what it was doing wrong, briefly and without fawning
   ("you're right — I leaned recent because the log is recent-heavy,
   but the older 5★s aren't represented yet").
2. Revises its stance for the rest of the build, not just the next
   turn — write the revision into `/tmp/Profile.md` so subsequent
   `recommend` calls see it.
3. Doesn't relitigate or reframe the correction as agreement.

This is what makes the conversation feel like a real librarian:
they update their model of you in front of you.  The current skill
treats reader replies as inputs to the next pitch; this makes them
inputs to the model's stance.

**Reader-interruption-as-primary-signal.**  When the reader pivots
mid-genre-run ("actually, what about indie?"), follow the pivot.
Don't finish the current run first.

**Process narration: removed structurally, not just by rule.**  No
"Pivoting to horror."  No "73 of 100."  No "reflection beat."  The
fix is to make `status` (§4) return *only* what's actionable for the
next decision — the floor at risk, the underused vector, the
rejection cluster forming — not a dashboard.  If the tool doesn't
return counts, the model can't leak counts.  The reader sees status
only when they ask ("where are we") or when the math is the answer
to a question they just asked.

### Reflection — trigger-based, not counter-based

The previous "every 2-3 batches" rule and the revised "every ~10
picks" rule are both clocks.  The reflection beats that worked in
the smoke test fired *organically* — at moments the model noticed a
pattern.  Replace the counter with explicit triggers:

- **Rejection pattern.**  ≥3 picks rejected in the same cluster
  (genre / page-bucket / indie-or-classic / tone register) with no
  intervening accepts.  `recommend` already computes this as
  `probe_recommended`; the reflection trigger reads the same
  signal.
- **Floor near saturation.**  Indie or classic floor within 1 pick
  of meeting; or any genre floor within 1 of meeting and the
  reader hasn't been told the build is closing in on it.
- **Reader pivots twice in same direction.**  Two reader-correction
  events with overlapping content (both about length, both about
  tone, both about indie distribution) fire a reflection regardless
  of pick count.
- **Long stretch since last reflection** *as a backstop only* —
  e.g. 25+ picks with no other trigger firing.  Catches the case
  where the build is going smoothly but breadth needs sanity-check.

Reflection output unchanged: 2-3 sentence observation + open prose
question + turn-ending wait + profile write on reply.  The smoke
test confirmed reflection beats produced two of the best list
redirects.  Trigger-based firing keeps that without making it
mechanical.

### Goal language — floors and ranges, not targets

Replace "Core target = 100 fixed" with:

- **Working range: 100-110** before stretch picks, **110-125** after.
- **Genre goals are floors that guide direction**, not numbers to hit
  exactly.  Skill phrasing:
  > "You wanted ~12 historical fiction; we're at 4.  Want to lean
  > there next, or stay with what we're doing?"
- **Indie / classic floors stay floors** (already correct).
- **Stretch goals → "books coming out next year"** in reader voice,
  always.  "Stretch" only ever appears in internal vocabulary; even
  there, prefer "upcoming releases."

### `librarian-build-finish` vocabulary cleanup

- "Phase 3" → "upcoming releases" (already in translation map; just
  enforce internally).
- "Phase 4" → "walk the full list."
- "Phase 5" → "five to start with."
- "Stretch picks" → never used in chat *or* in internal narration.

### Anti-jargon translation map updates

Add to map:

| Internal term | Reader-facing |
|---|---|
| stretch / stretch goals / Phase 3 stretch | "upcoming releases" |
| batch / next batch | (removed; replaced by pitch shape vocabulary) |
| 73 of 100 / 14 of 100 indie | (silent unless reader asked) |
| pitch / prelude / three-part pitch | (silent — model picks shape) |

---

## 3. Taste cartography — living, not frozen at setup

A first cartography pass in `librarian-build-setup` (after Phase 0,
before goals) seeds the vectors.  But the build itself reveals
taste — adding Faithful and the Fallen mid-run, declining doorstops
repeatedly, asking for Empire of the Wolf — and a vector set frozen
at setup goes stale against the conversation actually happening.
The vectors must be living.

### Initial pass (`librarian-build-setup`)

Read the full `Reading_Log.csv` (not just top-rated recents).
Cluster ≥4★ titles into 8-12 distinct taste vectors.  Each vector
has:

- A short label (model-generated, reader-readable: "structural
  cleverness", "humor with serious stakes", "monastic isolation",
  "intimate POV with unreliable narrator").
- 2-4 example titles spanning years (forces breadth).
- Catalog signal correspondence (which `taste_signals.positive`
  values map to this vector — see §6 catalog cleanup).

Reader sees a one-message prose summary of the vectors, no
checklist.  Reader can correct ("that's not really me anymore" /
"add one for X"); corrections write to `/tmp/Profile.md` and
update `build_state.taste_vectors`.

### Live re-derivation (`librarian-build`)

Vectors are *not* frozen.  The skill re-derives them lightly when
the build signals taste shift:

- **After a rejection cluster.**  Three rejections in the same
  cluster → re-evaluate whether a vector that had been driving picks
  in that cluster still belongs, or split it ("epic fantasy" → "epic
  fantasy with intimate POV" + "epic fantasy with sweeping
  ensemble"), or retire it.
- **After a reader-correction event** (§2).  The correction names
  what was off; re-derivation translates that to a vector edit.
- **After a positive surprise.**  Reader picks a book whose vector
  signature is weak in the current set — add or strengthen.
- **At reflection beats.**  The reflection's open prose question
  often surfaces a vector that wasn't named at setup; capture it.

Re-derivation is *light* — usually one vector edited, rarely the
whole set re-clustered.  The model writes deltas to
`build_state.taste_vectors` with a short rationale, and Profile.md
gets one consolidated line per session-end.  Vector history isn't
audited every turn; it just stays current.

### Why this matters

Recommender (§4) reads vectors on every call, so vector drift
shapes ranking immediately.  A frozen vector set turns the
recommender into "match books to the reader you were at the start
of the session," which is the same recency-drift problem in a
different costume — except the frozen point is session-start
instead of log-recent.

---

## 4. Recommender redesign — constraint satisfaction, not multiplicative scoring

### Why not the multiplicative formula

The earlier draft proposed `goodreads_rating × taste_signal_overlap
× theme_match × recency_dampener × entry_point_factor`.  Wrong
shape.  Multiplication collapses to "find the book that matches as
many of your current vectors as possible."  A book with 0 overlap
× any high-quality factors = 0.  A book with 0.1 overlap × high
rating = tiny score.  The sorted result is almost entirely high-
overlap books, which is the *recent-taste-heavy* problem in a new
costume — the recency dampener helps but doesn't fix it.  The
underlying issue is treating recommendation as a ranking problem
when it's actually a portfolio-construction problem.

### Constraint satisfaction + vector-spread sampling

Recommendation has two stages, neither of which is "rank everything
by a single score and slice the top."

**Stage 1 — quality-floor candidate pool.**  Filter the catalog to
books that meet *minimum* viability:

- `goodreads_rating ≥ 3.8` (quality floor; not a sort key).
- ≥1 theme overlap with reader's profile theme set, OR ≥1 taste-
  signal overlap with any vector.  Cheap relevance gate.
- Passes universal exclusion (already-read / on-list / rejected this
  session).
- Passes entry-point gate.  Non-Book-1 / `author_entry_point=false`
  books are pulled unless reader has read another book by the
  author already, in which case they enter the pool.
- `goodreads_reviews` not consulted at any point.

This produces a candidate pool of plausibly N=200-2000 books,
depending on the catalog and the reader.  No ranking yet.

**Stage 2 — vector-spread sampling.**  The recommender's job is
"give me K candidates with good vector spread," not "give me the
top K by score."  Sampling rules:

- For each vector currently *underused* in the build (vector
  coverage tally below proportional share), preferentially sample
  candidates that match it.  Underused vectors get more candidates
  than oversaturated ones.
- For each floor at risk (indie below floor, classic below floor,
  genre below floor), preferentially sample matching candidates.
  Floor satisfaction is a constraint, not a tiebreaker.
- Within each vector / floor slice, *quality is a tiebreaker*:
  rating, comp-overlap with reader favorites, log-anchor strength
  (does the author / theme / tone match a non-recent 5★?).
- Time-bucket the log signals: vector matches sourced from last
  12mo / 12-36mo / 3+yrs in roughly equal proportion, so older
  taste vectors compete for slot space against recent ones.
- The result is K candidates that *cover* the build's gaps, not
  K candidates that all match the same overlap-heavy point.

This is closer to a stratified sample than a sort.  The
multiplicative score becomes a per-stratum tiebreaker, not the
global ordering.

**Pitch-shape parameter.**  Caller passes `--n` (how many
candidates to return).  No "shape one/ab/scan/deep-cut" — the
model decides shape at the chat layer based on conversation
context.  The recommender just returns candidates; whether they
get pitched as one hard pick or four-up is the model's call.

### Inputs

- `--catalog /tmp/Library_Catalog.sqlite`
- `--log $PROJECT_LOG`
- `--profile /tmp/Profile.md`  (taste vectors parsed from sections)
- `--reading-list /tmp/Reading_List.md`  (exclusion gate)
- `--build-state /tmp/build_state.json`  (schema v2: vectors,
  floors, current counts, rejected candidates this session, a
  `preferences` block, and `defended`/`session_lock` events. v1
  files load transparently — absent fields normalize to v2
  defaults: `series_commitment=binary`, `curiosity_targets=[]`,
  `expansion_appetite=moderate`)
- `--genre <G>` (optional — restricts pool to that genre slice;
  vector spread still applies within the slice)
- `--n <int>` (default 6; caller picks)
- `--lean <vector|floor>` (optional — caller asks for skew toward
  a specific vector or floor; recommender respects but still
  returns spread, not a pile of clones)
- `--variance {similar,balanced,broad,adjacent,focused}`
  (optional — default derives from
  `build_state.preferences.expansion_appetite`: high→broad,
  low→similar, else balanced. `balanced` reserves ~20% of slots
  for residual/outside-vector picks; `broad` ~35-40%; `similar`
  is similarity-heavy with no residual quota)
- `--show-gr` / `--show-audio` (optional — `goodreads_rating`
  and `audio_suitability` are dropped from the default projection
  to stop their reflexive use as cut criteria; these flags opt
  them back in. Audio also surfaces when the reader's profile
  flags an audio preference)
- `--mode {discover,curate}` (default `discover`. `curate`
  refuses to source new candidates and exits non-zero with a
  message pointing at `compare`/`status` — a structural guarantee
  that curation conversations never spawn new picks)

### Output

```json
{
  "candidates": [
    {
      "key": "...",
      "title": "...",
      "author": "...",
      "pages": ...,
      "match_reasoning": {
        "resonance_titles": [{"title": "Pet Sematary", "rating": 5, "bucket": "3+yrs"}],
        "matched_vectors": ["grief-rooted horror", "lyrical grimdark"],
        "matched_themes": ["isolation", "loss"],
        "comp_overlap": ["A Head Full of Ghosts"],
        "entry_point_ok": true
      },
      "fills_gap": {
        "vector": "grief-rooted horror",
        "floor": null
      },
      "warnings": []
    }
  ],
  "pool_size": 847,
  "probe_recommended": false
}
```

`match_reasoning` is **fact source, not pitch text.**  The skill
explicitly forbids quoting catalog summaries or `match_reasoning`
language directly; the personal connection synthesizes fresh every
time.  `fills_gap` tells the model *why* this candidate was
sampled (which underused vector or at-risk floor it covers), so
the pitch can ground in the right anchor.

**Anti-pattern check (auto-warn).**  If `series_position` ≠ Book 1
or `author_entry_point` is false (and reader hasn't read the
author), the recommender either pulls the book or adds a
`warnings` entry.  Default behavior is pull; warnings surface
only on edge cases (author read but unfamiliar series).  Skill
treats any warning as a stop signal.

### `status` returns only what's actionable

Earlier draft had `status` returning a dashboard.  Wrong — gives the
model material to leak.  Revised: `status` returns *only* the
signals that should drive the next decision, nothing more:

```json
{
  "floors_at_risk": [
    {"name": "indie", "remaining": 3, "books_left": 11}
  ],
  "vectors_underused": [
    {"name": "humor with serious stakes", "matched_picks": 0}
  ],
  "rejection_clusters": [],
  "page_budget_warning": null
}
```

Empty arrays when nothing is at risk.  No genre breakdown, no
"73 of 100", no average-page-count.  If the model wants those
numbers it can compute them from `Reading_List.md` directly, but
the tool surface doesn't hand them over for free.  This is the
structural fix for process narration: less to say means less
gets said.

### `series-fit` — unchanged from previous draft

Given a series name, returns: full book list with page counts and
`series_role`, narrative shape (one arc / loose subseries /
dip-in), recommended scope based on profile signals.  Replaces
`series-continuation` plus manual scope-question loop.

### `unfinished-series` — keep

Already works.

### Drop these scripts

- `lookup` — replaced by inline SQL where needed.
- `weight` — vestigial.
- `mark-shown` — picks live in `/tmp/Reading_List.md`; build state
  doesn't shadow them (§5).
- `is-read`, `is-on-list`, `is-shown` — exclusion gate moves into
  `recommend`; quickref does inline SQL for the ad-hoc cases.
- `profile-append` — `/tmp/Profile.md` is plain markdown; the
  skill writes to it directly.  No helper for what's two lines of
  Python.
- `series-continuation` — folded into `series-fit`.
- `candidates` — replaced by `recommend`.
- `distribution` — folded into `status`.
- `session-reset` — manual file delete; not a script.

This shrinks `librarian_query.py` from 14 subcommands to **4**
(`recommend`, `status`, `series-fit`, `unfinished-series`), plus
`norm` for shared use by `library-cataloguer`.

### Bug fix: ledger format mismatch

Out the door anyway with the rewrite — `recommend` reads exclusions
from `/tmp/Reading_List.md` directly (the source of truth) plus the
log.  No build-state ledger involvement.

---

## 5. State separation

| Surface | Holds | Mutation cadence |
|---|---|---|
| `/tmp/Reading_List.md` | The picks themselves (only source of truth) | Per pick |
| `/tmp/Profile.md` | Taste signals, vectors, reader corrections | Per signal |
| `/tmp/build_state.json` | Goals, floors, vectors (parsed cache), session notes, scope decisions, **rejected** candidates only, phase markers | Per decision |
| `Reading_Log.csv` (project knowledge) | Read history (ratings) | Read-only from chat |
| `/tmp/log_pending_updates.csv` | Queued log additions | Per finished-book signal |

`build_state.json` no longer carries `ledger` of selected picks — only
rejected ones (so the recommender can apply rejection penalties).
This collapses the duplication and removes the `mark-shown` round-trip.

---

## 6. Catalog cleanup ideas (out-of-scope to implement)

The skill redesign assumes data the catalog *almost* has but doesn't
quite.  If the catalog gets cleaned up, the skill changes land cleanly.
If not, several skill changes degrade to "best-effort over messy data."

**One of these is a load-bearing dependency, not a parallel
improvement: 6.1 (canonicalize taste_signals) is doing the real
work in the redesign.**  Without it, `taste_signal_overlap` in the
new recommender is substring matching on free-form strings, which
is approximately what the old query already did.  Building the
constraint-satisfaction sampler on top of dirty signal data
produces a more flexible-feeling but still-mid recommender.  6.1
should be sequenced *first*, before the skill rewrite (see §7).

Other items in this section are genuinely parallel and degrade
gracefully.

Pitched in priority order:

### 6.1 Canonicalize `taste_signals` vocabulary  — high value

**Problem.**  `taste_signals.positive` is free-form per-book strings.
Same concept appears as "lyrical, gothic prose", "lyrical grimdark
prose", "atmospheric gothic register" across three books.  Cross-book
overlap (the central recommender input) can't be computed reliably
from free-form strings.

**Idea.**  Cluster the existing free-form signals (~5000 distinct
strings across the catalog) into a controlled vocabulary of ~80-150
canonical signal IDs.  Add a `signal_canonical` column on
`taste_signals` and populate.  Profile vectors reference canonical
IDs.  Free-form strings stay for human readability.

**How to do it (sketch):** export distinct signals; cluster via
embedding similarity; LLM-label clusters; human-review the label
list; backfill canonical column.  Multi-day job, but a one-time cost.

**Cost of not doing it:**  taste_signal_overlap in `recommend`
degrades to substring matching on free-form strings.  Works for
some pairs ("grief" matches "grief-rooted") but misses semantic
overlap ("ensemble cast" / "sweeping cast of characters").

### 6.2 Canonicalize `themes` vocabulary  — high value

Same shape as 6.1, smaller magnitude — themes are already shorter and
more repetitive but still free-form.  Lower payoff but lower cost
(maybe ~50 canonical themes).  Same backfill approach.

### 6.3 Populate `pub_year`  — medium value, low cost

`pub_year` column is in the schema, NULL for every row.  Recency
dampener in `recommend` currently has to derive recency from
*reader* log dates, not publication dates.  Populating `pub_year`
from Goodreads API or existing CSVs would let the recommender also
distinguish "old book the reader hasn't gotten to" from "recent
release" independent of read history.

Likely possible from `Library.csv` if Goodreads export carries
`Year Published`; otherwise web scrape backfill.

### 6.4 Add a `taste_vectors` catalog table  — medium value, depends on 6.1

After 6.1 lands, define ~15-25 cross-cutting taste vectors at the
catalog level (not per-reader).  Each vector is a curated bundle of
canonical signals + themes + tone descriptors.  Books get tagged
with the vectors they exemplify (sparse — most books exemplify 2-4).

Then per-reader profile vectors (§3) become projections of catalog
vectors weighted by the reader's log.  Vector coverage tracking in
`status` becomes a SQL query, not a string-matching exercise.

### 6.5 Audit `author_entry_point`  — high value, medium cost

The Smiley's People misfire and the Of Darkness and Light prequel
confusion both happened because `author_entry_point` was wrong /
missing on those entries.  The recommender's auto-warn (§4) only
helps if the underlying flag is correct.

Audit:  for every author with ≥2 books in the catalog, verify exactly
one is flagged as the entry point (or that none are, with a documented
reason).  Cross-check against Goodreads "Where to Start" data and the
`series_role: "entry-point"` rows.  `catalogue.py
--audit-entry-points` exists already; surface its output as a
review queue for the maintainer.

### 6.6 Strip `goodreads_reviews` from query surface  — low cost

Field stays in the catalog (audit / debug value), but `recommend`
never reads it, and we add a comment to `sqlite_export.py` flagging
it as quality-irrelevant.  Prevents accidental re-introduction of
popularity-as-quality in future scoring changes.

### 6.7 Comparable-book quality audit  — medium value, high cost

Some `comparable_books` entries are weak (genre-only, not tone-
matched).  A pass that scores each comp link by signal/theme overlap
and flags low-quality comps for cataloguer review would lift
recommender precision.  Plausibly out of scope until 6.1 lands.

---

## 7. Implementation order

Suggested sequencing.  Each phase ships a working state.

1. **Catalog cleanup 6.1 — canonicalize `taste_signals`.**
   Sequenced first, not parallel.  The new recommender's
   constraint-satisfaction sampler depends on canonical signal
   IDs to compute vector overlap reliably.  Skipping or deferring
   this step delivers a more flexible-feeling skill on top of
   substring-matching data — same recommendation quality as
   today, just with prettier framing.  Cluster signals, label
   canonicals, backfill `signal_canonical` column, ship.
2. **Catalog cleanup 6.2 — canonicalize `themes`.**  Same shape
   as 6.1, smaller magnitude.  Folds in alongside 6.1 since the
   pipeline is shared.
3. **Helper script rewrite.**  New `recommend` (constraint
   satisfaction + vector-spread sampling, reads canonical
   signals), `status` (actionable-only, not a dashboard),
   `series-fit`, `unfinished-series` (port).  Drop the rest.
   Tests for each.
4. **Skill rewrite — `librarian-build-setup`.**  Add taste
   cartography opening pass.  Goals-as-floors language.  No phase
   numbering in internal voice.
5. **Skill rewrite — `librarian-build`.**  New conversation
   grammar (pitch principles not menu, reader-correction-as-
   feedback, trigger-based reflection, living taste cartography,
   reader-interruption-as-primary-signal).  Process narration
   removed structurally via `status` shape.
6. **Skill rewrite — `librarian-build-finish`.**  Vocabulary
   cleanup, no phase numbering.
7. **Triage + cataloguer + quickref edits.**  Small surface —
   drop references to dropped scripts, update phrase set, point
   to new `status` for `where are we`.
8. **Build artifact `dist/skills/*.zip` rebuild.**  Smoke-test
   in fresh chat against the smoke-test feedback as a regression
   checklist.

Catalog cleanup items 6.3-6.7 run in parallel on the Code surface
during phases 3-8.  Skill changes don't block on them — they
degrade gracefully and improve as those land.

---

## 8. Out of scope for this plan

- Implementation of any of the above.  This is design intent.
- Catalog cleanup work (6.1-6.7) — pitched, not specified.
- The Code-side skills on `main` — unchanged, per CLAUDE.md.
- React picker artifact changes — pure renderers, no design issue.
- Drive / project-knowledge layout changes — orthogonal.
