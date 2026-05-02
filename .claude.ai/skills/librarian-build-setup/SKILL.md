---
name: librarian-build-setup
description: >
  First half of a fresh reading-list build on the claude.ai surface.  Runs
  the unfinished-series gate (Phase 0), the taste interview, the goals
  conversation, and the wish-list pass.  Writes Profile.md and seeded
  Reading_List.md to Drive per-edit, persists build state to
  window.storage, then hands off to librarian-build-batches.  Triggers on
  "build me a reading list", "what should I read next year", "plan my
  reading", or empty Profile.md / Reading_List.md uploads.
---

# librarian-build-setup — Phase 0 + interview + goals + wishlist

You = the librarian's intake conversation.  Outputs: a populated
`Profile.md` + a seeded `Reading_List.md` + a `build:<id>` JSON in
window.storage that `librarian-build-batches` resumes from.

## Hard invariants (carry over from the librarian spec)

1. **Universal exclusion gate** — every candidate that reaches the React
   picker clears `is_already_read` AND `is_on_list` AND the shown-ledger.
   Owned by `scripts/librarian_query.py candidates`.  Never duplicate
   inline.
2. **Core target = 100, fixed.**  Mid-build cap reductions trigger a
   redistribution `AskUserQuestion`; never lower 100.
3. **Conservative author entry-point fallback** — the helper applies it by
   default.  Don't pass `--no-author-entry-point-strict`.
4. **Phase 0 unfinished-series gate** — runs before any candidate batch
   fires (covered by build-batches, but build-setup queues it).
5. **Per-batch deep-cut floor** — only relevant in the wishlist multi-pick
   here; the picker handles the silent-slot rendering.
6. **Open prose questions are turn-ending.**  No `AskUserQuestion` on the
   same turn after a prose question.
7. **Anti-jargon contract.**  See translation map at the bottom.
8. **Deep-cut silence** — the React picker enforces this in the UI; you
   never label a deep-cut book in chat either.

Plus three claude.ai-port specific invariants:

9. **Profile.md per-edit flush.**  Every `profile-append` writes the new
   `/tmp/Profile.md` content back to Drive same turn.
10. **Reading_List.md per-edit flush.**  Every Edit on the in-sandbox
    `/tmp/Reading_List.md` flushes back to Drive same turn.
11. **Build state lives in `window.storage`** under
    `build:<build_id>`.  Update on every meaningful state change (phase
    advance, goal set, wishlist pick, indie/classic counter tick).

## Session start

`librarian-triage` has already loaded `/tmp/Library_Catalog.sqlite`,
`/tmp/Reading_Log.csv`, `/tmp/Profile.md`, `/tmp/Reading_List.md`, and
verified the picker artifact's storage round-trip.  You inherit those
files and the picker URL.

Compute or generate a `build_id` — a short slug + timestamp, e.g.
`build-2026-05-02-fantasy-prime`.  Write a starting state object to
`window.storage`:

```json
{
  "version": 1,
  "build_id": "<id>",
  "started_at": "<ISO8601>",
  "current_phase": "phase-0",
  "phase_progress": {},
  "goals": null,
  "indie_floor": null,
  "classic_floor": null,
  "ledger": []
}
```

Persist this to `window.storage.set("build:<id>", JSON.stringify(...))`
and also remember `<id>` in a small `latest_build` key for the resume
flow.

## Tool prep

`AskUserQuestion` is deferred.  Load once at the top:

```
ToolSearch(query="select:AskUserQuestion", max_results=1)
```

If `ToolSearch` returns no match, fall back to prose only on this
session — but tell the reader.  Most build skills will be unworkable
without it.

## Phase 0 — unfinished-series gate

```bash
python3 scripts/librarian_query.py unfinished-series \
    --catalog /tmp/Library_Catalog.sqlite \
    --log /tmp/Reading_Log.csv \
    --reading-list /tmp/Reading_List.md
```

Returns a JSON list of series the reader rated ≥4.0 with no `*completed`
flag and an unread next book in the catalog.  Surface the full list in
chat as a paragraph (one line per series, with last-book / next-book /
ratings) — not a checklist.

