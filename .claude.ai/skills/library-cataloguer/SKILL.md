---
name: library-cataloguer
description: >
  Owns writes to the SQLite catalog (Library_Catalog.sqlite) on the
  claude.ai surface.  Triggers when the reader wants to add a new book,
  correct an existing entry, fix tags, add a content flag, audit needs_review
  rows, save catalog edits to Drive, or look up a single entry's full detail.
  Accepts up to 20 new books per chat batch — for more, the reader should
  run catalogue.py locally.  Hands off larger structural questions to
  librarian-quickref or the build skills.
---

# library-cataloguer — catalog write owner

You = keeper of the reader's library knowledge base on the claude.ai
surface.  Owns the only writes to `Library_Catalog.sqlite`.  Build skills
read; you write.

## Hard invariants

1. **Catalog scope is objective, public, contextual only.**  Reader sentiment
   never enters the catalog.  Per-book ratings → `Reading_Log.csv`.
   Reader's personal positives/negatives → `Profile.md`.  Reader's personal
   triggers → `Profile.md`.  See "Catalog/profile/log boundary" below.
2. **Confirm every write with `AskUserQuestion` before touching SQLite.**
   Never silently mutate.
3. **Catalog write cadence: session-end flush only.**  In-session edits
   go to the in-sandbox `/tmp/Library_Catalog.sqlite`; they don't reach
   Drive until the reader says "save catalog" or the session ends.
4. **≤20 new books per chat batch.**  More than 20 → tell the reader to
   run `catalogue.py --library Library.csv` locally OR to break the
   request into multiple ≤20 chunks.
5. **Comparable_books reciprocity** — when adding A→B, also add B→A.
6. **Catalog edits take a `window.storage` lock** so two concurrent sessions
   can't race on the encode-and-flush step.

## Quickref / single-book lookups

When the reader asks "what do you know about X?" without proposing a
write, answer in chat from SQLite — same shape as the librarian-quickref
skill.  Don't bounce the reader between skills for a read query.

```python
import sqlite3, json
conn = sqlite3.connect("/tmp/Library_Catalog.sqlite")
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT * FROM books WHERE key = ?", (key,)).fetchone()
audit = json.loads(row["audit_json"]) if row["audit_json"] else None
```

If the reader follows up with "fix X" / "add Y", switch into write mode
(below).

## In-session catalog edits

Every write goes through three steps: queue → confirm → apply.

### 1. Queue the change

Hold proposed changes in the conversation context (no persistent queue
needed — the cataloguer skill is single-turn-per-edit by default).
Format the queue summary for the reader:

```
About to apply:
- Brave New World - Aldous Huxley
    content_flags: append "racism (period-typical depiction)"
- Dune - Frank Herbert
    taste_signals.positive: append "slow-burn worldbuilding payoff"
    comparable_books: append "The Stars My Destination - Alfred Bester"
- New entry: The Mountain in the Sea - Ray Nayler
    primary_genre=Science Fiction, status=complete (High, training)
```

One bullet per change.  Updates: entry key + field + before → after.
New entries: title + author + key fields.

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

Wait for go-ahead before any SQLite write.  If the reader edits any of
the proposed changes in chat, re-summarise and re-ask.

### 3. Apply via SQL

Open the in-sandbox SQLite and apply.  Use parameter binding — never
string-interpolate user content into SQL:

```python
import sqlite3, json
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

# Update a scalar field (e.g. primary_genre correction).
cur.execute("UPDATE books SET primary_genre = ? WHERE key = ?", (new_genre, key))

# Insert a new book.  Ensure title_normalized / title_short / author_normalized
# are populated using the same norm() the build skills query against.
sys.path.insert(0, "scripts")
from sqlite_export import norm, title_short
cur.execute(
    "INSERT INTO books (key, title, title_normalized, title_short, "
    "author, author_normalized, ...) VALUES (?, ?, ?, ?, ?, ?, ...)",
    (
        f"{title} - {author}",
        title, norm(title), title_short(title),
        author, norm(author),
        # ...remaining columns from the schema in webhelper/sqlite_export.py
    ),
)

conn.commit()
```

After SQL, report what changed in one short chat summary.  Don't dump
file contents.

### Maintaining `comparable_books` reciprocity

Every time you `INSERT INTO comparable_books (book_key, comp_key) VALUES
(A, B)`, also insert `(B, A)`.  See SQL above.  The build skills'
`comp_overlap_count` scoring depends on bidirectional links.

## Adding new books (≤20 per batch)

When the reader says "add *X* and *Y*":

1. **Confirm titles + authors via `AskUserQuestion`** (or in prose if only
   one book and the names are unambiguous).
2. **For each book, fill catalog fields.**  Use training knowledge first
   (`research_source: "training"`); for low-confidence titles or indie
   books, run a web search via Claude's native WebSearch tool and set
   `research_source: "web_search"`.
3. **Quality bar for `status: complete`:**
   - `summary` ≥ one full sentence (≥50 chars)
   - `tone`, `pacing`, `setting` filled
   - 3-6 `comparable_books` (canonical "Title - Author" keys preferred when
     the comp is in-library; external comps fine when they convey vibe)
   - ≥2 `taste_signals.positive`, ≥1 `taste_signals.negative`
   - `audio_suitability` set
   Below the bar → `status: needs_review`.
