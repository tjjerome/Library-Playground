---
name: librarian-quickref
description: >
  Single-book query handler. Ask "anything like X?", "worth time?",
  "what come after X?", "any plans on Y?". Query SQLite direct, give
  1-3 para answer fit to reader profile, append signals to /tmp/Profile.md.
  No batch builds, no multi-book, no catalog edits.
---

# librarian-quickref — single-book mode

Reader ask one question. Give one answer. No interview, no goals talk, no batch, no list edits.

## Hard invariants

1. **Catalog reads only.**  Reader correct catalog ("actually literary fiction, not fantasy") → hand to library-cataloguer same turn.
2. **Profile edits write to `/tmp/Profile.md` silently.**  Append bullet via helper; surface consolidated diff in one sentence at turn end (see "Profile updates").
3. **Page count mandatory** when naming any book.
4. **Anti-jargon contract** — see translation map in
   `librarian-build/SKILL.md`.

## Inputs at session start

Triage bound:

- `PROJECT_LOG` → path to `Reading_Log.csv` in project knowledge.
- `/tmp/Profile.md` → seeded from `PROJECT_PROFILE` (or empty stub).
- `/tmp/Reading_List.md` → seeded from `PROJECT_LIST` (or empty stub).
- Decoded SQLite at `/tmp/Library_Catalog.sqlite` (decoded by triage at
  session start — always present by the time quickref runs).

## Catalog reads

All reads through SQLite. Presence checks, structured lookups, full per-book detail (summary, themes, comparable_books, taste_signals, content_flags) — query direct:

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

Or fuzzy match inline. `webhelper/librarian_query.py` exposes `norm`
for normalization (same function the build skills query against);
use it from the helper as a CLI step or import directly:

```bash
python3 webhelper/librarian_query.py norm "<reader-supplied>"
```

```python
import sqlite3, sys
sys.path.insert(0, "scripts")
from librarian_query import norm

conn = sqlite3.connect("/tmp/Library_Catalog.sqlite")
conn.row_factory = sqlite3.Row
q = norm(reader_supplied)
rows = conn.execute(
    "SELECT * FROM books "
    "WHERE title_normalized LIKE ? OR author_normalized LIKE ? "
    "LIMIT 5",
    (f"%{q}%", f"%{q}%"),
).fetchall()
```

Cross-check against `PROJECT_LOG` (already-read) and
`/tmp/Reading_List.md` (already-on-list) inline when it matters for
the answer.

## Answer shape

Three parts, narrative form:

1. **Personal anchor.**  Name rated title from `PROJECT_LOG` or stated taste from `/tmp/Profile.md`.
2. **Plot / tone hook.**  One or two sentences.
3. **Fit verdict.**  Honest with page count. Mention
   `audio_suitability` only when profile flag audio preference.

Length: 1-3 paragraphs. Stop. If reader ask "what else like this?", offer escalate and hand to `librarian-build-setup` (fresh) or
`librarian-build` (resume).

### "Anything like X?" responses

Pull `comparable_books` for X from SQLite. For each comp, check
already-read and already-on-list inline using normalized
title/author pairs:

```python
import csv, sys
sys.path.insert(0, "scripts")
from librarian_query import norm

read_pairs = set()
with open(PROJECT_LOG) as f:
    for r in csv.DictReader(f):
        if r.get("title") and r.get("authors"):
            read_pairs.add((norm(r["title"]), norm(r["authors"])))

list_text = open("/tmp/Reading_List.md").read()
on_list = lambda t, a: f"{t} — {a}" in list_text or f"{t}—{a}" in list_text
```

Surface 2-4 unread + not-on-list comps in narrative. Page counts inline.

### "Is X worth my time?" responses

Pull X from SQLite + `PROJECT_LOG` + `/tmp/Profile.md`. Cover:

- Exclusion gate (already read or on list?).
- Author entry-point status.
- Profile match — two specific positive signals that line up, one negative that doesn't (if any).
- Page count, audio note when relevant.
- Honest summary: "yes" / "yes but read Y first" / "not for current taste — try Z instead".

### "What comes after X in its series?" responses

```bash
python3 scripts/librarian_query.py series-fit \
    --series "<series name>" \
    --catalog /tmp/Library_Catalog.sqlite \
    --log $PROJECT_LOG \
    --reading-list /tmp/Reading_List.md
```

`series-fit` returns the full book list with page counts and
`series_role`, the series' narrative shape (one arc / loose subseries
/ dip-in), and a recommended scope. For a quickref answer, surface
the next unread book with page count and one sentence on whether to
keep going (or pause). Not found in catalog → offer cataloguer add.

## Profile updates — append to /tmp/Profile.md

Signal worth capturing → append to `/tmp/Profile.md` same turn via
direct file write. The `profile-append` helper subcommand was retired
during the recomposition; markdown editing is two lines of Python:

```python
from pathlib import Path

p = Path("/tmp/Profile.md")
text = p.read_text()
section = "## Negative indicators"
bullet = "- graphic horror in third act (Q&A 2026-05)"
if section not in text:
    text += f"\n\n{section}\n"
if bullet not in text:
    text = text.rstrip() + f"\n{bullet}\n"
    p.write_text(text)
```

No artifact write; no `window.storage`.

**Silent during answer.**  No mid-answer announcement. End of response, one consolidated sentence covering all profile writes from this turn, e.g.:

> "Profile updated: two notes (graphic-horror ceiling, audio pref for first-person narrators). Session end → download link to refresh `Profile.md` in project knowledge."

One sentence, end-of-turn. No mid-answer interruption.

## Hand-off triggers

- Factual catalog correction → `library-cataloguer`.
- Reader escalate to "actually build me a list" →
  `librarian-build-setup` (fresh) or `librarian-build` (resume).
- Reader bought new book → `library-cataloguer`.
- Session wrap + any profile edits → hand to `library-cataloguer` session-end to surface `/tmp/Profile.md` download.

State hand-off in one sentence; stop.

## Page count is mandatory

Every named book show pages. Format inline: "*Hyperion* — Dan Simmons
(482 pp)". Two exceptions: upcoming releases without published counts; entries where `pages` is null in catalog (flag gap, offer cataloguer fix).