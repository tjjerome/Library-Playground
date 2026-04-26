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

For each book you are given, produce a complete catalog entry as a JSON object.

---

CATALOG ENTRY SCHEMA:
{
  "title": "exact title",
  "author": "exact author name(s)",
  "series": "series name or null",
  "series_position": "e.g. Book 1, or null",
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
- indie: true if self-published or originally self-published before traditional pickup
- classic: true if broadly considered classic literature
- taste_signals: map to reader preference signals — e.g. "found family", "propulsive pacing", "morally grey protagonist", "slow meditative pacing", "romance-heavy"
- content_flags: flag only meaningful content warnings — graphic violence, sexual content, necrophilia, animal death, suicide. Do NOT over-flag.
- confidence: High = you know it well. Medium = partial knowledge. Low = limited info or post-training-cutoff.
- status: use "needs_review" when confidence is Low or information is uncertain/conflicting.

WEB SEARCH:
Use web search for any book you don't recognise, are uncertain about, or that appears to postdate your training data. Search for "[Title] [Author] book review" and "[Title] [Author] plot summary genre". Use results to complete the catalog entry. Set research_source to "web_search".

NEVER fabricate plot details or author information. If you genuinely cannot find reliable information after searching, set confidence to "Low" and status to "needs_review", leaving uncertain fields as null.

OUTPUT FORMAT:
After processing all books in the batch, output a single JSON object where each key is "Title - Author" and each value is the complete catalog entry. Wrap it in a markdown code block:

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
    lines = ["Catalogue the following books. Use web search for any you are uncertain about.\n"]
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
