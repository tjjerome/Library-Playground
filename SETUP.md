# Setup — Library-Playground on claude.ai

This is the user-facing setup guide for the **claude.ai port** of the
librarian agent.  It runs on a Claude Pro subscription, no separate
API key, no Anthropic API credits beyond what Pro covers.  The
Code-side implementation on `main` is unchanged and stays as a
comparison reference.

If you're looking for the original Claude Code workflow, see
`README.md` on the `main` branch.

> **Time budget:** ≤30 minutes from cloning the repo to a working
> first session, *not counting* the one-time bulk catalogue build
> (~2-6 hours of mostly unattended runtime).

## How state moves between sessions

The librarian's mutable state lives in **project-knowledge files**, not
in published artifacts.  During a session, the librarian works in
`/tmp/` (`Reading_List.md`, `Profile.md`, `build_state.json`,
`log_pending_updates.csv`); at session end it surfaces those files via
download links so you can re-upload them to project knowledge.  The
next session reads them back from project knowledge.

The three React artifacts (`batch-picker`, `profile`, `reading-list`)
are pure renderers — they take content via props and have no
persistence layer.  You don't need to publish them for storage to
work.  The librarian renders one inline when it wants you to look at
your current list / profile, or to provide a richer batch-picker view
for a specific decision.

---

## 1. Prerequisites

You'll need:

| Requirement | Notes |
|---|---|
| Claude Pro subscription (or Max / Team / Enterprise) | Pro is enough.  Code execution must be enabled in Settings → Features. |
| Google Drive account, connected to claude.ai | The reader's mutable files (catalog, log, profile, list) live here. |
| Local Python 3.11+ | For the one-time catalog build + SQLite export. |
| Your `Library.csv` (Goodreads export format) | The full library you own. |
| Your `Reading_Log.csv` (Goodreads export format) | Optional for casual lookups; required for full builds. |
| Claude Code OR an Anthropic API key | **One-time only**, for the bulk cataloguer.  See note in §4. |

> **Pro-only setup note:** if you don't have Claude Code installed or
> an API key handy, you can still use the librarian — but the bulk
> cataloguer can only process up to 20 books per chat batch on the
> claude.ai surface (via the `library-cataloguer` skill), so seeding a
> 5,000-book library will take many sittings.  Bulk runs locally in
> Claude Code take 2-6 hours unattended.

## 2. Clone the repo and switch branches

```bash
git clone https://github.com/<you>/Library-Playground.git
cd Library-Playground
git checkout claude-ai-port
pip install -r requirements.txt
```

The `claude-ai-port` branch is parallel to `main`.  Don't expect
features to migrate between them — they exist side by side.

## 3. Drop in your CSVs

Put `Library.csv` and `Reading_Log.csv` in the repo root.  Both can
come straight from a Goodreads export.

`Library.csv` columns expected: `title`, `authors`, `genre`,
`series`, `series_type`, `indie`, `classic`, plus optional `pages`,
`goodreads_rating`, `goodreads_reviews`.

`Reading_Log.csv` columns expected: `title`, `authors`,
`Last Date Read`, `My Rating`, `genre`, `series_type`, `my_tags`,
`goodreads_shelves`.

## 4. Build the catalog (one-time, local)

```bash
python3 catalogue.py --library Library.csv
```

This processes every book in `Library.csv` through Claude, building
`Library_Catalog.json`.  Saves after every chunk; safe to interrupt
and resume.  Takes 2-6 hours for a 5,000-book library.

**Authentication:** Inside a Claude Code session, this picks up the
session ingress token automatically.  Outside Claude Code, set
`ANTHROPIC_API_KEY` in your environment first.  (The script refuses
to run if both are present, to avoid accidental external billing.)

After the bulk run, optionally backfill `series_role` and
`author_entry_point` (the librarian's recommendation gate uses
these):

```bash
python3 catalogue.py --library Library.csv --audit-entry-points
```

## 5. Export the catalog

```bash
# Full SQLite (used in-sandbox for queries) + the gzip+base64
# wrapped form (used to ship the catalog through the Drive connector).
python3 catalogue.py --library Library.csv \
    --export-sqlite Library_Catalog.sqlite --emit-encoded
```

Outputs:

