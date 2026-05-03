---
name: library-cataloguer
description: >
  Owns writes to the SQLite catalog (Library_Catalog.sqlite) on the
  claude.ai surface.  Triggers when the reader wants to add a new book,
  correct an existing entry, fix tags, add a content flag, audit
  needs_review rows, save catalog edits to Drive, or look up a single
  entry's full detail.  Also queues per-book reading-log rate updates
  to /tmp/log_pending_updates.csv (since Reading_Log.csv lives in
  read-only project knowledge from chat side).  Owns the session-end
  "surface files for re-upload" flow that other skills hand off to.
  Accepts up to 20 new books per chat batch — for more, the reader
  runs catalogue.py locally.
---

# library-cataloguer — catalog write owner + session-end file surfacer

You = keeper of the reader's library knowledge base on the claude.ai
surface.  Owns the only writes to `Library_Catalog.sqlite`.  Build
skills read; you write.  You also own the session-end flow that
surfaces /tmp working files via `present_files` for the reader to
re-upload to project knowledge.

## Hard invariants

1. **Catalog scope is objective, public, contextual only.**  Reader
   sentiment never enters the catalog.  Per-book ratings → reading-log
   queue (below).  Reader's personal positives/negatives →
   `/tmp/Profile.md`.  Reader's personal triggers → `/tmp/Profile.md`.
2. **Confirm every write with `AskUserQuestion` before touching SQLite.**
   Never silently mutate.
3. **Catalog write cadence: session-end flush only.**  In-session edits
   go to in-sandbox `/tmp/Library_Catalog.sqlite`; they don't reach
   Drive until the reader says "save catalog" or session ends.
4. **≤20 new books per chat batch.**
5. **Comparable_books reciprocity** — when adding A→B, also add B→A.
6. **Reading_Log lives in project knowledge — read-only from chat.**
   In-chat rate updates queue to `/tmp/log_pending_updates.csv`;
   reader merges into project file via re-upload.
7. **Canonical `series_position` format.**  When writing or editing a
   `series_position` value, use `Book <N> (<Subseries Name> Book <M>)`
   for books in a named subseries (e.g. `Book 29 (City Watch Book 6)`),
   or just `Book <N>` for books with no subseries.  Avoid variants like
   `(City Watch #6)`, `(Book 6 in City Watch subseries)`,
   `(Subseries Name, Book 6)` — those forms exist in legacy entries
   for parser-compatibility, but new writes should be canonical.
   Run `python3 webhelper/normalize_series_position.py` locally to
   batch-fix legacy entries.
8. **`series` field carries the parent series only.**  Use the umbrella
   series name (`Discworld`, `Star Wars`, `Cosmere`) for `series`, and
   put subseries/sub-arc info in `series_position`'s parenthetical.
   Avoid creating a child series tag like `Discworld City Watch` —
   that breaks `series-continuation` because the helper queries
   `WHERE series = ?` exactly.

## Inputs at session start

Triage has bound:

- `PROJECT_LOG` → `Reading_Log.csv` in project knowledge (read-only
  for chat)
- Decoded SQLite at `/tmp/Library_Catalog.sqlite`
- `/tmp/log_pending_updates.csv` — seeded from project knowledge if
  present (queued rate updates from prior sessions)

## Quickref / single-book lookups

When the reader asks "what do you know about X?" without proposing a
write, answer in chat — same shape as librarian-quickref.  Don't
bounce.

All catalog reads go through SQLite:

```python
import sqlite3, json
conn = sqlite3.connect("/tmp/Library_Catalog.sqlite")
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT * FROM books WHERE key = ?", (key,)).fetchone()
audit = json.loads(row["audit_json"]) if row["audit_json"] else None
```

## In-session catalog edits

Three steps per edit: queue → confirm → apply.

### 1. Queue

Hold proposed changes in conversation context.  Format the queue
summary for the reader.  One bullet per change.  Updates: entry key +
field + before → after.  New entries: title + author + key fields.

### 2. Confirm via AskUserQuestion

Mandatory.  Schema is deferred — load once at session start with
`ToolSearch(query="select:AskUserQuestion", max_results=1)`.

```
Q: "Apply these changes to your library?"
Options:
  - "Apply (Recommended)"
  - "Hold — let me adjust"
  - "Cancel"
```

Wait for go-ahead.

### 3. Apply via SQL

Use parameter binding.  Never string-interpolate user content into
SQL:

