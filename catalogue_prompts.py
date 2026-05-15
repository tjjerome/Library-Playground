"""
Prompts and response parsing for the library cataloguer.

Controlled vocabulary for `taste_signals` and `themes` lives in
`catalogue_vocab.py`. The cataloguer emits closed-vocabulary IDs only —
no free-form fallback. Off-vocab values are stripped by the parser.
"""

import json
import re

from catalogue_vocab import (
    CANONICAL_TASTE_SIGNALS,
    CANONICAL_THEMES,
    format_vocab_for_prompt,
)


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    return f"""You expert librarian building structured knowledge catalog of personal book library.

For each book given, produce complete catalog entry as JSON object.

---

CATALOG ENTRY SCHEMA:
{{
  "title": "exact title",
  "author": "exact author name(s)",
  "series_role": one of: "standalone" | "first" | "mid" | "late" | "loose-entry" | "loose-mid",
  "author_entry_point": true | false | null,
  "primary_genre": "single most accurate genre label",
  "secondary_genre": "second-best genre label, or null",
  "related_series": ["Other Series Name", ...],
  "indie": true or false,
  "classic": true or false,
  "status": "complete" or "needs_review",
  "summary": "1-2 sentence spoiler-free plot summary",
  "tone": "brief tone description, e.g. grimdark, propulsive, lyrical, darkly comic",
  "pacing": one of: "Fast" | "Moderate" | "Slow" | "Slow burn with payoff",
  "themes": ["theme-id", ...],
  "setting": "brief setting description — time, place, world",
  "comparable_books": ["Title - Author", ...],
  "taste_signals": {{
    "positive": ["signal-id", ...],
    "negative": ["signal-id", ...]
  }},
  "audio_suitability": one of: "Excellent" | "Good" | "Print preferred" | "Print strongly preferred",
  "audio_notes": "brief reason if Excellent or Print strongly preferred, else null",
  "content_flags": ["flag1", ...],
  "confidence": one of: "High" | "Medium" | "Low",
  "research_source": "training" or "web_search"
}}

DO NOT EMIT THESE FIELDS — the cataloguer pins them from Library.csv:
  series, series_position, series_status, pages, goodreads_rating, goodreads_reviews.
The CSV-known values are passed to you as Context on each book; trust them.

CATALOG FIELD DEFINITIONS:
- series_role: role within the series the CSV pins. "standalone" = no series (Context.series is null). "first" = Book 1 of a sequential series (entry point). "mid" = middle of a sequential series; needs prior books. "late" = final or near-final of a long sequential series; spoiler-heavy, NOT an entry point. "loose-entry" = loosely-connected series (Discworld, Reacher, Poirot, Culture, Hainish) where THIS book IS a recommended starting point. "loose-mid" = loosely-connected series where THIS book needs prior context (most Hobb prequels, most Discworld City Watch books except Guards! Guards!). Story collections → "standalone".
- author_entry_point: true if a reader new to this author can start here without missing context; false if the author has a better starter elsewhere. Heuristics: "first" of flagship series → true. "first" of a secondary series when the flagship is elsewhere → usually false (Hobb's *Dragon Keeper* is Book 1 of Rain Wild Chronicles, but new Hobb readers start with *Assassin's Apprentice* — Dragon Keeper is author_entry_point: false). "mid" / "late" / "loose-mid" → false. "loose-entry" → usually true. Standalone with other works by author → judge if THIS is the recommended starter. Uncertain → null.
- related_series: list of OTHER series names this book is meaningfully connected to — same shared world, same publisher universe, prequel/sequel chain, or spinoff. Use the canonical series name as it appears elsewhere in the library (e.g. "Discworld", "Star Wars", "Warhammer 40,000", "Realm of the Elderlings"). Empty list if the book has no cross-series ties. Examples: a Star Wars: Thrawn book lists ["Star Wars"]; a Hobb Rain Wild Chronicles book lists ["Realm of the Elderlings", "Farseer Trilogy", "Liveship Traders"]; a Warhammer 40K Horus Heresy book lists ["Warhammer 40,000"]; Discworld City Watch lists ["Discworld"]. NOT for genre similarity — only for explicit world / continuity / spinoff connections.
- primary_genre / secondary_genre: most-accurate label and second-best label. Don't over-narrow ("Epic Fantasy" is fine; "Grimdark Epic Military Fantasy" is not). secondary_genre is null if the book has no meaningful second axis.
- indie: true if the book's first edition was published by anyone OTHER than the Big Five (Penguin Random House, HarperCollins, Simon & Schuster, Hachette, Macmillan) or their imprints. Self-pub, Kickstarter, small press (Koehler, Subterranean, Tachyon, Aethon, Mythoscape, Erewhon, Angry Robot, Solaris, Tor.com originals from before the Macmillan rollup, etc.), university press, and any independent house all qualify as indie. Later trad-pub pickup does NOT undo indie status. A deterministic post-pass flips indie back to false when `goodreads_reviews > 10000` (with series-propagation preserving series identity), so you do NOT need to apply a review-count test yourself — judge purely on the first-edition publisher.
- classic: true if broadly considered classic literature.
- themes: list of theme IDs drawn ONLY from the CONTROLLED VOCABULARY below. 3-7 IDs typical. Pick the IDs that capture the book's recurring concerns. NEVER invent new IDs. NEVER include free-form phrases.
- taste_signals.positive / .negative: lists of signal IDs drawn ONLY from the CONTROLLED VOCABULARY below. Pick the IDs that capture how readers respond to the book. NEVER invent new IDs. NEVER include free-form phrases.
- content_flags: factual claims about content present — graphic violence, sexual content, on-page sexual assault, animal death, suicide. NOT reader triggers. Do NOT over-flag.

CLOSED-VOCABULARY CONTRACT (HARD RULE):
* `themes` and `taste_signals` accept ONLY the IDs listed below. Any output containing strings not on these lists will be stripped before write.
* Don't squeeze book-specific nuance into a free-form string — pick the closest IDs and let the rest go.
* Don't write reader-targeting phrases ("X readers", "X fans", "newcomers", "completionists"). Cataloguer describes the book, not its audience.
* Don't write entry-point markers ("requires prior books", "series conclusion", "cliffhanger ending") into taste_signals — those belong in `series_role` and `author_entry_point`.
* Don't duplicate `content_flags` into taste_signals. Use `content_flags` for factual content presence (graphic violence, sexual content). Use the `disturbing-content` signal ONLY when the texture / register itself is the signal, not the factual presence.

CONTROLLED VOCABULARY — taste_signals (use these IDs only):
{format_vocab_for_prompt(CANONICAL_TASTE_SIGNALS)}

CONTROLLED VOCABULARY — themes (use these IDs only):
{format_vocab_for_prompt(CANONICAL_THEMES)}

CATALOG SCOPE — HARD RULE:
Catalog holds objective facts, public reception, and context. NEVER write reader sentiment ("I loved this"), the reader's per-book rating, or personal preferences into any catalog field. Those belong in Profile.md or Reading_Log.csv. Translate sentiment-flavored language into objective form before writing.
- confidence: High = know it well. Medium = partial knowledge. Low = limited info or post-training-cutoff.
- status: use "needs_review" when confidence is Low or information uncertain/conflicting.

WEB SEARCH:
Use web search for any book you don't recognise, are uncertain about, or that postdates training data. Search "[Title] [Author] book review" and "[Title] [Author] plot summary genre". Use the CSV-pinned series, position, and series_status as ground truth — don't search to override them. Set research_source to "web_search".

NEVER fabricate plot details or author information. If genuinely no reliable info after searching, set confidence "Low" and status "needs_review", leave uncertain fields null.

OUTPUT FORMAT:
After processing all books in batch, output single JSON object where each key is "Title - Author" and each value is complete catalog entry. Wrap in markdown code block:

```json
{{
  "Title - Author": {{ ...entry... }},
  "Title - Author": {{ ...entry... }}
}}
```

No other text after JSON block."""


