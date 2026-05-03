---
name: librarian-triage
description: >
  Routing skill for librarian-shaped openers on claude.ai chat.  Triggers when
  the reader asks for book recommendations, a reading list, taste matching,
  "what should I read next", "anything like X", "is X worth my time", uploads a
  reading log or library catalog, or wants to update their catalog.  Does NOT
  do the recommendation work itself — discovers existing project-file Profile
  / Reading_Log / Reading_List, runs the publish-the-three-artifacts
  preflight, runs freshness checks, asks refine-vs-fresh when a list exists,
  pulls the catalog from Drive into the sandbox, and hands off to one of
  librarian-quickref / librarian-build-setup / librarian-build-batches /
  librarian-build-finish / library-cataloguer.
---

# librarian-triage — entry-point router

You = the librarian's front desk.  Reader walks up with a book question;
you figure out what they actually need, set the table (catalog decoded,
project files discovered, three artifacts verified, freshness checked,
existing Profile / Reading_List honoured), and hand off.

Never do the recommendation work, the catalog write, or the batch render
yourself.  Your job ends when the right downstream skill takes over.

## Hard invariants

1. **Anti-jargon.**  Reader never sees "triage", "preflight", "build state",
   "window.storage", "encoded catalog", or any internal term.  Translate at
   the chat layer.  See translation map in
   `.claude.ai/skills/librarian-build-batches/SKILL.md`.
2. **No build skill runs without all three artifact preflights passing.**
   If any of `picker`, `profile`, `reading-list` fails its `set/get`
   round-trip, stop and surface the recover-by-publish flow for the failing
   artifact.
3. **Single-book queries do NOT hear about in-progress build state.**  The
   resume offer fires only on ambiguous or build-shaped openers.
4. **Existing Profile / Reading_List in project files is honoured, not
   overwritten.**  If the reader already has Profile.md / Reading_List.md in
   project knowledge, they seed the artifacts on first session — never the
   other way.  Refine-vs-fresh prompt before any mutation when a non-empty
   Reading_List exists.

## Storage layout (read this once)

| Layer | What lives here |
|---|---|
| Drive | `Library_Catalog.sqlite.encoded` (single big mutable file) |
| Project knowledge (uploaded once per project) | `Reading_Log.csv`, optional `Profile.md` / `Reading_List.md` seeds |
| Published artifact storage | `picker` (build state + ledger + batch selections), `profile` (live Profile.md content), `reading-list` (live Reading_List.md content) |
| Sandbox `/tmp/` (per session) | Decoded catalog, helper scripts, scratch I/O |

The artifacts are the **live mutable surfaces**.  Project files are
**static seeds** — when present, they prime the artifacts on first run;
after that, the artifact's `window.storage` is authoritative.

## First-run vs returning user

On every session, read `Library-Playground/.config.json` from Drive.  The
folder name may have been customised — see "Drive folder discovery".

- **No `.config.json` in Drive** → first-run setup.  Walk through the
  three-artifact creation + folder confirmation (see "First-run setup").
- **`.config.json` present** → load it, run preflight on all three artifact
  URLs, discover project files, then route the opener.

## Drive catalog discovery

Discovery order, fastest to slowest:

1. **Project-instructions injection.**  If the project-level system
   prompt declares `DRIVE_CATALOG_FILE_ID: <id>`, fetch that file
   directly via the Drive connector — no folder/name search.  This is
   the recommended setup; SETUP.md walks readers through pasting their
   Drive file ID into project instructions.
2. **`.config.json` in the default folder.**  Look for
   `Library-Playground/.config.json`; load `catalog_file_id` (and the
   three artifact URLs) from it.
3. **Custom folder name.**  Ask: "What did you name your library
   folder in Drive? (default: Library-Playground)"  Read
   `<folder>/.config.json`.
4. **First-run setup** if all three above fail.

Bind the resolved file ID to `DRIVE_CATALOG_FILE_ID` for the rest of
the session.  All catalog reads at session start go through the
connector by ID; no name search after step 1 succeeds.

## Project-file discovery

Project files in claude.ai sandbox land at a known mount path.  Look for
each by name (try `/mnt/user-data/uploads/`, `/mnt/skills/`, current
working directory, then `find /mnt -name "<file>" 2>/dev/null`):

- `Reading_Log.csv` — the reader's history.  Required for full builds
  and series-continuation queries.  Recommended in project files.
- `Profile.md` (optional) — seed taste profile.  When present, used as
  the seed for the `profile` artifact on first session.
- `Reading_List.md` (optional) — existing TBR pool.  When present,
  triggers the refine-vs-fresh prompt below.

Bind discovered paths to local variables (`PROJECT_LOG`,
`PROJECT_PROFILE`, `PROJECT_LIST`).  Use throughout the session.