4. **Indie books deserve more web search, not less.**  Goodreads rating +
   review count carry signal:
   - ≥4.3 with 1k+ reviews → solid resonance
   - ≥4.3 with <500 reviews → hidden-gem signal (call it out in
     `taste_signals.positive`)
   - <100 reviews → caution; mark `confidence: Low` and consider
     `needs_review`.
5. **Show before/after** in the queue summary, then run the
   `AskUserQuestion` confirmation.
6. **Apply via SQL** as above.

If the reader says "add 25 books" or pastes a long list:

> "I can take up to 20 books per chat batch — beyond that, you'll get
> better results running `python3 catalogue.py --library Library.csv`
> locally and re-exporting (it batches 20 at a time and handles rate
> limits cleanly).  Want me to do the first 20 here, or do you want to
> run the local script?"

## Tag corrections / content flag updates

Same three-step flow.  Specifically watch the catalog/profile/log
boundary:

| Reader signal | Where it goes |
|---|---|
| "Actually that's literary fiction, not fantasy" | catalog (UPDATE primary_genre) |
| "The pages are wrong — mine has 540" | catalog (UPDATE pages) |
| "There's a graphic content warning that should be flagged" | catalog (INSERT content_flags) |
| "I loved the slow pacing on that one" | **Profile.md** — hand off to whichever skill owns Profile (build-setup / build-batches / quickref).  Sentiment, not catalog. |
| "I'd rather avoid graphic horror right now" | **Profile.md** — reader trigger / preference, not catalog. |
| "Most readers actually find the pacing a sticking point" | catalog (taste_signals.negative) — public-reception correction, not personal. |

Test before any catalog write: *would another reader using this catalog
get value from this fact?*  Yes → catalog.  No → Profile.md.  Reader's
*rating* of a book never enters the catalog.

## needs_review queue

```python
needs = list(conn.execute("SELECT key, title, author, confidence FROM books WHERE status = 'needs_review'"))
```

For each entry, surface what's known and what's uncertain; ask the reader
to fill gaps.  Confirmed corrections → queue + confirm + apply, with
`status: complete` once the quality bar is met.

## Saving the catalog back to Drive (session-end flush)

Either at session end OR when the reader says "save catalog" / "save those":

```python
import sqlite3, sys
sys.path.insert(0, "scripts")
from encoded_codec import encode_bytes

# Run integrity check before encoding.
ok = sqlite3.connect("/tmp/Library_Catalog.sqlite").execute("PRAGMA integrity_check").fetchone()[0]
if ok != "ok":
    raise SystemExit(f"Refusing to flush corrupted SQLite: {ok}")

raw = open("/tmp/Library_Catalog.sqlite", "rb").read()
encoded_text = encode_bytes(raw)
# Then write `encoded_text` to Library-Playground/Library_Catalog.sqlite.encoded
# in Drive via the Drive connector's save-file path.
```

After successful flush, drop the editing lock:

```
window.storage.delete("catalog_edit_lock")
```

Confirm in chat: "Catalog saved to your Drive folder."

## Concurrency lock

Before the first edit in a session, set a lock:

```
window.storage.set("catalog_edit_lock",
    JSON.stringify({"session_id": "<uuid>", "started_at": "<ISO>"}))
```

If the lock is already set by a different session, refuse the edit:

> "Another session is currently editing your catalog (started at <time>).
> Finish that one first, or if it crashed, say 'force unlock' and I'll
> clear it."

Lock is released on successful flush.  `force unlock` deletes the lock
key and proceeds.

## Boundaries — what cataloguer does NOT do

- Render batch checklists (that's `librarian-build-batches`).
- Run the universal exclusion gate or candidate scoring (that's the
  helper script via the build skills).
- Write to `Profile.md` or `Reading_List.md` — those are owned by the
  build / quickref skills.
- Bulk additions of >20 books per chat batch — defer to local
  `catalogue.py`.
- The entry-point audit (`series_role`, `author_entry_point`
  backfill) — that's `python3 catalogue.py --audit-entry-points` locally.

## Hand-offs

- "Build me a list" / "what should I read next" → librarian-build-setup
  (or -build-batches if a build is in progress).
- "Anything like X?" / "is X worth my time?" → librarian-quickref.
- "I finished Y, rate it 5 stars" → reading-log update.  Append a row to
  `/tmp/Reading_Log.csv` (CSV format, same columns as the Goodreads
  export), then flush to Drive same turn.  This is the one mutable file
  besides Profile.md and Reading_List.md that gets per-edit Drive flush.

## Library_Catalog.json deprecation note

This skill is the cutover point.  After Step 6 ships:

- `Library_Catalog.json` is no longer authoritative on this branch.
- All catalog reads + writes go through `Library_Catalog.sqlite`.
- The JSON stays in `.gitignore` as a one-time conversion input from the
  original Code-side workflow.  Users who want to re-export to JSON for
  backup can write a small reverse-export script — not bundled.

The Code-side `librarian-query.py` and `library-cataloguer/SKILL.md` on
`main` continue to use JSON.  That is intentional: the two implementations
stay separate for comparison.
