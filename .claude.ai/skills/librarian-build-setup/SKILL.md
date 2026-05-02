---
name: librarian-build-setup
description: >
  First half of a fresh reading-list build on the claude.ai surface.  Runs
  the unfinished-series gate (Phase 0), the taste interview (using any
  existing project-file or artifact Profile.md as a seed), the goals
  conversation, and the wish-list pass.  Honours an existing Reading_List
  via the refine-vs-fresh prompt that triage already asked.  Writes profile
  and reading-list artifact storage per-edit, persists build state to the
  picker artifact's window.storage, then hands off to
  librarian-build-batches.  Triggers on "build me a reading list", "what
  should I read next year", "plan my reading", or fresh-start routings from
  triage.
---

# librarian-build-setup — Phase 0 + interview + goals + wishlist

You = the librarian's intake conversation.  Outputs:

- `profile` artifact → populated Profile.md (seeded from project file
  if present)
- `reading-list` artifact → seeded with Phase 0 picks + wish-list
  selections
- `picker` artifact's `build:<id>` JSON → goals + ledger + phase state
  that `librarian-build-batches` resumes from

## Hard invariants (carry over from the librarian spec)

1. **Universal exclusion gate** — every candidate that reaches the React
   picker clears `is_already_read` AND `is_on_list` AND the shown-ledger.
   Owned by `scripts/librarian_query.py candidates`.  Never duplicate
   inline.
2. **Core target = 100, fixed.**
3. **Conservative author entry-point fallback** — helper applies it by
   default.
4. **Phase 0 unfinished-series gate** — runs before any candidate batch.
5. **Per-batch deep-cut floor** — relevant in the wishlist multi-pick.
6. **Open prose questions are turn-ending.**
7. **Anti-jargon contract.**
8. **Deep-cut silence.**
9. **Profile artifact per-edit storage write.**
10. **Reading-list artifact per-edit storage write.**
11. **Build state lives in the picker artifact's `window.storage`** under
    `build:<build_id>`.

## Inputs at session start

Triage has bound:

- `PROJECT_LOG` → `Reading_Log.csv` in project knowledge.  **Required**
  for full builds.  Triage already ran the freshness check; if it was
  >4 months old, the reader chose to refresh OR proceed anyway.
- `PROJECT_PROFILE` → optional `Profile.md` seed in project knowledge.
- `PROJECT_LIST` → optional `Reading_List.md` seed in project knowledge.
- Profile artifact content → already seeded by triage.  Read with
  `window.storage.get("profile")`.
- Reading-list artifact content → already seeded by triage.  Read with
  `window.storage.get("reading_list")`.
- Decoded SQLite at `/tmp/Library_Catalog.sqlite`.

Mirror Reading_List artifact content to `/tmp/Reading_List.md` so the
helper can read it via `--reading-list`:

```bash
echo "$READING_LIST_CONTENT" > /tmp/Reading_List.md
```

## Existing-Profile handling — refine, don't overwrite

Before running the taste interview, inspect the profile artifact's
content:

- **Empty seed** (only the boilerplate "# Reader Profile" header) →
  full taste interview from Step 2 (below).
- **Populated** (non-empty sections beyond the header) → **partial
  interview**.  Skip MC questions whose answers are already in the
  profile.  Confirm with the reader:

  > "Your existing profile covers: <list of sections, e.g. Tone (lyrical
  > grimdark / mixed), Pacing (slow-burn), Audio split (60/40), Series
  > appetite (open to long-series).>  Anything to revise here, or
  > should I work from this and just probe the gaps?"

  `AskUserQuestion`:
  - "Work from this profile, probe gaps only (Recommended)"
  - "Run the full interview again — taste shifted"
  - "Other"

- **Stale** (artifact updated_at >10 months ago) → recommend full
  interview, defer to reader:

  > "Your profile was last updated <date> — about <X> months ago.
  > Tastes drift.  Want a fresh interview, or work from the existing
  > profile and probe the gaps?"

  `AskUserQuestion`:
  - "Fresh interview (Recommended)"
  - "Work from the existing profile"
  - "Other"