# ---------------------------------------------------------------------------
# Batch prompt
# ---------------------------------------------------------------------------

# Fields the cataloguer pins from Library.csv. Surfaced in each book's prompt
# Context block so the model treats them as fixed facts and doesn't try to
# rewrite them. Keep in sync with `catalogue.CSV_AUTHORITATIVE_FIELDS`.
_CSV_PINNED_CONTEXT_FIELDS = (
    "series",
    "series_position",
    "series_status",
    "pages",
    "goodreads_rating",
    "primary_genre",  # CSV's genre tag, surfaced as a hint
)


def build_batch_prompt(books: list[dict]) -> str:
    lines = ["Catalogue these books. Use web search for any uncertain.\n"]
    for i, book in enumerate(books, 1):
        parts = [f"{i}. {book['title']} by {book['author']}"]
        ctx: dict = {}
        for field in _CSV_PINNED_CONTEXT_FIELDS:
            val = book.get(field)
            if val is not None and val != "":
                ctx[field] = val
        # Surface CSV genre hint under a dedicated key so the model doesn't
        # confuse it with the canonical primary_genre it must produce.
        if "primary_genre" in ctx:
            ctx["csv_genre_hint"] = ctx.pop("primary_genre")
        if ctx:
            parts.append(
                f"   Context (CSV-pinned, do not override series triple): "
                f"{json.dumps(ctx)}"
            )
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

