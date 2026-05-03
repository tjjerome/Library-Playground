---
name: librarian-triage
description: >
  Routing skill for librarian-shaped openers on claude.ai chat.  Triggers when
  the reader asks for book recommendations, a reading list, taste matching,
  "what should I read next", "anything like X", "is X worth my time", uploads a
  reading log or library catalog, or wants to update their catalog.  Does NOT
  do the recommendation work itself — discovers project-knowledge files
  (Reading_Log.csv, optional Profile.md / Reading_List.md / build_state.json),
  copies them into /tmp for the session, pulls the catalog from Drive into the
  sandbox, runs freshness checks, asks refine-vs-fresh when a list exists, and
  hands off to one of librarian-quickref / librarian-build-setup /
  librarian-build-batches / librarian-build-finish / library-cataloguer.
---

# librarian-triage — entry-point router

You = the librarian's front desk.  Reader walks up with a book question;
you figure out what they need, set the table (catalog decoded, project
files discovered and copied to /tmp, freshness checked, existing
Profile / Reading_List honoured), and hand off.

Never do the recommendation work, the catalog write, or the batch
selection yourself.  Your job ends when the right downstream skill takes
over.

## Hard invariants

1. **Anti-jargon.**  Reader never sees "triage", "build state", "encoded
   catalog", or any internal term.  Translate at the chat layer.  See
   translation map in `.claude.ai/skills/librarian-build-batches/SKILL.md`.
2. **Existing Profile / Reading_List in project knowledge is honoured,
   not overwritten.**  When the reader has Profile.md / Reading_List.md
   uploaded, those seed `/tmp/Profile.md` and `/tmp/Reading_List.md` for
   the session.  Refine-vs-fresh prompt before any mutation when a
   non-empty Reading_List exists.
3. **Single-book queries do NOT hear about in-progress build state.**
   The resume offer fires only on ambiguous or build-shaped openers.

## Storage layout (read this once)

| Layer | Holds | Mutability |
|---|---|---|
| Drive | `Library_Catalog.sqlite.encoded` | Read-only from chat; cataloguer surfaces a download link at session end for manual replacement |
| Project knowledge | `Reading_Log.csv` (recommended as a plain file, not a `<documents>` injection — see SETUP.md), optional `Profile.md`, `Reading_List.md`, `build_state.json` | Reader re-uploads at the end of any session that changed them |
| Sandbox `/tmp/` (per session) | `Library_Catalog.sqlite`, `Profile.md`, `Reading_List.md`, `build_state.json`, `log_pending_updates.csv` | Mutated freely during session; surfaced via `present_files` at session end |
| `picker` / `profile` / `reading-list` artifacts | Read-only renderers — content passed via `seed` prop | None — no `window.storage` |

The /tmp files are the **live working surfaces** during a session.
Project files are the **carry-across-sessions** layer; the reader
re-uploads anything that changed when the session ends (the
build-finish / cataloguer skills present them via `present_files`).
The artifacts are pure renderers — they never persist.

## Project-file discovery

Look for each by name in the canonical project mount path:

- `/mnt/project/Reading_Log.csv` — reader's history.  Required for full
  builds and series-continuation queries.
- `/mnt/project/Profile.md` (optional) — seed taste profile.
- `/mnt/project/Reading_List.md` (optional) — existing TBR pool.
- `/mnt/project/build_state.json` (optional) — in-progress build resume
  pointer from a previous session.
- `/mnt/project/log_pending_updates.csv` (optional) — queued reading-log
  rate updates from previous sessions, not yet merged into the log.

Fallback search if not at the canonical path:
`find /mnt -maxdepth 4 -name "<file>" 2>/dev/null`.

Bind discovered paths to local variables (`PROJECT_LOG`,
`PROJECT_PROFILE`, `PROJECT_LIST`, `PROJECT_STATE`, `PROJECT_LOG_QUEUE`).
Use throughout the session.

### Copy seeds into /tmp working files

Once discovered, copy each into /tmp:

```bash
[ -f "$PROJECT_PROFILE"  ] && cp "$PROJECT_PROFILE"  /tmp/Profile.md
[ -f "$PROJECT_LIST"     ] && cp "$PROJECT_LIST"     /tmp/Reading_List.md
[ -f "$PROJECT_STATE"    ] && cp "$PROJECT_STATE"    /tmp/build_state.json
[ -f "$PROJECT_LOG_QUEUE" ] && cp "$PROJECT_LOG_QUEUE" /tmp/log_pending_updates.csv
```

Missing seed → create an empty stub:

```bash
[ ! -f /tmp/Profile.md ]      && printf '# Reader Profile\n\n_Living memory._\n' > /tmp/Profile.md
[ ! -f /tmp/Reading_List.md ] && printf '# Reading List\n' > /tmp/Reading_List.md
```

These /tmp files are the source of truth for the session.  Build /
quickref / cataloguer skills read and edit them in place; build-finish
and cataloguer surface them via `present_files` at session end so the
reader can download the updated copy and replace it in project
knowledge.

## Drive catalog discovery

Discovery order, fastest to slowest:

