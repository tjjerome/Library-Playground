# Skill Recomposition Plan

Response to the post-smoke-test feedback. Goal: shift the librarian from
*"don't miss anything"* to *"put the right book in the reader's hands."*
Different objective, different shape.

This plan covers (1) skill recomposition, (2) recommender redesign,
(3) script pruning, (4) state separation, and (5) a pitch list for
catalog-side cleanup that would unblock the redesign.  Catalog cleanup
is **out of scope to implement here**; it's pitched so that the skill
changes can be designed against a known target.

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

The skill specifies *what to do*, not *what to say*.  Pitch shape is
the model's choice within explicit shape options.

**Pitch shapes (model picks one per turn):**

1. **One-book hard pitch.**  Single recommendation, prose paragraph,
   conviction tone.  Reader replies in chat ("yes / pass / tell me
   more / what else").  No `AskUserQuestion`.
2. **A/B tension.**  Two picks framed against each other.  Reader
   replies in chat OR `AskUserQuestion` if the choice is genuinely
   binary.
3. **Scan handful.**  3-4 picks, multi-select via `AskUserQuestion`
   — the current default, but reserved for moments when the reader
   has signalled "show me more options" rather than every turn.
4. **"Almost didn't show you."**  Single deep-cut framed with
   reasoning, prose only.  No multi-select — buys conviction.

**When to use which:**
- Reader's last reply was specific ("more like Buehlman") → 1 or 4.
- Reader's last reply was open ("what else?") → 3.
- Two picks pull in different directions on a genuine tradeoff
  (length, tone, era) → 2.
- Floor decision (genre, indie, classic) needs reader input → use
  `AskUserQuestion` for the *direction*, then pitch in chosen shape.

`AskUserQuestion` reverts to its original purpose: discrete choices
with named options.  Not the medium of every pitch.

**Reader-interruption-as-signal.**  When the reader pivots
("actually, what about indie?", "you've got too many doorstops"),
treat that as the next prompt — don't try to finish the current
genre run before responding.

**Process narration: removed.**  No "Pivoting to horror."  No
"73 of 100."  No "reflection beat."  Status surfaces only when:
- the reader asks ("where are we"),
- the math matters for a decision the reader is making,
- the reflection checkpoint fires (every ~10 picks; see below).

The `status` script (§4) makes silent floor tracking cheap — model
calls it before deciding what to pitch next, doesn't print it.

### Reflection checkpoints — keep, with one change

Currently fires after every 2-3 batches.  Change to **every ~10 picks
or when a tag floor is within 1 pick of being met**, whichever comes
first.  Output unchanged: 2-3 sentence observation + open prose
question + turn-ending wait + profile write on reply.

The smoke test confirmed reflection beats produced two of the best
list redirects.  Don't lose this — just don't gate it on batch count.

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

## 3. Taste cartography opening pass

New step in `librarian-build-setup`, runs after Phase 0 and before
goals.  Structural distinction from quickref.

**What it does.**  Read the full `Reading_Log.csv` (not just the
top-rated recents).  Cluster ≥4★ titles into 8-12 distinct taste
vectors.  Each vector has:

- A short label (model-generated, reader-readable: "structural
  cleverness", "humor with serious stakes", "monastic isolation",
  "intimate POV with unreliable narrator").
- 2-4 example titles spanning years (forces breadth).
- Catalog signal correspondence (which `taste_signals.positive`
  values map to this vector — see §6 catalog cleanup).

**Why now.**  Three problems it solves:

1. Recency drift — vectors carry old 5★s that recent-only sourcing
   misses (Witcher, Pale Blue Dot, Sword of Kaigen).
2. Coverage tracking — vectors become a checklist the recommender
   tallies during the build ("12 picks match 'structural cleverness',
   0 match 'humor with serious stakes'").
3. Pitch synthesis — the personal anchor in every pitch grounds in a
   *named vector*, not the most recent 5★.

**Reader sees:** a one-message summary of the vectors, prose form, no
checklist.  Reader can correct ("that's not really me anymore" / "add
one for X") and the corrections write to `/tmp/Profile.md`.

Vectors persist in `build_state.taste_vectors`.  Recommender (§4)
reads them on every call.

---

## 4. Recommender redesign — one synthesis tool, not eleven SQL wrappers

### The new `recommend` command

Replaces `candidates`.  Single-purpose, takes the full picture, does
the synthesis the model used to do by hand (and got wrong with
goodreads-rating-as-quality).

**Inputs:**
- `--catalog /tmp/Library_Catalog.sqlite`
- `--log $PROJECT_LOG`
- `--profile /tmp/Profile.md`  (taste vectors parsed from sections)
- `--reading-list /tmp/Reading_List.md`  (exclusion + duplicate gate)
- `--build-state /tmp/build_state.json`  (vectors, floors, current
  counts)
- `--genre <G>` (optional — focuses the slice)
- `--shape one|ab|scan|deep-cut` (controls return size; one→1 rec,
  ab→2 contrasting recs, scan→4, deep-cut→1 with low popularity)
- `--n <int>` (override slice size)

**Score (replaces the `score_candidate` formula):**

```
score = goodreads_rating
      × taste_signal_overlap
      × theme_match
      × recency_dampener(log)
      × (1 - 0.3 if author_in_recent_year else 0)
      × entry_point_factor    # 0 if not entry point, 1 otherwise
      − rejection_penalty
```

- `goodreads_rating` is a quality factor only — never a sort key on
  its own.  Capped at 5.0.
- `taste_signal_overlap` = count of book's `taste_signals.positive`
  that match a vector signal in the reader's profile, normalized.
  This is the **central change** — surfaces deep cuts that match
  taste over popular-but-mid-fit titles.
- `theme_match` = jaccard of book themes vs. profile theme set.
- `recency_dampener` down-weights books whose author appears in the
  log's last 12 months (those tastes are already represented in
  continuations / wishlist).
- `goodreads_reviews` is **not used.**  The skill should explicitly
  forbid review-count-as-quality-proxy.
- `entry_point_factor` is the entry-point gate baked in (was opt-in
  via `--author-entry-point-strict`; now always on).

**Time-bucketed log read.**  Recommender splits the log into three
pools — last 12mo, 12-36mo, 3+ years — and pulls taste signals
proportionally across all three, not weighted toward recent.

**Output:**

```json
{
  "shape": "scan",
  "picks": [
    {
      "key": "...",
      "title": "...",
      "author": "...",
      "pages": ...,
      "score": 18.4,
      "match_reasoning": {
        "anchor_log_entries": [{"title": "Pet Sematary", "rating": 5}],
        "matched_vectors": ["grief-rooted horror", "lyrical grimdark"],
        "matched_themes": ["isolation", "loss"],
        "comp_overlap": ["A Head Full of Ghosts", "..."],
        "entry_point_ok": true,
        "popularity_note": "small audience (4.4 / 287 reviews)"
      },
      "is_deep_cut": true,
      "warnings": []
    }
  ],
  "vector_coverage": {
    "structural cleverness": {"used": 12, "vector_books": 4},
    "humor with serious stakes": {"used": 0, "vector_books": 1},
    ...
  },
  "floors": {
    "indie": {"used": 4, "floor": 15},
    "classic": {"used": 7, "floor": 12}
  },
  "probe_recommended": false
}
```

The `match_reasoning` field is **fact source**, not pitch text.  The
skill explicitly forbids quoting catalog summaries.  The model
synthesizes the personal connection itself ("you went 5★ on Pet
Sematary, this is grief-rooted horror in a similar register").

**Anti-pattern check (auto-warn).**  If `series_position` ≠ Book 1
or `author_entry_point` is false, the recommender adds a `warnings`
entry: `"not an entry point — series_position: Book 5"`.  Skill
treats any warning as a hard pull-and-resort signal.

### Other synthesis tools to keep / improve

- **`unfinished-series`** — already works.  Keep.
- **`status`** — new.  Single command returning current state vs.
  goals: genre distribution, indie/classic floor progress, page-budget
  rough estimate (sum of pages so far, average pages/book), long-
  series slot usage, vector coverage, last reflection-checkpoint pick
  count.  Skill calls this constantly **silently** — output is for the
  model, not the reader.
- **`series-fit`** — new.  Given a series name, returns: full book
  list with page counts and `series_role`, narrative shape (one arc
  / loose subseries / dip-in — derived from series_status + position
  patterns), recommended scope based on profile signals (e.g.
  reader prefers ≤3-book commitments → defaults to "Book 1" or
  "Books 1-3").  Replaces `series-continuation` plus the manual
  scope-question loop.

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

1. **Helper script rewrite.**  New `recommend`, `status`, `series-fit`,
   `unfinished-series` (port).  Drop the rest.  Tests for each.
   *Catalog stays as-is* — `recommend` does substring matching on
   `taste_signals.positive` until 6.1 lands.
2. **Skill rewrite — `librarian-build-setup`.**  Add taste cartography
   pass.  Goals-as-floors language.  No phase numbering in
   internal voice.
3. **Skill rewrite — `librarian-build`.**  New conversation grammar
   (pitch shapes, no batch structure, silent status, reflection
   every ~10 picks).  Reader-interruption-as-primary-signal.
4. **Skill rewrite — `librarian-build-finish`.**  Vocabulary cleanup,
   no phase numbering.
5. **Triage + cataloguer + quickref edits.**  Small surface — drop
   references to dropped scripts, update phrase set, point to new
   `status` for `where are we`.
6. **Build artifact `dist/skills/*.zip` rebuild.**  Smoke-test in a
   fresh chat.

Catalog cleanup (6.1-6.7) runs in parallel on the Code surface,
independent of the skill rewrite.  Skill changes don't block on it
— they degrade gracefully and improve as catalog cleanup lands.

---

## 8. Out of scope for this plan

- Implementation of any of the above.  This is design intent.
- Catalog cleanup work (6.1-6.7) — pitched, not specified.
- The Code-side skills on `main` — unchanged, per CLAUDE.md.
- React picker artifact changes — pure renderers, no design issue.
- Drive / project-knowledge layout changes — orthogonal.