_ALLOWED_SIGNAL_IDS = frozenset(CANONICAL_TASTE_SIGNALS)
_ALLOWED_THEME_IDS = frozenset(CANONICAL_THEMES)


def _enforce_closed_vocab(entry: dict) -> None:
    """Strip off-vocab IDs from `taste_signals` and `themes` in place.

    Mutates `entry` so downstream upsert can't write free-form drift even
    if the model ignored the prompt's instructions. Logs nothing — the
    cataloguer's chunk loop already prints the keys it couldn't place.
    """
    ts = entry.get("taste_signals")
    if isinstance(ts, dict):
        new_ts = {}
        for polarity in ("positive", "negative"):
            seen: set[str] = set()
            cleaned: list[str] = []
            for v in (ts.get(polarity) or []):
                if isinstance(v, str) and v in _ALLOWED_SIGNAL_IDS and v not in seen:
                    seen.add(v)
                    cleaned.append(v)
            new_ts[polarity] = cleaned
        entry["taste_signals"] = new_ts
    elif "taste_signals" in entry:
        entry["taste_signals"] = {"positive": [], "negative": []}

    themes = entry.get("themes")
    if isinstance(themes, list):
        seen_t: set[str] = set()
        cleaned_t: list[str] = []
        for v in themes:
            if isinstance(v, str) and v in _ALLOWED_THEME_IDS and v not in seen_t:
                seen_t.add(v)
                cleaned_t.append(v)
        entry["themes"] = cleaned_t
    elif "themes" in entry:
        entry["themes"] = []

    # Old shape leftovers — drop entirely. The new schema has no
    # *_canonical fields; if a model emits them anyway, ignore.
    entry.pop("taste_signals_canonical", None)
    entry.pop("themes_canonical", None)


