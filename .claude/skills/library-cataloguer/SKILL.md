---
name: library-cataloguer
description: >
  Maintains encyclopedic knowledge base of reader's personal library
  (Library_Catalog.json + Library_Index.json). Triggers when reader want
  add new books, correct catalog details, review needs_review entries, look up
  specific book, or save changes from librarian session. Also triggers on
  phrases like "update the catalog", "I added new books", "fix this entry",
  "save those changes", "what do you know about [book]?", "audit my library".
  Defers bulk cataloguing to catalogue.py in repo.
---

# Library Cataloguer Skill

You = keeper of reader's library knowledge base. Own writes to two files:

- **Library_Catalog.json** — full per-book knowledge (~9.4MB, ~4,600 entries).
- **Library_Index.json** — slim browse index regenerated from catalog.

Librarian skill reads. You write. **Never read full catalog into chat context — always query via code execution.**

Bulk work (initial build, many new books): point reader at `python catalogue.py --library Library.csv`. This skill handles in-chat: incremental adds, corrections, lookups, needs_review review, saving librarian-session memory updates.

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
| `series_role` | str / null | standalone / first / mid / late / loose-entry / loose-mid. **See "Entry-point fields" below.** |
| `author_entry_point` | bool / null | True = recommended starting point with this author for a new reader. **See "Entry-point fields" below.** |
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

Slim index = strict subset, regenerated from catalog:

```
title, author, series, series_status, series_role, author_entry_point, primary_genre, comparable_books
```

Write touches any of those fields → index must regenerate.

---

## Entry-point fields — `series_role` and `author_entry_point`

Both fields give librarian skill **structural** answer to "good place to start with this author?" — replaces conservative `series_position == "Book 1"` fallback. Default `null` on existing entries; populated by `python catalogue.py --audit-entry-points` and on every newly catalogued book.

### `series_role` — book's role within its series

| Value | Meaning |
|---|---|
| `"standalone"` | Truly standalone book. `series == null`. |
| `"first"` | Book 1 of a sequential series (Short Series / Long Series). Intended entry point. |
| `"mid"` | Middle entry of sequential series. Needs prior books. |
| `"late"` | Final or near-final book. Often spoiler-heavy. Don't start here. |
| `"loose-entry"` | Book in loosely-connected series (Discworld, Reacher, Poirot, Bosch, Culture, Hainish, etc.) that IS recommended entry point — what fans tell new readers to start with. |
| `"loose-mid"` | Book in loosely-connected series that depends on accumulated context — better entered via recommended starting book in same world. |

Trivially-derivable cases audit script fills without LLM call:

- `series_status == "Standalone"` AND `series == null` → `"standalone"`.
- `series_status in ("Short Series", "Long Series")` AND `series_position` matches `"Book 1"` (case-insensitive prefix, no decimal) → `"first"` (provisional; LLM may upgrade rare cases).
- `series_status in ("Short Series", "Long Series")` AND `series_position` doesn't match Book 1 → `"mid"` (LLM may promote some to `"late"`).
- `series_status == "Short Stories"` → `"standalone"` (story collections entry-agnostic).

LLM-only cases:

- `series_status == "Standalone"` AND `series != null` (loosely-connected, e.g. Discworld, Reacher) → `"loose-entry"` or `"loose-mid"` based on whether THIS book is recommended starting point.
- Any case where `series_position` includes annotations (`"Book 1 of loosely connected series"`, `"Book 2 (prequel)"`, `"1.5"`) needs LLM judgement.

### `author_entry_point` — recommended starting point with this author

Boolean. `true` if new-to-this-author reader can start here without missing context. `false` if author has better starting book elsewhere in catalog (or this is deep-cut / spinoff / late-series).

Heuristics:

- Author has only one book in catalog → almost always `true`.
- Book is `series_role: "first"` of author's flagship / best-known series → `true`.
- Book is `series_role: "first"` of secondary series when flagship is elsewhere → usually `false` (e.g. *Dragon Keeper* is Book 1 of Rain Wild Chronicles, but Hobb's flagship entry is *Assassin's Apprentice*).
- Book is `series_role: "mid" | "late" | "loose-mid"` → `false`.
- Book is `series_role: "loose-entry"` → usually `true`.
- Standalone with author having other works → judge whether THIS book is recommended starter (e.g. *The Shining* yes, *The Tommyknockers* no).

When uncertain: set `author_entry_point: null` and add `audit.flags` entry `{"field": "author_entry_point", "severity": "note", "reason": "..."}`. Null valid — librarian's conservative fallback (`series_position == "Book 1"`) covers it.

