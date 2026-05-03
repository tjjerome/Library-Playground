---
name: library-cataloguer
description: >
  Owns writes to the SQLite catalog (Library_Catalog.sqlite) on the
  claude.ai surface.  Triggers when the reader wants to add a new book,
  correct an existing entry, fix tags, add a content flag, audit
  needs_review rows, save catalog edits to Drive, or look up a single
  entry's full detail.  Also queues per-book reading-log rate updates
  (since Reading_Log.csv is read-only project knowledge from chat side).
  Accepts up to 20 new books per chat batch — for more, the reader runs
  catalogue.py locally.
---

# library-cataloguer — catalog write owner

You = keeper of the reader's library knowledge base on the claude.ai
surface.  Owns the only writes to `Library_Catalog.sqlite`.  Build
skills read; you write.

## Hard invariants

1. **Catalog scope is objective, public, contextual only.**  Reader
   sentiment never enters the catalog.  Per-book ratings → reading-log
   queue (below).  Reader's personal positives/negatives → profile
   artifact.  Reader's personal triggers → profile artifact.
2. **Confirm every write with `AskUserQuestion` before touching SQLite.**
   Never silently mutate.
3. **Catalog write cadence: session-end flush only.**  In-session edits
   go to in-sandbox `/tmp/Library_Catalog.sqlite`; they don't reach
   Drive until the reader says "save catalog" or session ends.
4. **≤20 new books per chat batch.**
5. **Comparable_books reciprocity** — when adding A→B, also add B→A.
6. **Catalog edits take a `window.storage` lock** on the picker artifact
   so two concurrent sessions can't race on encode-and-flush.
7. **Reading_Log lives in project knowledge — read-only from chat.**
   In-chat rate updates queue to `window.storage["log_pending_updates"]`
   on the picker artifact; reader merges into project file via
   re-upload.
8. **Canonical `series_position` format.**  When writing or editing a
   `series_position` value, use `Book <N> (<Subseries Name> Book <M>)`
   for books in a named subseries (e.g. `Book 29 (City Watch Book 6)`),
   or just `Book <N>` for books with no subseries.  Avoid variants like
   `(City Watch #6)`, `(Book 6 in City Watch subseries)`,
   `(Subseries Name, Book 6)` — those forms exist in legacy entries
   for parser-compatibility, but new writes should be canonical.
   Run `python3 webhelper/normalize_series_position.py` locally to
   batch-fix legacy entries.
9. **`series` field carries the parent series only.**  Use the umbrella
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

## Concurrency lock

Before the first edit in a session, set a lock on the picker artifact:

```javascript
await window.storage.set("catalog_edit_lock", JSON.stringify({
  session_id: "<uuid>", started_at: "<ISO>"
}));
```

If the lock is already set by a different session, refuse the edit:

> "Another session is currently editing your catalog (started at
> <time>).  Finish that one first, or if it crashed, say 'force
> unlock' and I'll clear it."

`force unlock` deletes the lock and proceeds.

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
2. **On approval, append to the queue** in the picker artifact's
   window.storage:

   ```javascript
   let q = JSON.parse((await window.storage.get("log_pending_updates")).value || "[]");
   q.push({
     title: "Hyperion",
     authors: "Dan Simmons",
     last_date_read: "<today MM/DD/YYYY>",
     my_rating: 5,
     genre: "Science Fiction",        // optional
     series_type: "Long Series",       // optional
     my_tags: "",                      // optional, "*completed" if final book
     captured_at: "<ISO8601>",
   });
   await window.storage.set("log_pending_updates", JSON.stringify(q));
   ```

3. **Confirm in chat:**

   > "Logged.  I'll surface this on your next session-start so you can
   > paste it into your `Reading_Log.csv` and re-upload to project
   > knowledge.  In the meantime: if the book was on your reading
   > list, want me to remove it?"

4. **If the book was on `Reading_List.md`**, edit the reading-list
   artifact same turn to remove the row; flush.

If the reader asks "show me pending log updates", read the queue and
render as a CSV-ready block:

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

```javascript
await window.storage.set("log_pending_updates", "[]");
```

## Tag corrections / content flag updates

Same three-step flow.  Watch the catalog/profile/log boundary:

| Reader signal | Where it goes |
|---|---|
| "Actually that's literary fiction, not fantasy" | catalog (UPDATE primary_genre) |
| "The pages are wrong — mine has 540" | catalog (UPDATE pages) |
| "There's a graphic content warning that should be flagged" | catalog (INSERT content_flags) |
| "I loved the slow pacing on that one" | profile artifact — hand off to whichever skill owns the conversation. |
| "I'd rather avoid graphic horror right now" | profile artifact — reader trigger / preference. |
| "Most readers actually find the pacing a sticking point" | catalog (taste_signals.negative) — public-reception correction. |
| "I finished Y, rate it 4 stars" | reading-log queue (above). |

Test before any catalog write: *would another reader using this
catalog get value from this fact?*  Yes → catalog.  No → profile
artifact (or log queue for ratings).

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
> Summary of changes:
> - <one line per change, plain language>"

4. Drop the lock after the link is rendered (the reader's manual
   upload completes the loop, but the in-session lock is no longer
   needed once the encoded file is produced):

```javascript
await window.storage.delete("catalog_edit_lock");
```

**Why manual.**  The Drive connector's write path needs explicit
reader confirmation per change to avoid silent agent mutation of a
shared file.  Surfacing the file as a download link gives the reader
an explicit checkpoint where they confirm + replace, with the option
to inspect the encoded form first.

If the session has zero catalog edits, skip the flush entirely — no
download offered, no lock to drop.

## Boundaries — what cataloguer does NOT do

- Render batch checklists (build-batches).
- Run universal exclusion gate or candidate scoring (helper script).
- Write to profile or reading-list artifacts — those are owned by
  build / quickref skills.
- Bulk additions of >20 books per chat batch — defer to local
  `catalogue.py`.
- Entry-point audit (`series_role`, `author_entry_point` backfill) —
  that's `python3 catalogue.py --audit-entry-points` locally.

## Hand-offs

- "Build me a list" / "what should I read next" → librarian-build-setup
  (or -build-batches if a build is in progress).
- "Anything like X?" / "is X worth my time?" → librarian-quickref.

## Library_Catalog.json deprecation note

After Step 6 ships, `Library_Catalog.json` is no longer authoritative
on this branch.  All catalog reads + writes go through SQLite.  The
JSON stays as a one-time conversion input from the original Code-side
workflow.  The Code-side `librarian-query.py` and
`library-cataloguer/SKILL.md` on `main` continue to use JSON.