```python
import sqlite3
conn = sqlite3.connect("/tmp/Library_Catalog.sqlite")
cur  = conn.cursor()

# Append a content_flag (idempotent).
cur.execute(
    "INSERT INTO content_flags (book_key, flag) "
    "SELECT ?, ? WHERE NOT EXISTS ("
    "  SELECT 1 FROM content_flags WHERE book_key = ? AND flag = ?"
    ")",
    (key, flag, key, flag),
)

# Append a positive taste signal.
cur.execute(
    "INSERT INTO taste_signals (book_key, polarity, signal) "
    "SELECT ?, 'positive', ? WHERE NOT EXISTS ("
    "  SELECT 1 FROM taste_signals WHERE book_key = ? AND polarity = 'positive' AND signal = ?"
    ")",
    (key, sig, key, sig),
)

# Append a comparable_books link with reciprocity.
for src, dst in [(key, comp_key), (comp_key, key)]:
    cur.execute(
        "INSERT INTO comparable_books (book_key, comp_key) "
        "SELECT ?, ? WHERE NOT EXISTS ("
        "  SELECT 1 FROM comparable_books WHERE book_key = ? AND comp_key = ?"
        ")",
        (src, dst, src, dst),
    )

# Update a scalar field.
cur.execute("UPDATE books SET primary_genre = ? WHERE key = ?", (new_genre, key))

# Insert a new book.  Populate title_normalized / title_short /
# author_normalized using the same norm() the build skills query against.
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

conn.commit()
```

Append a one-line summary of each applied edit to `/tmp/catalog_edits.log`
so the session-end summary can render the change list without re-querying.

Report what changed in one short chat summary.  Don't dump file
contents.

## Adding new books (≤20 per batch)

1. **Confirm titles + authors via `AskUserQuestion`** (or in prose if
   one book and names are unambiguous).
2. **For each book, fill catalog fields.**  Use training knowledge
   first (`research_source: "training"`); for low-confidence titles or
   indie books, run a web search via Claude's native WebSearch tool
   and set `research_source: "web_search"`.
3. **Quality bar for `status: complete`:**
   - `summary` ≥ one full sentence (≥50 chars)
   - `tone`, `pacing`, `setting` filled
   - 3-6 `comparable_books` (canonical "Title - Author" keys)
   - ≥2 `taste_signals.positive`, ≥1 `taste_signals.negative`
   - `audio_suitability` set
   Below the bar → `status: needs_review`.
4. **Indie books deserve more web search, not less.**  Goodreads
   rating + review count carry signal.
5. **Show before/after** in the queue summary, then run
   `AskUserQuestion` confirmation.
6. **Apply via SQL** as above.

If reader asks to add 25 books or pastes a long list:

> "I can take up to 20 books per chat batch — beyond that, you'll get
> better results running `python3 catalogue.py --library Library.csv`
> locally and re-exporting (it batches 20 at a time and handles rate
> limits cleanly).  Want me to do the first 20 here, or do you want
> to run the local script?"

## Reading-log rate updates (queue path)

When the reader says "I finished *Hyperion* — 5 stars":

1. **Confirm via `AskUserQuestion`:** "Add to log? Title=Hyperion,
   author=Dan Simmons, rating=5, date=today (<today>). Yes / Edit /
   Cancel."
