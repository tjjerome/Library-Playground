---
name: librarian-quickref
description: >
  Answers single-book queries against the reader's library — "anything like
  X?", "is X worth my time?", "what do you know about X?", "what comes after
  X in its series?", "any plans you have on Y?".  Reads from the project-file
  browse index for fast presence checks, decodes the SQLite catalog only when
  needed for full per-book detail, gives a 1-3 paragraph answer that fits the
  book to the reader's profile, and writes any signal-capture bullets into
  the profile artifact immediately.  Does NOT do batch builds, batch picks,
  multi-book workflows, or catalog edits.
---

# librarian-quickref — single-book mode

Reader asks one focused question.  You give one focused answer.  No
interview, no goals conversation, no batch checklists, no list edits.

## Hard invariants

1. **Triage already verified the artifacts** — but quickref doesn't write
   to the picker artifact, so its preflight failure is irrelevant here.
   Quickref DOES write to the profile artifact, so the profile preflight
   must have passed before quickref runs.  Triage gates this.
2. **Catalog reads only.**  Factual catalog corrections from the reader
   ("actually that's literary fiction, not fantasy") → hand off to
   library-cataloguer same turn.
3. **Profile artifact per-edit storage write.**  Any time you append a
   bullet to the profile, write the updated content to
   `window.storage["profile"]` same turn.
4. **Page count mandatory** in any single-book answer that names a book.
5. **Anti-jargon contract** — see translation map in
   `librarian-build-batches/SKILL.md`.

## Inputs at session start

Triage has bound:

- `PROJECT_INDEX` → path to `Library_Browse_Index.json` (slim, ~800KB)
  in project knowledge.  May be missing on minimal Pro setups.
- `PROJECT_LOG` → path to `Reading_Log.csv` in project knowledge.
- Profile content → `window.storage["profile"].content` on the profile
  artifact (text markdown).
- Reading_List content → `window.storage["reading_list"].content` on
  the reading-list artifact (text markdown).