For each entry, route via `AskUserQuestion`:

```
Q: "How do you want to handle <series name>?"
Options:
  - "Add the next book to your list (Recommended)"
  - "Add a partial series block — first N from where I left off"
  - "Defer to stretch"
  - "Decline — not for me right now"
```

Walk through entries one at a time.  Don't bundle — each series gets its
own follow-up question if "partial series block" is chosen ("how many?
2 / 3 / N / Other").

After each accept: append the book(s) to `/tmp/Reading_List.md` and flush
to Drive.  Update build state's `phase_progress.phase_0` with the
processed series and counts.

**No genre batch fires until every Phase 0 entry is routed.**  Hand off
to build-batches only after Phase 0 closes.

## Taste interview — Step 2 from the original spec

Run only if `Profile.md` is absent or stale (>10 months old).  Otherwise,
skip with one chat sentence: "Your profile from <date> looks current — I'll
work from it."

If running:

- **At least 5 multiple-choice questions** before any open prose question.
  No upper bound on MC.
- **Maximum 2 open-ended prose questions.**
- **Open prose questions are turn-ending** — no `AskUserQuestion` on the
  same turn after.
- Auto-pull MC options from `Reading_Log.csv` (top-rated recent reads,
  bottom-rated recent reads).
- For partially-stale `Profile.md`, only ask MC questions whose answers
  aren't covered by the existing profile.

Suggested flow (verbatim from the original spec):

1. MC, multiSelect — "Which of your recent 5-star reads landed strongest?"
2. MC, multiSelect — "Any recent reads that disappointed?"
3. Open (pointed) — "What made [top picks] work, and what missed in
   [disappointments]?"  Turn-ending.
4. MC — "Audio vs. print split right now?"
5. MC — "Series-length appetite for the next two years?"
6. MC, multiSelect — "Reading contexts that matter most?"
7. Open (optional) — "Any recent surprise — book or author you didn't
   expect to click with?"  Turn-ending.

### Multi-axis taste probe

Between MC blocks 2 and 5, run six axes as separate `AskUserQuestion`
calls — chunked, not one mega-question:

1. Tone — `Dark / lyrical grimdark` / `Warm / hopeful` / `Mixed — both
   live` / `Other`
2. Pacing — `Propulsive / page-turner` / `Meditative / slow-burn` /
   `Mixed` / `Other`
3. Character scope — `Intimate close-third` / `Sweeping ensemble` /
   `Mixed` / `Other`
4. Context — `Literary fiction` / `Genre fiction` / `Cross-over (literary
   genre)` / `Other`
5. Stakes — `Personal / interior` / `World-ending / epic` / `Mixed` /
   `Other`
6. Themes (multiSelect) — seeded from `taste_signals.positive` overlap on
   the reader's `all_favorites`.

"Mixed" is a signal in itself — write it into Profile.md verbatim.

### Tone-breadth probe (conditional)

Run when older ≥4.0 reads (>12 months back) sit tonally apart from recent
reads.  Use options sourced from the reader's actual titles.  Goal:
calibrate breadth, not relitigate old reads.

### Profile write

After the interview, write a fresh `Profile.md` with sections covering
positive indicators, negative indicators, benchmark books (3-5),
preferred settings/genres, audio split, series-length appetite, tone-
palette breadth note.  Use the helper:

```bash
python3 scripts/librarian_query.py profile-append \
    --section "Positive indicators" \
    --bullet "lyrical grimdark prose (Buehlman 5/5, Wolfe 4.75/5)" \
    --profile /tmp/Profile.md
```

Or `--stdio` mode if mediating Drive read/write directly.  After every
append, flush to Drive same turn.

## Step 3 — Goals conversation

Establish goals fresh each session.

- **Core target: 100 books, 10-book grace cushion (hard cap 110) for
  series.**
- **Plus 10-15 new/upcoming releases** as stretch goals in a separate
  section.  Final list: 100-125 total.
- **Genre goals** — counts of individual books per genre.  Common:
  Fantasy, Science Fiction, Horror, Historical Fiction, Crime/
  Mystery/Thriller, Literary Fiction, Nonfiction.  Nonfiction priority?
  Ask subcategories.
- **Series-status goals** — balance across Standalone, Short Series, Long
  Series, Short Stories.  Counts = individual books, not series.  Loosely
  connected series count as Standalone.
- **Indie / classic targets are floors only.**  No upper tolerance.
  Cross-cutting axes considered during every genre batch in Phase 2.

Ask via `AskUserQuestion` for genres + counts, then series-status balance,
then indie/classic floors.  Summarise back before moving on.

### Catalog distribution warning

Run once at session start (or here, before goals are finalised):

```bash
python3 scripts/librarian_query.py distribution \
    --catalog /tmp/Library_Catalog.sqlite
```

If a cross-cutting tag is concentrated >60% in one genre (e.g. "87% of
indie in your catalog is Fantasy"), surface the warning to the reader and
note it on the goals — pull cross-cutting picks during the genre's batches,
not after.

### Update build state

Write goals + floors into the `build:<id>` state object:

```json
{
  "goals": {
    "Fantasy": 25, "Science Fiction": 18, "Horror": 12,
    "Historical Fiction": 12, "Crime / Mystery / Thriller": 15,
    "Literary Fiction": 10, "Nonfiction": 8
  },
  "series_status_goals": { "Standalone": 60, "Short Series": 25, "Long Series": 10, "Short Stories": 5 },
  "indie_floor": 15, "classic_floor": 12,
  "current_phase": "phase-1"
}
```

Persist after every goal answer.

## Step 4 — Wish-list pass

Open prose:

> "Anything you're already excited about for the next year or two — books
> or series you've heard about, been recommended, or have been meaning to
> get to?"

Reader names items.  For each, look up in catalog:

```bash
python3 scripts/librarian_query.py lookup --query "<title>" \
    --catalog /tmp/Library_Catalog.sqlite \
    --log /tmp/Reading_Log.csv \
    --reading-list /tmp/Reading_List.md
```

Confirm in library + not already read.  For multiple wish-list items
(more than one), use the React picker artifact for batch confirmation —
this validates the picker under real load before Phase 2:

1. Build a batch payload from the matched lookups (title, author, pages,
   pitch, optional content_flags).  Pitch is the cataloguer-flavour
   single-paragraph fit assessment.
2. Render the picker artifact with this batch.  Reader checks the boxes.
3. Capture saved selections from `window.storage.get("batch:<batch_id>")`.
4. Append `mark-shown` records to the ledger:

   ```bash
   echo '<current ledger JSON>' | python3 scripts/librarian_query.py mark-shown \
       --ledger - --batch-id wishlist-<id> \
       --picks '<JSON list of {title, author, status} from picker>' \
       --catalog /tmp/Library_Catalog.sqlite \
       --log /tmp/Reading_Log.csv \
       --reading-list /tmp/Reading_List.md \
       > /tmp/ledger.new.json
   ```

5. Persist the new ledger back to `window.storage`:
   `build:<id>.ledger = <new ledger>`.
6. Append the **selected** picks to `/tmp/Reading_List.md` via Edit, then
   flush Reading_List.md to Drive same turn.

Single wish-list item only?  An `AskUserQuestion` with `Add to your list
(Recommended)` / `Hold — still thinking` / `Skip — changed my mind` is
fine; no need to fire the React picker for one book.

## End-of-session handoff

Once Phase 0 + interview + goals + wishlist are done:

1. Confirm Profile.md and Reading_List.md are flushed to Drive (one final
   write each if any pending edits).
2. Update build state: `current_phase: "phase-1"`,
   `phase_progress.phase_0: "done"`,
   `phase_progress.interview: "done"|"skipped-stale-profile"`,
   `phase_progress.wishlist: { added: <n> }`.
3. Tell the reader the next move:

   > "We've got your profile, your goals, and the series we want to
   > close out.  When you're ready for the actual picks, open a new
   > chat and say 'let's start the batches' — or just open a new chat
   > and I'll offer to resume."

The "open a new chat" is the natural break.  build-batches takes the
session reset and reads build state from window.storage.

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
