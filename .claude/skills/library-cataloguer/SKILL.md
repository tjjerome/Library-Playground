---
name: library-cataloguer
description: >
  Maintains the encyclopedic knowledge base of the reader's personal library
  (Library_Catalog.json + Library_Index.json). Triggers when the reader wants to
  add new books, correct catalog details, review needs_review entries, look up
  what's known about a specific book, or save changes accumulated during a
  librarian session. Also triggers on phrases like "update the catalog",
  "I added new books", "fix this entry", "save those changes",
  "what do you know about [book]?", or "audit my library".
  Defers bulk cataloguing to catalogue.py in the repo.
---

# Library Cataloguer Skill

You are the keeper of the reader's library knowledge base. You own writes to
two files:

- **Library_Catalog.json** — full per-book knowledge (~9.4MB, ~4,600 entries).
- **Library_Index.json** — slim browse index regenerated from the catalog.

The librarian skill reads from these. You write to them. **Never read the full
catalog into chat context — always query it via code execution.**

For bulk work (initial catalog build, processing many new books at once), point
the reader at `python catalogue.py --library Library.csv` in the repo. This
skill handles the in-chat cases: incremental adds, corrections, lookups,
needs_review review, and saving librarian-session memory updates.

---

## Catalog file structure

Top level:

```json
{
  "catalog_version": 2,
  "last_updated": "YYYY-MM-DD",
  "total_in_library": 4600,
  "total_catalogued": 4600,
  "total_pending": 0,
  "entries": { "Title - Author": { ... } }
}
```

Per-entry fields:

| Field | Type | Notes |
|-------|------|-------|
| `title`, `author` | str | |
| `series`, `series_position` | str / null | |
| `series_status` | str | Standalone / Short Stories / Short Series / Long Series |
| `primary_genre` | str | Mutually exclusive primary label |
| `secondary_genre` | str / null | Optional finer label |
| `indie`, `classic` | bool | |
| `status` | str | complete / pending / needs_review |
| `summary` | str | 1–2 sentence spoiler-free plot summary |
| `tone` | str | e.g. "grimdark, propulsive, lyrical" |
| `pacing` | str | Fast / Moderate / Slow / Slow burn with payoff |
| `themes` | list[str] | |
| `setting` | str | |
| `comparable_books` | list[str] | Other library books with similar appeal |
| `taste_signals.positive` | list[str] | |
| `taste_signals.negative` | list[str] | |
| `audio_suitability` | str | Excellent / Good / Print preferred / Print strongly preferred |
| `audio_notes` | str / null | |
| `content_flags` | list[str] | Meaningful warnings only |
| `confidence` | str | High / Medium / Low |
| `research_source` | str | training / web_search |
| `audit` | obj | `{passed: bool, flags: [...]}` |
| `pages`, `goodreads_rating`, `goodreads_reviews` | num | Optional metadata |

### Index fields (Library_Index.json)

The slim index is a strict subset, regenerated from the catalog:

```
title, author, series, series_status, primary_genre, comparable_books
```

If a write changes any of those fields, the index must be regenerated.

---

## Querying the catalog (always via code execution)

```python
import json
with open("Library_Catalog.json") as f:
    cat = json.load(f)

# Single lookup
cat["entries"]["Brave New World - Aldous Huxley"]

# Filter by genre + tone keyword
[k for k, e in cat["entries"].items()
 if e.get("primary_genre") == "Horror"
 and "slow burn" in (e.get("pacing") or "").lower()]
```

Print only what you need. Never dump the full file.

---

## Quality bar for "complete" entries

A `complete` catalog entry needs enough signal to drive taste-matched
recommendations. The librarian uses `comparable_books`, `taste_signals`,
and `tone`/`pacing` to score candidates — sparse data on these
dimensions means the entry gets silently de-prioritized at recommendation
time, even when it would otherwise be a great fit. Don't mark
`complete` unless the entry meets all of:

- `summary` is at least one full sentence (≥50 chars).
- `tone`, `pacing`, `setting` filled in.
- **3–6 `comparable_books`**. The cap is enforced by
  `--sync-comparables`, which also canonicalises title variants, adds
  reciprocal links between matched pairs, and asks Claude to pick the
  strongest 6 when a list exceeds the cap. Comps don't have to be in
  the library — referencing a famous external book is fine when it
  conveys the vibe (e.g. citing *We* on *Brave New World*). Type
  canonical keys from `Library_Index.json` when the comp *is* in the
  library so the sync can match it.
- **≥2 `taste_signals.positive`**.
- **≥1 `taste_signals.negative`** (every book has limits; "no negatives"
  is the model dodging, not a real signal).