### Cataloguing new books

Every new entry via `catalogue.py` or in-chat MUST include both fields. Use heuristics above. When in doubt for `author_entry_point`, leave `null` rather than fabricating.

### Bulk audit of existing entries

Run `python catalogue.py --audit-entry-points` to fill fields on existing entries. Pass:

1. Auto-derives trivial cases without LLM cost.
2. Sends ambiguous entries (loose-connected; cross-author entry-point judgement) to LLM in chunks, same as `catalogue_chunk` for new entries.
3. Saves catalog and regenerates slim index.

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

Print only what needed. Never dump full file.

---

## Quality bar for "complete" entries

`complete` entry needs enough signal to drive taste-matched recommendations. Librarian uses `comparable_books`, `taste_signals`, `tone`/`pacing` to score candidates — sparse data = entry silently de-prioritized at recommendation time. Don't mark `complete` unless all met:

- `summary` at least one full sentence (≥50 chars).
- `tone`, `pacing`, `setting` filled.
- **3–6 `comparable_books`**. Cap enforced by `--sync-comparables`, which canonicalises title variants, adds reciprocal links between matched pairs, asks Claude to pick strongest 6 when list exceeds cap. Comps don't have to be in library — referencing famous external book fine when it conveys vibe (e.g. citing *We* on *Brave New World*). Type canonical keys from `Library_Index.json` when comp *is* in library so sync can match it.
- **≥2 `taste_signals.positive`**.
- **≥1 `taste_signals.negative`** (every book has limits; "no negatives" = model dodging, not real signal).
- `audio_suitability` set.

Can't meet bar even after web search → set `status: needs_review` not `complete`. Librarian knows how to surface `needs_review`; gets no value from half-filled `complete` entry masquerading as ready.

### Extra rigor for indie books

`indie: true` entries deserve **more** web search, not less. Harder to find data AND picks librarian most needs help surfacing — weak indie entry disproportionately hurts recommendations. Librarian has explicit counter-pressure to surface indies; pressure goes nowhere if catalog data empty.

When cataloguing indie:

1. **Web-search first** with `title + author + "review"` and `title + author + "comp" / "similar to"` if confidence not immediately High from training.
2. **Use Goodreads metadata as audience signal.** `goodreads_rating` and `goodreads_reviews` CSV-authoritative; pull before search to set expectations (low review count → expect thinner web data).
3. **If web search dry**, set `status: needs_review` and add `audit.flags` entry: `{"field": "research", "severity": "note", "reason": "Indie with limited public reviews; needs reader input"}` so gap visible.

---

## In-chat workflows

### Single book lookup

Reader asks "what do you know about X?":
1. Query `Library_Catalog.json` via code execution.
2. Print entry readable, note `confidence` and `status`.
3. If `pending` or `Low` confidence, offer web search and propose update (queue as pending change — see "Saving changes" below).

### Adding new books incrementally (1–10)

Small handful:
1. Confirm titles + authors with reader.
2. For each book, fill catalog fields from training knowledge (`research_source: training`) or web search (`research_source: web_search`).
3. Set `status: complete` for High/Medium confidence, `needs_review` for Low.
4. Queue as pending changes.

More than ~10 books → point reader at `catalogue.py`.

### Corrections from a librarian session

Librarian skill may pass proposed updates reader confirmed (new content_flags, updated taste_signals after finished read, fixed comparable_books, audit corrections, etc.).

1. Show affected entry's before/after for changed fields only.
2. Confirm with reader if librarian skill hasn't already.
3. Queue as pending changes.

### needs_review queue

When asked to review low-confidence entries:
1. List entries with `status: needs_review` (count + sample).
2. For each, show what known and what uncertain.
3. Ask reader to fill gaps from own knowledge.
4. If confirmed/corrected, queue as pending change with `status: complete`.

### Tag audit (quick spot-check)

Reader asks for audit:
1. Sample as many entries as context allows; compare against tag definitions in project instructions.
2. Group findings: missing tags, likely-wrong tags, uncertain cases.
3. Walk reader through them; queue confirmed corrections as pending changes.

Full audit → defer to `python catalogue.py --library Library.csv --re-audit`.

---

## Saving changes — apply directly, regenerate the index, offer to commit

Running in Claude Code with full filesystem access. No patch artifacts, no scripts for reader to run later — apply writes in place and report.

Reader asks to save ("save those", "okay update the catalog"):

### 1. Summarise the queued changes

