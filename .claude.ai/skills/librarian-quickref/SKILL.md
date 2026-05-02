---
name: librarian-quickref
description: >
  Answers single-book queries against the reader's library — "anything like
  X?", "is X worth my time?", "what do you know about X?", "what comes after
  X in its series?", "any plans you have on Y?".  Pulls one or two entries
  from the SQLite catalog, gives a 1-3 paragraph answer that fits the book
  to the reader's profile, and writes any signal-capture bullets into
  Profile.md immediately.  Does NOT do batch builds, batch picks, multi-book
  workflows, or catalog edits.
---

# librarian-quickref — single-book mode

Reader asks one focused question.  You give one focused answer.  No
interview, no goals conversation, no batch checklists, no list edits.

## Hard invariants

1. **Triage already verified the picker artifact is published** — but
   quickref doesn't write to `window.storage`, so a publish failure in this
   skill is fine.  Don't run preflight here.
2. **Catalog reads only.**  If the reader hands you a factual catalog
   correction ("actually that's literary fiction, not fantasy"), hand off to
   library-cataloguer same turn.  Don't write to SQLite yourself.
3. **Profile.md per-edit flush.**  Any time you append a bullet to
   Profile.md, immediately write the updated file back to Drive in the
   same turn.  Don't queue Profile writes.
4. **Page count mandatory** in any single-book answer that names a book.
5. **Anti-jargon contract** carries over from the librarian invariants —
   no "ledger", "candidate", "score", "deep cut", "Bk 1", "Phase N",
   "primary_genre", "is-read".  Translate to the reader-facing language map
   before output (see librarian-build-batches/SKILL.md).

## Inputs at session start

`librarian-triage` has already decoded the catalog into
`/tmp/Library_Catalog.sqlite` and downloaded `Reading_Log.csv`,
`Profile.md`, `Reading_List.md` into `/tmp/`.  Quickref reads them via the
helper script:

```bash
python3 scripts/librarian_query.py lookup --query "<reader-supplied>" \
    --catalog /tmp/Library_Catalog.sqlite \
    --log /tmp/Reading_Log.csv \
    --reading-list /tmp/Reading_List.md
```

`lookup` returns canonical key + `is_already_read` / `is_on_list` /
`is_shown` booleans for each match.  Three-pass fuzzy match handles
subtitle-truncation ("Side Jobs" matches "Side Jobs: Stories from the
Dresden Files") and series-name searches ("Cesare Aldo" → all D. V. Bishop
entries).

For the full per-book detail (summary, themes, comparable_books,
taste_signals, content_flags, audio_suitability), open SQLite directly:

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

## Answer shape

Three components, in narrative form (no bullet list, no headings):

1. **Personal anchor.**  Name a rated title from `Reading_Log.csv` or a
   stated taste from `Profile.md`.  ("You rated *The Blacktongue Thief* 5/5,
   and your profile flags 'lyrical grimdark' as a positive…")
2. **Plot / tone hook.**  One or two sentences on what the book is and how
   it lands tonally.
3. **Fit verdict.**  Honest assessment with page count.  Mention
   `audio_suitability` only when the reader's profile flags an audio
   preference.

Length: 1-3 paragraphs.  Stop there — single-book mode is not a runway to a
build session.  If the reader follows up with "what else like this?", that's
when you offer to escalate ("want me to put together a horror batch?") and
hand off to `librarian-build-setup` or `librarian-build-batches` depending
on whether a build is already in progress.

### "Anything like X?" responses

Pull `comparable_books` for X from the catalog.  For each comp, run
`is-read` and `is-on-list` to filter:

```bash
python3 scripts/librarian_query.py is-read --title "<comp-title>" --author "<comp-author>" \
    --log /tmp/Reading_Log.csv
python3 scripts/librarian_query.py is-on-list --title "<comp-title>" --author "<comp-author>" \
    --reading-list /tmp/Reading_List.md
```

Surface 2-4 unread, unreadlisted comps in narrative ("…the closest match in
your library is *Foo* by *Bar*; *Baz* by *Quux* lands in the same lyrical-
grimdark register but with a tighter page count.").  Page counts in line.
Skip the helper's full ranking machinery — for a single-book reply, two or
three good comps from the catalog beat a scored batch.

### "Is X worth my time?" responses

Pull X from SQLite + `Reading_Log.csv` + `Profile.md`.  Cover:

- Whether X clears the universal exclusion gate (already-read or
  on-list?  Then say so and offer comps instead.)
- Author entry-point status (X is mid-series, reader hasn't read author?
  Cite the rule and recommend the entry point if available.)
- Profile match — name two specific positive indicators from `Profile.md`
  that line up, and one negative indicator that doesn't (if any).
- Page count, audio note when relevant.
- Honest summary: "yes, worth it" / "yes but read Y first" / "not for your
  current taste — try Z instead".

### "What comes after X in its series?" responses

```bash
python3 scripts/librarian_query.py series-continuation \
    --title "X" --author "<author>" \
    --catalog /tmp/Library_Catalog.sqlite \
    --log /tmp/Reading_Log.csv \
    --reading-list /tmp/Reading_List.md
```

Helper handles sub-threads (Discworld City Watch, First Law's Age of
Madness).  If the next book is in the catalog, name it with page count and
a one-sentence reason to read on (or pause).  If not, say so and offer to
have the cataloguer add it.

## Profile.md writes — per-edit flush

When the reader gives a signal worth capturing — "I'd actually rather avoid
graphic horror right now", "I loved how slow that one was", "I don't want
another long series" — append to `Profile.md` same turn:

```bash
python3 scripts/librarian_query.py profile-append \
    --section "Negative indicators" \
    --bullet "graphic horror in third act (Q&A 2026-05)" \
    --profile /tmp/Profile.md
```

Or `--stdio` style (read existing Profile from stdin, write updated to
stdout) when the skill mediates the Drive read/write itself:

```bash
echo "$(cat /tmp/Profile.md)" | python3 scripts/librarian_query.py profile-append \
    --section "Negative indicators" \
    --bullet "..." \
    --stdio > /tmp/Profile.md.new
mv /tmp/Profile.md.new /tmp/Profile.md
```

After the in-sandbox file is updated, **flush to Drive same turn** — write
the updated `/tmp/Profile.md` content back to the
`Library-Playground/Profile.md` Drive object.  Do not queue.  Do not wait
for end-of-session.

Confirm with one chat sentence: "Noted in your profile: <bullet>."  Then
keep going.  Per-edit flush keeps the reader's profile durable even if the
session ends abruptly.

## Hand-off triggers

- Factual catalog correction → `library-cataloguer`.  Examples:
  - "Actually that's literary fiction, not fantasy."
  - "The page count on Y is wrong; mine has 540 pages."
  - "There's a graphic content warning that's missing from the entry."
- Reader escalates from "any like X?" to "actually build me a list" →
  `librarian-build-setup` (fresh) or `librarian-build-batches` (resume an
  existing build).
- Reader bought a new book and wants it in the library → `library-
  cataloguer`.

In every case: state the hand-off in one sentence so the reader sees the
skill change ("let me bring in the cataloguer to fix that"), then stop.

## Page count is mandatory

Every named book in the response shows pages.  Format inline: "*Hyperion* —
Dan Simmons (482 pp)".  Two exceptions: upcoming releases without published
counts, and entries where `pages` is null in the catalog (flag the gap and
offer a cataloguer fix).
