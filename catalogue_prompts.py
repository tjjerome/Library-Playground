"""
Prompts and response parsing for the library cataloguer.
"""

import json
import re


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    return """You expert librarian building structured knowledge catalog of personal book library.

For each book given, produce complete catalog entry as JSON object.

---

CATALOG ENTRY SCHEMA:
{
  "title": "exact title",
  "author": "exact author name(s)",
  "series": "series name or null",
  "series_position": "e.g. Book 1, or null",
  "series_role": one of: "standalone" | "first" | "mid" | "late" | "loose-entry" | "loose-mid",
  "author_entry_point": true | false | null,
  "genre": "single most accurate genre label",
  "series_status": one of: "Standalone" | "Short Stories" | "Short Series" | "Long Series",
  "indie": true or false,
  "classic": true or false,
  "status": "complete" or "needs_review",
  "summary": "1-2 sentence spoiler-free plot summary",
  "tone": "brief tone description, e.g. grimdark, propulsive, lyrical, darkly comic",
  "pacing": one of: "Fast" | "Moderate" | "Slow" | "Slow burn with payoff",
  "themes": ["theme1", "theme2", ...],
  "setting": "brief setting description — time, place, world",
  "comparable_books": ["Title - Author", ...],
  "taste_signals": {
    "positive": ["signal1", ...],
    "negative": ["signal1", ...]
  },
  "audio_suitability": one of: "Excellent" | "Good" | "Print preferred" | "Print strongly preferred",
  "audio_notes": "brief reason if Excellent or Print strongly preferred, else null",
  "content_flags": ["flag1", ...],
  "confidence": one of: "High" | "Medium" | "Low",
  "research_source": "training" or "web_search"
}

CATALOG FIELD DEFINITIONS:
- series_status: Standalone = single book or loosely connected series (e.g. Poirot, Culture, Hainish Cycle). Short Stories = novella <50k words or story collection. Short Series = <4 books OR <600k total words published. Long Series = 4+ books AND 600k+ words published.
- series_role: book's role within its series. "standalone" = no series. "first" = Book 1 of a sequential series (intended entry point). "mid" = middle entry of a sequential series. "late" = final or near-final book (spoiler-heavy; reader should not start here). "loose-entry" = book in a loosely-connected series (Discworld, Reacher, Poirot, Culture) that IS a recommended starting point. "loose-mid" = book in a loosely-connected series that depends on accumulated context. Story collections default to "standalone".
- author_entry_point: true if a new-to-this-author reader can start here without missing context; false if the author has a better starting book elsewhere. Heuristics: "first" of an author's flagship series → true. "first" of a secondary series when flagship is elsewhere → usually false. "mid" / "late" / "loose-mid" → false. "loose-entry" → usually true. Standalone with author having other works → judge whether THIS book is a recommended starter. When uncertain, set null.
- indie: true if self-published or originally self-published before traditional pickup
- classic: true if broadly considered classic literature
- taste_signals: map to reader preference signals — e.g. "found family", "propulsive pacing", "morally grey protagonist", "slow meditative pacing", "romance-heavy"
- content_flags: flag only meaningful content warnings — graphic violence, sexual content, necrophilia, animal death, suicide. Do NOT over-flag.
- confidence: High = know it well. Medium = partial knowledge. Low = limited info or post-training-cutoff.
- status: use "needs_review" when confidence is Low or information uncertain/conflicting.

WEB SEARCH:
Use web search for any book you don't recognise, uncertain about, or that postdates training data. Search "[Title] [Author] book review" and "[Title] [Author] plot summary genre". Use results to complete catalog entry. Set research_source to "web_search".

NEVER fabricate plot details or author information. If genuinely no reliable info after searching, set confidence "Low" and status "needs_review", leave uncertain fields null.

OUTPUT FORMAT:
After processing all books in batch, output single JSON object where each key is "Title - Author" and each value is complete catalog entry. Wrap in markdown code block:

```json
{
  "Title - Author": { ...entry... },
  "Title - Author": { ...entry... }
}
```

No other text after JSON block."""


# ---------------------------------------------------------------------------
# Batch prompt
# ---------------------------------------------------------------------------