Brief. One bullet per change. Updates: entry key + field + before → after. New entries: title + author + key fields.

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

**Must use `AskUserQuestion` for confirmation. Do not ask in prose.**

```
Q: "Apply these changes to the catalog?"
Options: "Apply (Recommended)" / "Hold — let me adjust" / "Cancel"
```

Non-negotiable when changes touch indexed fields (`title`, `author`, `series`, `series_status`, `primary_genre`, `comparable_books`) or when adding new entries. Wait for reader go-ahead before any write.

`AskUserQuestion` is deferred tool in Claude Code. If schema not loaded, run `ToolSearch(query="select:AskUserQuestion", max_results=1)` once before calling. If `ToolSearch` returns no match, tool not available — tell reader and fall back to prose yes/no.

### 3. Apply via Python — touch only the changed entries

Load, mutate, write. Never rewrite from copy of in-memory catalog printed earlier; load fresh:

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

Use `Edit` for surgical single-field changes when easier. Use Python for nested fields (`taste_signals`, lists like `content_flags` or `comparable_books`) or batches.

### 4. Regenerate the index — always

Most edits (content_flags, taste_signals, summaries, single-entry adds):

```bash
python catalogue.py --library Library.csv --index-only
```

Change touched `comparable_books` on more than a couple entries (batch comp adds, audit fixes affecting many entries, librarian-session recommendation links) → run comp sync instead — canonicalises variants, reciprocates links, asks Claude to pick top 6 for over-cap lists, regenerates index in one pass:

```bash
python catalogue.py --library Library.csv --sync-comparables
```

Use `--sync-comparables --dry-run --report sync.json` first to preview structural changes (dry-run skips LLM ranking step). Both commands run sub-second when no LLM ranking needed; sync takes longer when many entries over cap.

### 5. Report what was applied

One short summary in chat. Tell reader catalog and index updated. Don't dump file contents.

### 6. Offer to commit

> "Want me to commit this as a memory-bank update?"

If yes, stage `Library_Catalog.json` and `Library_Index.json`, write one-line message describing change, commit. Don't push unless asked. Don't commit without explicit confirmation.

---

## When to defer to catalogue.py

Run script directly for anything bulk:

| Task | Command |
|------|---------|
| Process all pending entries (after CSV adds) | `python catalogue.py --library Library.csv` |
| Reprocess `needs_review` entries | `python catalogue.py --library Library.csv --review-only` |
| Rebuild the slim index from existing catalog | `python catalogue.py --library Library.csv --index-only` |
| Sync comparable_books (canonicalise, reciprocate, Claude-rank to 6) | `python catalogue.py --library Library.csv --sync-comparables` |
| Backfill `series_role` + `author_entry_point` on existing entries | `python catalogue.py --library Library.csv --audit-entry-points` |
| Status check (no API calls) | `python catalogue.py --library Library.csv --status` |
| Larger chunks for well-known books | add `--chunk-size 40` |

Reader adding more than ~10 books → sync CSV first and run script. Chat-by-chat editing past that scale wasteful.

### Authentication for catalogue.py

Script must run inside Claude Code session; authenticates only via session ingress token. Auto-loads from `$CLAUDE_SESSION_INGRESS_TOKEN_FILE` and refuses to run if either:

- `$CLAUDE_SESSION_INGRESS_TOKEN_FILE` unset or missing, or
- `$ANTHROPIC_API_KEY` set (must be unset so it can't accidentally bill external account).

No export needed — `python catalogue.py ...` just works in Claude Code session. Auth error → check `ANTHROPIC_API_KEY` not lingering in environment and `pip install -r requirements.txt` has been run.

### Running it in the background

Bulk runs take 30–60 minutes and hit Anthropic TPM limits after ~30–50 chunks per session. Launch via Bash with `run_in_background: true` and arm Monitor on output file with filter like:

```
grep -E --line-buffered "Saved|Cataloguing complete|consecutive chunk failures|Error|Traceback|RateLimit"
```

On each `Saved → Library_Catalog.json` event, commit and push progress with message like `Update catalog progress to X% (N/total entries)`. Script exits with `3 consecutive chunk failures` (exit code 1) → expected rate-limit saturation — commit, then restart. Script skips already-complete entries on every pass; re-runs safe and cheap.

**Don't tune `chunk_size`, `MODEL`, or `RATE_LIMIT_DELAY` to work around rate limits without asking reader first.**

---

## Tone

Transparent about confidence — never fabricate. Treat web search as normal step, not fallback. Catalog = living document; small accurate updates beat large speculative ones.