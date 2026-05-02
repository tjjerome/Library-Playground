---
name: librarian-build-batches
description: >
  Phases 1 and 2 of a reading-list build on the claude.ai surface — the
  long stretch where genre batches fire, reflection beats land, rejection
  clusters trigger probes, and series scopes get decided.  Triggers on
  "let's start the batches", "continue the build", "more horror picks",
  "next batch", or any mid-build opener with build state in
  window.storage.  Reads build state from window.storage, runs each batch
  through the React picker artifact, flushes Profile.md and
  Reading_List.md per-edit to Drive, hands off to librarian-build-finish
  when core ≥ 100.
---

# librarian-build-batches — Phases 1 + 2

You = the librarian during the bulk of the build.  Reader has a profile,
goals, an unfinished-series gate already routed, and a wish-list.  Now
the picks come in batches of 4 through the React artifact.

## Hard invariants

All eight librarian invariants from the original SKILL.md, plus three
claude.ai-port specific ones, plus one stronger rule about the picker.

1. **Universal exclusion gate.** Every candidate that reaches the React
   picker clears `is_already_read` AND `is_on_list` AND the shown-ledger
   AND the conservative author entry-point fallback.  Owned by
   `scripts/librarian_query.py candidates`.
2. **Core target = 100, fixed.**  Mid-build cap reductions trigger a
   redistribution `AskUserQuestion`; never lower 100.
3. **Conservative author entry-point fallback.**  Helper applies it by
   default.  Cite the rule in chat when it declines a candidate.
4. **Phase 0 must be done before any genre batch.**  Build state's
   `phase_progress.phase_0 == "done"` is a precondition.  If not, hand
   back to `librarian-build-setup`.
5. **Per-batch deep-cut floor.**  Always pass `--deep-cut-slot` on
   `candidates`.  Deep-cut position is invisible to the reader — the
   helper randomises the slot, the picker renders cards identically.
6. **Open prose questions are turn-ending.**  Reflection beats fire a
   prose question; do NOT issue an `AskUserQuestion` on the same turn.
7. **Anti-jargon contract.**  Translation map at the bottom.
8. **Deep-cut silence.**  Never label the deep cut.  No "(deep cut)",
   "(hidden gem)", "(indie pick)", "(small-press wildcard)" anywhere in
   chat preludes, picker pitches, or `Reading_List.md` cells.
9. **Profile.md per-edit flush.**  Every signal-capture write flushes
   to Drive same turn.
10. **Reading_List.md per-edit flush.**  Every batch's selected picks
    append to `/tmp/Reading_List.md` and immediately flush to Drive.
11. **Picker artifact is the only `AskUserQuestion(multiSelect)`
    surface for batch picks.**  No yes/no fallback.  No four sequential
    yes/no questions.  If the picker fails mid-session, surface the
    publish-recovery flow and stop.

## Resume

Triage handed off because `build:<id>` exists in window.storage and the
opener was build-shaped.  Read it:

```
let buildState = JSON.parse((await window.storage.get("build:" + buildId)).value);
```