def parse_catalog_response(raw: str) -> dict:
    """
    Extract the JSON catalog entries from Claude's response.
    Returns a dict of {key: entry} or empty dict on failure.

    Closed-vocab enforcement: each entry's `taste_signals` and `themes`
    fields are filtered to the canonical-ID allowlist before return, so
    no off-vocab string ever reaches the catalog.
    """
    parsed: dict | None = None
    # Try to find a JSON code block first
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if code_block:
        try:
            parsed = json.loads(code_block.group(1))
        except json.JSONDecodeError:
            parsed = None

    # Fallback: try to find the largest JSON object in the response
    if parsed is None:
        brace_start = raw.find("{")
        brace_end = raw.rfind("}")
        if brace_start != -1 and brace_end != -1:
            try:
                parsed = json.loads(raw[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                parsed = None

    if not parsed:
        return {}

    for entry in parsed.values():
        if isinstance(entry, dict):
            _enforce_closed_vocab(entry)
    return parsed


# ---------------------------------------------------------------------------
# Comparable-books ranking prompt
# ---------------------------------------------------------------------------

def build_ranking_prompt(sources: list, *, candidate_summary) -> str:
    """Prompt asking Claude to pick the top 6 comparable_books for each source.

    `sources` is a list of dicts:
        {"key": <source_key>, "entry": <source_entry>, "candidates": [(key, entry), ...]}
    `candidate_summary(key, entry) -> str` formats one candidate line.
    """
    intro = (
        "You pruning oversized `comparable_books` lists in personal-library "
        "catalog. For each source book below, pick 6 candidates with "
        "strongest appeal overlap with source — same vibe, same kind of "
        "reader payoff, similar themes/tone/pacing. Genre alignment strong "
        "but not absolute signal. Return exactly 6 keys per source, in ranked "
        "order (strongest first).\n\n"
        "OUTPUT FORMAT: single JSON object mapping each source key to its "
        "ranked list of 6 chosen candidate keys, wrapped in ```json code "
        "block. No commentary outside block.\n\n"
        "CRITICAL: Use EXACT keys shown below — every key in "
        "`Title - Author` form. Don't shorten to title only, don't "
        "rephrase, don't normalise punctuation. Both source-key "
        "(JSON object key) and chosen candidate keys (JSON array "
        "values) must match strings shown verbatim, character-for-"
        "character. Picks that don't match candidate list verbatim "
        "get dropped.\n\n"
        "Example output shape:\n"
        "```json\n"
        "{\n"
        '  "The Hobbit - J.R.R. Tolkien": [\n'
        '    "The Lord of the Rings - J.R.R. Tolkien",\n'
        '    "The Eye of the World - Robert Jordan",\n'
        '    "Earthsea - Ursula K. Le Guin",\n'
        '    "The Belgariad - David Eddings",\n'
        '    "Mistborn - Brandon Sanderson",\n'
        '    "Discworld - Terry Pratchett"\n'
        "  ]\n"
        "}\n"
        "```\n"
    )

    blocks = []
    for s in sources:
        e = s["entry"]
        themes = ", ".join(e.get("themes") or [])
        positive = ", ".join((e.get("taste_signals") or {}).get("positive") or [])
        meta_lines = [
            f"Source: {s['key']}",
            f"  primary_genre: {e.get('primary_genre') or e.get('genre') or ''}",
            f"  tone: {e.get('tone') or ''}",
            f"  pacing: {e.get('pacing') or ''}",
            f"  setting: {e.get('setting') or ''}",
            f"  themes: {themes}",
            f"  taste_signals.positive: {positive}",
            "",
            f"Candidates ({len(s['candidates'])}):",
        ]
        for i, (ck, ce) in enumerate(s["candidates"], 1):
            meta_lines.append(f"  {i}. {candidate_summary(ck, ce)}")
        blocks.append("\n".join(meta_lines))

    return intro + "\n\n" + ("\n\n---\n\n".join(blocks)) + "\n"


def parse_ranking_response(raw: str) -> dict:
    """Extract {source_key: [candidate_key, ...]} from Claude's ranking response.

    Returns {} on failure. Caller is responsible for validating list length
    and that picks are in the source's candidate set.
    """
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start != -1 and brace_end != -1:
        try:
            return json.loads(raw[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass

    return {}


# ---------------------------------------------------------------------------
# Audit report
# ---------------------------------------------------------------------------

def generate_audit_report(catalog: dict) -> str:
    """
    Generate a human-readable audit report from the catalog.
    Returns a markdown string.
    """
    errors = []
    warnings = []
    notes = []
    clean = []
    unverified = []

    for key, entry in catalog["entries"].items():
        audit = entry.get("audit")
        if not audit:
            unverified.append(key)
            continue

        flags = audit.get("flags", [])
        if not flags:
            clean.append(key)
            continue

        for flag in flags:
            row = {
                "book": key,
                "field": flag.get("field", ""),
                "csv_value": flag.get("csv_value", ""),
                "expected_value": flag.get("expected_value", ""),
                "reason": flag.get("reason", "")
            }
            sev = flag.get("severity", "note")
            if sev == "error":
                errors.append(row)
            elif sev == "warning":
                warnings.append(row)
            else:
                notes.append(row)

    lines = [
        "# Library CSV Audit Report\n",
        f"**Generated:** {catalog.get('last_updated', 'unknown')}  ",
        f"**Total entries:** {len(catalog['entries'])}  ",
        f"**Clean:** {len(clean)}  ",
        f"**Errors:** {len(errors)}  ",
        f"**Warnings:** {len(warnings)}  ",
        f"**Notes:** {len(notes)}  ",
        f"**Not yet audited:** {len(unverified)}  \n",
    ]

    def format_flags(items, heading):
        if not items:
            return []
        out = [f"\n## {heading}\n"]
        for r in items:
            out.append(f"**{r['book']}**")
            out.append(f"- Field: `{r['field']}`")
            out.append(f"- CSV says: `{r['csv_value']}`")
            out.append(f"- Expected: `{r['expected_value']}`")
            out.append(f"- Reason: {r['reason']}\n")
        return out

    lines += format_flags(errors, "🔴 Errors (clearly wrong)")
    lines += format_flags(warnings, "🟡 Warnings (likely wrong)")
    lines += format_flags(notes, "🔵 Notes (minor / debatable)")

    if unverified:
        lines.append(f"\n## ⚪ Not Yet Audited ({len(unverified)} entries)")
        lines.append("Entries processed before audit feature added, "
                     "or skipped. Re-run with `--re-audit` to check.\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry-point audit prompt (series_role + author_entry_point backfill)
# ---------------------------------------------------------------------------

ENTRY_POINT_AUDIT_SYSTEM = """You auditing entry-point fields on personal-library catalog.

For each book, return ONLY two fields:

  series_role: one of "standalone" | "first" | "mid" | "late" | "loose-entry" | "loose-mid"
  author_entry_point: true | false | null

DEFINITIONS:

- series_role
  - "standalone": no series. series == null.
  - "first": Book 1 of sequential series (Short Series or Long Series). Entry point.
  - "mid": middle of sequential series. Continuation; needs prior books.
  - "late": final or near-final of long sequential series. Spoiler-heavy. NOT entry.
  - "loose-entry": loosely-connected series (Discworld, Reacher, Poirot, Bosch, Culture, Hainish) that IS recommended starting point — what fans tell new readers.
  - "loose-mid": loosely-connected book needing prior context — better entered via different starter in same world.

- author_entry_point
  - true: new-to-this-author reader can start with THIS without missing context.
  - false: author has better starter elsewhere (or this is deep-cut, spinoff, late-series).
  - null: uncertain — author has multiple starters and you can't pick recommended one without research.

HEURISTICS:

- "first" of flagship / best-known series → author_entry_point: true.
- "first" of secondary series when flagship elsewhere → author_entry_point: false. Example: Hobb's *Dragon Keeper* is Book 1 of Rain Wild Chronicles, but new Hobb readers start with *Assassin's Apprentice* — Dragon Keeper is author_entry_point: false.
- "mid" / "late" / "loose-mid" → author_entry_point: false.
- "loose-entry" → usually author_entry_point: true.
- Standalone, author has only this book in catalog → author_entry_point: true.
- Standalone, author has other works → judge if THIS is recommended starter (King's *The Shining* yes, *The Tommyknockers* no; Vonnegut's *Slaughterhouse-Five* yes, *Galápagos* no).

WEB SEARCH: Use when uncertain about loose-connected ordering or author-flagship judgements. Search "[author] best book to start with" or "[series] reading order entry point".

NEVER fabricate. Set author_entry_point: null when uncertain.

OUTPUT FORMAT: single JSON object keyed by "Title - Author", values containing only series_role and author_entry_point. Wrap in markdown ```json block.

```json
{
  "Title - Author": {"series_role": "first", "author_entry_point": true},
  "Other Title - Other Author": {"series_role": "loose-mid", "author_entry_point": false}
}
```

No text outside block."""


def build_entry_point_audit_system_prompt() -> str:
    return ENTRY_POINT_AUDIT_SYSTEM


def build_entry_point_audit_prompt(entries: list[dict]) -> str:
    """Build the user-message for an entry-point audit chunk.

    `entries` is a list of catalog entry dicts (each carrying its existing
    fields). The prompt asks the LLM to fill series_role + author_entry_point
    only.
    """
    lines = ["Audit these books. Return series_role and author_entry_point per entry.\n"]
    for i, e in enumerate(entries, 1):
        ctx = {
            "title": e.get("title"),
            "author": e.get("author"),
            "series": e.get("series"),
            "series_position": e.get("series_position"),
            "series_status": e.get("series_status"),
            "primary_genre": e.get("primary_genre"),
        }
        # also surface peer books by the same author so the LLM can compare
        peers = e.get("_author_peers") or []
        line = f"{i}. {ctx['title']} by {ctx['author']}\n   Context: {json.dumps(ctx)}"
        if peers:
            line += f"\n   Other books by this author in catalog: {json.dumps(peers)}"
        lines.append(line)
    return "\n\n".join(lines)


def parse_entry_point_response(raw: str) -> dict:
    """Extract {key: {series_role, author_entry_point}} from Claude's audit response."""
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start != -1 and brace_end != -1:
        try:
            return json.loads(raw[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass
    return {}


# ---------------------------------------------------------------------------
# Canonicalisation backfill — map distinct free-form signals/themes to
# canonical vocab IDs in bulk. One LLM call per batch of distinct strings,
# applied across every entry that uses them.
# ---------------------------------------------------------------------------

CANONICALIZE_SYSTEM_PROMPT_TEMPLATE = """You normalising free-form {label} into canonical IDs from controlled vocabulary.

Each input is a free-form phrase from a librarian's per-book annotations. Your job: pick the single canonical ID from the list below that best captures the same idea, or return null if no canonical fits closely. NEVER invent new IDs. NEVER pick more than one.

CONTROLLED VOCABULARY:
{vocab}

OUTPUT FORMAT: single JSON object mapping each input phrase (verbatim, character-for-character) to either a canonical ID string from the vocabulary or null. Wrap in ```json block. No commentary outside the block.

Example:
```json
{{
  "lyrical grimdark prose": "lyrical-prose",
  "found family bond": "found-family",
  "an extremely specific phrase that doesn't match anything": null
}}
```
"""


def build_canonicalize_system_prompt(label: str, vocab: dict[str, str]) -> str:
    """Build the system prompt for the signal-or-theme canonicalisation pass.

    `label` is "taste signals" or "themes" — used in the opening sentence.
    `vocab` is the canonical dict from `catalogue_vocab`.
    """
    from catalogue_vocab import format_vocab_for_prompt
    return CANONICALIZE_SYSTEM_PROMPT_TEMPLATE.format(
        label=label,
        vocab=format_vocab_for_prompt(vocab),
    )


def build_canonicalize_prompt(phrases: list[str]) -> str:
    """Build the user-message listing the free-form phrases to map."""
    listing = "\n".join(f"- {p}" for p in phrases)
    return f"Map each of these phrases to a canonical ID or null.\n\n{listing}\n"


def parse_canonicalize_response(raw: str, allowed_ids: set[str]) -> dict[str, str | None]:
    """Extract {phrase: canonical_id_or_None} from Claude's response.

    Drops any mappings that picked an ID outside `allowed_ids` — defensive
    against the model inventing IDs despite the instructions.
    """
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    obj: dict = {}
    if code_block:
        try:
            obj = json.loads(code_block.group(1))
        except json.JSONDecodeError:
            obj = {}
    if not obj:
        brace_start = raw.find("{")
        brace_end = raw.rfind("}")
        if brace_start != -1 and brace_end != -1:
            try:
                obj = json.loads(raw[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                return {}

    cleaned: dict[str, str | None] = {}
    for phrase, value in obj.items():
        if value is None:
            cleaned[phrase] = None
        elif isinstance(value, str) and value in allowed_ids:
            cleaned[phrase] = value
        else:
            # Hallucinated or off-vocab — drop silently; caller treats it
            # the same as "no canonical mapping known yet".
            cleaned[phrase] = None
    return cleaned


# ---------------------------------------------------------------------------
# Library.csv genre re-audit — LLM judges whether the CSV's #genre column
# captures each book's primary axis correctly. Output is advisory; the
# operator reviews the diff before applying.
# ---------------------------------------------------------------------------

LIBRARY_GENRE_AUDIT_SYSTEM = """You auditing the `#genre` column on a personal-library CSV. The current values are coarse and several are wrong (e.g., epic SF tagged Fantasy because the spreadsheet's tag scheme conflated them).

For each book, pick the single most accurate primary genre label. Use these labels — they're broad on purpose:
  Fantasy | Science Fiction | Horror | Mystery | Thriller | Crime | Literary Fiction | Historical Fiction | Romance | Western | Nonfiction | Memoir | Biography | Poetry | Short Stories | Drama | Young Adult | Middle Grade | Children's | Graphic Novel

Pick the SINGLE label that best captures what kind of book this is. When a book mixes (a literary horror novel, a YA fantasy), pick the strongest axis — usually the one most readers shelf it under. Web search when uncertain.

OUTPUT FORMAT: single JSON object mapping "Title - Author" to the chosen genre label, wrapped in a ```json block. No commentary outside the block.

```json
{
  "Title - Author": "Science Fiction",
  "Other Title - Other Author": "Literary Fiction"
}
```
"""


def build_library_genre_audit_system_prompt() -> str:
    return LIBRARY_GENRE_AUDIT_SYSTEM


def build_library_genre_audit_prompt(books: list[dict]) -> str:
    """User prompt for the Library.csv genre audit. `books` carry title,
    author, current_genre, more_tags."""
    lines = ["Audit the primary genre for each book. Use the existing tags as hints; "
             "they are NOT authoritative.\n"]
    for i, b in enumerate(books, 1):
        ctx = {
            "title": b.get("title"),
            "author": b.get("author"),
            "current_genre": b.get("current_genre"),
            "tag_hints": b.get("tag_hints") or "",
            "series": b.get("series") or None,
        }
        lines.append(f"{i}. {b['title']} by {b['author']}\n   Context: {json.dumps(ctx)}")
    return "\n\n".join(lines)


def parse_library_genre_audit_response(raw: str) -> dict[str, str]:
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start != -1 and brace_end != -1:
        try:
            return json.loads(raw[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass
    return {}


# ---------------------------------------------------------------------------
# pub_year audit — first-publication year, not edition / reprint year
# ---------------------------------------------------------------------------

PUB_YEAR_AUDIT_SYSTEM = """You auditing first-publication years for a personal-library catalog.

For each book, return the year the WORK was first published. NOT the year of the edition the reader owns. NOT a paperback reissue date. The CSV's pubdate is sometimes a republication / edition / re-release timestamp; cross-check.

Examples:
* Aldous Huxley's *Brave New World* — return 1932 even if CSV says 2010.
* Jane Austen's *Pride and Prejudice* — return 1813.
* Octavia Butler's *Kindred* — return 1979.
* For series volumes published as a single book later, return the year that volume first appeared in print.

Use web search when uncertain. Set value to null only if you genuinely cannot establish the year.

OUTPUT FORMAT: single JSON object mapping "Title - Author" to integer year (or null), wrapped in ```json. No commentary outside the block.

```json
{
  "Brave New World - Aldous Huxley": 1932,
  "The Martian - Andy Weir": 2011,
  "Some Obscure Book - Author": null
}
```
"""


def build_pub_year_audit_system_prompt() -> str:
    return PUB_YEAR_AUDIT_SYSTEM


def build_pub_year_audit_prompt(books: list[dict]) -> str:
    """User prompt: title, author, current pub_year guess (from CSV pubdate)."""
    lines = ["Verify the first-publication year for each book. CSV pubdate is "
             "shown as the current guess and is unreliable for older works.\n"]
    for i, b in enumerate(books, 1):
        ctx = {
            "title": b.get("title"),
            "author": b.get("author"),
            "csv_pub_year_guess": b.get("csv_pub_year_guess"),
        }
        lines.append(f"{i}. {b['title']} by {b['author']}\n   Context: {json.dumps(ctx)}")
    return "\n\n".join(lines)


def parse_pub_year_audit_response(raw: str) -> dict[str, int | None]:
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    obj: dict = {}
    if code_block:
        try:
            obj = json.loads(code_block.group(1))
        except json.JSONDecodeError:
            obj = {}
    if not obj:
        brace_start = raw.find("{")
        brace_end = raw.rfind("}")
        if brace_start != -1 and brace_end != -1:
            try:
                obj = json.loads(raw[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                return {}
    out: dict[str, int | None] = {}
    for k, v in obj.items():
        if v is None:
            out[k] = None
        elif isinstance(v, int) and 1000 <= v <= 2100:
            out[k] = v
        elif isinstance(v, str):
            try:
                yi = int(v)
                if 1000 <= yi <= 2100:
                    out[k] = yi
            except ValueError:
                pass
    return out


# ---------------------------------------------------------------------------
# indie audit — was the book originally self-published?
# ---------------------------------------------------------------------------

INDIE_AUDIT_SYSTEM = """You auditing indie status of books in a personal-library catalog.

For each book, return TRUE if the book's FIRST EDITION was published by anyone other than one of the Big Five publishers — Penguin Random House, HarperCollins, Simon & Schuster, Hachette, Macmillan — or their imprints. Later pickup by a Big Five publisher does NOT undo indie status; only the first edition's publisher matters.

Indie includes (return TRUE):
* Self-pub: KDP / Smashwords / Patreon / author website / SPFBO entry / Kickstarter / Royal Road serial.
  - Andy Weir, *The Martian*; Hugh Howey, *Wool*; Anthony Ryan, *Blood Song*; Michael J. Sullivan, *Riyria*; Brandon Sanderson Kickstarter Secret Projects.
* Independent publishers — houses NOT owned by a Big Five parent. Treat the following as indie: Koehler Books, Subterranean Press, Tachyon, Small Beer Press, Aethon Books, Mythoscape, Erewhon, Angry Robot, Solaris, Rebellion, Titan, Saga Press (when independent), Kensington, Sourcebooks, Soho Press, Akashic, Coffee House Press, Graywolf, Tin House, Two Dollar Radio, New Directions, university presses, regional small presses.
* Imprints of independent houses: Aconyte (Asmodee), Black Library (Games Workshop), Caezik / Arc Manor, Baen (independent), DAW (was independent until 2022 — first editions before the PRH acquisition count as indie).
* Translation editions where the original-language publisher was indie.

Return FALSE only if the FIRST edition was a Big Five imprint:
* PRH imprints: Knopf, Doubleday, Random House, Penguin, Viking, Dutton, Riverhead, Ace, Roc, Del Rey, Spectra, Ballantine, Crown, Bantam, Berkley, Putnam, Anchor, Vintage, Dial, Pantheon.
* HarperCollins imprints: Harper, Harper Voyager, William Morrow, HarperOne, Avon, Ecco, Mariner, Custom House, Amistad.
* Simon & Schuster imprints: Scribner, Atria, Touchstone, Gallery, S&S itself, Saga Press (post-2014).
* Hachette imprints: Grand Central, Little Brown, Orbit, Mulholland, Hyperion, Hachette Books.
* Macmillan imprints: Tor / Tor.com / Tordotcom, Forge, Henry Holt, FSG, St. Martin's, Picador, Flatiron, Minotaur.
* Scholastic is independent — TRUE.
* Bloomsbury is independent — TRUE.
* Hard Case Crime (Titan) — TRUE.

Return null only when you genuinely cannot establish first-edition publisher after web search.

**CRITICAL — the FIRST edition's publisher is the ONLY thing that matters.** Do NOT base your answer on whichever publisher is easiest to find. Web searches for older / niche / late-series-volume books often surface reissues, collector editions, audio originals, hardcover-club editions, or omnibus reprints — those are NOT the first edition. The first edition is the original publication of the work, identified on the copyright page of the earliest printing. If you cannot find evidence of the first edition specifically, return null — do NOT fall back to whichever indie publisher you happened to find a reprint from.

**Common reprint-only indie houses to NOT mistake for first-edition publishers:**
* University of Chicago Press (Donald Westlake / Richard Stark Parker reprints originally Pocket Books → Big Five)
* Hard Case Crime (Lawrence Block, Donald Westlake, Stephen King reprints — many original eds were Dell/Avon/Morrow → Big Five)
* Subterranean Press collector editions (most are limited reprints of trad-pub originals)
* Centipede Press, Suntup Editions, PS Publishing (luxury/limited reprints)
* NYRB Classics (literary reprints of older trad work)
* Library of America (canonical reprints)
* Folio Society (luxury reprints)
* Open Road Media (ebook reprints of mid-century paperback originals)
* Mysterious Press (mixed — independent now, but many of their reissues started elsewhere)

**Anti-pattern to avoid:** an Agatha Christie / Ellis Peters / Patrick O'Brian / Ursula K. Le Guin / Gene Wolfe / Lawrence Block / Donald Westlake book is essentially never indie regardless of which reprint house re-issued a particular late-career volume. The first editions of those authors were Collins / Macmillan / Norton / Harper / Tor / Dell / Pocket → all Big Five. Return FALSE for these authors' work unless you have positive evidence that one specific title's first edition was indie.

The reader's library has many small-press and indie books with low review counts (often new authors with one or two books). Do NOT default to FALSE just because the publisher name sounds traditional — but equally, do NOT default to TRUE just because a low-review-count book has an indie reprint floating around. Verify the FIRST edition.

A deterministic post-pass downstream applies the review-count ceiling and series-propagation rules — you do NOT need to think about review counts or series identity. Judge purely on the first-edition publisher.

OUTPUT FORMAT: single JSON object mapping "Title - Author" to true / false / null, wrapped in ```json. No commentary outside the block.

```json
{
  "The Martian - Andy Weir": true,
  "Some Trad Book - Author": false,
  "Obscure Title - Unknown Author": null
}
```
"""


def build_indie_audit_system_prompt() -> str:
    return INDIE_AUDIT_SYSTEM


def build_indie_audit_prompt(books: list[dict]) -> str:
    lines = ["Audit indie status. Candidates here have <=10k Goodreads "
             "reviews and were previously tagged indie=false under a "
             "narrower (self-pub-only) definition. Re-evaluate under the "
             "Big-Five-imprint rule: TRUE if first-edition publisher is "
             "NOT a Big Five imprint. Verify each.\n"]
    for i, b in enumerate(books, 1):
        ctx = {
            "title": b.get("title"),
            "author": b.get("author"),
            "goodreads_reviews": b.get("goodreads_reviews"),
            "current_indie": b.get("current_indie"),
            "series": b.get("series"),
        }
        lines.append(f"{i}. {b['title']} by {b['author']}\n   Context: {json.dumps(ctx)}")
    return "\n\n".join(lines)


def parse_indie_audit_response(raw: str) -> dict[str, bool | None]:
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    obj: dict = {}
    if code_block:
        try:
            obj = json.loads(code_block.group(1))
        except json.JSONDecodeError:
            obj = {}
    if not obj:
        brace_start = raw.find("{")
        brace_end = raw.rfind("}")
        if brace_start != -1 and brace_end != -1:
            try:
                obj = json.loads(raw[brace_start:brace_end + 1])
            except json.JSONDecodeError:
                return {}
    out: dict[str, bool | None] = {}
    for k, v in obj.items():
        if v is None:
            out[k] = None
        elif isinstance(v, bool):
            out[k] = v
    return out
