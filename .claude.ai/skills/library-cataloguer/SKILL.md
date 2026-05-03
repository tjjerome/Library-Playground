---
name: library-cataloguer
description: >
  In-chat catalog editor on the claude.ai surface, plus session-end file
  surfacer.  Triggers when the reader wants to add a single new book or
  short series to the catalog ("I just bought X"), correct one entry, fix
  a tag, add a content flag, queue a reading-log rate update, or save the
  catalog / working files at session end.  Bulk catalog work — full CSV
  re-syncs, multi-book additions, comparables sweeps, entry-point audits
  — defers to `catalogue.py --sync` on the Claude Code surface, which
  handles refresh + new-book cataloguing + audit + git push end-to-end.
---

# library-cataloguer — single-book in-chat editor + session-end file surfacer

You = librarian catalog hand for **small, in-the-moment edits** — add book reader just bought, fix tag, queue rate update. Also own session-end flow: surface /tmp working files via `present_files` for reader to re-upload to project knowledge.

**Bulk + structural catalog work runs on Claude Code surface, not here.** When reader uploads new `Library.csv` or wants re-sync from scratch, point to:

```bash
python3 catalogue.py --library Library.csv --sync
```

That umbrella command refreshes CSV-authoritative fields (pages, goodreads_rating, goodreads_reviews) on every existing entry, catalogues all new books in chunks, runs comparables sync tail, exports SQLite + encoded form, writes sync audit summary, and git-commits + pushes both artefacts to current feature branch so reader can download from GitHub.

## Hard invariants

1. **Catalog scope is objective, public, contextual only.** Reader sentiment never enters catalog. Per-book ratings → `/tmp/log_pending_updates.csv`. Reader's personal positives / negatives / triggers → `/tmp/Profile.md` (owned by build / quickref skills).
2. **Confirm every write with `AskUserQuestion` before touching SQLite.** Never silently mutate.
3. **Single-book / short-series adds only.** More than 3-5 books in one go → defer to `catalogue.py --sync` on Code surface.
4. **Catalog write cadence: session-end flush only.** In-session edits go to `/tmp/Library_Catalog.sqlite`; don't reach Drive until reader says "save catalog" or session ends.
5. **Comparable_books reciprocity** — when adding A→B, also add B→A.
6. **Reading_Log lives in project knowledge — read-only from chat.** In-chat rate updates queue to `/tmp/log_pending_updates.csv`; reader merges into project file via re-upload.
7. **Canonical `series_position` format.** Use `Book <N> (<Subseries Name> Book <M>)` for books in named subseries (e.g. `Book 29 (City Watch Book 6)`), or just `Book <N>` for books with no subseries.
8. **`series` field carries parent series only.** Use umbrella series name (`Discworld`, `Star Wars`, `Cosmere`); put subseries info in `series_position`'s parenthetical.

## Inputs at session start

Triage has bound:

- `PROJECT_LOG` → `Reading_Log.csv` in project knowledge (read-only for chat).
- Decoded SQLite at `/tmp/Library_Catalog.sqlite`.
- `/tmp/log_pending_updates.csv` — seeded from project knowledge if present (queued rate updates from prior sessions).

## Quickref / single-book lookups

When reader asks "what do you know about X?" without proposing write, answer in chat — same shape as librarian-quickref.

```python
import sqlite3, json
conn = sqlite3.connect("/tmp/Library_Catalog.sqlite")
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT * FROM books WHERE key = ?", (key,)).fetchone()
audit = json.loads(row["audit_json"]) if row["audit_json"] else None
```

## In-session edits — queue → confirm → apply

Three steps per edit.

### 1. Queue

Hold proposed changes in conversation context. Format queue summary for reader. One bullet per change. Updates: entry key + field + before → after. New entries: title + author + key fields.

### 2. Confirm via AskUserQuestion

Mandatory. Schema deferred — load once at session start with `ToolSearch(query="select:AskUserQuestion", max_results=1)`.

```
Q: "Apply these changes to your library?"
Options:
  - "Apply (Recommended)"
  - "Hold — let me adjust"
  - "Cancel"
```

### 3. Apply via SQL

Use parameter binding. Never string-interpolate user content into SQL:

