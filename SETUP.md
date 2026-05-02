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

## Required: publish the picker artifact

This is the one prerequisite easy to miss.  The librarian uses a
React artifact (the "library picker") for batch selections.  The
picker also stores all in-progress build state — phase, goals,
ledger, indie/classic floor counters.  Persistence works **only on
published artifacts**, and unpublishing the artifact **permanently
deletes the storage**.  Setup step 4 below walks through the publish
flow.  Once published, leave it published.

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

## 5. Export to SQLite + the encoded form

One command, both outputs:

```bash
python3 catalogue.py --library Library.csv \
    --export-sqlite Library_Catalog.sqlite --emit-encoded
```

Outputs:

- `Library_Catalog.sqlite` — the queryable form for local diagnostics
  (the librarian uses this in-sandbox).
- `Library_Catalog.sqlite.encoded` — gzip+base64 wrapped text file
  (~1-1.5MB per 5,000 books).  This is the file you upload to Drive,
  because the Drive connector reads text but not binary.

The first line of `.encoded` is `# library-playground-catalog v1
gzip+b64`.  Skills detect format drift from this header.

You can verify the export round-trips cleanly:

```bash
python3 tests/sqlite_roundtrip.py
python3 tests/encoded_roundtrip.py
```

Both should report `OK`.

## 6. Set up Google Drive

In Google Drive, create a folder.  The default name is
`Library-Playground` (the librarian-triage skill uses this name
unless you override it on first run).

Upload these four files into the folder:

```
Library-Playground/
├── Library_Catalog.sqlite.encoded   # from §5
├── Reading_Log.csv                   # from §3
├── Profile.md                        # empty file, the librarian fills it
└── Reading_List.md                   # empty file, the librarian fills it
```

Two empty placeholders are easiest to create with `touch`:

```bash
touch Profile.md Reading_List.md
```

…then drag-and-drop into Drive.

In claude.ai, go to **Settings → Connectors**, find Google Drive,
click **Connect**, and grant access to the folder.  When you start a
session, you'll add the folder to the chat via the paperclip icon
or the "Add Content" button.

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

## 8. Publish the picker artifact

This is the publish-once-leave-published step.  Without it, build
sessions can't store state.

1. Open a fresh chat in claude.ai.
2. With the Drive folder added to the chat, type:

   > "Create the library picker."

3. The `librarian-build-batches` skill renders the picker artifact
   with sample books.  Click the **Publish** button on the artifact
   panel.
4. Copy the resulting URL (looks like
   `https://claude.ai/public/artifacts/<uuid>`).
5. Paste the URL back into the chat.  The triage skill validates,
   does a tiny `set/get` round-trip to confirm storage works, and
   writes `.config.json` into your Drive folder.

After this step, your Drive folder also has:

```
Library-Playground/
├── ...the four files from §6...
└── .config.json                      # picker URL + folder name
```

> **If you ever unpublish the picker:** all in-progress build state
> is permanently lost.  The committed picks still live in
> `Reading_List.md`, but the conversation context (current phase,
> shown-ledger, rejection-cluster counters) is gone.  Don't unpublish.

## 9. Start your first session

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

## 10. Reader cheat sheet

Phrases the librarian recognises at any time.  You don't need to
memorise them — the librarian usually offers the right next move
on its own — but they're useful when you want to bypass the
small talk:

| Phrase | What it does |
|---|---|
| `where are we` | Triage replays your build state ("23 books in your list, indie at 4 of 15") |
| `flush now` | Force a Drive flush of Profile.md + Reading_List.md (auto-fires on every edit too) |
| `save catalog` | Cataloguer flushes in-session catalog edits to Drive (gzip+b64 re-encode) |
| `continue` | After a recovery prompt, resume the prior flow |
| `start fresh` | Discard build state in window.storage; preserve Profile.md + Reading_List.md in Drive |

## 11. Maintenance

### Adding a few books (≤20)

Tell the cataloguer in chat:

