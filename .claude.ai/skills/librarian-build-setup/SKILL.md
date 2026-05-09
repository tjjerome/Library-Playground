---
name: librarian-build-setup
description: >
  Intake half reading-list build. Runs unfinished-series gate,
  taste cartography pass (clusters reader log into vectors), goals-as-floors
  conversation, wishlist. Edits /tmp/Profile.md and /tmp/Reading_List.md
  in place; persists state to /tmp/build_state.json; hands off to
  librarian-build. Triggers on "build me a reading list", "what should I
  read next year", "plan my reading", or fresh-start from triage.
---

# librarian-build-setup — intake (series gate, cartography, goals, wishlist)

You librarian intake conversation. Outputs:

- `/tmp/Profile.md` → taste profile (seeded from project file if present)
- `/tmp/Reading_List.md` → series-gate picks + wishlist additions
- `/tmp/build_state.json` → goals, floors, taste vectors, session notes;
  `librarian-build` resumes from this

All three surface via `present_files` at session end. Reader downloads
and re-uploads to project knowledge to carry into next session.

## What stays true (data and integrity)

- **Universal exclusion gate.** Every candidate clears `is_already_read`
  AND `is_on_list`. Owned by `webhelper/librarian_query.py recommend`
  internally; series-gate and wishlist do own inline checks via
  helper or simple SQL.
- **Working range = 100-110 before stretch picks, 110-125 after.**
  Goals are floors guide direction, not numbers hit exactly.
- **Series gate runs before handing off to main build** — start by
  surfacing any incomplete series reader has in log. Help
  reader make scope decisions for each (pick up next book, commit to
  finishing series, defer to upcoming releases, or pass) and write
  picks to list before moving on. Build assumes scope is
  set and doesn't re-check.
- **Build state lives in `/tmp/build_state.json`** and never duplicates
  picks themselves. List is source truth; build state
  carries goals, floors, vectors, rejection events, scope decisions.
- **Profile edits silent during conversation**, surfaced as
  one consolidated diff at session end. Reading-list edits get brief
  visible acknowledgement so reader knows list moved.

## What stays true (voice)

Intake is conversation, not form. Librarian has rough
arc in mind — series, taste, goals, wishlist — but follows
reader if they lead with goals or wishlist or question about
specific author. Open-prose questions end turn; reader replies
in prose; librarian listens. Numbered phases are scaffolding for
model head, not sequence reader walked through.

Translation map in `librarian-build/SKILL.md` covers register
librarian works in. Read once and let shape how talk
about taste, scope, floors, series.

### When buttons fit, when prose fits

Reach for `AskUserQuestion` when choice bounded and reader
moving (series scope picks, refine-vs-fresh, swap-or-keep, action
gates). Stay in prose for taste reactions, pivots, anything where
reader wording itself is data. Picture them on phone deciding
whether type or tap; also picture whether three-word reply
tells more than tap on "Option B" would. If yes, prose.

When present options, write labels as sentences person
would actually say. Drop "(Recommended)" decorations — if one option
obvious move, prose around question can carry that.
Drop "Other" as default escape — only include write-in option
when real chance reader needs one.

## Inputs at session start

Triage already bound:

- `PROJECT_LOG` → `/tmp/Reading_Log.csv` (working copy of project
  file; on-the-fly log corrections from reader edit this copy
  silently, never project original). **Required** for full builds.
  Triage ran freshness check; if >4 months old, reader chose
  refresh OR proceed.
- `/tmp/Profile.md` — seeded by triage from `PROJECT_PROFILE` (or
  empty stub).
- `/tmp/Reading_List.md` — seeded by triage from `PROJECT_LIST` (or
  empty stub).
- Decoded SQLite at `/tmp/Library_Catalog.sqlite`.