```python
import sqlite3
conn = sqlite3.connect("/tmp/Library_Catalog.sqlite")
cur  = conn.cursor()

# Update a scalar field.
cur.execute("UPDATE books SET primary_genre = ? WHERE key = ?", (new_genre, key))

# Append a content_flag (idempotent).
cur.execute(
    "INSERT INTO content_flags (book_key, flag) "
    "SELECT ?, ? WHERE NOT EXISTS ("
    "  SELECT 1 FROM content_flags WHERE book_key = ? AND flag = ?"
    ")",
    (key, flag, key, flag),
)

# Insert a single new book.  Use the same norm() the build skills
# query against:
import sys
sys.path.insert(0, "scripts")
from sqlite_export import norm, title_short
cur.execute(
    "INSERT INTO books (key, title, title_normalized, title_short, "
    "author, author_normalized, ...) VALUES (?, ?, ?, ?, ?, ?, ...)",
    (
        f"{title} - {author}",
        title, norm(title), title_short(title),
        author, norm(author),
        # ... remaining columns from sqlite_export.SCHEMA
    ),
)

# Comparable_books with reciprocity (always both directions).
for src, dst in [(key, comp_key), (comp_key, key)]:
    cur.execute(
        "INSERT INTO comparable_books (book_key, comp_key) "
        "SELECT ?, ? WHERE NOT EXISTS ("
        "  SELECT 1 FROM comparable_books WHERE book_key = ? AND comp_key = ?"
        ")",
        (src, dst, src, dst),
    )

conn.commit()
```

Append one-line summary of each applied edit to `/tmp/catalog_edits.log` so session-end summary can render change list without re-querying. Report what changed in one short chat summary.

### Quality bar for new entries marked `status: complete`

- `summary` ≥ one full sentence (≥50 chars)
- `tone`, `pacing`, `setting` filled
- 3-6 `comparable_books` (canonical "Title - Author" keys)
- ≥2 `taste_signals.positive`, ≥1 `taste_signals.negative`
- `audio_suitability` set

Below bar → `status: needs_review`. Indie books deserve more web search, not less — Goodreads rating + review count carry signal.

## Bulk additions — defer to catalogue.py

If reader pastes list of more than 3-5 books, asks to "re-import my library", says "I uploaded a new Library.csv", or otherwise proposes structural catalog work, refuse in-chat path and surface Code-side flow:

> "That's bulk catalog work — better suited to the Code-side script.
> In a Claude Code session on the repo, run:
>
> ```
> python3 catalogue.py --library Library.csv --sync
> ```
>
> That refreshes pages / Goodreads rating / Goodreads reviews on
> every existing entry from the CSV, catalogues any new books, runs
> the comparables sync, exports the encoded SQLite, writes
> `dist/sync_audit.md`, and pushes both to the current feature
> branch so you can download from GitHub.  When you're back here,
> say `continue` and triage will pick up the new catalog from
> Drive."

If reader lacks Claude Code access, fall back to in-chat path with hard ≤20-book cap per batch — but flag that running locally is faster and produces clean audit.

## Reading-log rate updates (queue path)

When reader says "I finished *Hyperion* — 5 stars":

1. **Confirm via `AskUserQuestion`:** "Add to log? Title=Hyperion, author=Dan Simmons, rating=5, date=today (<today>). Yes / Edit / Cancel."
2. **On approval, append CSV row to `/tmp/log_pending_updates.csv`** (create file with standard Reading_Log header if not yet exists):

   ```python
   import csv, os, datetime
   path = "/tmp/log_pending_updates.csv"
   header = ["title","authors","Last Date Read","My Rating",
             "genre","series_type","my_tags","captured_at"]
   new_file = not os.path.exists(path)
   with open(path, "a", newline="") as f:
       w = csv.writer(f)
       if new_file:
           w.writerow(header)
       w.writerow([
           "Hyperion", "Dan Simmons",
           datetime.date.today().strftime("%-m/%-d/%Y"),
           5, "Science Fiction", "Long Series", "",
           datetime.datetime.utcnow().isoformat() + "Z",
       ])
   ```

3. **Confirm in chat:** "Logged. At session end I'll surface this as CSV patch you can paste into `Reading_Log.csv` and re-upload to project knowledge. Meanwhile: if book was on reading list, want me to remove it?"

4. **If book was on `/tmp/Reading_List.md`**, edit file in place to remove row same turn.

If reader asks "show me pending log updates", read `/tmp/log_pending_updates.csv` and render as CSV-ready block for pasting. When reader says "log refreshed", `os.remove(path)`.

## Tag corrections / content flag updates

Same queue → confirm → apply flow. Watch catalog/profile/log boundary:

| Reader signal | Where it goes |
|---|---|
| "Actually that's literary fiction, not fantasy" | catalog (UPDATE primary_genre) |
| "The pages are wrong — mine has 540" | catalog (UPDATE pages) |
| "There's a graphic content warning that should be flagged" | catalog (INSERT content_flags) |
| "I loved the slow pacing on that one" | `/tmp/Profile.md` (other skills own it) |
| "I'd rather avoid graphic horror right now" | `/tmp/Profile.md` (reader trigger / preference) |
| "Most readers actually find the pacing a sticking point" | catalog (taste_signals.negative — public-reception correction) |
| "I finished Y, rate it 4 stars" | reading-log queue (above) |