def build_batch_prompt(books: list[dict]) -> str:
    lines = ["Catalogue these books. Use web search for any uncertain.\n"]
    for i, book in enumerate(books, 1):
        parts = [f"{i}. {book['title']} by {book['author']}"]
        ctx = {}
        for field in ("genre", "series", "series_status", "series_type", "indie", "classic"):
            val = book.get(field)
            if val is not None and val != "":
                ctx[field] = val
        if ctx:
            parts.append(f"   Context: {json.dumps(ctx)}")
        lines.append("\n".join(parts))
    return "\n\n".join(lines)


# ---------------------------------------------------------------------------
# Response parsing
# ---------------------------------------------------------------------------

def parse_catalog_response(raw: str) -> dict:
    """
    Extract the JSON catalog entries from Claude's response.
    Returns a dict of {key: entry} or empty dict on failure.
    """
    # Try to find a JSON code block first
    code_block = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if code_block:
        try:
            return json.loads(code_block.group(1))
        except json.JSONDecodeError:
            pass

    # Fallback: try to find the largest JSON object in the response
    brace_start = raw.find("{")
    brace_end = raw.rfind("}")
    if brace_start != -1 and brace_end != -1:
        try:
            return json.loads(raw[brace_start:brace_end + 1])
        except json.JSONDecodeError:
            pass

    return {}


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

ENTRY_POINT_AUDIT_SYSTEM = """You auditing entry-point fields on a personal-library catalog.

For each book given, return ONLY two fields:

  series_role: one of "standalone" | "first" | "mid" | "late" | "loose-entry" | "loose-mid"
  author_entry_point: true | false | null

DEFINITIONS:

- series_role
  - "standalone": no series at all. series == null.
  - "first": Book 1 of a sequential series (Short Series or Long Series). Intended entry point.
  - "mid": middle entry in a sequential series. Continuation; depends on prior books.
  - "late": final or near-final entry in a long sequential series. Often spoiler-heavy. Reader should NOT start here.
  - "loose-entry": book in a loosely-connected series (Discworld, Reacher, Poirot, Bosch, Culture, Hainish, etc.) that IS a recommended starting point — what fans tell new readers to start with.
  - "loose-mid": book in a loosely-connected series that depends on accumulated context — better entered via a different starting book in the same world.

- author_entry_point
  - true: a new-to-this-author reader can start with THIS book without missing context.
  - false: the author has a better starting book elsewhere in the catalog (or this is a deep-cut, spinoff, or late-series).
  - null: genuinely uncertain — author has multiple starting points and you cannot pick a recommended one without more research.

HEURISTICS:

- "first" of an author's flagship / best-known series → author_entry_point: true.
- "first" of a secondary series when the flagship is elsewhere → author_entry_point: false. Example: Hobb's *Dragon Keeper* is Book 1 of Rain Wild Chronicles, but new Hobb readers start with *Assassin's Apprentice* — so Dragon Keeper is author_entry_point: false.
- "mid" / "late" / "loose-mid" → author_entry_point: false.
- "loose-entry" → usually author_entry_point: true.
- Standalone, author has only this book in catalog → author_entry_point: true.
- Standalone, author has other works → judge whether THIS book is a recommended starter (e.g. King's *The Shining* yes, *The Tommyknockers* no; Vonnegut's *Slaughterhouse-Five* yes, *Galápagos* no).

WEB SEARCH: Use web search when uncertain about loose-connected series ordering or author-flagship judgements. Search "[author] best book to start with" or "[series] reading order entry point".

NEVER fabricate. Set author_entry_point: null when genuinely uncertain.

OUTPUT FORMAT: a single JSON object keyed by "Title - Author", values containing only series_role and author_entry_point. Wrap in a markdown ```json code block.

```json
{
  "Title - Author": {"series_role": "first", "author_entry_point": true},
  "Other Title - Other Author": {"series_role": "loose-mid", "author_entry_point": false}
}
```

No other text outside the block."""


def build_entry_point_audit_system_prompt() -> str:
    return ENTRY_POINT_AUDIT_SYSTEM


def build_entry_point_audit_prompt(entries: list[dict]) -> str:
    """Build the user-message for an entry-point audit chunk.

    `entries` is a list of catalog entry dicts (each carrying its existing
    fields). The prompt asks the LLM to fill series_role + author_entry_point
    only.
    """
    lines = ["Audit these books. Return only series_role and author_entry_point per entry.\n"]
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