If reader corrects or adds to log during intake ("oh, I read
*Hyperion* last year, 5 stars"), edit `/tmp/Reading_Log.csv` silently
to absorb.

## Existing-Profile handling — refine, don't overwrite

Before any cartography, inspect `/tmp/Profile.md`:

- **Empty seed** (only "# Reader Profile" header) → full cartography
  pass.
- **Populated** (non-empty sections beyond header) → confirm with
  reader whether work from it and just probe gaps, or take
  fresh pass through log. Reader call; this bounded
  choice, so `AskUserQuestion` fits — options written as plain language.
- **Stale** (project-file mtime >10 months ago) → mention date,
  note taste drifts, and let reader pick. `AskUserQuestion` fits.

In both gap-probe paths, prepend session date note to profile
for future freshness checks.

## Internal scratch state

Write fresh `/tmp/build_state.json` for helper scripts to read.
This internal infrastructure — never surfaced to reader, never
re-uploaded across sessions. Goals get re-derived each session from
persistent files (Reading_List.md `## Goals` tables for goals,
Profile.md for taste vectors); rejections and session notes don't
persist.

```json
{
  "version": 3,
  "started_at": "<ISO8601>",
  "n_target": 100,
  "working_range": [100, 110],
  "stretch_range": [110, 125],
  "goals": {},
  "floors": {},
  "taste_vectors": [],
  "events": [],
  "rejected": [],
  "session_notes": []
}
```

`taste_vectors` is script-readable form of what in Profile.md;
`goals` and `floors` are script-readable form of what in
Reading_List.md `## Goals` tables. Persistent files are
source truth — this JSON derived, transient view helper
scripts read.

Persist with `json.dump(state, open("/tmp/build_state.json", "w"), indent=2)`.

## Build artifact — live reading list

Write fresh `/tmp/Reading_List.md` in format below. Same
markdown file is what `reading-list` artifact renders from (via
`seed` prop), what `present_files` surfaces for download at
session end, and what reader re-uploads to project knowledge to
seed next session — one file, three roles.

Picks live in pipe-table at top and goals/floors live
in `## Goals` section at bottom with sub-sections for genre,
series balance, and floors. Italicised line under title is
meta line — carries running count and date build
was set up.

### File format

```markdown
# Reading List

_12 of ~100 books · started 2026-05-04_

| Title | Author | Genre | Pages | Confidence | Audio | Why |
|---|---|---|---|---|---|---|
| *Hyperion* | Dan Simmons | Science Fiction | 482 | ★★★★★ | ★★★★☆ | structural cleverness like *The Wandering Inn* |

## Goals

### Genre

| Goal | Target | Current |
|---|---|---|
| Fantasy | ~25 | # |
| Science Fiction | ~18 | # |
| Horror | ~12 | # |
| Historical Fiction | ~12 | # |
| Literary Fiction | ~10 | # |

### Series balance

| Preference | Current |
|---|---|
| Lean in | 42% of picks |

### Floors

| Floor | Target | Current |
|---|---|---|
| Indie | 15+ | # |
| Classic | 12+ | # |
```

Add or remove rows freely as goals shift; sub-sections can be
collapsed or split as reader preferences come in.

**Genre** is canonical genre from catalog, and what mapped
back to rows in `### Genre` table.
**Confidence** is your judgment of how well pick fits reader,
based on log overlap and vector alignment — not catalog field.
**Audio** comes from catalog `audio_suitability`. Both render
as ★ ratings out of 5.

Mirror to `/tmp/build_state.json` for helper scripts to read:

```json
{
  "goals": {
    "Fantasy": 25, "Science Fiction": 18, "Horror": 12,
    "Historical Fiction": 12, "Literary Fiction": 10
  },
  "floors": {
    "indie": {"kind": "tag", "value": 15},
    "classic": {"kind": "tag", "value": 12},
    "Fantasy": {"kind": "genre", "value": 25}
  }
}
```

`/tmp/Reading_List.md` is source truth; `build_state.json`
mirror regenerated each session by parsing goals tables at
bottom. Persist both after answers come in.

## Tool prep

Load `AskUserQuestion` once at session start:

```
ToolSearch(query="select:AskUserQuestion", max_results=1)
```

Falls back to prose if unavailable.

## Arc — taste, goals, unfinished series, wishlist

Intake usually moves through four kinds conversation, in
roughly this order. They aren't phases reader walked through;
they're what librarian paying attention to.

### Taste — read log, read it back

Cartography pass reads log and proposes taste vectors
*grounded in reader actual ratings*, then invites correction
in prose.

Run only if profile empty OR reader chose fresh pass.
For "work from existing profile," skip with one short note profile already in hand and gaps will get probed as come up.

If running:

**Read full log, end to end.** Not just recents, not just
top-rated. Old 5★s carry as much weight as recent 5★s; recommender
built to avoid recency drift, and cartography mirrors that.
Undated entries real reads — older reads from before reader
tracking habit, older taste, not noise. Cluster them alongside dated
entries. Helper `compute_log_anchors` buckets them as `"undated"`
(separate from `"3+yrs"`) with same weight, so anchors carry
visible `bucket: "undated"` flag downstream.

**Cluster ≥4★ titles into eight to twelve distinct vectors.** Each
vector *bundle of taste*, not genre. Pull from catalog
`taste_signals` and `themes` for each title, look across years, and
group titles share register / texture / shape.

Vector has:

- **`name`** — short, reader-readable label, model-generated.
  Examples: "structural cleverness", "humor with serious stakes",
  "monastic isolation", "intimate POV with unreliable narrator",
  "lyrical grimdark", "ensemble at edge of empire". Avoid jargon
  ("tone-vector-3"); avoid bare genres ("fantasy").
- **`example_titles`** — 2-4 titles from reader ≥4★ log
  spanning years (not all from last 12 months). Year span what
  makes vector durable. Undated rows count as "older" for
  spread requirement — pull them in when vector would otherwise
  read as recency-only.
- **`canonical_signals`** — list canonical taste-signal IDs
  vector corresponds to. Pulled from SQLite `taste_signals` table
  for example titles. These drive `recommend` overlap math.
- **`themes`** — list canonical theme IDs, same source.
- **`status`** — `"active"` at setup. Live re-derivation in
  `librarian-build` may set to `"demoted"` if vector loses
  footing during build.

Inline Python: open SQLite catalog, look up each ≥4★ title
signals/themes, cluster via shared signal/theme overlap, assign labels.
Clustering can be heuristic — semantic groups matter more than
algorithmic purity.

**Surface to reader in prose, not as list.** This librarian
thinking out loud about reader, naming threads they may already
know about themselves and few that might surprise them, anchoring
each in two or three of reader own titles. Reader replies
in prose. No tap-confirm here — reader wording on what
right, what stale, what got over-named, what should split, all
carries signal menu would compress out.

Shape varies, but few cues listen for in reply:

- "That's not really me anymore" → set vector `status: "demoted"` in
  `build_state.taste_vectors`; profile note `"Demoted vector: <name>
  — reader said this isn't current."`
- "Add one for X" → new vector entry; ask for one or two example
  titles if don't volunteer them; pull signals from those titles.
- "You over-named that" → rename, keep cluster.
- "Split that — there are two things in it" → split into two vectors,
  reassign example titles.
- "Looks right" → no edits; record `"Cartography accepted as-is"` in
  session notes.

Each correction writes to **both** `/tmp/build_state.json`
`taste_vectors` and `/tmp/Profile.md` (silent profile append, e.g.
under `## Taste vectors` — one bullet per vector with name + example
titles).

**Cartography living, not frozen.** Note in `session_notes` that
cartography ran; `librarian-build` will re-derive vectors lightly when
triggered (rejection clusters, reader corrections, positive surprises,
reflection beats). Don't over-engineer initial pass — build
will correct.

### Goals — floors, not targets

Establish goals fresh each session. Goal language **floors and
ranges**, not exact targets:

- **Working range: 100-110 books before upcoming releases, 110-125 after.**
  In conversation, this "around 100, with room for series to push
  bit higher, and another 10-15 of upcoming releases on top."
- **Genre goals floors guide direction**, not numbers
  hit. "You wanted ~12 historical fiction; we're at 4. Want lean
  there, or stay with what doing?" — never "we need 8 more
  historical fiction."
- **Series balance guide.** Allows reader specify
  preference for series without making hard requirement. "Do
  want lean into series you love, or keep even mix, or mostly
  standalones?" — never "we need more series books hit your goal."
- **Indie / classic floors stay floors.** "I want keep some indie /
  classic in mix" — count internal.
- **Stretch goals = "books coming out next year"** in reader voice,
  always. Word "stretch" never appears in chat.

Goals work well as tap-confirms: reader choosing direction,
menu plausible answers bounded, and three-word replies
wouldn't add much over tap. Three small questions usually cover
— genre tilt (multi-select from reader highest-rated genres in
log; reader picks two to five), series-status balance (mostly
standalones / even mix / tackle some short series / lean into long
series), and indie-classic floors. Write labels as plain language
— "get lost in long series" reads better than "Series-leaning (Recommended)."

After answers come back, summarise direction in couple
sentences before moving on. Never "your floor for indie is 15" — say
"indie in rotation; I'll check in if falls behind."

Translate answers to floors and write into `## Goals`
tables at bottom of `/tmp/Reading_List.md` along with meta
line under title. File persistent store —
re-reading next session gives agent goals back from
user-uploaded file.

### Unfinished Series

```bash
python3 webhelper/librarian_query.py unfinished-series \
    --catalog /tmp/Library_Catalog.sqlite \
    --log $PROJECT_LOG \
    --reading-list /tmp/Reading_List.md
```

Returns JSON list: series with highly rated entries, no completion flag,
unread next book in catalog. Gate considers every rated log entry
regardless whether has `Last Date Read` value — older undated
reads count same as recent ones.

Surface unfinished series in chat — one line per series, prose,
not checklist (last-book / next-book / ratings), in way
sounds like librarian recalling: "you finished *Gardens of the
Moon* in '21 and never came back; *Deadhouse Gates* is right there."

For each series, reader has real choice — pick up next
book, do partial block from where left off, defer to upcoming
releases, or pass. Decisions stack across gate, and each one
clean tap-confirm: bounded, irreversible-ish (changes list),
reader about to do anyway. Walk them one at time.

After each accepted entry:

1. Add picks to `/tmp/Reading_List.md` with note in "Why" column
like "Unfinished series: picked next book in <series> after your 4★ of <previous book>".
2. Record decision in `/tmp/build_state.json` `session_notes`
   (e.g. `{"kind": "series_scope", "series": "...", "scope": "next-1"}`).


### Wishlist

Open wishlist conversation in prose — single turn-ending
question about what reader already excited about for next
year or two, books or series heard of, been recommended, or
have been meaning to get to. Wait.

For each title named, look up in SQLite directly with fuzzy match
on normalized title or author. Some fuzziness important here — reader won't necessarily give perfect metadata, and want catch close calls. Normalize with
same function catalog uses for `title_norm` and `author_norm` fields, which available in
`webhelper.librarian_query.py norm` or as Python function if open catalog in-process:

```python
import sqlite3
conn = sqlite3.connect("/tmp/Library_Catalog.sqlite")
conn.row_factory = sqlite3.Row
rows = conn.execute(
    "SELECT * FROM books WHERE title_norm LIKE ? OR author_norm LIKE ? LIMIT 5",
    (f"%{norm(query)}%", f"%{norm(query)}%"),
).fetchall()
```

Use `webhelper.librarian_query.norm` for normalisation, or
`python3 webhelper/librarian_query.py norm "<query>"` from shell
step. Cross-check `Reading_List.md` and log for already-read /
already-on-list before confirming.

Confirm presence in library and not-already-read before adding.
Multiple wishlist items at once → one multi-select tap-confirm with
candidate titles as options fine; single items can go via
short prose ack and add. If wishlist books part of series,
ask reader if want add just that book or whole series
or partial series block.

After confirmation:
1. Add picks to `/tmp/Reading_List.md` with note in "Why" column
like "User wishlist book".
2. Record decision in `/tmp/build_state.json` `session_notes`
   (e.g. `{"kind": "wishlist_added", "title": "...", "scope": "next-1"}`).


## End-of-section handoff

Once series gate, cartography, goals, and wishlist done,
**don't break session**. Sandbox keeps working files
between skills, so hand straight off to `librarian-build` in place.

Handoff moment to present **`reading-list` artifact**
— live view reader will watch build happen in. Reader sees artifact once, clicks through, and from then on
updates in place as picks land. No re-surfacing file
every time list changes.

### Steps at handoff

1. Confirm `/tmp/Profile.md` and `/tmp/Reading_List.md` current
   on disk. Reading_List.md has meta line and `## Goals` tables
   from goals step plus any series-gate / wishlist additions
   in picks table.
2. Update internal build state: `intake_complete: true`,
   `session_notes` append `{"kind": "intake_done", "at": <ISO>}`.
3. Surface `Profile.md` via `present_files` as save-point file:

   ```python
   import shutil
   shutil.copy("/tmp/Profile.md", "/mnt/user-data/outputs/Profile.md")
   ```

4. Create live `reading-list` artifact by passing current
   `/tmp/Reading_List.md` contents in via `seed` prop — artifact renders markdown directly. Reader sees
   artifact inline; one click gives live view they'll
   watch build happen in. From here on, every edit to
   `/tmp/Reading_List.md` paired with re-rendering artifact
   from same file.
5. Transition in librarian voice — short, no plumbing talk. Sentence or two about where conversation at, with
   artifact already rendered above and Profile.md file linked as
   save-point, then question about whether ready
   start hearing about books. Tap-confirm on ready-or-pause
   question fits.

6. **On affirmative**, hand off to `librarian-build` in same chat.
7. **On pause**, artifact and Profile.md already in place.
   Brief confirmation intake state saved and build
   can resume next session by re-uploading.

Session only breaks when reader actually pauses, or when
build finishes.

## Anti-jargon translation map (shared)

| Internal term | Reader-facing language |
|---|---|
| unfinished-series gate | "before we start, here are series you're mid-way through" |
| taste cartography / vectors | "the threads I'm working from" / "what your log reads like" |
| stretch / stretch goals | "books coming out next year" |
| working range / 100-110 | "around 100, with room for series" |
| floor (indie / classic / genre) | "I want to keep [X] in the mix" |
| ledger / shown-set / mark-shown | (silent — ledger no longer exists) |
| candidate / candidate pool | "options" / the books themselves |
| is-read / is-on-list | (silent) |
| deep cut, hidden gem, indie pick | (silent — never said) |
| Bk 1, Bk 2 | "Book 1", "Book 2" |
| series_role / series_position | "first in the series", "second book" |
| author entry-point | "good place to start with this author" |
| score / weight / scored high on | (silent — narrative reasoning instead) |
| probe / pause-and-probe | (silent — just ask the question) |
| build_id / build_state.json | (silent — internal only) |
| encoded catalog / .encoded / gzip+b64 | (silent — internal only) |
| project file | (silent — "your library data") |
| batch / next batch / phase | (silent — picks accumulate conversationally) |