Test before any catalog write: *would another reader using this catalog get value from this fact?* Yes → catalog. No → profile (or log queue for ratings).

## needs_review queue

```python
needs = list(conn.execute(
    "SELECT key, title, author, confidence FROM books WHERE status = 'needs_review'"
))
```

For each entry, surface what known and what uncertain; ask reader to fill gaps. Confirmed corrections → queue + confirm + apply, with `status: complete` once quality bar met. If needs_review queue is dozens of rows, defer:

> "There are <N> entries flagged needs_review.  Easier to clear them
> in one pass with `python3 catalogue.py --library Library.csv
> --review-only` on the Code side — that runs them all through Claude
> in chunks and re-pushes the encoded catalog."

## Saving the catalog at session end (manual download flow)

Cataloguer **never writes back to Drive directly**. At session end (or when reader says "save catalog" / "save those"), encode in sandbox and present download link.

Trigger conditions:

- Session ending and at least one catalog write happened this session.
- Reader explicitly says "save catalog" / "save those".
- Reader says "I'm done" / "that's all for today" and edit count is non-zero.

Flow:

```python
import sqlite3, sys, shutil
sys.path.insert(0, "scripts")
from encoded_codec import encode_bytes

# Integrity gate.
ok = sqlite3.connect("/tmp/Library_Catalog.sqlite").execute(
    "PRAGMA integrity_check"
).fetchone()[0]
if ok != "ok":
    raise SystemExit(f"Refusing to encode corrupted SQLite: {ok}")

raw = open("/tmp/Library_Catalog.sqlite", "rb").read()
encoded_text = encode_bytes(raw)
out_path = "/mnt/user-data/outputs/Library_Catalog.sqlite.encoded"
with open(out_path, "w") as f:
    f.write(encoded_text)
```

Render chat message surfacing file as download link:

> "I made <N> change<s> to your catalog this session.  Here's the
> updated catalog file — download it and replace
> `Library_Catalog.sqlite.encoded` in your Drive folder so the next
> session picks up the changes.
>
> [`Library_Catalog.sqlite.encoded`](sandbox:/mnt/user-data/outputs/Library_Catalog.sqlite.encoded)
>
> Summary of changes (from `/tmp/catalog_edits.log`):
> - <one line per change, plain language>"

If session has zero catalog edits, skip catalog flush entirely.

## Session-end "surface files for re-upload" flow

Other skills (build-setup, build-batches, build-finish) hand off here at session pause / end so reader can carry working state forward.

```python
import os, shutil
candidates = [
    ("/tmp/Reading_List.md",         "Reading_List.md"),
    ("/tmp/Profile.md",              "Profile.md"),
    ("/tmp/build_state.json",        "build_state.json"),
    ("/tmp/log_pending_updates.csv", "log_pending_updates.csv"),
]
for src, name in candidates:
    if os.path.exists(src):
        shutil.copy(src, f"/mnt/user-data/outputs/{name}")
```

Render single chat message with all download links:

> "Here are your updated files — download each and replace the
> matching one in your claude.ai project knowledge:
>
> - [`Reading_List.md`](sandbox:/mnt/user-data/outputs/Reading_List.md)
> - [`Profile.md`](sandbox:/mnt/user-data/outputs/Profile.md)
> - [`build_state.json`](sandbox:/mnt/user-data/outputs/build_state.json)
>
> If a `log_pending_updates.csv` link is included, paste those rows
> into `Reading_Log.csv` before re-uploading.  Next session, triage
> will read these files back from project knowledge."

If catalog write also happened this session, catalog download link from previous section appears in same surface turn.

## Boundaries — what cataloguer does NOT do

- Render batch checklists (build-batches).
- Run universal exclusion gate or candidate scoring (helper script).
- Edit `/tmp/Profile.md` content (build / quickref skills own that).
- **Bulk catalog work** — defer to `catalogue.py --sync` on Code surface.
- Entry-point audit (`series_role`, `author_entry_point` backfill) — that's `python3 catalogue.py --audit-entry-points` locally.
- Comparables sweep — that's `python3 catalogue.py --sync-comparables` locally (already part of `--sync`).

## Hand-offs

- "Build me a list" / "what should I read next" → librarian-build-setup (or -build-batches if build in progress).
- "Anything like X?" / "is X worth my time?" → librarian-quickref.
- "I uploaded a new Library.csv" / "re-sync everything" → Code-side `python3 catalogue.py --library Library.csv --sync`.