- `Library_Catalog.sqlite` — queryable, ~12MB.  Local diagnostics
  only; the on-Drive form is the encoded one.
- `Library_Catalog.sqlite.encoded` — gzip+base64, ~5MB at 5,000
  books.  Drive uploadable.  First line is
  `# library-playground-catalog v1 gzip+b64`.

You can verify the SQLite + encoded round-trip cleanly:

```bash
python3 tests/sqlite_roundtrip.py
python3 tests/encoded_roundtrip.py
```

Both should report `OK`.

## 6. Set up Google Drive

In Google Drive, create a folder.  Default name: `Library-Playground`
(triage uses this unless you override on first run).

Upload **one file** into the folder:

```
Library-Playground/
└── Library_Catalog.sqlite.encoded   # from §5
```

That's it.  Profile, Reading_List, and build_state live in project
knowledge (see §6b); the reading log lives in project knowledge as
well.

In claude.ai, go to **Settings → Connectors**, find Google Drive,
click **Connect**, and grant access to the folder.

### 6a. Bake the Drive file ID into project instructions

Recommended for fast catalog loads (skips name-based discovery on
every session start) and to give the librarian the full set of
voice / routing / hard-rule instructions in one place.

1. In Drive, open `Library_Catalog.sqlite.encoded`, click **Share**
   or open the file and copy the URL.
2. Extract the file ID — the long alphanumeric segment between
   `/d/` and `/view` in the URL, e.g.:

   ```
   https://drive.google.com/file/d/1QEe3-9Hv0CEe1lsT4C9aRFFYTFgKsjPy/view
                                  ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
                                          file ID
   ```

3. Open `PROJECT_INSTRUCTIONS.md` in this repo.  Copy the contents
   of the codeblock inside it.
4. In claude.ai, open your project, click **Edit project
   instructions**, paste the codeblock content, and substitute your
   own Drive file ID for the placeholder on the first line.
5. Save.  Triage now fetches the catalog by ID directly; the
   embedded librarian rules are loaded into every chat in the
   project.

If you skip this step, triage falls back to looking for the file by
name in `Library-Playground/` (or your custom folder).  Slower but
works.

## 6b. Set up project knowledge

claude.ai projects can hold static reference files that load into
every chat in the project.  Create a project (or reuse one), then
upload:

- `Reading_Log.csv` (from §3) — your reading history.  **Upload as
  a file attachment, not inline content.**  Inline content gets
  injected as a `<documents>` block into every chat's system prompt
  and chews through context fast (Reading_Log.csv at 80KB+ is
  enough to push first-build attempts past the conversation-size
  cap on Pro).  As a file, the librarian reads it on demand via
  bash and only the rows it needs land in context.
- (optional) `Profile.md` — taste profile seed.  When present, the
  librarian copies it into `/tmp/Profile.md` at session start and
  edits in place; at session end you get a download link to the
  updated copy.
- (optional) `Reading_List.md` — existing TBR pool.  When present,
  the librarian asks "refine this or start fresh?" before doing
  anything.  Same /tmp + present-files cycle as Profile.md.
- (optional) `build_state.json` — only present after the librarian
  surfaces it at the end of a build session.  Re-upload between
  sessions to enable resume.
- (optional) `log_pending_updates.csv` — queued reading-log rate
  updates.  Re-upload between sessions until you merge them into
  Reading_Log.csv.

Empty `Profile.md` / `Reading_List.md` placeholders aren't
necessary — only upload them if you have content worth seeding.

**Do NOT upload `Library_Catalog.sqlite.encoded` to project
knowledge.**  It's ~5MB of base64 — well over the project-knowledge
budget on Pro (a single user reported 218% capacity after one
upload).  The catalog lives in Drive only.

## 7. Install the six skills

Build the zips locally:

```bash
make skills
```

This produces six files in `dist/skills/`:

- `librarian-triage.zip`
- `librarian-quickref.zip`
- `librarian-build-setup.zip`
- `librarian-build-batches.zip`
- `librarian-build-finish.zip`
- `library-cataloguer.zip`

In claude.ai:

1. Click your avatar → **Settings** → **Features**.
2. Make sure **Code execution and file creation** is on.
3. Scroll to **Skills**, ensure **Custom skills** is enabled.
4. Click the **+** button.
5. Drag each zip from `dist/skills/` one at a time.  Wait for the
   "Skill installed" toast between uploads.  Order doesn't matter;
   skills auto-trigger on description match.

## 8. Start your first session

Open a fresh chat and say one of:

- **"Build me a reading list."** → triage routes to
  `librarian-build-setup`.  Expect a taste interview, goals
  conversation, unfinished-series gate, and wishlist pass.  Plan on
  30-60 minutes for the setup phase.  When the setup phase ends, open
  a new chat and say "let's start the batches" — or just open a new
  chat and triage will offer to resume.

- **"Anything like *Between Two Fires*?"** → triage routes to
  `librarian-quickref`.  One focused 1-3 paragraph answer.  No
  workflow, no list edits.

- **"I just bought *Mountain Fast* by Brian Lerner"** → triage routes
  to `library-cataloguer`.  Confirms the entry, fills catalog fields,
  asks before writing.

## 9. Reader cheat sheet

Phrases the librarian recognises at any time.  You don't need to
memorise them — the librarian usually offers the right next move
on its own — but they're useful when you want to bypass the
small talk:

| Phrase | What it does |
|---|---|
| `where are we` | Triage replays your build state from `/tmp/build_state.json` ("23 books in your list, indie at 4 of 15") |
| `save my files` | Cataloguer surfaces the current `/tmp/Reading_List.md`, `/tmp/Profile.md`, `/tmp/build_state.json`, and any pending log updates as download links to replace in project knowledge |
| `save catalog` | Cataloguer re-encodes the in-session catalog and presents a download link.  Replace the Drive file manually. |
| `continue` | After a recovery prompt, resume the prior flow |
| `start fresh` | Archive the in-session reading list and build state; preserve `Profile.md`; route to build-setup |

## 10. Maintenance

### Adding a few books (≤20)

Tell the cataloguer in chat:

> "I just bought *The Lesser Dead* by Christopher Buehlman."

The cataloguer confirms, fills catalog fields, and writes to the
in-sandbox SQLite.  At session end (or when you say "save catalog"),
the cataloguer re-encodes the modified database and presents a
download link in chat.  Click the link, save the file, and replace
`Library_Catalog.sqlite.encoded` in your Drive folder.  The next
session loads the updated catalog.

The cataloguer never writes to Drive directly — every catalog change
is reader-confirmed and reader-applied.

### Adding more than 20 books at once

You have two paths:

1. **Run `catalogue.py` locally** (recommended for big batches):

   ```bash
   # update Library.csv with new rows
   python3 catalogue.py --library Library.csv
   python3 catalogue.py --library Library.csv \
       --export-sqlite Library_Catalog.sqlite --emit-encoded
   ```

   Then re-upload `Library_Catalog.sqlite.encoded` to Drive,
   replacing the old one.

2. **Break into ≤20 chunks for the cataloguer skill.**  Tell it 20
   books, say "save catalog", repeat.  Slower but doesn't need a
   local Python environment.

### Updating the reading log

After finishing a book:

> "I finished *Hyperion* — 5 stars."

The cataloguer queues the rate update to `/tmp/log_pending_updates.csv`.
If the book was on `/tmp/Reading_List.md`, it's removed same turn.  At
session end, the cataloguer surfaces the pending-updates file as a
download link.  On the next session start, triage seeds it back from
project knowledge and surfaces queued updates as a CSV-ready paste
block:

> "I have 3 pending rate updates from previous sessions.  Paste these
> rows into your `Reading_Log.csv`, save, re-upload to project
> knowledge, and say 'log refreshed' here — I'll clear the queue."

To refresh the whole log from Goodreads:

1. Export a fresh `Reading_Log.csv` from Goodreads.
2. Replace it in your project knowledge.
3. In chat: "log refreshed" — the librarian re-reads it and clears
   any pending queue.

### Refreshing comparable_books across the catalog

```bash
python3 catalogue.py --library Library.csv --sync-comparables
python3 catalogue.py --library Library.csv \
    --export-sqlite Library_Catalog.sqlite --emit-encoded
```

Re-upload `.encoded` to Drive.

## 11. Troubleshooting

### Skills don't trigger