- Decoded SQLite at `/tmp/Library_Catalog.sqlite` (decoded by triage if
  the reader's question requires per-book detail).

## Read order — start cheap

For "do you have X?" / "is X in my library?", **try the browse index
first**.  No SQLite decode needed:

```python
import json
with open(PROJECT_INDEX) as f:
    idx = json.load(f)
# Field map at idx["field_map"]; entries at idx["entries"][key].
# Try exact key match, then linear scan with norm().
key = next((k for k in idx["entries"]
            if k.lower() == f"{title} - {author}".lower()), None)
```

If you only need to confirm presence + genre + series role + page count
+ goodreads rating, the browse index is enough.  For full detail
(summary, themes, comparable_books, taste_signals, content_flags),
decode the catalog (triage handles this on first need) and query SQLite:

```python
import sqlite3
conn = sqlite3.connect("/tmp/Library_Catalog.sqlite")
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT * FROM books WHERE key = ?", (key,)).fetchone()
themes = [r[0] for r in conn.execute("SELECT theme FROM themes WHERE book_key = ?", (key,))]
comps  = [r[0] for r in conn.execute("SELECT comp_key FROM comparable_books WHERE book_key = ?", (key,))]
flags  = [r[0] for r in conn.execute("SELECT flag FROM content_flags WHERE book_key = ?", (key,))]
sig_p  = [r[0] for r in conn.execute("SELECT signal FROM taste_signals WHERE book_key = ? AND polarity='positive'", (key,))]
sig_n  = [r[0] for r in conn.execute("SELECT signal FROM taste_signals WHERE book_key = ? AND polarity='negative'", (key,))]
```

Or via the helper script for fuzzy matching:

```bash
python3 scripts/librarian_query.py lookup --query "<reader-supplied>" \
    --catalog /tmp/Library_Catalog.sqlite \
    --log $PROJECT_LOG \
    --reading-list /tmp/Reading_List.md
```

`lookup` returns canonical key + `is_already_read` / `is_on_list` /
`is_shown` for each match.  Three-pass fuzzy match handles
subtitle-truncation and series-name searches.

For `is_on_list`, write the artifact's content to
`/tmp/Reading_List.md` first so the helper has a file to read:

```bash
# At session start (or before first list-aware query):
echo "$RL_CONTENT" > /tmp/Reading_List.md   # RL_CONTENT from window.storage
```

## Answer shape

Three components, narrative form:

1. **Personal anchor.**  Name a rated title from `PROJECT_LOG` or a
   stated taste from the profile artifact's content.
2. **Plot / tone hook.**  One or two sentences.
3. **Fit verdict.**  Honest assessment with page count.  Mention
   `audio_suitability` only when the profile flags an audio preference.

Length: 1-3 paragraphs.  Stop there.  If the reader follows up with
"what else like this?", offer to escalate ("want me to put together a
horror batch?") and hand off to `librarian-build-setup` (fresh) or
`librarian-build-batches` (resume).

### "Anything like X?" responses

Pull `comparable_books` for X from SQLite.  For each comp, check the
browse index for presence and run `is-read` / `is-on-list`:

```bash
python3 scripts/librarian_query.py is-read \
    --title "<comp-title>" --author "<comp-author>" --log $PROJECT_LOG
python3 scripts/librarian_query.py is-on-list \
    --title "<comp-title>" --author "<comp-author>" \
    --reading-list /tmp/Reading_List.md
```

Surface 2-4 unread, unreadlisted comps in narrative.  Page counts in
line.

### "Is X worth my time?" responses

Pull X from SQLite + `PROJECT_LOG` + profile artifact content.  Cover:

- Universal exclusion gate clearance (already-read or on-list?).
- Author entry-point status.
- Profile match — name two specific positive indicators that line up
  and one negative that doesn't (if any).
- Page count, audio note when relevant.
- Honest summary: "yes" / "yes but read Y first" / "not for current
  taste — try Z instead".

### "What comes after X in its series?" responses

```bash
python3 scripts/librarian_query.py series-continuation \
    --title "X" --author "<author>" \
    --catalog /tmp/Library_Catalog.sqlite \
    --log $PROJECT_LOG \
    --reading-list /tmp/Reading_List.md
```

If next book in catalog → name it with page count + one-sentence reason
to read on (or pause).  If not → offer cataloguer add.

## Profile updates — per-edit artifact write

When the reader gives a signal worth capturing, append to the profile
artifact same turn.  Read current content, update, write back:

```python
import json, sys, subprocess
# Get current profile content from the model's earlier read:
profile_text = current_profile_content  # already loaded at session start

# Append via helper (stdio mode — pure transformation):
new_text = subprocess.run(
    ["python3", "scripts/librarian_query.py", "profile-append",
     "--section", "Negative indicators",
     "--bullet", "graphic horror in third act (Q&A 2026-05)",
     "--stdio"],
    input=profile_text, capture_output=True, text=True, check=True,
).stdout
```

Then write back to the artifact:

```javascript
await window.storage.set("profile", JSON.stringify({
  version: 1,
  content: new_text,
  updated_at: new Date().toISOString(),
}));
```

Confirm with one chat sentence: "Noted in your profile: <bullet>."

## Hand-off triggers

- Factual catalog correction → `library-cataloguer`.
- Reader escalates from "any like X?" to "actually build me a list" →
  `librarian-build-setup` (fresh) or `librarian-build-batches` (resume).
- Reader bought a new book → `library-cataloguer`.

State the hand-off in one sentence; stop.

## Page count is mandatory

Every named book shows pages.  Format inline: "*Hyperion* — Dan Simmons
(482 pp)".  Two exceptions: upcoming releases without published counts,
and entries where `pages` is null in the catalog (flag the gap, offer
cataloguer fix).