1. **Project-instructions injection.**  If the project-level system
   prompt declares `DRIVE_CATALOG_FILE_ID: <id>`, fetch that file
   directly via the Drive connector — no folder/name search.  This is
   the recommended setup; SETUP.md walks readers through pasting their
   Drive file ID into project instructions.
2. **Folder + filename search.**  Look for
   `Library-Playground/Library_Catalog.sqlite.encoded`.
3. **Custom folder name.**  Ask: "What did you name your library
   folder in Drive? (default: Library-Playground)"  Search inside.
4. **Reader hasn't done first-run setup** if all three above fail —
   point them to `SETUP.md`.

## Catalog load (one-shot per session)

Once the catalog file is located, fetch the encoded form via the Drive
connector and decode into the sandbox:

```bash
# 1. Drive connector: read file by ID; write raw bytes to
#    /tmp/Library_Catalog.sqlite.encoded.
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
download link the reader uses to manually replace the Drive file.
Never re-fetch the encoded catalog mid-session — that overwrites
in-session edits.

## Reading_Log freshness check

Once `PROJECT_LOG` is found:

```python
import csv, datetime
log_path = PROJECT_LOG
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
> knowledge.  Or we can keep going — newer reads just won't influence
> picks."

`AskUserQuestion`: `Refresh first (Recommended)` / `Keep going with
current log` / `Other`.

If `/tmp/log_pending_updates.csv` exists from a prior session, count
its rows and surface:

> "I have <N> pending rate updates from previous chats that haven't
> made it into your reading log yet.  Want me to show them so you can
> paste into your CSV before re-uploading?"

## Profile freshness check

Read `/tmp/Profile.md` (the seeded copy).  Look at the project file's
mtime via `stat $PROJECT_PROFILE` for the freshness signal.

If the file's mtime is more than **10 months ago** OR the content is
the unmodified seed header only, treat the profile as stale.  Don't
refuse to use it — surface to the reader and let
`librarian-build-setup` decide (refine vs fresh interview).

## Reading_List discovery + refine-vs-fresh

Read `/tmp/Reading_List.md`.  Determine "list has real content" — count
`|` table rows or `-` bullet items beyond the seed header.

If the opener is build-shaped AND the list has real content, ask:

```
Q: "I found an existing reading list — <N> books in <M> sections.
   Want to refine that, or build a new one from scratch?"
Options:
  - "Refine the existing list (Recommended)"
  - "Start fresh — archive the existing list"
  - "Other"
```

Routes:
- "Refine" → `librarian-build-batches` directly with `/tmp/Reading_List.md`
  in place.  Skips Phase 0 / interview / goals (already established by
  the existing list).
- "Start fresh" → archive the seed (`mv /tmp/Reading_List.md
  /tmp/Reading_List.md.<ISO>`), reset `/tmp/Reading_List.md` to the
  empty seed, route to `librarian-build-setup`.

## Routing

Match opener shape, then ask one disambiguating `AskUserQuestion` only
when shape is genuinely unclear.  `AskUserQuestion` is deferred — load
once at session start with
`ToolSearch(query="select:AskUserQuestion", max_results=1)`.

| Opener shape | Route to |
|---|---|
| "Anything like X?" / "Is X worth my time?" / "What do you know about X?" | librarian-quickref |
| "Build me a reading list" / "what should I read next year" / opener with no in-progress state | librarian-build-setup (or refine-flow when existing Reading_List has content) |
| "Continue the build" / "let's do more batches" / opener while `/tmp/build_state.json` exists with `current_phase` < complete | librarian-build-batches (or -build-finish if Phase ≥ 3) |
| "Add this book" / "fix this entry" / "I bought X" / "save the catalog" | library-cataloguer |
| Genuinely ambiguous | one `AskUserQuestion` with the four routes above as options |

### Resume-offer rule

If `/tmp/build_state.json` exists AND its `current_phase` is not
`"complete"` AND the opener is build-shaped or ambiguous, surface a
resume offer:

> "You're <N> books into the build I started with you on
> <human-readable date> — <short summary, e.g. 'three batches into the
> horror genre'>. Want to pick up where we left off, or start
> something new?"

Options: `Resume the build (Recommended)` / `Start fresh` / `Single-book
question` / `Other`.

Do NOT fire the resume offer for a clean single-book query.

## Documented phrase set

Phrases the reader can type at any time and triage will recognize.
Document in `SETUP.md`:

| Phrase | What triage does |
|---|---|
| `where are we` | Read `/tmp/build_state.json`; render a human-readable summary (current phase, books in pool, indie/classic floors, last batch genre). |
| `save catalog` | Hand off to library-cataloguer to re-encode the in-sandbox SQLite and present a download link.  Reader manually replaces their Drive file. |
| `save my files` | Hand off to library-cataloguer's session-end flow to present `Reading_List.md`, `Profile.md`, `build_state.json`, and any pending log updates as downloads. |
| `continue` | After a recovery prompt, resume the prior flow. |
| `start fresh` | Archive `/tmp/Reading_List.md` and `/tmp/build_state.json`; preserve Profile.md; route to build-setup. |
| `show pending log updates` | Print rows from `/tmp/log_pending_updates.csv` so the reader can merge into Reading_Log.csv and re-upload. |

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