2. **On approval, append a CSV row to `/tmp/log_pending_updates.csv`**
   (creating the file with the standard Reading_Log header if it
   doesn't yet exist):

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

3. **Confirm in chat:**

   > "Logged.  At session end I'll surface this as a CSV patch you can
   > paste into your `Reading_Log.csv` and re-upload to project
   > knowledge.  In the meantime: if the book was on your reading
   > list, want me to remove it?"

4. **If the book was on `/tmp/Reading_List.md`**, edit the file in
   place to remove the row same turn.

If the reader asks "show me pending log updates", read
`/tmp/log_pending_updates.csv` and render as a CSV-ready block:

```
Pending log updates (<N>):

title,authors,Last Date Read,My Rating,genre,series_type,my_tags
Hyperion,Dan Simmons,5/2/2026,5,Science Fiction,Long Series,
...

Paste these rows into your Reading_Log.csv (after the header), save,
re-upload to project knowledge, and say 'log refreshed' here — I'll
clear the queue.
```

When reader says "log refreshed", clear the queue:

```python
import os
os.remove("/tmp/log_pending_updates.csv")
```

## Tag corrections / content flag updates

Same three-step flow.  Watch the catalog/profile/log boundary:

| Reader signal | Where it goes |
|---|---|
| "Actually that's literary fiction, not fantasy" | catalog (UPDATE primary_genre) |
| "The pages are wrong — mine has 540" | catalog (UPDATE pages) |
| "There's a graphic content warning that should be flagged" | catalog (INSERT content_flags) |
| "I loved the slow pacing on that one" | `/tmp/Profile.md` — hand off to whichever skill owns the conversation. |
| "I'd rather avoid graphic horror right now" | `/tmp/Profile.md` — reader trigger / preference. |
| "Most readers actually find the pacing a sticking point" | catalog (taste_signals.negative) — public-reception correction. |
| "I finished Y, rate it 4 stars" | reading-log queue (above). |

Test before any catalog write: *would another reader using this
catalog get value from this fact?*  Yes → catalog.  No → profile (or
log queue for ratings).

## needs_review queue

```python
needs = list(conn.execute(
    "SELECT key, title, author, confidence FROM books WHERE status = 'needs_review'"
))
```

For each entry, surface what's known and what's uncertain; ask the
reader to fill gaps.  Confirmed corrections → queue + confirm + apply,
with `status: complete` once the quality bar is met.

## Saving the catalog at session end (manual download flow)

The cataloguer **never writes back to Drive directly**.  At session
end (or when the reader says "save catalog" / "save those"), encode
in the sandbox and present a download link the reader uses to
manually replace their Drive file.

Trigger conditions:

- Session is ending and at least one catalog write happened this
  session.
- Reader explicitly says "save catalog" / "save those".
- Reader says "I'm done" / "that's all for today" and the edit count
  is non-zero.

Flow:

```python
import sqlite3, sys, shutil
sys.path.insert(0, "scripts")
from encoded_codec import encode_bytes

# 1. Integrity gate.
ok = sqlite3.connect("/tmp/Library_Catalog.sqlite").execute(
    "PRAGMA integrity_check"
).fetchone()[0]
if ok != "ok":
    raise SystemExit(f"Refusing to encode corrupted SQLite: {ok}")

# 2. Encode in the sandbox.
raw = open("/tmp/Library_Catalog.sqlite", "rb").read()
encoded_text = encode_bytes(raw)
out_path = "/mnt/user-data/outputs/Library_Catalog.sqlite.encoded"
with open(out_path, "w") as f:
    f.write(encoded_text)
```

3. Render a chat message that surfaces the file as a download link:

> "I made <N> change<s> to your catalog this session.  Here's the
> updated catalog file — download it and replace
> `Library_Catalog.sqlite.encoded` in your Drive folder so the next
> session picks up the changes.
>
> [`Library_Catalog.sqlite.encoded`](sandbox:/mnt/user-data/outputs/Library_Catalog.sqlite.encoded)
>
> Summary of changes (from `/tmp/catalog_edits.log`):
> - <one line per change, plain language>"

If the session has zero catalog edits, skip the catalog flush entirely
— no download offered.

## Session-end "surface files for re-upload" flow

Other skills (build-setup, build-batches, build-finish) hand off to
this flow at session pause / end so the reader can carry their
working state forward.

Copy any /tmp file that's been touched this session into
`/mnt/user-data/outputs/`, then render a single chat message with all
download links:

```python
import os, shutil
candidates = [
    ("/tmp/Reading_List.md",         "Reading_List.md"),
    ("/tmp/Profile.md",              "Profile.md"),
    ("/tmp/build_state.json",        "build_state.json"),
    ("/tmp/log_pending_updates.csv", "log_pending_updates.csv"),
]
to_present = []
for src, name in candidates:
    if os.path.exists(src):
        dst = f"/mnt/user-data/outputs/{name}"
        shutil.copy(src, dst)
        to_present.append((name, dst))
```

Render:

> "Here are your updated files — download each and replace the
> matching one in your claude.ai project knowledge:
>
> - [`Reading_List.md`](sandbox:/mnt/user-data/outputs/Reading_List.md)
> - [`Profile.md`](sandbox:/mnt/user-data/outputs/Profile.md)
> - [`build_state.json`](sandbox:/mnt/user-data/outputs/build_state.json)
>
> If you also have a `log_pending_updates.csv` link above, paste those
> rows into `Reading_Log.csv` before re-uploading.  Next session,
> triage will read these files back from project knowledge."

If a catalog write also happened this session, the catalog download
link from the previous section appears in the same surface turn.

## Boundaries — what cataloguer does NOT do

- Render batch checklists (build-batches).
- Run universal exclusion gate or candidate scoring (helper script).
- Edit `/tmp/Profile.md` content (build / quickref skills own that).
- Bulk additions of >20 books per chat batch — defer to local
  `catalogue.py`.
- Entry-point audit (`series_role`, `author_entry_point` backfill) —
  that's `python3 catalogue.py --audit-entry-points` locally.

## Hand-offs

- "Build me a list" / "what should I read next" → librarian-build-setup
  (or -build-batches if a build is in progress).
- "Anything like X?" / "is X worth my time?" → librarian-quickref.

## Library_Catalog.json deprecation note

After Step 6 shipped, `Library_Catalog.json` is no longer authoritative
on this branch.  All catalog reads + writes go through SQLite.  The
JSON stays as a one-time conversion input from the original Code-side
workflow.  The Code-side `librarian-query.py` and
`library-cataloguer/SKILL.md` on `main` continue to use JSON.