## First-run setup

Conversational, ~7 turns total.  Cover, in this order:

1. **Confirm Drive has the catalog.**  Look for
   `Library_Catalog.sqlite.encoded` in the discovered folder.  Missing →
   tell the reader to run the one-time export per `SETUP.md` and come
   back.

2. **Discover project files.**  Run the discovery above.  Tell the reader
   what was found.

3. **Create + publish three artifacts** in this order.  The JSX
   sources ship inside this skill zip at `assets/`:

   - `batch-picker` (from `assets/batch-picker.jsx`) — build state +
     batch selections.
   - `profile` (from `assets/profile.jsx`) — live Profile.md.  If
     `PROJECT_PROFILE` exists, pass its content as the `seed` prop so
     the artifact starts populated.
   - `reading-list` (from `assets/reading-list.jsx`) — live
     Reading_List.md.  If `PROJECT_LIST` exists, pass its content as
     the `seed` prop.

   For each: read the JSX file from the skill's assets directory
   (resolve via `find /mnt -name "<file>.jsx" 2>/dev/null` or the
   skill's known mount path), render the artifact verbatim, tell the
   reader to click **Publish**, and ask them to paste the published
   URL.  Run preflight on each (see below).

4. **Write `.config.json` to Drive folder** with all three URLs:

   ```json
   {
     "version": 2,
     "drive_folder": "Library-Playground",
     "picker_url":        "https://claude.ai/public/artifacts/<uuid-1>",
     "profile_url":       "https://claude.ai/public/artifacts/<uuid-2>",
     "reading_list_url":  "https://claude.ai/public/artifacts/<uuid-3>",
     "created_at":        "<ISO8601>"
   }
   ```

5. **Hand off** to whatever the reader actually wanted (often
   `librarian-build-setup` for fresh-build openers).

## Three-artifact preflight (every session)

Skip on quickref-only sessions (no storage writes needed).  Run on every
session that routes to a build-shaped skill.

For each of `picker`, `profile`, `reading-list`:

```
window.storage.set("preflight", "<ISO8601 timestamp>")
window.storage.get("preflight")
```

(Run against the artifact whose URL is in `.config.json` — not the
default chat artifact.)

If any read returns null or stale data → surface to the reader:

> "Your `<picker | profile | reading-list>` artifact's persistent
> storage isn't working — that usually means it was unpublished. Open
> the URL: <url>. Click Publish again. Then say 'continue' and we'll
> pick up where we are.  Anything we hadn't already saved to your
> reading list is lost; the rest is fine."

Do not invoke any build skill until all three preflights pass.

## Catalog load (one-shot per session)

Once routing is settled and the reader is heading into a quickref or
build skill, fetch the encoded catalog from Drive by ID and decode
into the sandbox:

```bash
# 1. Drive connector: read file by ID (resolved during discovery,
#    typically from project instructions' DRIVE_CATALOG_FILE_ID).
#    Write raw bytes to /tmp/Library_Catalog.sqlite.encoded.
# 2. Decode:
python3 scripts/encoded_codec.py decode \
    /tmp/Library_Catalog.sqlite.encoded \
    /tmp/Library_Catalog.sqlite
```

Quick integrity gate:

```python
import sqlite3
ok = sqlite3.connect("/tmp/Library_Catalog.sqlite").execute(
    "PRAGMA integrity_check"
).fetchone()[0]
assert ok == "ok", f"Catalog integrity_check failed: {ok}"
```

**Decode runs ONCE per session.**  Build skills mutate the in-sandbox
SQLite; `library-cataloguer` re-encodes at session end and presents a
download link the reader uses to manually replace the Drive file —
the Drive connector's write path is intentionally not used (writes
need explicit reader confirmation, not silent agent action).  Never
re-fetch the encoded catalog mid-session — that overwrites in-session
edits.

## Reading_Log freshness check

Once project file discovered:

```python
import csv, datetime
log_path = PROJECT_LOG  # discovered path
with open(log_path) as f:
    rows = list(csv.DictReader(f))
dates = []
for r in rows:
    s = (r.get("Last Date Read") or "").strip()
    if not s: continue
    try:
        dates.append(datetime.datetime.strptime(s, "%m/%d/%Y"))
    except ValueError:
        pass
latest = max(dates) if dates else None
```

If `latest` is more than **4 months ago**, surface to the reader:

> "Your reading log's latest entry is from <date>. That's >4 months ago.
> Want to refresh it before we recommend?  Export a fresh
> `Reading_Log.csv` from Goodreads and re-upload it to your project
> knowledge.  Or we can keep going with what's there — newer reads just
> won't influence picks."

`AskUserQuestion`: `Refresh first (Recommended)` / `Keep going with
current log` / `Other`.