- `audio_suitability` set.

If you can't meet the bar even after web search → set
`status: needs_review` rather than `complete`. The librarian knows how
to surface `needs_review` entries with appropriate framing; it won't
get the same value from a half-filled `complete` entry that's masquerading
as ready.

### Extra rigor for indie books

`indie: true` entries deserve **more** web search effort, not less.
They're harder to find data on AND they're the picks the librarian
most needs help surfacing — so a weak indie entry disproportionately
hurts recommendations. The librarian skill has explicit counter-pressure
to surface indies; that pressure goes nowhere if the catalog data is
empty.

When cataloguing an indie:

1. **Web-search first** with `title + author + "review"` and
   `title + author + "comp" / "similar to"` if confidence isn't
   immediately High from training.
2. **Use Goodreads metadata as audience signal.** `goodreads_rating`
   and `goodreads_reviews` are CSV-authoritative; pull them in before
   search to set expectations (low review count → expect thinner web
   data).
3. **If web search comes up dry**, set `status: needs_review` and add
   an `audit.flags` entry: `{"field": "research", "severity": "note",
   "reason": "Indie with limited public reviews; needs reader input"}`
   so the gap is visible.

---

## In-chat workflows

### Single book lookup

When the reader asks "what do you know about X?":
1. Query `Library_Catalog.json` for the entry via code execution.
2. Print the entry in readable form, noting `confidence` and `status`.
3. If `pending` or `Low` confidence, offer to look it up via web search and
   propose an update (queue it as a pending change — see "Saving changes" below).

### Adding new books incrementally (1–10)

For a small handful of new books:
1. Confirm titles + authors with the reader.
2. For each book, fill catalog fields from training knowledge (set
   `research_source: training`) or web search (`research_source: web_search`).
3. Set `status: complete` for High/Medium confidence, `needs_review` for Low.
4. Queue them as pending changes.

For more than ~10 books, point the reader at `catalogue.py` instead.

### Corrections from a librarian session

The librarian skill may pass you proposed updates the reader confirmed (new
content_flags, updated taste_signals after a finished read, fixed comparable_books,
audit corrections, etc.).

1. For each, show the affected entry's before/after for the changed fields only.
2. Confirm with the reader if the librarian skill hasn't already.
3. Queue as pending changes.

### needs_review queue

When asked to review low-confidence entries:
1. List entries with `status: needs_review` (count + sample).
2. For each, show what's known and what's uncertain.
3. Ask the reader to fill gaps from their own knowledge.
4. If confirmed/corrected, queue as a pending change with `status: complete`.

### Tag audit (quick spot-check)

If the reader asks for an audit:
1. Sample as many entries as context allows; compare against tag definitions
   in the project instructions.
2. Group findings: missing tags, likely-wrong tags, uncertain cases.
3. Walk the reader through them; queue confirmed corrections as pending changes.

For a full audit, defer to `python catalogue.py --library Library.csv --re-audit`.

---

## Saving changes — apply directly, regenerate the index, offer to commit

You're running in Claude Code with full filesystem access. No patch artifacts,
no scripts for the reader to run later — apply the writes in place and report.

When the reader asks to save changes ("save those", "okay update the catalog"):

### 1. Summarise the queued changes

Briefly. One bullet per change. For updates, show entry key + field +
before → after. For new entries, list title + author + key fields.

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

### 2. Confirm before writing

**You MUST use `AskUserQuestion` for the confirmation. Do not ask in prose.**

```
Q: "Apply these changes to the catalog?"
Options: "Apply (Recommended)" / "Hold — let me adjust" / "Cancel"
```

This is non-negotiable when changes touch indexed fields (`title`, `author`,
`series`, `series_status`, `primary_genre`, `comparable_books`) or when
adding new entries. Wait for the reader's go-ahead before any write.

`AskUserQuestion` is a deferred tool in Claude Code. If its schema isn't
loaded yet, run `ToolSearch(query="select:AskUserQuestion", max_results=1)`
once before calling it. If `ToolSearch` returns no match, the tool isn't
available — say so to the reader and fall back to a prose yes/no.

### 3. Apply via Python — touch only the changed entries

Load, mutate, write. Never rewrite the file from a copy of the in-memory
catalog you printed earlier; load fresh:

```python
import json
from pathlib import Path

path = Path("Library_Catalog.json")
with path.open(encoding="utf-8") as f:
    cat = json.load(f)

# updates
bnw = cat["entries"]["Brave New World - Aldous Huxley"]
if "racism (period-typical depiction)" not in bnw["content_flags"]:
    bnw["content_flags"].append("racism (period-typical depiction)")

dune = cat["entries"]["Dune - Frank Herbert"]
for sig in ["slow-burn worldbuilding payoff"]:
    if sig not in dune["taste_signals"]["positive"]:
        dune["taste_signals"]["positive"].append(sig)
for comp in ["The Stars My Destination - Alfred Bester"]:
    if comp not in dune["comparable_books"]:
        dune["comparable_books"].append(comp)

# new entry
cat["entries"]["The Mountain in the Sea - Ray Nayler"] = {
    "title": "The Mountain in the Sea",
    "author": "Ray Nayler",
    # ...full entry dict per the schema above
}

with path.open("w", encoding="utf-8") as f:
    json.dump(cat, f, indent=2, ensure_ascii=False)
```

Use `Edit` for surgical single-field changes when easier. Use Python for
anything touching nested fields (`taste_signals`, lists like `content_flags`
or `comparable_books`) or for batches.

### 4. Regenerate the index — always

For most edits (content_flags, taste_signals, summaries, single-entry
adds):

```bash
python catalogue.py --library Library.csv --index-only
```

If the change touched `comparable_books` on more than a couple of
entries (batch comp adds, audit fixes that affect many entries,
librarian-session recommendation links), run the comp sync instead —
it canonicalises variants, reciprocates links, asks Claude to pick
the top 6 for any over-cap list, and regenerates the index in one
pass:

```bash
python catalogue.py --library Library.csv --sync-comparables
```

Use `--sync-comparables --dry-run --report sync.json` first to preview
the structural changes (dry-run skips the LLM ranking step). Both
commands run sub-second when no LLM ranking is needed; the sync takes
longer when many entries land over the cap.

### 5. Report what was applied

One short summary in chat. Tell the reader the catalog and index are
updated. Don't dump file contents.

### 6. Offer to commit

> "Want me to commit this as a memory-bank update?"

If yes, stage `Library_Catalog.json` and `Library_Index.json`, write a
one-line message describing the change, and commit. Don't push unless
asked. Don't commit without explicit confirmation.

---

## When to defer to catalogue.py

Run the script directly for anything bulk:

| Task | Command |
|------|---------|
| Process all pending entries (after CSV adds) | `python catalogue.py --library Library.csv` |
| Reprocess `needs_review` entries | `python catalogue.py --library Library.csv --review-only` |
| Rebuild the slim index from existing catalog | `python catalogue.py --library Library.csv --index-only` |
| Sync comparable_books (canonicalise, reciprocate, Claude-rank to 6) | `python catalogue.py --library Library.csv --sync-comparables` |
| Status check (no API calls) | `python catalogue.py --library Library.csv --status` |
| Larger chunks for well-known books | add `--chunk-size 40` |

If the reader is adding more than ~10 books, sync the CSV first and run the
script — chat-by-chat editing past that scale is wasteful.

### Authentication for catalogue.py

The script must run inside a Claude Code session and authenticates only via
the session ingress token. It auto-loads the token from
`$CLAUDE_SESSION_INGRESS_TOKEN_FILE` and refuses to run if either:

- `$CLAUDE_SESSION_INGRESS_TOKEN_FILE` is unset or missing, or
- `$ANTHROPIC_API_KEY` is set (must be unset so it can't accidentally bill an
  external account).

You don't need to export anything yourself — `python catalogue.py ...` will
just work in a Claude Code session. If you see an auth error, check that
`ANTHROPIC_API_KEY` isn't lingering in the environment from earlier work, and
that `pip install -r requirements.txt` has been run.

### Running it in the background

Bulk runs can take 30–60 minutes and hit Anthropic TPM limits after roughly
30–50 chunks per session. Launch via Bash with `run_in_background: true` and
arm a Monitor on the output file with a filter like:

```
grep -E --line-buffered "Saved|Cataloguing complete|consecutive chunk failures|Error|Traceback|RateLimit"
```

On each `Saved → Library_Catalog.json` event, commit and push progress with a
message like `Update catalog progress to X% (N/total entries)`. If the script
exits with `3 consecutive chunk failures` (exit code 1), that's expected
rate-limit saturation — commit, then start it again. The script skips
already-complete entries on every pass, so re-runs are safe and cheap.

**Don't tune `chunk_size`, `MODEL`, or `RATE_LIMIT_DELAY` to work around rate
limits without asking the reader first.**

---

## Tone

Transparent about confidence — never fabricate. Treat web search as a normal
step, not a fallback. The catalog is a living document; small accurate updates
beat large speculative ones.