In both gap-probe paths, prepend a short note to the profile noting the
session date so future freshness checks have a recent timestamp.

## Build-id + initial build state

Compute or generate a `build_id` — short slug + ISO date, e.g.
`build-2026-05-02-fantasy-prime`.  Write a starting state object to
the picker artifact's `window.storage`:

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
  "ledger": [],
  "seeded_from": {
    "project_profile": "<true/false>",
    "project_list":    "<true/false>"
  }
}
```

Persist via `window.storage.set("build:<id>", ...)` against the picker
artifact.  Also write `latest_build` = `<id>` for resume.

## Tool prep

Load `AskUserQuestion` once:

```
ToolSearch(query="select:AskUserQuestion", max_results=1)
```

If unavailable, fall back to prose and tell the reader.  Most build
work is unworkable without it.

## Phase 0 — unfinished-series gate

```bash
python3 scripts/librarian_query.py unfinished-series \
    --catalog /tmp/Library_Catalog.sqlite \
    --log $PROJECT_LOG \
    --reading-list /tmp/Reading_List.md
```

Returns JSON list of series rated ≥4.0 with no `*completed` flag and an
unread next book in the catalog.  Surface the full list in chat as a
paragraph (one line per series, with last-book / next-book / ratings) —
not a checklist.

For each entry, route via `AskUserQuestion`:

```
Q: "How do you want to handle <series name>?"
Options:
  - "Add the next book to your list (Recommended)"
  - "Add a partial series block — first N from where I left off"
  - "Defer to stretch"
  - "Decline — not for me right now"
```

Walk through one at a time.  After each accept:

1. Append the picks to the reading-list artifact's content + flush:

   ```javascript
   let rl = JSON.parse((await window.storage.get("reading_list")).value);
   rl.content = rl.content + "\n## Series continuations\n\n| ... |";
   rl.updated_at = new Date().toISOString();
   await window.storage.set("reading_list", JSON.stringify(rl));
   ```

   Then mirror the new content to `/tmp/Reading_List.md` for the next
   helper call.

2. Update build state's `phase_progress.phase_0`.

**No genre batch fires until every Phase 0 entry is routed.**  Hand off
to build-batches only after Phase 0 closes.

## Step 2 — Taste interview

Run only if profile is **empty** OR the reader chose "fresh interview"
in the existing-profile prompt above.  Skip with one sentence if the
reader chose "work from existing profile":

> "Working from your existing profile.  I'll probe gaps as we go."

If running:

- **At least 5 multiple-choice questions** before any open prose
  question.  No upper bound on MC.
- **Maximum 2 open-ended prose questions.**
- **Open prose questions are turn-ending** — no `AskUserQuestion` on
  the same turn after.
- Auto-pull MC options from `PROJECT_LOG` (top-rated recent reads,
  bottom-rated recent reads).
- For partial interview (existing profile, gaps only), only ask MC
  questions whose answers aren't covered by the existing profile.

Suggested flow:

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
calls:

1. Tone — `Dark / lyrical grimdark` / `Warm / hopeful` / `Mixed — both
   live` / `Other`
2. Pacing — `Propulsive / page-turner` / `Meditative / slow-burn` /
   `Mixed` / `Other`
3. Character scope — `Intimate close-third` / `Sweeping ensemble` /
   `Mixed` / `Other`
4. Context — `Literary fiction` / `Genre fiction` / `Cross-over
   (literary genre)` / `Other`
5. Stakes — `Personal / interior` / `World-ending / epic` / `Mixed` /
   `Other`
6. Themes (multiSelect) — seeded from `taste_signals.positive` overlap
   on the reader's `all_favorites`.

"Mixed" is a signal in itself — write into the profile verbatim.

### Tone-breadth probe (conditional)

When older ≥4.0 reads sit tonally apart from recent ones.  Use options
sourced from actual titles.  Goal: calibrate breadth, not relitigate.

### Profile artifact write

After the interview, write a fresh Profile content with sections
covering positive indicators, negative indicators, benchmark books
(3-5), preferred settings/genres, audio split, series-length appetite,
tone-palette breadth note.

Read current artifact content, transform via helper, write back:

```python
# Build text in-memory or use multiple profile-append calls.
# When the existing profile has scaffolding, prefer profile-append per
# bullet (idempotent on duplicates).
result = subprocess.run(
    ["python3", "scripts/librarian_query.py", "profile-append",
     "--section", "Positive indicators",
     "--bullet", "lyrical grimdark prose (Buehlman 5/5, Wolfe 4.75/5)",
     "--stdio"],
    input=profile_content, capture_output=True, text=True, check=True,
).stdout
```

Then write back via `window.storage.set("profile", ...)`.  After every
append, the artifact storage write IS the per-edit flush — there's no
secondary Drive flush step (Drive doesn't hold the profile anymore).

## Step 3 — Goals conversation

Establish goals fresh each session.

- **Core target: 100 books, 10-book grace cushion (hard cap 110) for
  series.**
- **Plus 10-15 new/upcoming releases** as stretch goals in a separate
  section.  Final list: 100-125 total.
- **Genre goals** — counts of individual books per genre.
- **Series-status goals** — Standalone / Short Series / Long Series /
  Short Stories balance.
- **Indie / classic targets are floors only.**

Ask via `AskUserQuestion` for genres + counts, then series-status
balance, then indie/classic floors.  Summarise back before moving on.

### Catalog distribution warning

```bash
python3 scripts/librarian_query.py distribution \
    --catalog /tmp/Library_Catalog.sqlite