Open Settings → Features → Skills.  Confirm all six show as
installed and enabled.  Re-upload from `dist/skills/` if any are
missing.  Confirm "Code execution and file creation" is on.

### Drive disconnects mid-session

The librarian's in-progress edits live in `/tmp/` (Profile.md,
Reading_List.md, build_state.json) and the sandbox SQLite — they
don't depend on Drive.  Reconnect via Settings → Connectors → Google
Drive → Reconnect.  Catalog changes only need Drive at session end
when you replace the file from the download link.

### Catalog file looks corrupted

> "The catalog file in your Drive looks corrupted."

Likely cause: interrupted upload or a stale `.encoded` from a schema
change.  Recovery:

```bash
python3 catalogue.py --library Library.csv \
    --export-sqlite Library_Catalog.sqlite --emit-encoded
```

Re-upload `Library_Catalog.sqlite.encoded` to Drive.  In chat:
`continue`.

### Build state can't be read

Likely cause: forgot to re-upload `build_state.json` to project
knowledge after the previous session surfaced it.  Recovery:

1. If you have the download from the prior session in your local
   downloads folder, re-upload it to project knowledge.
2. Otherwise the build is unrecoverable mid-stream — but
   `Reading_List.md` still has your committed picks (provided you
   re-uploaded it).  Tell the librarian "refine my list" to pick up
   from there.

### Pro plan usage limit cutoff mid-build

Anything you committed to `/tmp/Reading_List.md` and
`/tmp/Profile.md` during the cut-off session is gone unless the
session got far enough to surface those files via download links.
Recovery: open a new chat after the cooldown, triage will read
whatever was last re-uploaded to project knowledge.  In practice,
this means re-uploading early and often — say "save my files" any
time you want a checkpoint.

Catalog changes that hadn't reached the session-end download link
are also gone — re-state them in the next session.

### Multiple users on the same Pro account

Not supported.  Pro is per-user; project knowledge is shared per
project but uploads collide if two people are mutating the same
files.

## 12. Files reference

```
~/Library-Playground/                  # the user's clone
├── Library.csv                        # source of truth, you provide
├── Reading_Log.csv                    # you provide
├── Library_Catalog.json               # built by catalogue.py (deprecated post-build)
├── Library_Catalog.sqlite             # built by catalogue.py --export-sqlite (gitignored)
├── Library_Catalog.sqlite.encoded     # built by --emit-encoded (gitignored)
├── webhelper/                         # runtime helpers (bundled in skill zips)
├── artifacts/batch-picker.jsx         # picker artifact source
├── artifacts/profile.jsx              # profile artifact source
├── artifacts/reading-list.jsx         # reading-list artifact source
├── .claude.ai/skills/                 # skill source — each gets zipped + uploaded
├── catalogue.py                       # bulk cataloguer + SQLite/index export
├── librarian-query.py                 # CODE-side helper (unchanged on this branch)
├── tests/                             # round-trip parity tests
├── dist/skills/*.zip                  # build outputs (gitignored)
├── UX_DESIGN.md                       # design rationale for the port
└── SETUP.md                           # this file

Drive/Library-Playground/              # the user's claude.ai-side store (bare)
└── Library_Catalog.sqlite.encoded

claude.ai project knowledge            # carry-across-sessions store
├── Reading_Log.csv                    # reading history (upload as a file, not inline)
├── Profile.md (optional)              # taste profile, re-uploaded after each editing session
├── Reading_List.md (optional)         # TBR list, re-uploaded after each editing session
├── build_state.json (optional)        # in-progress build state, re-uploaded between sessions
└── log_pending_updates.csv (optional) # queued reading-log rate updates

Sandbox /tmp/                          # per-session working state
├── Library_Catalog.sqlite             # decoded from Drive at session start
├── Profile.md                         # seeded from project knowledge, edited in place
├── Reading_List.md                    # seeded from project knowledge, edited in place
├── build_state.json                   # build phase / goals / ledger
├── log_pending_updates.csv            # pending log queue
└── catalog_edits.log                  # per-session catalog change list

Artifacts                              # pure renderers — no persistence
├── batch-picker.jsx  — opt-in richer batch view
├── profile.jsx       — read-only Profile.md preview
└── reading-list.jsx  — read-only Reading_List.md preview
```
