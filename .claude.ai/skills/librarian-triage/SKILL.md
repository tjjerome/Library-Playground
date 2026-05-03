---
name: librarian-triage
description: >
  Route skill for reader book questions on claude.ai chat. Triggers: recommend, reading list, taste match, "what should I read next", "anything like X", "is X worth my time", log upload, catalog update. No recommendation work — discover project files (Reading_Log.csv, optional Profile.md / Reading_List.md / build_state.json), copy to /tmp, pull catalog from Drive, freshness check, refine-vs-fresh if list exists, hand off to librarian-quickref / librarian-build-setup / librarian-build-batches / librarian-build-finish / library-cataloguer.
---

# librarian-triage — entry-point router

You = front desk. Reader ask book question; figure out need, set table (catalog decoded, project files to /tmp, freshness checked, existing Profile / Reading_List honoured), hand off.

Never do recommendation, catalog write, batch selection. Job end when downstream skill take over.

## Hard invariants

1. **Anti-jargon.** Reader never see "triage", "build state", "encoded catalog", internal terms. Translate at chat layer. See map in `.claude.ai/skills/librarian-build-batches/SKILL.md`.
2. **Existing Profile / Reading_List in project knowledge is honoured, not overwritten.** Reader has Profile.md / Reading_List.md → seed `/tmp/Profile.md` and `/tmp/Reading_List.md`. Refine-vs-fresh prompt before mutation if Reading_List non-empty.
3. **Single-book queries do NOT hear about in-progress build state.** Resume offer fire only on ambiguous or build-shaped openers.

## Storage layout (read this once)

| Layer | Holds | Mutability |
|---|---|---|
| Drive | `Library_Catalog.sqlite.encoded` | Read-only from chat; cataloguer surface download link at end for manual replace |
| Project knowledge | `Reading_Log.csv` (plain file, not `<documents>` injection — see SETUP.md), optional `Profile.md`, `Reading_List.md`, `build_state.json` | Reader re-upload at end of changed sessions |
| Sandbox `/tmp/` (per session) | `Library_Catalog.sqlite`, `Profile.md`, `Reading_List.md`, `build_state.json`, `log_pending_updates.csv` | Mutated freely during session; surfaced via `present_files` at session end |
| `picker` / `profile` / `reading-list` artifacts | Read-only renderers — content passed via `seed` prop | None — no `window.storage` |

/tmp files = live working surface. Project files = carry-across-sessions; reader re-upload changed files at end (build-finish / cataloguer present via `present_files`). Artifacts = pure renderers, never persist.

## Project-file discovery

Look by name at canonical path:

- `/mnt/project/Reading_Log.csv` — reader history. Need for full builds, series queries.
- `/mnt/project/Profile.md` (optional) — seed taste profile.
- `/mnt/project/Reading_List.md` (optional) — existing TBR pool.
- `/mnt/project/build_state.json` (optional) — in-progress build resume from prior session.
- `/mnt/project/log_pending_updates.csv` (optional) — queued log rate updates from prior sessions, not yet merged.

Fallback if not at canonical path:
`find /mnt -maxdepth 4 -name "<file>" 2>/dev/null`.

Bind to local vars (`PROJECT_LOG`, `PROJECT_PROFILE`, `PROJECT_LIST`, `PROJECT_STATE`, `PROJECT_LOG_QUEUE`). Use throughout session.

### Copy seeds into /tmp working files

Discovered → copy to /tmp:

```bash
[ -f "$PROJECT_PROFILE"  ] && cp "$PROJECT_PROFILE"  /tmp/Profile.md
[ -f "$PROJECT_LIST"     ] && cp "$PROJECT_LIST"     /tmp/Reading_List.md
[ -f "$PROJECT_STATE"    ] && cp "$PROJECT_STATE"    /tmp/build_state.json
[ -f "$PROJECT_LOG_QUEUE" ] && cp "$PROJECT_LOG_QUEUE" /tmp/log_pending_updates.csv
```

Missing seed → create empty stub:

```bash
[ ! -f /tmp/Profile.md ]      && printf '# Reader Profile\n\n_Living memory._\n' > /tmp/Profile.md
[ ! -f /tmp/Reading_List.md ] && printf '# Reading List\n' > /tmp/Reading_List.md
```

/tmp files = session truth. Build / quickref / cataloguer read/edit in place; build-finish and cataloguer surface via `present_files` at end for reader download + replace in project knowledge.

### Capture session-start mtimes

After seeding /tmp files, record the timestamp so cataloguer's session-end surface can tell which files actually changed:

```python
import json, os, time
SESSION_START = time.time()
# Stash for later skills to read.
with open("/tmp/.session_start.json", "w") as f:
    json.dump({"started_at": SESSION_START}, f)
```

Cataloguer's session-end flow reads this and only surfaces files whose mtime exceeds it.

## Drive catalog discovery

Discovery order, fastest to slowest:

1. **Project-instructions injection.** System prompt has `DRIVE_CATALOG_FILE_ID: <id>` → fetch direct via Drive connector, no search. Recommended; SETUP.md walks reader through pasting file ID.
2. **Folder + filename search.** Look for `Library-Playground/Library_Catalog.sqlite.encoded`.
3. **Custom folder name.** Ask reader for folder name (default: Library-Playground). Search inside.
4. **Reader hasn't done first-run setup** if all three fail — point to `SETUP.md`.

## Catalog load (one-shot per session)

Catalog found → fetch encoded via Drive connector, decode to sandbox:

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

**Decode ONCE per session.** Build skills mutate in-sandbox SQLite; `library-cataloguer` re-encodes at end, presents download link. Never re-fetch mid-session — overwrites in-session edits.

## Reading_Log freshness check

Once `PROJECT_LOG` found:

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

If `latest` > 4 months ago, tell reader:

> "Your reading log's latest entry is from <date>. That's >4 months ago.
> Want to refresh it before we recommend?  Export a fresh
> `Reading_Log.csv` from Goodreads and re-upload it to your project
> knowledge.  Or we can keep going — newer reads just won't influence
> picks."

`AskUserQuestion`: `Refresh first (Recommended)` / `Keep going with current log` / `Other`.

If `/tmp/log_pending_updates.csv` exists from prior session, count rows and tell reader:

> "I have <N> pending rate updates from previous chats that haven't
> made it into your reading log yet.  Want me to show them so you can
> paste into your CSV before re-uploading?"

## Profile freshness check

Read `/tmp/Profile.md`. Check mtime via `stat $PROJECT_PROFILE`.

mtime > 10 months ago OR content = unmodified seed → stale. Don't refuse — surface to reader, let `librarian-build-setup` decide (refine vs fresh).

## Reading_List discovery + refine-vs-fresh

Read `/tmp/Reading_List.md`. Count `|` rows or `-` items beyond seed header to check real content.

If opener is build-shaped AND list has real content, ask:

```
Q: "I found an existing reading list — <N> books in <M> sections.
   Want to refine that, or build a new one from scratch?"
Options:
  - "Refine the existing list (Recommended)"
  - "Start fresh — archive the existing list"
  - "Other"
```

Routes:
- "Refine" → `librarian-build-batches` with `/tmp/Reading_List.md` in place. Skip Phase 0 / interview / goals (already in list).
- "Start fresh" → archive seed (`mv /tmp/Reading_List.md /tmp/Reading_List.md.<ISO>`), reset to empty seed, route to `librarian-build-setup`.

## Routing

Match opener shape, ask `AskUserQuestion` only when genuinely unclear. Deferred — load once at session start with `ToolSearch(query="select:AskUserQuestion", max_results=1)`.

| Opener shape | Route to |
|---|---|
| "Anything like X?" / "Is X worth my time?" / "What do you know about X?" | librarian-quickref |
| "Build me a reading list" / "what should I read next year" / opener with no in-progress state | librarian-build-setup (or refine-flow when existing Reading_List has content) |
| "Continue the build" / "let's do more batches" / opener while `/tmp/build_state.json` exists with `current_phase` < complete | librarian-build-batches (or -build-finish if Phase ≥ 3) |
| "Add this book" / "fix this entry" / "I bought X" / "save the catalog" | library-cataloguer |
| Genuinely ambiguous | one `AskUserQuestion` with the four routes above as options |

### Resume-offer rule

If `/tmp/build_state.json` exists AND `current_phase` ≠ `"complete"` AND opener is build-shaped or ambiguous → surface resume offer:

> "You're <N> books into the build I started with you on
> <human-readable date> — <short summary, e.g. 'three batches into the
> horror genre'>. Want to pick up where we left off, or start
> something new?"

Options: `Resume the build (Recommended)` / `Start fresh` / `Single-book question` / `Other`.

Do NOT fire the resume offer for a clean single-book query.

## Documented phrase set

Phrases reader can type. Document in `SETUP.md`:

| Phrase | What triage does |
|---|---|
| `where are we` | Read `/tmp/build_state.json`; render summary (phase, pool count, floors, last genre). |
| `save catalog` | Hand off to library-cataloguer; re-encode SQLite, present download link. Reader replaces Drive file. |
| `save my files` | Hand off to library-cataloguer session-end; present `Reading_List.md`, `Profile.md`, `build_state.json`, pending log updates as downloads. |
| `continue` | Resume prior flow after recovery prompt. |
| `start fresh` | Archive `/tmp/Reading_List.md` and `/tmp/build_state.json`; keep Profile.md; route to build-setup. |
| `show pending log updates` | Print `/tmp/log_pending_updates.csv` rows; reader merge into Reading_Log.csv and re-upload. |

## Hand-off

Hand-off verbal: say which skill take over so reader see skill chip change. e.g.

> "Got it — switching into single-book mode."  (librarian-quickref takes over.)

> "Good — let's start with the interview."  (librarian-build-setup takes over.)

> "Picking up where we left off — three batches into Horror."
> (librarian-build-batches takes over.)

Never invoke build mechanics. Doubt → ask one question, hand off.