```

If a cross-cutting tag is concentrated >60% in one genre (e.g. "87% of
indie in your catalog is Fantasy"), surface the warning to the reader
before goals are finalised — pull cross-cutting picks during the
genre's batches, not after.

### Update build state

Write goals + floors into `build:<id>` state:

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

Persist via picker artifact's `window.storage` after every goal
answer.

## Step 4 — Wish-list pass

Open prose:

> "Anything you're already excited about for the next year or two —
> books or series you've heard about, been recommended, or have been
> meaning to get to?"

Reader names items.  For each, look up in the SQLite catalog:

```bash
python3 scripts/librarian_query.py lookup --query "<title>" \
    --catalog /tmp/Library_Catalog.sqlite \
    --log $PROJECT_LOG \
    --reading-list /tmp/Reading_List.md
```

Confirm in library + not already read.  For multiple wish-list items,
use the React picker artifact for batch confirmation.  Single item →
`AskUserQuestion` is fine.

After the picker save, persist ledger updates to `build:<id>.ledger`,
then append selected picks to the reading-list artifact:

```javascript
let rl = JSON.parse((await window.storage.get("reading_list")).value);
rl.content = rl.content + "\n## Wishlist additions\n\n" + table_text;
rl.updated_at = new Date().toISOString();
await window.storage.set("reading_list", JSON.stringify(rl));
```

Mirror to `/tmp/Reading_List.md` for the next helper call.

## End-of-session handoff

Once Phase 0 + interview + goals + wishlist are done:

1. Confirm both artifacts have current content (one final read-back to
   verify storage round-trip — no separate Drive step).
2. Update build state: `current_phase: "phase-1"`,
   `phase_progress.phase_0: "done"`,
   `phase_progress.interview: "done" | "skipped-existing-profile" |
   "partial-gap-probe"`,
   `phase_progress.wishlist: { added: <n> }`.
3. Tell the reader the next move:

   > "We've got your profile, your goals, and the series we want to
   > close out.  When you're ready for the actual picks, open a new
   > chat and say 'let's start the batches' — or just open a new chat
   > and I'll offer to resume."

The "open a new chat" is the natural break.  build-batches takes the
session reset and reads build state from the picker artifact's
window.storage.

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
| project file | (silent — "your library data") |
| picker artifact / profile artifact / reading-list artifact | "the picker" / "your profile" / "your reading list" |