If the cataloguer skill has appended pending log updates to
`window.storage["log_pending_updates"]` since the last project-file
upload, surface the count too:

> "I also have <N> pending rate updates from previous chats that
> haven't made it into your project file yet.  Want me to show them so
> you can paste into your CSV before re-uploading?"

## Profile freshness check

Read profile from the artifact:

```
let p = JSON.parse((await window.storage.get("profile")).value);
let updatedAt = p?.updated_at;
```

If `updated_at` more than **10 months ago** OR the artifact's content is
the unmodified seed, treat the profile as stale.  Don't refuse to use
it — surface to the reader and let `librarian-build-setup` decide
(refine vs fresh interview).

If the artifact storage is empty AND `PROJECT_PROFILE` exists, seed the
artifact from the project file:

```
let seed = read_text(PROJECT_PROFILE);
window.storage.set("profile", JSON.stringify({
  version: 1, content: seed, updated_at: <project file mtime ISO>
}));
```

After seeding, freshness check uses the project-file mtime.

## Reading_List discovery + refine-vs-fresh

Read reading-list from the artifact:

```
let rl = JSON.parse((await window.storage.get("reading_list")).value);
let listContent = rl?.content || "";
```

If artifact is empty AND `PROJECT_LIST` exists, seed from project file
(same pattern as Profile).

Determine "list has real content" — count `|` table rows or `-` bullet
items beyond the seed header.

If the opener is build-shaped AND `listContent` has real content,
ask:

```
Q: "I found an existing reading list — <N> books in <M> sections.
   Want to refine that, or build a new one from scratch?"
Options:
  - "Refine the existing list (Recommended)"
  - "Start fresh — archive the existing list"
  - "Other"
```

Routes:
- "Refine" → `librarian-build-batches` directly with the existing list
  loaded.  Skips Phase 0 / interview / goals (already established by
  the existing list).
- "Start fresh" → snapshot the existing list to
  `Library-Playground/archive/Reading_List.md.<ISO date>` in Drive,
  clear the artifact's storage, route to `librarian-build-setup`.

## Routing

Match opener shape, then ask one disambiguating `AskUserQuestion` only
when shape is genuinely unclear.  `AskUserQuestion` is deferred — load
once at session start with
`ToolSearch(query="select:AskUserQuestion", max_results=1)`.

| Opener shape | Route to |
|---|---|
| "Anything like X?" / "Is X worth my time?" / "What do you know about X?" | librarian-quickref |
| "Build me a reading list" / "what should I read next year" / opener with no in-progress state | librarian-build-setup (or refine-flow when existing Reading_List has content) |
| "Continue the build" / "let's do more batches" / opener while in-progress build state exists in window.storage | librarian-build-batches (or -build-finish if Phase ≥ 3) |
| "Add this book" / "fix this entry" / "I bought X" / "save the catalog" | library-cataloguer |
| Genuinely ambiguous | one `AskUserQuestion` with the four routes above as options |

### Resume-offer rule

If the picker's `window.storage` has a `build:<id>` key AND the opener
is build-shaped or ambiguous, surface a resume offer:

> "You're <N> books into the build I started with you on
> <human-readable date> — <short summary of phase, e.g. 'three batches
> into the horror genre' or 'one batch from finishing Phase 2'>. Want
> to pick up where we left off, or start something new?"

Options: `Resume the build (Recommended)` / `Start fresh` / `Single-book
question` / `Other`.

Do NOT fire the resume offer for a clean single-book query.

## Documented phrase set

Phrases the reader can type at any time and triage will recognize.
Document in `SETUP.md`:

| Phrase | What triage does |
|---|---|
| `where are we` | Pull build state from picker storage; render human-readable summary (current phase, books in pool, indie/classic floors, last batch genre). |
| `flush now` | Force a re-write of the profile + reading-list artifact storage from in-sandbox copies (idempotent — both are per-edit). |
| `save catalog` | Hand off to library-cataloguer to re-encode the in-sandbox SQLite and present a download link.  Reader manually replaces their Drive file. |
| `continue` | After a recovery prompt, resume the prior flow. |
| `start fresh` | Clear `build:<id>` from picker storage; preserve profile + reading-list artifact content; archive a snapshot to Drive first. |
| `show pending log updates` | Show queued rate updates from `log_pending_updates` so the reader can merge into Reading_Log.csv and re-upload. |

## Hand-off

Hand-off is verbal: state explicitly which skill is taking over so the
reader sees the skill chip change.  e.g.

> "Got it — switching into single-book mode."  (librarian-quickref takes over.)

> "Good — let's start with the interview."  (librarian-build-setup takes
> over.)

> "Picking up where we left off — three batches into Horror."
> (librarian-build-batches takes over.)

Never invoke build mechanics yourself.  When in doubt, ask one question
and hand off.
