"""
Prompts and response parsing for the library cataloguer.
"""

import json
import re


# ---------------------------------------------------------------------------
# System prompt
# ---------------------------------------------------------------------------

def build_system_prompt() -> str:
    return """You are an expert librarian building a structured knowledge catalog of a personal book library.

For each book you are given, produce a complete catalog entry as a JSON object. You will also audit the tags supplied from the library CSV against your knowledge of the book, flagging any discrepancies.

---

CSV FORMAT & STRUCTURE
The library CSV contains the following fields:
- title: book title
- authors: author name(s)
- genre: the primary genre classification (e.g. Fantasy, Science Fiction, Mystery)
- series: series name if part of a series, otherwise null/empty
- series_position: position in series (e.g. Book 1, Book 3) if applicable
- series_type: one of "Standalone" | "Short Stories" | "Short Series" | "Long Series"
- pubdate: publication date (not required for cataloguing, but may be useful for auditing)
- #pages: page count, calculated from epub data, useful for determining book length and level of commitment to reader
- #goodreads_rating: average Goodreads rating to determine general reception and quality
- #goodreads_reviews: number of Goodreads reviews, to determine popularity and how much information is likely available online for research
- tags: comma-separated values from a controlled vocabulary (see VALID TAGS below)
- goodreads_shelves: original Goodreads shelf data (context, not primary audit target)

CSV TAGS — VALID VALUES (Controlled Vocabulary)
Most tags are derived from Goodreads shelf data. The following values are the only valid tags:
- Status markers: *completed (book finished), *tbr (to-be-read) — these are for reader's own records, not content classification
- Content tags: Aerospace, Biography, Classics, Comics, Competence, Cosmic Horror, Cozy, Cyberpunk, Detective, Dragons, Dystopian, Epic Fantasy, Espionage, First Contact, Hard Sci-Fi, Heist, Historical Fiction, History, Humor, Indie, Legal Thriller, Literary, Monster Hunting, Nautical, Noir, Nonfiction, Post-Apocalyptic, Progression Fantasy, Psychological Thriller, Romance, Sci-Fi Horror, Short Stories, Space Opera, Star Wars, Supernatural Horror, Survival, Sword & Sorcery, Techno-Thriller, Time Travel, Translated, Urban Fantasy, Warhammer, Western, Whodunnit

Note: A book may have multiple valid tags (e.g. "Space Opera, Hard Sci-Fi, First Contact"). Any tag not in this list is invalid and should be flagged as an error.

---

CATALOG ENTRY SCHEMA:
{
  "title": "exact title",
  "author": "exact author name(s)",
  "series": "series name or null",
  "series_position": "e.g. Book 1, or null",
  "genre": "single most accurate genre label",
  "series_status": one of: "Standalone" | "Short Stories" | "Short Series" | "Long Series",
  "pages": integer page count or null,
  "goodreads_rating": float average rating or null,
  "goodreads_reviews": integer review count or null,
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
  "research_source": "training" or "web_search",
  "audit": {
    "passed": true or false,
    "flags": [
      {
        "field": "field name from CSV",
        "csv_value": "what the CSV says",
        "expected_value": "what it should be based on your knowledge",
        "severity": "error" | "warning" | "note",
        "reason": "brief explanation"
      }
    ]
  }
}

CATALOG FIELD DEFINITIONS:
- series_status: Standalone = single book or loosely connected series (e.g. Poirot, Culture, Hainish Cycle). Short Stories = novella <50k words or story collection. Short Series = <4 books OR <600k total words published. Long Series = 4+ books AND 600k+ words published.
- indie: true if self-published or originally self-published before traditional pickup
- classic: true if broadly considered classic literature
- taste_signals: map to reader preference signals — e.g. "found family", "propulsive pacing", "morally grey protagonist", "slow meditative pacing", "romance-heavy"
- content_flags: flag only meaningful content warnings — graphic violence, sexual content, necrophilia, animal death, suicide. Do NOT over-flag.
- confidence: High = you know it well. Medium = partial knowledge. Low = limited info or post-training-cutoff.
- status: use "needs_review" when confidence is Low or information is uncertain/conflicting.

AUDIT FIELD DEFINITIONS:
Check only the fields that were supplied in the CSV for each book. Do not flag missing fields — only flag fields that are present but appear incorrect.

PRIMARY AUDIT TARGETS (priority order):
1. **tags** — Verify each tag is in the valid vocabulary list above. Any tag outside the controlled list is an ERROR.
   - Separate comma-separated values and validate each one independently.
   - Status markers (*completed, *tbr) are valid but are reader records, not content tags.
   - Multiple tags are expected and OK (e.g. "Science Fiction, Hard Sci-Fi, First Contact").
   - Flag invalid tags as errors. Flag obviously wrong tag selections (e.g. book is Literary Fiction but tagged only "Space Opera") as errors/warnings.

2. **genre** — The single primary genre label. Cross-check against your knowledge of the book.
   - ERROR if genre is fundamentally wrong (e.g. books tagged "Fantasy" but it's clearly Science Fiction or Nonfiction).
   - WARNING if the genre is narrow or debatable but not wrong (e.g. book could reasonably be "Mystery" or "Psychological Thriller").
   - NOTE if it's arguable (e.g. "Literary Fiction" vs. "Historical Fiction" for a literary work set in the past).

3. **series_status** — Cross-check the series status against known series structure.
   - Use the series_status field definitions from the CATALOG FIELD DEFINITIONS section below.
   - ERROR if fundamentally wrong (e.g. tagged "Standalone" but the book is actually Book 1 of a 14-book series).
   - WARNING if word count or book count is borderline (e.g. tagged "Short Series" but total published words exceed 600k).

Severity levels (apply to all fields, not just the three above):
- "error": clearly wrong (e.g. invalid tag; genre fundamentally mismatches book; series_status contradicts known series structure)
- "warning": likely wrong or inconsistent (e.g. series_status borderline; tag selection seems odd for the book's content; indie status conflicts with known publisher)
- "note": minor or debatable (e.g. genre could reasonably go either way; classic status is arguable; tag is valid but unusual for this book)

Set audit.passed to false if there are any errors or warnings. Notes alone do not fail the audit.
Set audit.flags to an empty list [] if everything checks out.

WEB SEARCH:
Use web search for any book you don't recognise, are uncertain about, or that appears to postdate your training data. Search for "[Title] [Author] book review" and "[Title] [Author] plot summary genre". Use results to complete both the catalog entry and the audit. Set research_source to "web_search".

NEVER fabricate plot details or author information. If you genuinely cannot find reliable information after searching, set confidence to "Low" and status to "needs_review", leaving uncertain fields as null. In this case, set audit.passed to false and add a note that the entry could not be verified.

OUTPUT FORMAT:
After processing all books in the batch, output a single JSON object where each key is "Title - Author" and each value is the complete catalog entry including the audit field. Wrap it in a markdown code block:

```json
{
  "Title - Author": { ...entry... },
  "Title - Author": { ...entry... }
}
```

Do not include any other text after the JSON block."""


# ---------------------------------------------------------------------------
# Batch prompt
# ---------------------------------------------------------------------------

def build_batch_prompt(books: list[dict]) -> str:
    lines = [
        "Catalogue the following books and audit their CSV fields. "
        "Use web search for any you are uncertain about.\n"
    ]
    for i, book in enumerate(books, 1):
        parts = [f"{i}. {book['title']} by {book['author']}"]
        # Pass through all CSV fields so Claude can audit them
        # Prioritize: tags, genre, series_status (primary audit targets)
        csv_data = {}
        
        # Primary audit targets — pass these first
        for field in ("tags", "genre", "series_status", "series_type"):
            val = book.get(field)
            if val is not None and val != "":
                csv_data[field] = val
        
        # Secondary fields for context
        for field in ("indie", "classic", "series", "goodreads_shelves", "my_tags"):
            val = book.get(field)
            if val is not None and val != "":
                csv_data[field] = val
        
        if csv_data:
            parts.append(f"   CSV data: {json.dumps(csv_data)}")
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
        lines.append("These entries were processed before the audit feature was added, "
                     "or were skipped. Re-run with `--re-audit` to check them.\n")

    return "\n".join(lines)