> "I just bought *The Lesser Dead* by Christopher Buehlman."

The cataloguer confirms, fills catalog fields, and writes to the
in-sandbox SQLite.  At session end, say "save catalog" and it
re-encodes + flushes back to Drive.

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

The cataloguer appends to `Reading_Log.csv` and flushes to Drive
same turn.  If the book was on `Reading_List.md`, it's removed.

If you'd rather refresh the whole log from Goodreads:

1. Export a fresh `Reading_Log.csv` from Goodreads.
2. Replace `Library-Playground/Reading_Log.csv` in Drive.
3. In chat: "log refreshed" — the librarian re-reads it.

### Refreshing comparable_books across the catalog

```bash
python3 catalogue.py --library Library.csv --sync-comparables
python3 catalogue.py --library Library.csv \
    --export-sqlite Library_Catalog.sqlite --emit-encoded
```

Re-upload `.encoded` to Drive.

## 12. Troubleshooting

### Skills don't trigger

Open Settings → Features → Skills.  Confirm all six show as
installed and enabled.  Re-upload from `dist/skills/` if any are
missing.  Confirm "Code execution and file creation" is on.

### Drive disconnects mid-session

The librarian's in-progress edits are still in window.storage; they
flush back to Drive once you reconnect.  Reconnect via Settings →
Connectors → Google Drive → Reconnect, then say `flush now`.

### Catalog file looks corrupted

> "The catalog file in your Drive looks corrupted."

Likely cause: an interrupted upload or a stale `.encoded` from a
schema change.  Recovery:

```bash
python3 catalogue.py --library Library.csv \
    --export-sqlite Library_Catalog.sqlite --emit-encoded
```

Re-upload `Library_Catalog.sqlite.encoded` to Drive.  In chat: `continue`.

### Build state can't be read / window.storage is empty

Likely cause: the picker artifact was unpublished.  Recovery:

1. Open the picker URL.
2. Click **Publish** again.
3. Return to the chat and say `continue`.

In-progress build state from before the unpublish is gone, but
Reading_List.md in Drive still has your committed picks — the
librarian re-orients from there.

### I forgot the picker URL

The picker URL lives in `Library-Playground/.config.json` in your
Drive folder.  Open it in a text view (Google Drive supports this
for `.json`).

### Pro plan usage limit cutoff mid-build

Your committed picks and profile updates are safe — both files are
flushed to Drive on every edit.  Wait out the cooldown, open a new
chat, and triage will offer to resume.  The picker artifact's state
survives the reset.

### Multiple users on the same Pro account

Not supported.  Pro is per-user; shared accounts get shared
window.storage on a single artifact, which collides build state.

## 13. Files reference

```
~/Library-Playground/                 # the user's clone
├── Library.csv                       # source of truth, you provide
├── Reading_Log.csv                   # you provide
├── Library_Catalog.json              # built by catalogue.py (deprecated post-build)
├── Library_Catalog.sqlite            # built by catalogue.py --export-sqlite (gitignored)
├── Library_Catalog.sqlite.encoded    # built by --emit-encoded (gitignored)
├── webhelper/                        # runtime helpers (bundled in skill zips)
├── artifacts/batch-picker.jsx        # the published picker artifact
├── .claude.ai/skills/                # skill source — each gets zipped + uploaded
├── catalogue.py                      # bulk cataloguer + SQLite export
├── librarian-query.py                # CODE-side helper (unchanged on this branch)
├── tests/                            # round-trip parity tests
├── dist/skills/*.zip                 # build outputs (gitignored)
├── UX_DESIGN.md                      # design rationale for the port
└── SETUP.md                          # this file

Drive/Library-Playground/              # the user's claude.ai-side store
├── Library_Catalog.sqlite.encoded
├── Reading_Log.csv
├── Profile.md
├── Reading_List.md
├── archive/                          # auto-created snapshots before flushes
└── .config.json                      # picker URL + folder name
```