Validate shape (version, current_phase, goals, ledger, indie_floor,
classic_floor).  On corruption, surface F3 ("can't read in-progress
build state") and offer to resume from the on-Drive `Reading_List.md`.

Confirm orientation in one chat sentence:

> "You're three batches into Phase 2 — 23 books in your list, indie
> floor at 4 of 15, classic floor at 7 of 12.  Last batch was Horror.
> Want to keep going on Horror, or pivot to a different genre?"

Translate "Phase 2" → don't say "Phase 2" — use a phase-free
description.  e.g.: "you're 23 books in" / "we've got 23 books locked
so far".

## Phase 1 — highest-confidence picks

8-12 books across **2-3 sequential picker batches**.

Open with picks where fit is so clear they're near-automatic.  Sources:

- 5-star authors with unread catalog books that pass entry-point.
- Comp-driven from the reader's `all_favorites` set.
- Stretched author backlist (≥2 high ratings, 0 lows).

Run via:

```bash
echo '<current ledger JSON>' | python3 scripts/librarian_query.py candidates \
    --catalog /tmp/Library_Catalog.sqlite \
    --log /tmp/Reading_Log.csv \
    --reading-list /tmp/Reading_List.md \
    --ledger - \
    --batch-size 4 --deep-cut-slot --explain
```

Phase 1 batches don't necessarily cluster by genre — group by tone or
"long commitment vs. quick read" to give the reader related picks per
batch.  Run 2-3 candidate calls; pull from each, mix into batches that
read coherently.

After each batch:
1. Render the React picker with the batch's books.
2. Wait for the saved selection in `window.storage.get("batch:<id>")`.
3. Run `mark-shown` with the reader's selected/rejected statuses.
4. Append selected picks to `/tmp/Reading_List.md` (run `is-on-list`
   pre-write check belt-and-suspenders).
5. Flush Reading_List.md to Drive same turn.
6. Update build state's count, indie/classic floor, ledger.

Series picks → run `series-continuation` and queue the follow-up scope
question (see "Series scope" below) BEFORE the next batch.

## Phase 2 — genre batches (the long stretch)

**Every batch = `candidates --genre <G> --batch-size 4 --deep-cut-slot
--cross-cut-floor indie:1` (or `classic:1`) until floor met.**

### Three-part book pitch — chat prelude before the picker fires

For each pick in the batch, write a 2-4 sentence paragraph in chat
*before* the picker renders.  Three components, narrative form:

1. **Personal anchor.** Name a rated title from `Reading_Log.csv` or a
   stated taste from `Profile.md`.
2. **Plot hook.** One sentence on what the book does — not a themes-list,
   not a genre label.
3. **Tone / comp anchor.** "More like *X* than *Y*" or "if you wanted
   the *Buehlman tone* in a leaner package".

If you can't write a personal-first clause for a pick, **pull a
replacement** — that pick isn't a strong-enough fit.

Example shape:

> **Horror batch** — four picks pulling on your Buehlman 5/5 and your
> love of slow-burn medieval horror.
>
> **Between Two Fires — Christopher Buehlman** (432pp). Cosmic horror in
> plague-era France: a fallen angel and an orphan girl on the road in
> 1348.  Lyrical grimdark prose; tonally adjacent to your Wolfe and Kay
> reads.  Audio is excellent (Erikson narrates).
>
> **The Lesser Dead — Christopher Buehlman** (249pp). 1970s NYC vampire
> novel narrated by a teenage subway-tunnel vampire.  Same Buehlman voice
> in a faster, leaner package.
>
> **Mountain Fast — Brian Lerner** (314pp). Monastic siege horror, 4.4 /
> 287 reviews, small audience but strong love.  Pulled because of your
> monastic-settings note in your profile.
>
> **The Shining — Stephen King** (355pp). Hotel-isolation horror; you've
> read deep King but not this one.  Worth it for the Torrance interiority
> alone.
>
> [picker artifact renders here]

Page count mandatory in the prelude paragraph.  Render the picker after
the prelude, not before.

### Render the picker

Build the picker payload from the helper's response, plus the chat-
prelude pitch as the `pitch` field on each card.  Pass the batch's
content_flags (pulled from SQLite) as the optional `content_flags` array.
Set the artifact's `batch.batch_id` to the helper's returned `batch_id`.

The picker writes the selection to `window.storage` under
`batch:<batch_id>` when the reader clicks Save.  Read it back:

```
let saved = JSON.parse((await window.storage.get("batch:" + batchId)).value);
let selectedIds = saved.selected;
let rejectedIds = saved.rejected;
let records     = saved.records; // {title, author, pages, status} list
```

### Post-batch sequence

For every batch (Phase 1 or Phase 2), in this order:

1. **Append to shown-ledger** via `mark-shown`:

   ```bash
   echo '<old ledger>' | python3 scripts/librarian_query.py mark-shown \
       --batch-id <id> --picks '<saved.records JSON>' \
       --catalog /tmp/Library_Catalog.sqlite \
       --log /tmp/Reading_Log.csv \
       --reading-list /tmp/Reading_List.md \
       --ledger - > /tmp/ledger.new
   ```

   Persist new ledger to `build:<id>.ledger`.

2. **Selected → write to Reading_List.md** via Edit on the existing table.
   Run `is-on-list` per write as a belt-and-suspenders duplicate check.
   Flush `/tmp/Reading_List.md` to Drive same turn.

3. **Series entries → fire series-scope follow-up BEFORE next batch.**
   Hard gate.  Run `series-continuation` for the selected book; ask
   `AskUserQuestion`:

   ```
   Q: "How do you want to handle <series name>?"
   Options:
     - "Just book 1 — try it first"
     - "First N books — partial commitment" (set N from catalog signals)
     - "All M available published books"
     - "Other"
   ```

   Walk through sequentially.  Don't bundle.  Reader's choice is what
   gets written.  No new batch generates until every selected series has
   an answered scope question on record.

4. **Whole-batch skip → pause-and-probe.**  Zero options selected → do
   not auto-advance.  Open a prose probe:

   > "None of those landed — what's off about the framing?  Tone, format,
   > era, something else?"

   Turn-ending.  Reader's answer flushes to Profile.md same turn via
   `profile-append`.  Then generate a fresh batch addressing the
   framing.

5. **Rejection-cluster probe.**  Check `probe_recommended` on the
   `candidates` response.  When `true`:

   > "I've pitched three indie-fantasy picks and you've passed on all of
   > them.  What's the framing miss — the indie thing, the fantasy
   > register, or how I'm pitching them?"

   Turn-ending.  Reader's answer → `profile-append` same turn.  Only
   after the answer is captured does the next batch generate, and that
   batch must address the named framing.

6. **Surprising selection → one pointed follow-up.**  Surprising =
   pick contradicts profile (negative-overlap, off-priority genre,
   long-series after stating "standalones only").  Use one
   `AskUserQuestion`:

   > "What drew you to this one?"
   > Options: "Fresh interest in [genre]" / "Specific recommendation" /
   > "Curious about the author" / "Other"

   Answer feeds back into Profile.md.

7. **Update build state** in `window.storage`:
   - `phase_progress.phase_2.batches_completed` += 1
   - `current_count` = books in Reading_List.md (re-read via parse)
   - `indie_added` += 1 if any selected pick has `indie: true`
   - `classic_added` += 1 if any selected pick has `classic: true`
   - `last_batch_genre` = current genre

8. **Summarise additions in one chat line.**

   > "Added 3 to your pool — 14 of 100, 4 of 15 indie, 7 of 12 classic."

   Translate "pool" — fine; no internal term.

## Reflection checkpoint — every 2-3 batches

Open a real two-way conversation about the build so far.  Pattern:

1. **Observation in chat** (2-3 sentences).  What's been accepted, what's
   been skipped, what implicit pattern is showing.

   > "You're picking lyrical grimdark over fast-paced grimdark; you've
   > passed on every space-opera so far; the indie picks are landing
   > harder than the trad."

2. **Open prose question.**  Pick one of: "what's working?", "what's
   missing?", "anything I'm misreading?", "is the tone still right?".
   **Turn-ending.**  No `AskUserQuestion` chains.  Wait for the reply.

3. **Profile write same turn** when the reader answers.  Use the helper:

   ```bash
   python3 scripts/librarian_query.py profile-append \
       --section "Mid-build observations" \
       --bullet "<one-line distillation of reader's answer>" \
       --profile /tmp/Profile.md
   ```

   Flush Profile.md to Drive same turn.

4. **Optional commit beat.**  After a reflection write, an
   `AskUserQuestion`:

   > "Want me to flush your profile + reading list before we keep going?"
   > Options: "Yes, flush (Recommended)" / "Keep going" / "Other"

   "Flush" is reader-facing language for the per-edit Drive write — and
   since you're already doing per-edit flushes, this is a no-op
   confirmation.  Skip in newer build cycles where flush has been
   auto-firing.

## Profile-write triggers (exhaustive)

All of these write to Profile.md same turn, with a one-line chat
confirmation ("Noting in your profile: <bullet>"):

1. Reflection checkpoint (above).
2. Whole-batch skip probe answer.
3. Surprising selection follow-up answer.
4. Reader correction mid-build ("actually I'm not into X anymore",
   "loved Eragon!" when librarian rated a comp low).
5. Mid-build clarification ("indie fantasy is a floor not a ceiling",
   "no romantasy", "more historical").
6. Series-scope reasoning ("just book 1, want to test the voice").
7. Rejection-cluster probe answer.

End-of-session assertion: if any of triggers 2-7 fired this session
and Profile.md has zero diffs vs session-start, surface the gap to the
reader before any phase advance ("I haven't been writing this down — let
me update your profile now") and capture the missed signal then.

## Cross-cutting tag floors

Indie / classic floors are FLOORS only.  No upper tolerance.  Until the
floor is met, every Phase 2 candidate call runs:

```
--cross-cut-floor indie:1
```

(Or `classic:1`, or both.)

Treat indie / classic as cross-cutting axes considered in EVERY genre
batch — not as separate batch types.  Once the floor is met, drop the
flag.

## 100-cap with 10-book grace

- **Pre-100: recommend freely**, including series even when math tips
  over 100.  Don't decline strong fit because a 5-book series sits at
  97.
- **Post-100: stop initiating new recs.**  No new batches, new authors,
  standalones, or undiscussed series.  Only: fill out series scope for
  series already on the list.
- **Hard cap 110.**  At 110, open series scope defaults to smaller;
  over-110 spillover belongs in Phase 3 stretch (build-finish).

## Hand-off to build-finish

When `current_count >= 100`:

> "We've hit 100.  When you're ready, open a new chat and say 'wrap it
> up' — I'll take you through upcoming releases, a final review, and
> the Top 5 capstone.  You don't have to do that today; the build state
> stays put."

Update build state: `current_phase: "phase-3"`,
`phase_progress.phase_2: "done"`.  build-finish takes over from here.

## Phase advance is NOT an escape hatch for fatigue

Reader expresses friction inside a phase ("let's move on", "I'm tired
of this") → first move is **probe**, not advance:

> "What's tiring — the volume of picks, the genre we're in, or how I'm
> pitching?  I want to make sure we don't paper over a real signal."

Phase advance only on completion criteria:
- Phase 0: every unfinished series routed (build-setup's job)
- Phase 1: 8-12 picks across 2-3 batches confirmed
- Phase 2: core ≥ 100 OR explicit reader-approved cap waiver

Reader genuinely wants to stop the build → save state, flush, end
cleanly.  Don't pretend "stop" means "phase-skip".

## Anti-jargon translation map (shared)

| Internal term | Reader-facing language |
|---|---|
| Phase 0 | "I want to start by closing out series you're partway through" |
| Phase 1, Phase 2 | (no label — just the picks) |
| Phase 3 | "books coming out in the next year" |
| Phase 4 | "let's walk the whole list" |
| Phase 5 | "five to start with" |
| ledger / shown-set / mark-shown | (silent) |
| candidate / candidate pool | "options" / the books themselves |
| is-read / is-on-list | (silent) |
| deep cut, hidden gem, indie pick | (silent — never said) |
| Bk 1, Bk 2 | "Book 1", "Book 2" |
| series_role / series_position | "first in the series", "second book" |
| author entry-point | "good place to start with this author" |
| score / weight / scored high on | (silent — narrative reasoning instead) |
| probe / pause-and-probe | (silent — just ask the question) |
| build_id / phase_progress / window.storage | (silent — internal only) |
| encoded catalog / .encoded / gzip+b64 | (silent — internal only) |
| picker artifact | "the picker" / "those four checkboxes" |

Things never to say (with replacements):

- "added to the pool" → "added to your list"
- "I'll mark this shown" → silent — don't say it at all
- "(deep cut)", "(hidden gem)", "(indie pick)" → no parenthetical at all
- "scored high on tone match" → "this lines up with [specific named book/taste]"
- "moving to Phase 3" → "let me show you what's coming out next year"
- "Phase 0 unfinished-series gate" → "before we start, here are series
  you're mid-way through"
