#!/usr/bin/env python3
"""
Library Cataloguer
Autonomously builds Library_Catalog.json from a Library CSV.
Designed to run in Claude Code without requiring human approval between chunks.

Usage:
    python catalogue.py --library Library.csv
    python catalogue.py --library Library.csv --chunk-size 40
    python catalogue.py --library Library.csv --status
    python catalogue.py --library Library.csv --review-only  # reprocess needs_review entries

Requirements:
    pip install -r requirements.txt
    Must be run inside a Claude Code session — authenticates via the session
    ingress token at $CLAUDE_SESSION_INGRESS_TOKEN_FILE. Refuses to run if
    ANTHROPIC_API_KEY is set (to avoid accidental external billing).
"""

import argparse
import csv
import datetime as _datetime
import json
import os
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CATALOG_FILE = "Library_Catalog.json"
INDEX_FILE = "Library_Index.json"
MODEL = "claude-sonnet-4-6"
MAX_TOKENS = 16000
DEFAULT_CHUNK_SIZE = 20
RATE_LIMIT_DELAY = 10    # seconds between API calls
MAX_RETRIES = 3

COMPARABLES_CAP = 6
RANKING_BATCH_SIZE = 10        # over-cap entries per LLM call
RANKING_CANDIDATE_LIMIT = 25   # pre-trim safeguard before LLM ranking

WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search"
}

# ---------------------------------------------------------------------------
# Catalog I/O
# ---------------------------------------------------------------------------

def load_catalog(path: str) -> dict:
    if Path(path).exists():
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return {
        "catalog_version": 2,
        "last_updated": str(date.today()),
        "total_in_library": 0,
        "total_catalogued": 0,
        "total_pending": 0,
        "entries": {}
    }


def save_catalog(catalog: dict, path: str):
    catalog["last_updated"] = str(date.today())
    entries = catalog["entries"]
    catalog["total_in_library"] = len(entries)
    catalog["total_catalogued"] = sum(
        1 for e in entries.values() if e.get("status") in ("complete", "needs_review")
    )
    catalog["total_pending"] = sum(
        1 for e in entries.values() if e.get("status") == "pending"
    )
    with open(path, "w", encoding="utf-8") as f:
        json.dump(catalog, f, indent=2, ensure_ascii=False)


# Fields kept in the slim index. Everything else (summary, themes, comparables,
# taste_signals, audit, etc.) is fetched on demand from the full catalog via
# code execution so it never sits in the project's auto-loaded context.
INDEX_FIELDS = (
    "title",
    "author",
    "series",
    "series_status",
    "series_role",
    "author_entry_point",
    "primary_genre",
    "comparable_books",
)


def build_index(catalog: dict) -> dict:
    slim_entries = {}
    for key, entry in catalog["entries"].items():
        slim_entries[key] = {f: entry.get(f) for f in INDEX_FIELDS}
    return {
        "index_version": 1,
        "last_updated": str(date.today()),
        "total": len(slim_entries),
        "fields": list(INDEX_FIELDS),
        "note": "Slim browse index. For summary/themes/comparables/taste_signals, query Library_Catalog.json via code execution.",
        "entries": slim_entries,
    }


def save_index(catalog: dict, path: str):
    index = build_index(catalog)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(index, f, ensure_ascii=False, separators=(",", ":"))


def book_key(title: str, author: str) -> str:
    return f"{title.strip()} - {author.strip()}"


_QUOTE_NORMALIZE = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-",
    "​": "", "‌": "", "‍": "", "﻿": "",
})


def normalize_key(s: str) -> str:
    return " ".join(s.translate(_QUOTE_NORMALIZE).lower().split())


def resolve_canonical_key(
    raw: str,
    catalog_keys: set,
    normalized_index: dict,
) -> str | None:
    """Return the canonical catalog key for a raw key string, or None.

    Strict variant: exact match, then normalize_key fallback. No substring
    matching — that's only safe inside catalogue_chunk's upsert path.
    """
    if raw in catalog_keys:
        return raw
    return normalized_index.get(normalize_key(raw))

# ---------------------------------------------------------------------------
# Library CSV loading
# ---------------------------------------------------------------------------

def load_library(csv_path: str) -> list[dict]:
    books = []
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            book = {k.strip().lower(): v.strip() for k, v in row.items() if v}
            if book.get("title") and book.get("authors"):
                books.append(book)
    return books


# Library.csv is the source of truth for these fields. The cataloguer
# never asks the LLM for them and never lets stale catalog values stand:
# every sync re-applies whatever the CSV currently says.
#
# - pages / goodreads_rating / goodreads_reviews: numerics from the export.
# - series / series_position / series_status: structural facts about where
#   a book sits in a series. The CSV's `series`, `series_index`, and
#   `#series_type` columns carry these — the model used to be asked for
#   them and would occasionally invent ordering or misclassify length.
#   Treating them as authoritative pins the answer to the source data.
CSV_AUTHORITATIVE_FIELDS = (
    "pages",
    "goodreads_rating",
    "goodreads_reviews",
    "series",
    "series_position",
    "series_status",
)


def _format_series_position(raw: str | None) -> str | None:
    """Convert a CSV `series_index` value to a `series_position` string.

    "1.0" -> "Book 1"; "4.5" -> "Book 4.5"; "0" / "" / None -> None.
    """
    if raw is None or raw == "":
        return None
    try:
        f = float(raw)
    except (TypeError, ValueError):
        return None
    if f <= 0:
        return None
    if f.is_integer():
        return f"Book {int(f)}"
    # Preserve fractional positions for novellas (e.g. Book 4.5).
    return f"Book {f:g}"


def csv_authoritative_values(book: dict) -> dict:
    """Pull CSV-authoritative fields out of a Library.csv row.

    Numerics return only when the CSV provides a parseable value, so a silent
    column doesn't clobber existing catalog data.

    The series triple (series / series_position / series_status), by contrast,
    is *always* emitted — an empty `series` column is itself authoritative
    ("this book is not part of a series, regardless of what the catalog
    currently says"). That keeps the catalog from drifting when the reader
    corrects a series tag in the CSV.
    """
    out: dict = {}

    pages = book.get("#pages")
    if pages:
        try:
            out["pages"] = int(float(pages))
        except (TypeError, ValueError):
            pass

    grvotes = book.get("#grvotes")
    if grvotes:
        try:
            out["goodreads_reviews"] = int(float(grvotes))
        except (TypeError, ValueError):
            pass

    modrating = book.get("#modrating")
    if modrating:
        try:
            out["goodreads_rating"] = float(modrating)
        except (TypeError, ValueError):
            pass

    # series triple is always emitted (empty CSV value -> None).
    series_raw = (book.get("series") or "").strip()
    out["series"] = series_raw or None
    out["series_position"] = _format_series_position(book.get("series_index"))
    series_type = (book.get("#series_type") or "").strip()
    out["series_status"] = series_type or None
    # When the CSV says a book is standalone, drop any stale series_position
    # that the catalog might still carry.
    if out["series"] is None:
        out["series_position"] = None

    return out


def sync_library_to_catalog(books: list[dict], catalog: dict) -> dict:
    """Add stubs for new library books and re-apply CSV-authoritative fields.

    Returns a stats dict:
      - added: count of new pending stubs created
      - refreshed: count of field-value updates applied
      - added_titles: list of "Title — Author" strings for new entries
      - refreshed_by_field: {field: count} of which fields got updated
    """
    added_titles: list[str] = []
    refreshed_by_field: dict[str, int] = {f: 0 for f in CSV_AUTHORITATIVE_FIELDS}
    for book in books:
        key = book_key(book["title"], book["authors"])
        csv_fields = csv_authoritative_values(book)
        if key not in catalog["entries"]:
            catalog["entries"][key] = {
                "title": book["title"],
                "author": book["authors"],
                "series_role": None,
                "author_entry_point": None,
                "primary_genre": None,
                "secondary_genre": None,
                "related_series": [],
                "indie": None,
                "classic": None,
                "status": "pending",
                "summary": None,
                "tone": None,
                "pacing": None,
                "themes": [],
                "themes_canonical": [],
                "setting": None,
                "comparable_books": [],
                "taste_signals": {"positive": [], "negative": []},
                "taste_signals_canonical": {"positive": [], "negative": []},
                "audio_suitability": None,
                "audio_notes": None,
                "content_flags": [],
                "confidence": None,
                "research_source": None,
                **csv_fields,
            }
            added_titles.append(f"{book['title']} — {book['authors']}")
        else:
            entry = catalog["entries"][key]
            for field, value in csv_fields.items():
                if entry.get(field) != value:
                    entry[field] = value
                    refreshed_by_field[field] += 1
    return {
        "added": len(added_titles),
        "refreshed": sum(refreshed_by_field.values()),
        "added_titles": added_titles,
        "refreshed_by_field": refreshed_by_field,
    }


def get_book_csv_data(books: list[dict], key: str) -> dict:
    """Look up the original CSV row for a book by its catalog key."""
    for book in books:
        if book_key(book["title"], book["authors"]) == key:
            return book
    return {}

# ---------------------------------------------------------------------------
# API call with tool-use loop
# ---------------------------------------------------------------------------

def call_api_with_tools(client, messages: list, system: str, tools: list | None = None) -> str:
    """Runs the multi-turn tool-use loop. Returns final assistant text.

    `tools` defaults to [WEB_SEARCH_TOOL]. Pass [] to skip the tool loop —
    callers like the comparable_books ranker don't need web search and
    avoid wasted round-trips that way.
    """
    if tools is None:
        tools = [WEB_SEARCH_TOOL]
    # Cache the system prompt + tool list so they aren't re-billed on every call.
    # Note: Haiku 4.5 requires a >=4096-token prefix to actually cache; this prompt
    # is ~800 tokens, so the marker is currently a no-op. It activates automatically
    # if the prompt grows or the model changes (Sonnet 4.5 needs 1024).
    cached_system = [{
        "type": "text",
        "text": system,
        "cache_control": {"type": "ephemeral"},
    }]

    for attempt in range(MAX_RETRIES):
        try:
            kwargs = dict(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=cached_system,
                messages=messages,
            )
            if tools:
                kwargs["tools"] = tools
            response = client.messages.create(**kwargs)

            while response.stop_reason == "tool_use":
                tool_uses = [b for b in response.content if b.type == "tool_use"]
                tool_results = []
                for tu in tool_uses:
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": tu.id,
                        "content": ""
                    })
                messages = messages + [
                    {"role": "assistant", "content": response.content},
                    {"role": "user", "content": tool_results}
                ]
                kwargs["messages"] = messages
                response = client.messages.create(**kwargs)

            u = response.usage
            print(
                f"  tokens: in={u.input_tokens} "
                f"cache_read={getattr(u, 'cache_read_input_tokens', 0) or 0} "
                f"cache_write={getattr(u, 'cache_creation_input_tokens', 0) or 0} "
                f"out={u.output_tokens}"
            )

            text_blocks = [b.text for b in response.content if hasattr(b, "text")]
            return "\n".join(text_blocks)

        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            print(f"  Rate limited. Waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}...")
            time.sleep(wait)
        except anthropic.APIError as e:
            if attempt < MAX_RETRIES - 1:
                print(f"  API error: {e}. Retrying in 10s...")
                time.sleep(10)
            else:
                raise

    raise RuntimeError("Max retries exceeded")

# ---------------------------------------------------------------------------
# Cataloguing a chunk
# ---------------------------------------------------------------------------

def catalogue_chunk(
    client,
    chunk: list[dict],
    catalog: dict,
    system: str
) -> int:
    """
    Send a chunk of book dicts to Claude. Updates catalog entries in place.
    Returns n_catalogued.
    """
    from catalogue_prompts import build_batch_prompt, parse_catalog_response

    print(f"\n  Sending {len(chunk)} books to Claude...")

    prompt = build_batch_prompt(chunk)
    messages = [{"role": "user", "content": prompt}]

    raw = call_api_with_tools(client, messages, system)
    results = parse_catalog_response(raw)

    if not results:
        print("  Warning: could not parse response. Entries remain pending.")
        return 0

    catalogued = 0

    catalog_keys = set(catalog["entries"])
    normalized_index = {normalize_key(ck): ck for ck in catalog_keys}

    for key, entry_data in results.items():
        matched_key = resolve_canonical_key(key, catalog_keys, normalized_index)
        if matched_key is None:
            title_norm = normalize_key(entry_data.get("title", ""))
            if title_norm:
                for nck, ck in normalized_index.items():
                    if title_norm in nck:
                        matched_key = ck
                        break

        if matched_key:
            existing = catalog["entries"][matched_key]
            # CSV-pinned fields stay pinned even if the model emits values
            # for them. The system prompt instructs the model not to touch
            # them, but a defensive strip keeps a chatty response from
            # silently overriding ground truth.
            for pinned in CSV_AUTHORITATIVE_FIELDS:
                entry_data.pop(pinned, None)
            existing.update(entry_data)
            if "status" not in entry_data:
                existing["status"] = (
                    "needs_review" if entry_data.get("confidence") == "Low"
                    else "complete"
                )
            catalogued += 1
        else:
            print(f"  Warning: couldn't match '{key}' to a catalog entry — skipping.")

    return catalogued

# ---------------------------------------------------------------------------
# Entry-point fields (series_role + author_entry_point)
# ---------------------------------------------------------------------------

import re as _re

_AUDIT_BOOK1 = _re.compile(r"^book\s*1(?![\d.])", _re.IGNORECASE)


def _is_book_one_position(series_position: str | None) -> bool:
    if not series_position:
        return False
    return bool(_AUDIT_BOOK1.match(series_position.strip()))


def derive_series_role_provisional(entry: dict) -> str | None:
    """Auto-derive series_role for trivially-derivable cases — no LLM cost.

    Returns one of "standalone" | "first" | "mid", or None when the case
    needs LLM judgement (loose-connected entries, ambiguous positions, or
    promotion to "late" / "loose-entry" / "loose-mid").
    """
    status = entry.get("series_status")
    series = entry.get("series")
    pos = entry.get("series_position")

    if status == "Standalone" and not series:
        return "standalone"
    if status == "Short Stories":
        return "standalone"
    if status in ("Short Series", "Long Series"):
        if _is_book_one_position(pos):
            return "first"
        if pos and _re.search(r"book\s*\d", pos, _re.IGNORECASE):
            return "mid"
    # Standalone-with-series (loose-connected) and unparsed positions are
    # the LLM's job — return None to flag for the audit pass.
    return None


def needs_entry_point_audit(entry: dict) -> bool:
    """Entry needs the LLM-driven audit pass for series_role / author_entry_point."""
    if entry.get("series_role") is None:
        return True
    if entry.get("author_entry_point") is None:
        return True
    return False


def _author_peer_summary(catalog: dict, author: str, exclude_key: str) -> list[str]:
    """Return a short list of peer-by-this-author titles + series labels for prompt context."""
    out = []
    for k, e in catalog["entries"].items():
        if k == exclude_key:
            continue
        if (e.get("author") or "") != author:
            continue
        label = e.get("title") or ""
        s = e.get("series")
        if s:
            label += f" ({s} {e.get('series_position') or ''})".rstrip()
        out.append(label.strip())
        if len(out) >= 8:
            break
    return out


def audit_entry_points(
    catalog: dict,
    *,
    client=None,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    dry_run: bool = False,
    catalog_path: str | None = None,
    index_path: str | None = None,
) -> dict:
    """Backfill series_role + author_entry_point on entries that lack them.

    Phase 1 (no LLM cost): derive trivial cases via `derive_series_role_provisional`.
    Phase 2 (LLM): chunk through entries that still need either field after Phase 1.

    Returns a stats dict {auto_filled, llm_chunks, llm_filled, still_null}.
    """
    from catalogue_prompts import (
        build_entry_point_audit_system_prompt,
        build_entry_point_audit_prompt,
        parse_entry_point_response,
    )

    stats = {"auto_filled": 0, "llm_chunks": 0, "llm_filled": 0, "still_null": 0}

    # Phase 1: trivially-derivable fills (free).
    for key, entry in catalog["entries"].items():
        if entry.get("series_role") is None:
            provisional = derive_series_role_provisional(entry)
            if provisional is not None:
                entry["series_role"] = provisional
                stats["auto_filled"] += 1

    # Targets needing LLM: anything still missing either field.
    targets = [
        (key, entry) for key, entry in catalog["entries"].items()
        if needs_entry_point_audit(entry)
    ]
    print(f"  Phase 1 auto-filled series_role on {stats['auto_filled']} entries.")
    print(f"  {len(targets)} entries still need LLM audit "
          f"(loose-connected, ambiguous, author_entry_point judgement).")

    if dry_run or not targets:
        if dry_run:
            print("  --dry-run: skipping LLM pass.")
        stats["still_null"] = len(targets)
        return stats

    if client is None:
        raise RuntimeError("audit_entry_points: client required for LLM pass; pass dry_run=True to skip")

    system = build_entry_point_audit_system_prompt()

    processed = 0
    estimated_chunks = -(-len(targets) // chunk_size)
    while processed < len(targets):
        chunk_num = processed // chunk_size + 1
        chunk = targets[processed: processed + chunk_size]
        chunk_entries = []
        for key, entry in chunk:
            payload = {
                **{k: entry.get(k) for k in (
                    "title", "author", "series", "series_position",
                    "series_status", "primary_genre"
                )},
                "_author_peers": _author_peer_summary(catalog, entry.get("author") or "", key),
            }
            chunk_entries.append(payload)

        prompt = build_entry_point_audit_prompt(chunk_entries)
        messages = [{"role": "user", "content": prompt}]
        print(f"  Audit chunk {chunk_num}/{estimated_chunks} "
              f"({len(chunk)} entries)...")
        try:
            raw = call_api_with_tools(client, messages, system)
            results = parse_entry_point_response(raw)
        except Exception as e:
            print(f"    Error: {e}. Skipping chunk.")
            processed += len(chunk)
            time.sleep(RATE_LIMIT_DELAY)
            continue

        stats["llm_chunks"] += 1

        catalog_keys = set(catalog["entries"])
        normalized_index = {normalize_key(ck): ck for ck in catalog_keys}

        for key, fields in results.items():
            matched = resolve_canonical_key(key, catalog_keys, normalized_index)
            if matched is None:
                continue
            entry = catalog["entries"][matched]
            sr = fields.get("series_role")
            aep = fields.get("author_entry_point")
            if sr in {"standalone", "first", "mid", "late", "loose-entry", "loose-mid"}:
                entry["series_role"] = sr
                stats["llm_filled"] += 1
            if aep in (True, False, None):
                entry["author_entry_point"] = aep

        processed += len(chunk)

        # Save after every chunk so a mid-run failure doesn't lose work.
        # Re-runs skip already-filled entries via needs_entry_point_audit.
        if catalog_path:
            save_catalog(catalog, catalog_path)
            if index_path:
                save_index(catalog, index_path)
            print(f"  Saved → {catalog_path}"
                  + (f" (+ {index_path})" if index_path else ""))

        time.sleep(RATE_LIMIT_DELAY)

    stats["still_null"] = sum(
        1 for e in catalog["entries"].values() if needs_entry_point_audit(e)
    )
    return stats

# ---------------------------------------------------------------------------
# comparable_books postprocessing
# ---------------------------------------------------------------------------

def _build_canonical_indices(catalog: dict) -> tuple[set, dict]:
    keys = set(catalog["entries"])
    normalized: dict[str, str] = {}
    for k in keys:
        n = normalize_key(k)
        if n in normalized and normalized[n] != k:
            print(f"  warning: normalize_key collision: {normalized[n]!r} vs {k!r}")
        normalized[n] = k
    return keys, normalized


def canonicalise_comparables(catalog: dict) -> dict:
    """Phase 1 (in place). Replace matched comps with canonical keys, preserve
    unmatched, drop self-refs and within-list duplicates.

    Returns stats: canonicalised, self_dropped, duplicate_dropped,
    drops_per_entry.
    """
    keys, norm_index = _build_canonical_indices(catalog)
    canonicalised = 0
    self_dropped = 0
    duplicate_dropped = 0
    drops_per_entry: dict[str, list] = {}

    for k, entry in catalog["entries"].items():
        seen: set[str] = set()
        out: list[str] = []
        local_drops: list[tuple[str, str]] = []
        for c in entry.get("comparable_books") or []:
            canon = resolve_canonical_key(c, keys, norm_index)
            if canon is not None:
                if canon == k:
                    local_drops.append((c, "self"))
                    self_dropped += 1
                    continue
                n = normalize_key(canon)
                if n in seen:
                    local_drops.append((c, "duplicate"))
                    duplicate_dropped += 1
                    continue
                if canon != c:
                    canonicalised += 1
                seen.add(n)
                out.append(canon)
            else:
                # Unmatched: keep raw, but still dedupe variants within the list.
                n = normalize_key(c)
                if n in seen:
                    local_drops.append((c, "duplicate"))
                    duplicate_dropped += 1
                    continue
                seen.add(n)
                out.append(c)
        entry["comparable_books"] = out
        if local_drops:
            drops_per_entry[k] = local_drops

    return {
        "canonicalised": canonicalised,
        "self_dropped": self_dropped,
        "duplicate_dropped": duplicate_dropped,
        "drops_per_entry": drops_per_entry,
    }


def reciprocate_comparables(catalog: dict) -> int:
    """Phase 2 (in place). For every matched comp B in source A, append A to
    B's comparable_books if not already present. No cap check — over-cap
    lists are resolved later by Phase 3.

    Returns the number of reciprocal links added.
    """
    catalog_keys = set(catalog["entries"])
    added = 0
    for k in sorted(catalog["entries"]):
        for c in list(catalog["entries"][k].get("comparable_books") or []):
            if c not in catalog_keys:
                continue
            target = catalog["entries"][c]
            target_list = target.setdefault("comparable_books", [])
            if k in target_list:
                continue
            target_list.append(k)
            added += 1
    return added


def find_over_cap_entries(catalog: dict) -> list:
    return [
        k for k, e in catalog["entries"].items()
        if len(e.get("comparable_books") or []) > COMPARABLES_CAP
    ]


def _candidate_summary(key: str, entry: dict) -> str:
    """One-line description of a candidate comp for the ranking prompt."""
    genre = entry.get("primary_genre") or entry.get("genre") or ""
    tone = entry.get("tone") or ""
    summary = (entry.get("summary") or "").strip()
    if len(summary) > 160:
        summary = summary[:157].rstrip() + "..."
    parts = [key]
    if genre:
        parts.append(genre)
    if tone:
        parts.append(tone)
    if summary:
        parts.append(summary)
    return " | ".join(parts)


RANKING_SYSTEM_PROMPT = (
    "You are pruning oversized comparable_books lists in a personal-library "
    "catalog. For each source book, return the 6 candidates with the strongest "
    "appeal overlap. Output a single JSON object mapping each source key to a "
    "ranked list of exactly 6 candidate keys, wrapped in a ```json code block. "
    "No commentary outside the block."
)


def rank_comparables_with_claude(
    client,
    catalog: dict,
    over_cap_keys: list,
) -> dict:
    """Phase 3 (in place). For each over-cap entry, ask Claude to pick the
    strongest 6 comps. Mutates catalog. Returns stats.
    """
    from catalogue_prompts import build_ranking_prompt, parse_ranking_response

    pre_trimmed: list[str] = []
    ranking_failures: list[str] = []
    ranked = 0

    def _prefilter_score(source_entry: dict, cand_key: str) -> tuple:
        cand = catalog["entries"].get(cand_key)
        if cand is None:
            return (0, 0, cand_key)
        same_genre = (
            (source_entry.get("primary_genre") or "").lower()
            == (cand.get("primary_genre") or "").lower()
            and source_entry.get("primary_genre")
        )
        src_themes = {t.lower() for t in (source_entry.get("themes") or [])}
        cand_themes = {t.lower() for t in (cand.get("themes") or [])}
        shared_themes = len(src_themes & cand_themes)
        # Higher score wins. Tiebreak by normalize_key for determinism.
        return (1 if same_genre else 0, shared_themes, normalize_key(cand_key))

    work: list[tuple[str, list[str]]] = []
    for k in over_cap_keys:
        candidates = list(catalog["entries"][k]["comparable_books"])
        if len(candidates) > RANKING_CANDIDATE_LIMIT:
            source_entry = catalog["entries"][k]
            scored = sorted(
                candidates,
                key=lambda c: _prefilter_score(source_entry, c),
                reverse=True,
            )
            candidates = scored[:RANKING_CANDIDATE_LIMIT]
            pre_trimmed.append(k)
        work.append((k, candidates))

    print(f"\n  Ranking {len(work)} over-cap entries via Claude "
          f"(batch size={RANKING_BATCH_SIZE})...")

    for batch_start in range(0, len(work), RANKING_BATCH_SIZE):
        batch = work[batch_start: batch_start + RANKING_BATCH_SIZE]
        sources = []
        for source_key, candidate_keys in batch:
            source_entry = catalog["entries"][source_key]
            candidate_entries = [
                (ck, catalog["entries"][ck]) for ck in candidate_keys
                if ck in catalog["entries"]
            ]
            sources.append({
                "key": source_key,
                "entry": source_entry,
                "candidates": candidate_entries,
            })

        prompt = build_ranking_prompt(sources, candidate_summary=_candidate_summary)
        messages = [{"role": "user", "content": prompt}]

        try:
            raw = call_api_with_tools(client, messages, RANKING_SYSTEM_PROMPT, tools=[])
        except Exception as e:
            print(f"  Ranking batch failed: {e}")
            for source_key, candidate_keys in batch:
                ranking_failures.append(source_key)
                catalog["entries"][source_key]["comparable_books"] = (
                    candidate_keys[:COMPARABLES_CAP]
                )
            continue

        rankings = parse_ranking_response(raw)

        for source_key, candidate_keys in batch:
            # Accept Claude's response under either the exact source key or a
            # normalize_key-equivalent variant. Same for picks against the
            # candidate set — Claude occasionally drifts on smart quotes / dashes.
            cand_canon = {normalize_key(c): c for c in candidate_keys}
            picked_raw = rankings.get(source_key)
            if picked_raw is None:
                for rk, rv in rankings.items():
                    if normalize_key(rk) == normalize_key(source_key):
                        picked_raw = rv
                        break

            picked: list[str] = []
            if isinstance(picked_raw, list):
                for p in picked_raw[:COMPARABLES_CAP]:
                    if not isinstance(p, str):
                        continue
                    canon = cand_canon.get(normalize_key(p))
                    if canon is None or canon in picked:
                        continue
                    picked.append(canon)

            if len(picked) == COMPARABLES_CAP:
                catalog["entries"][source_key]["comparable_books"] = picked
                ranked += 1
            else:
                ranking_failures.append(source_key)
                catalog["entries"][source_key]["comparable_books"] = (
                    candidate_keys[:COMPARABLES_CAP]
                )

        time.sleep(RATE_LIMIT_DELAY)

    return {
        "ranked_entries": ranked,
        "pre_trimmed": pre_trimmed,
        "ranking_failures": ranking_failures,
    }


def sync_comparables(
    catalog: dict,
    *,
    client=None,
    dry_run: bool = False,
    report_path: str | None = None,
) -> dict:
    """Run the comparable_books postprocess. Phases 1 + 2 always run.
    Phase 3 (LLM ranking) runs only when client is provided and not dry_run.

    If dry_run, work on a deep copy and don't mutate the input catalog.
    """
    import copy
    target = copy.deepcopy(catalog) if dry_run else catalog
    before = {
        k: list(e.get("comparable_books") or [])
        for k, e in target["entries"].items()
    }

    phase1 = canonicalise_comparables(target)
    reciprocals_added = reciprocate_comparables(target)
    over_cap_entries = find_over_cap_entries(target)

    phase3 = {"ranked_entries": 0, "pre_trimmed": [], "ranking_failures": []}
    if over_cap_entries and client is not None and not dry_run:
        phase3 = rank_comparables_with_claude(
            client, target, over_cap_entries
        )
        # Recompute over-cap after ranking; should be empty unless Phase 3 itself
        # left lists over-cap (failure fallback already trims to cap).
        residual = find_over_cap_entries(target)
        if residual:
            for k in residual:
                target["entries"][k]["comparable_books"] = (
                    target["entries"][k]["comparable_books"][:COMPARABLES_CAP]
                )

    after = {k: list(e["comparable_books"]) for k, e in target["entries"].items()}
    lists_changed = sum(1 for k in before if before[k] != after[k])

    stats = {
        "lists_changed": lists_changed,
        "canonicalised": phase1["canonicalised"],
        "self_dropped": phase1["self_dropped"],
        "duplicate_dropped": phase1["duplicate_dropped"],
        "reciprocals_added": reciprocals_added,
        "over_cap_entries": over_cap_entries,
        "ranked_entries": phase3["ranked_entries"],
        "pre_trimmed": phase3["pre_trimmed"],
        "ranking_failures": phase3["ranking_failures"],
        "drops_per_entry": phase1["drops_per_entry"],
        "dry_run": dry_run,
    }

    if report_path:
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(stats, f, indent=2, ensure_ascii=False)

    return stats


def print_sync_summary(stats: dict):
    print("\n  comparable_books sync summary")
    print(f"    lists changed     : {stats['lists_changed']}")
    print(f"    canonicalised     : {stats['canonicalised']}")
    print(f"    self_dropped      : {stats['self_dropped']}")
    print(f"    duplicate_dropped : {stats['duplicate_dropped']}")
    print(f"    reciprocals_added : {stats['reciprocals_added']}")
    print(f"    over_cap entries  : {len(stats['over_cap_entries'])}")
    print(f"    ranked by Claude  : {stats['ranked_entries']}")
    if stats['pre_trimmed']:
        print(f"    pre_trimmed       : {len(stats['pre_trimmed'])} (>{RANKING_CANDIDATE_LIMIT} candidates)")
    if stats['ranking_failures']:
        print(f"    ranking_failures  : {len(stats['ranking_failures'])} (fell back to truncate)")
    if stats['dry_run']:
        print("    (dry run — no changes written, Phase 3 skipped)")


# ---------------------------------------------------------------------------
# Canonicalisation backfill — map free-form taste_signals / themes to the
# controlled vocabulary IDs in catalogue_vocab. One LLM call per chunk of
# distinct strings, applied across every entry that uses them. Idempotent:
# already-canonicalised entries skip the model.
# ---------------------------------------------------------------------------

CANONICALIZE_CHUNK_SIZE = 80   # distinct phrases per LLM call


def _collect_distinct_signals(catalog: dict) -> set[str]:
    out: set[str] = set()
    for entry in catalog["entries"].values():
        ts = entry.get("taste_signals") or {}
        if isinstance(ts, dict):
            for sig in (ts.get("positive") or []):
                if sig:
                    out.add(sig)
            for sig in (ts.get("negative") or []):
                if sig:
                    out.add(sig)
    return out


def _collect_distinct_themes(catalog: dict) -> set[str]:
    out: set[str] = set()
    for entry in catalog["entries"].values():
        for t in entry.get("themes") or []:
            if t:
                out.add(t)
    return out


def _build_canonical_mapping(
    client,
    phrases: set[str],
    label: str,
    vocab: dict[str, str],
    chunk_size: int = CANONICALIZE_CHUNK_SIZE,
) -> dict[str, str | None]:
    """Ask the LLM to map each free-form phrase to a canonical vocab ID
    (or None). Returns a dict; phrases with no mapping have value None."""
    from catalogue_prompts import (
        build_canonicalize_system_prompt,
        build_canonicalize_prompt,
        parse_canonicalize_response,
    )

    system = build_canonicalize_system_prompt(label, vocab)
    allowed = set(vocab.keys())
    sorted_phrases = sorted(phrases)
    mapping: dict[str, str | None] = {p: None for p in sorted_phrases}

    n_chunks = -(-len(sorted_phrases) // chunk_size)
    for i in range(n_chunks):
        chunk = sorted_phrases[i * chunk_size: (i + 1) * chunk_size]
        prompt = build_canonicalize_prompt(chunk)
        print(f"  canonicalize-{label} chunk {i + 1}/{n_chunks} ({len(chunk)} phrases)...")
        try:
            raw = call_api_with_tools(client, [{"role": "user", "content": prompt}],
                                      system, tools=[])
            chunk_map = parse_canonicalize_response(raw, allowed)
            mapping.update(chunk_map)
        except Exception as e:
            print(f"    Error: {e}. Phrases in this chunk left unmapped.")
        time.sleep(RATE_LIMIT_DELAY)

    return mapping


def _apply_signal_mapping(catalog: dict, mapping: dict[str, str | None]) -> int:
    """Write taste_signals_canonical onto every entry, using the mapping.
    Returns the number of entries whose canonical block changed."""
    changed = 0
    for entry in catalog["entries"].values():
        ts = entry.get("taste_signals") or {}
        if not isinstance(ts, dict):
            continue
        new_canon: dict[str, list[str | None]] = {}
        for polarity in ("positive", "negative"):
            new_canon[polarity] = [mapping.get(s) for s in (ts.get(polarity) or [])]
        # Only persist if any canonical was actually filled — keeps entries
        # that have purely unrecognised free-form values from acquiring an
        # all-null canonical block.
        any_canon = any(c for buck in new_canon.values() for c in buck)
        old = entry.get("taste_signals_canonical")
        if any_canon:
            if old != new_canon:
                entry["taste_signals_canonical"] = new_canon
                changed += 1
        elif old is not None:
            del entry["taste_signals_canonical"]
            changed += 1
    return changed


def _apply_theme_mapping(catalog: dict, mapping: dict[str, str | None]) -> int:
    changed = 0
    for entry in catalog["entries"].values():
        themes = entry.get("themes") or []
        new_canon = [mapping.get(t) for t in themes]
        any_canon = any(c for c in new_canon)
        old = entry.get("themes_canonical")
        if any_canon:
            if old != new_canon:
                entry["themes_canonical"] = new_canon
                changed += 1
        elif old is not None:
            del entry["themes_canonical"]
            changed += 1
    return changed


def canonicalize_signals(catalog: dict, client) -> dict:
    """Full pipeline: collect distinct free-form signals, map via LLM,
    apply across catalog. Returns stats."""
    from catalogue_vocab import CANONICAL_TASTE_SIGNALS
    distinct = _collect_distinct_signals(catalog)
    print(f"  {len(distinct)} distinct free-form taste_signals across the catalog.")
    mapping = _build_canonical_mapping(
        client, distinct, "taste_signals", CANONICAL_TASTE_SIGNALS
    )
    n_entries_changed = _apply_signal_mapping(catalog, mapping)
    n_mapped = sum(1 for v in mapping.values() if v is not None)
    return {
        "distinct_phrases": len(distinct),
        "phrases_mapped": n_mapped,
        "phrases_unmapped": len(distinct) - n_mapped,
        "entries_changed": n_entries_changed,
    }


def canonicalize_themes(catalog: dict, client) -> dict:
    from catalogue_vocab import CANONICAL_THEMES
    distinct = _collect_distinct_themes(catalog)
    print(f"  {len(distinct)} distinct free-form themes across the catalog.")
    mapping = _build_canonical_mapping(
        client, distinct, "themes", CANONICAL_THEMES
    )
    n_entries_changed = _apply_theme_mapping(catalog, mapping)
    n_mapped = sum(1 for v in mapping.values() if v is not None)
    return {
        "distinct_phrases": len(distinct),
        "phrases_mapped": n_mapped,
        "phrases_unmapped": len(distinct) - n_mapped,
        "entries_changed": n_entries_changed,
    }


# ---------------------------------------------------------------------------
# Library.csv genre re-audit — judges the CSV's `#genre` column with the
# LLM and writes a per-row diff for the operator to review before applying.
# ---------------------------------------------------------------------------

LIBRARY_GENRE_AUDIT_REPORT = "dist/library_genre_audit.md"


def audit_library_genres(
    csv_path: Path,
    client,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    apply_changes: bool = False,
    report_path: Path | None = None,
) -> dict:
    """Walk Library.csv and ask the LLM to verify each row's `#genre`.

    By default writes a diff report only — operator reviews and re-runs
    with `apply_changes=True` to commit the revised genre column to CSV.
    """
    from catalogue_prompts import (
        build_library_genre_audit_system_prompt,
        build_library_genre_audit_prompt,
        parse_library_genre_audit_response,
    )

    rows = load_library(str(csv_path))
    targets = []
    for row in rows:
        targets.append({
            "title": row.get("title"),
            "author": row.get("authors"),
            "current_genre": row.get("#genre") or "",
            "tag_hints": row.get("#more_tags") or "",
            "series": row.get("series") or None,
        })
    print(f"  {len(targets)} rows to audit.")

    system = build_library_genre_audit_system_prompt()
    n_chunks = -(-len(targets) // chunk_size)
    proposed: dict[str, str] = {}

    for i in range(n_chunks):
        chunk = targets[i * chunk_size: (i + 1) * chunk_size]
        prompt = build_library_genre_audit_prompt(chunk)
        print(f"  Genre audit chunk {i + 1}/{n_chunks} ({len(chunk)} rows)...")
        try:
            raw = call_api_with_tools(client, [{"role": "user", "content": prompt}],
                                      system)
            chunk_map = parse_library_genre_audit_response(raw)
            proposed.update(chunk_map)
        except Exception as e:
            print(f"    Error: {e}. Chunk skipped.")
        time.sleep(RATE_LIMIT_DELAY)

    # Build the diff report.
    diffs = []
    unchanged = 0
    for row in rows:
        key = book_key(row.get("title", ""), row.get("authors", ""))
        new = proposed.get(key)
        if new is None:
            continue
        cur = (row.get("#genre") or "").strip()
        if new != cur:
            diffs.append((key, cur, new))
        else:
            unchanged += 1

    report_path = report_path or Path(LIBRARY_GENRE_AUDIT_REPORT)
    report_path.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Library.csv #genre re-audit\n\n",
        f"Audit covered {len(rows)} rows; LLM responded for {len(proposed)}.\n",
        f"Unchanged: {unchanged}. Proposed changes: {len(diffs)}.\n\n",
        "## Proposed changes\n\n",
        "| Book | Current | Proposed |\n|---|---|---|\n",
    ]
    for key, cur, new in sorted(diffs):
        lines.append(f"| {key} | {cur} | {new} |\n")
    report_path.write_text("".join(lines), encoding="utf-8")
    print(f"  Wrote audit report → {report_path}")

    stats = {
        "rows_audited": len(rows),
        "responses_received": len(proposed),
        "proposed_changes": len(diffs),
        "applied": 0,
    }

    if apply_changes and diffs:
        # Rewrite Library.csv with the proposed genre values.
        import io as _io
        # Re-read raw rows so we keep all columns and ordering intact.
        with open(csv_path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            fieldnames = reader.fieldnames
            raw_rows = list(reader)
        change_set = {k: new for k, _cur, new in diffs}
        applied = 0
        for row in raw_rows:
            key = book_key(row.get("title", ""), row.get("authors", ""))
            if key in change_set:
                row["#genre"] = change_set[key]
                applied += 1
        # Preserve the file's original style (BOM, unquoted header, QUOTE_ALL
        # body, \n endings) — same shape as the series_type audit writer.
        with open(csv_path, "wb") as f:
            f.write("﻿".encode("utf-8"))
            f.write((",".join(fieldnames) + "\n").encode("utf-8"))
            buf = _io.StringIO()
            w = csv.DictWriter(
                buf, fieldnames=fieldnames,
                quoting=csv.QUOTE_ALL, lineterminator="\n",
            )
            for row in raw_rows:
                w.writerow(row)
            f.write(buf.getvalue().encode("utf-8"))
        stats["applied"] = applied
        print(f"  Applied {applied} genre changes to {csv_path}.")

    return stats


def authenticate_anthropic_client():
    """Set up the Anthropic client using the Claude Code session ingress token.

    Refuses to run if ANTHROPIC_API_KEY is set or the session token isn't
    available.
    """
    import anthropic
    token_file = os.environ.get("CLAUDE_SESSION_INGRESS_TOKEN_FILE")
    if not token_file or not Path(token_file).is_file():
        print(
            "Error: CLAUDE_SESSION_INGRESS_TOKEN_FILE is not set or does not point "
            "to a readable file. This script must run inside a Claude Code session."
        )
        sys.exit(1)
    if os.environ.get("ANTHROPIC_API_KEY"):
        print(
            "Error: ANTHROPIC_API_KEY is set. Unset it — this script only authenticates "
            "via the Claude Code session token."
        )
        sys.exit(1)
    os.environ["ANTHROPIC_AUTH_TOKEN"] = Path(token_file).read_text().strip()
    return anthropic.Anthropic()

# ---------------------------------------------------------------------------
# Progress and audit reporting
# ---------------------------------------------------------------------------

def print_status(catalog: dict):
    entries = catalog["entries"]
    total = len(entries)
    complete = sum(1 for e in entries.values() if e["status"] == "complete")
    needs_review = sum(1 for e in entries.values() if e["status"] == "needs_review")
    pending = sum(1 for e in entries.values() if e["status"] == "pending")
    pct = round((complete + needs_review) / total * 100, 1) if total else 0

    print(f"\n{'='*55}")
    print(f"  Library Catalog Status")
    print(f"{'='*55}")
    print(f"  Total in library : {total}")
    print(f"  Complete         : {complete}")
    print(f"  Needs review     : {needs_review}")
    print(f"  Pending          : {pending}")
    print(f"  Progress         : {pct}%")
    print(f"  Last updated     : {catalog.get('last_updated', 'never')}")
    print(f"{'='*55}\n")

# ---------------------------------------------------------------------------
# Sync export — umbrella step for the Code-side "I uploaded a new
# Library.csv, please update everything" workflow.
# ---------------------------------------------------------------------------

DEFAULT_SYNC_SQLITE = "Library_Catalog.sqlite"
DEFAULT_SYNC_AUDIT = "dist/sync_audit.md"


def _status_counts(catalog: dict) -> dict[str, int]:
    counts = {"complete": 0, "needs_review": 0, "pending": 0}
    for entry in catalog.get("entries", {}).values():
        counts[entry.get("status", "pending")] = counts.get(
            entry.get("status", "pending"), 0
        ) + 1
    counts["total"] = sum(counts[k] for k in ("complete", "needs_review", "pending"))
    return counts


def write_sync_audit(
    audit_path: Path,
    catalog: dict,
    library_sync_stats: dict,
    comparables_stats: dict | None,
    pre_counts: dict[str, int],
    encoded_path: Path,
    sqlite_path: Path,
) -> None:
    """Write a human-readable sync audit summary to `audit_path`."""
    audit_path.parent.mkdir(parents=True, exist_ok=True)
    post = _status_counts(catalog)
    delta = {k: post[k] - pre_counts.get(k, 0) for k in ("complete", "needs_review", "pending", "total")}

    encoded_size = encoded_path.stat().st_size if encoded_path.exists() else 0
    sqlite_size = sqlite_path.stat().st_size if sqlite_path.exists() else 0

    lines: list[str] = []
    lines.append(f"# Library catalog sync — {_datetime.datetime.now().isoformat(timespec='seconds')}")
    lines.append("")
    lines.append("## Catalog totals")
    lines.append("")
    lines.append("| Status | Before | After | Δ |")
    lines.append("|---|---|---|---|")
    for k in ("complete", "needs_review", "pending", "total"):
        lines.append(f"| {k} | {pre_counts.get(k, 0)} | {post[k]} | {delta[k]:+d} |")
    lines.append("")

    lines.append("## CSV-authoritative field refreshes")
    lines.append("")
    refreshed_by_field = library_sync_stats.get("refreshed_by_field", {})
    if any(refreshed_by_field.values()):
        lines.append("| Field | Entries updated |")
        lines.append("|---|---|")
        for field, count in refreshed_by_field.items():
            if count:
                lines.append(f"| `{field}` | {count} |")
    else:
        lines.append("_No CSV-authoritative fields drifted from the catalog this sync._")
    lines.append("")

    added_titles: list[str] = library_sync_stats.get("added_titles", [])
    lines.append(f"## New entries added ({len(added_titles)})")
    lines.append("")
    if added_titles:
        for t in added_titles[:200]:
            lines.append(f"- {t}")
        if len(added_titles) > 200:
            lines.append(f"- _…and {len(added_titles) - 200} more (truncated)._")
    else:
        lines.append("_None — every CSV row was already in the catalog._")
    lines.append("")

    if comparables_stats:
        lines.append("## comparable_books sync")
        lines.append("")
        for k, v in comparables_stats.items():
            if isinstance(v, (int, float, str)):
                lines.append(f"- **{k}:** {v}")
        lines.append("")

    lines.append("## Output artefacts")
    lines.append("")
    lines.append(f"- `{sqlite_path}` ({sqlite_size:,} bytes)")
    lines.append(f"- `{encoded_path}` ({encoded_size:,} bytes) — gzip+b64-wrapped, Drive-uploadable")
    lines.append(f"- `{audit_path}` (this file)")
    lines.append("")

    audit_path.write_text("\n".join(lines), encoding="utf-8")
    print(f"  Wrote sync audit → {audit_path}")


def _run_git(args: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a git command and stream its output."""
    print(f"  $ git {' '.join(args)}")
    return subprocess.run(["git", *args], check=check, text=True, capture_output=True)


def git_commit_and_push(paths: list[Path], message: str) -> None:
    """Stage `paths` (force-adding gitignored files), commit, and push the
    current branch to origin.  No-op if there are no actual changes to
    commit.
    """
    branch = _run_git(["rev-parse", "--abbrev-ref", "HEAD"]).stdout.strip()
    if branch in {"main", "master"}:
        print(f"  Refusing to auto-commit to protected branch '{branch}'.")
        print(f"  Run from a feature branch, or commit manually.")
        return

    for p in paths:
        if p.exists():
            _run_git(["add", "-f", str(p)])
        else:
            print(f"  Skipping missing path: {p}")

    status = _run_git(["status", "--porcelain"]).stdout
    if not status.strip():
        print("  Nothing to commit — working tree matches HEAD after staging.")
        return

    _run_git(["commit", "-m", message])

    # Push with simple linear retry — surfaces network blips without
    # silently swallowing real failures.
    for delay in (0, 2, 4, 8):
        if delay:
            print(f"  Push retry after {delay}s …")
            time.sleep(delay)
        result = subprocess.run(
            ["git", "push", "-u", "origin", branch],
            text=True, capture_output=True,
        )
        if result.returncode == 0:
            print(f"  Pushed → origin/{branch}")
            print(result.stdout.strip())
            return
        print(f"  push failed: {result.stderr.strip()}")
    raise SystemExit(f"git push failed after retries on branch {branch}")


def run_sync_export(
    catalog: dict,
    library_sync_stats: dict,
    comparables_stats: dict | None,
    pre_counts: dict[str, int],
    sqlite_path: Path,
    audit_path: Path,
    push: bool,
) -> None:
    """Export SQLite + encoded form, write audit summary, optionally git
    commit + push.  Called at the tail of `main()` when --sync is set.
    """
    from webhelper.sqlite_export import export as _sqlite_export
    from webhelper.encoded_codec import encode_file as _encode_file

    print("\nSync export:")
    _sqlite_export(catalog, sqlite_path)
    n = len(catalog.get("entries") or {})
    print(f"  Wrote SQLite catalog → {sqlite_path} ({n} entries)")

    encoded_path = sqlite_path.with_suffix(sqlite_path.suffix + ".encoded")
    _encode_file(sqlite_path, encoded_path)
    print(f"  Wrote encoded catalog → {encoded_path}")

    write_sync_audit(
        audit_path=audit_path,
        catalog=catalog,
        library_sync_stats=library_sync_stats,
        comparables_stats=comparables_stats,
        pre_counts=pre_counts,
        encoded_path=encoded_path,
        sqlite_path=sqlite_path,
    )

    if push:
        message = (
            f"catalog: sync from Library.csv "
            f"(+{library_sync_stats['added']} new, "
            f"{library_sync_stats['refreshed']} field refreshes)"
        )
        git_commit_and_push(
            paths=[encoded_path, audit_path],
            message=message,
        )
    else:
        print("  --no-push set; skipping git commit + push.")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Autonomously catalogue a book library.")
    parser.add_argument("--library", required=True, help="Path to Library.csv")
    parser.add_argument("--catalog", default=CATALOG_FILE)
    parser.add_argument("--index", default=INDEX_FILE,
                        help="Slim browse index regenerated alongside the catalog")
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--status", action="store_true", help="Print progress and exit")
    parser.add_argument("--review-only", action="store_true",
                        help="Only reprocess needs_review entries")
    parser.add_argument("--index-only", action="store_true",
                        help="Rebuild the slim index from the existing catalog and exit")
    parser.add_argument("--sync-comparables", action="store_true",
                        help="Canonicalise variants, reciprocate links, and "
                             "Claude-rank top 6 when over cap")
    parser.add_argument("--audit-entry-points", action="store_true",
                        help="Backfill series_role and author_entry_point on "
                             "entries that lack them (auto-derives the trivial "
                             "cases for free; LLM for the rest).")
    parser.add_argument("--dry-run", action="store_true",
                        help="With --sync-comparables or --audit-entry-points: "
                             "compute changes but don't call Claude")
    parser.add_argument("--report", default=None,
                        help="With --sync-comparables: write JSON report to this path")
    parser.add_argument("--export-sqlite", dest="export_sqlite", default=None,
                        metavar="PATH",
                        help="One-shot: convert the existing JSON catalog to a "
                             "SQLite database at PATH and exit. Pair with "
                             "--emit-encoded to also produce the gzip+b64 "
                             "wrapped form for upload to the claude.ai surface.")
    parser.add_argument("--emit-encoded", action="store_true",
                        help="With --export-sqlite: also emit "
                             "<sqlite-path>.encoded — gzip+base64 wrapped, "
                             "Drive-uploadable, decoded once per session by "
                             "the librarian-triage skill.")
    parser.add_argument("--sync", action="store_true",
                        help="Umbrella mode for the Code-side 'I uploaded a "
                             "new Library.csv' workflow. After the normal "
                             "sync + catalogue + comparables tail, exports "
                             "the SQLite catalog, emits the encoded form, "
                             "writes a sync audit summary, and (unless "
                             "--no-push) git-commits both artefacts and "
                             "pushes the current branch to origin so the "
                             "user can download from GitHub.")
    parser.add_argument("--sync-sqlite", default=DEFAULT_SYNC_SQLITE,
                        metavar="PATH",
                        help=f"With --sync: path to write the SQLite catalog "
                             f"(default: {DEFAULT_SYNC_SQLITE}).")
    parser.add_argument("--sync-audit", default=DEFAULT_SYNC_AUDIT,
                        metavar="PATH",
                        help=f"With --sync: path to write the audit summary "
                             f"(default: {DEFAULT_SYNC_AUDIT}).")
    parser.add_argument("--no-push", action="store_true",
                        help="With --sync: skip the git commit + push step "
                             "(useful for dry runs / local-only inspection).")
    parser.add_argument("--canonicalize-signals", action="store_true",
                        help="Map free-form taste_signals on every entry to "
                             "canonical IDs from catalogue_vocab. Idempotent; "
                             "writes taste_signals_canonical and saves.")
    parser.add_argument("--canonicalize-themes", action="store_true",
                        help="Same as --canonicalize-signals, for themes / "
                             "themes_canonical.")
    parser.add_argument("--audit-library-genres", action="store_true",
                        help="LLM-walks Library.csv and proposes a primary "
                             "genre per row. Writes a diff report by default; "
                             "pass --apply-changes to commit the proposal "
                             "to the CSV.")
    parser.add_argument("--apply-changes", action="store_true",
                        help="With --audit-library-genres: rewrite "
                             "Library.csv with the LLM's proposed genres.")
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)

    if args.export_sqlite:
        # Lazy import — the export path stays usable on Pro setups that
        # don't have the anthropic SDK installed.
        from pathlib import Path as _Path
        from webhelper.sqlite_export import export as _sqlite_export
        from webhelper.encoded_codec import encode_file as _encode_file

        sqlite_path = _Path(args.export_sqlite)
        _sqlite_export(catalog, sqlite_path)
        n = len(catalog.get("entries") or {})
        print(f"  Wrote SQLite catalog → {sqlite_path} ({n} entries)")
        if args.emit_encoded:
            encoded_path = sqlite_path.with_suffix(sqlite_path.suffix + ".encoded")
            _encode_file(sqlite_path, encoded_path)
            print(f"  Wrote encoded catalog → {encoded_path}")
        sys.exit(0)

    if args.index_only:
        save_index(catalog, args.index)
        print(f"  Wrote slim index → {args.index} ({len(catalog['entries'])} entries)")
        sys.exit(0)

    if args.audit_entry_points:
        client = None
        if not args.dry_run:
            client = authenticate_anthropic_client()
        stats = audit_entry_points(
            catalog,
            client=client,
            chunk_size=args.chunk_size,
            dry_run=args.dry_run,
            catalog_path=None if args.dry_run else args.catalog,
            index_path=None if args.dry_run else args.index,
        )
        print(f"\nEntry-point audit complete.")
        print(f"  auto_filled: {stats['auto_filled']}")
        print(f"  llm_chunks:  {stats['llm_chunks']}")
        print(f"  llm_filled:  {stats['llm_filled']}")
        print(f"  still_null:  {stats['still_null']}")
        if args.dry_run:
            print(f"  --dry-run: catalog NOT written.")
        else:
            # Final save (in addition to per-chunk saves) — ensures the
            # last chunk's stats land on disk.
            save_catalog(catalog, args.catalog)
            save_index(catalog, args.index)
            print(f"  Cataloguing complete. Wrote → {args.catalog} (+ {args.index})")
        sys.exit(0)

    if args.sync_comparables:
        client = None
        if not args.dry_run:
            client = authenticate_anthropic_client()
        stats = sync_comparables(
            catalog,
            client=client,
            dry_run=args.dry_run,
            report_path=args.report,
        )
        print_sync_summary(stats)
        if not args.dry_run:
            save_catalog(catalog, args.catalog)
            save_index(catalog, args.index)
            print(f"  Wrote → {args.catalog} (+ {args.index})")
        sys.exit(0)

    if args.canonicalize_signals or args.canonicalize_themes:
        client = authenticate_anthropic_client()
        if args.canonicalize_signals:
            print("\nCanonicalising taste_signals…")
            stats = canonicalize_signals(catalog, client)
            print(f"  distinct phrases : {stats['distinct_phrases']}")
            print(f"  mapped           : {stats['phrases_mapped']}")
            print(f"  unmapped         : {stats['phrases_unmapped']}")
            print(f"  entries changed  : {stats['entries_changed']}")
            save_catalog(catalog, args.catalog)
            save_index(catalog, args.index)
        if args.canonicalize_themes:
            print("\nCanonicalising themes…")
            stats = canonicalize_themes(catalog, client)
            print(f"  distinct phrases : {stats['distinct_phrases']}")
            print(f"  mapped           : {stats['phrases_mapped']}")
            print(f"  unmapped         : {stats['phrases_unmapped']}")
            print(f"  entries changed  : {stats['entries_changed']}")
            save_catalog(catalog, args.catalog)
            save_index(catalog, args.index)
        print(f"\n  Wrote → {args.catalog} (+ {args.index})")
        sys.exit(0)

    if args.audit_library_genres:
        client = authenticate_anthropic_client()
        stats = audit_library_genres(
            Path(args.library),
            client,
            chunk_size=args.chunk_size,
            apply_changes=args.apply_changes,
        )
        print(f"\nLibrary genre audit complete.")
        print(f"  rows audited       : {stats['rows_audited']}")
        print(f"  responses received : {stats['responses_received']}")
        print(f"  proposed changes   : {stats['proposed_changes']}")
        print(f"  applied            : {stats['applied']}")
        if not args.apply_changes and stats["proposed_changes"]:
            print("  (review report; rerun with --apply-changes to commit.)")
        sys.exit(0)

    books = load_library(args.library)

    if not books:
        print(f"Error: no books found in {args.library}. Check CSV format.")
        sys.exit(1)

    # Capture pre-sync status counts so the audit summary can report deltas.
    pre_counts = _status_counts(catalog)

    # Sync library — adds pending stubs for new books and re-applies CSV-authoritative
    # fields (pages, goodreads_rating, goodreads_reviews) onto every existing entry.
    library_sync_stats = sync_library_to_catalog(books, catalog)
    if library_sync_stats["added"]:
        print(f"  Added {library_sync_stats['added']} new pending entries from library.")
    if library_sync_stats["refreshed"]:
        print(f"  Refreshed {library_sync_stats['refreshed']} CSV-authoritative field values on existing entries.")
    if library_sync_stats["added"] or library_sync_stats["refreshed"]:
        save_catalog(catalog, args.catalog)
        save_index(catalog, args.index)

    print_status(catalog)

    # Early exits
    if args.status:
        sys.exit(0)

    # Determine which entries to process
    if args.review_only:
        target_statuses = {"needs_review"}
        print("Mode: reprocessing needs_review entries.\n")
    else:
        target_statuses = {"pending"}
        print("Mode: cataloguing all pending entries.\n")

    pending_entries = [
        (key, {**entry, **get_book_csv_data(books, key)})
        for key, entry in catalog["entries"].items()
        if entry["status"] in target_statuses
    ]

    if not pending_entries:
        print("Nothing to process.")
        sys.exit(0)

    total_to_process = len(pending_entries)
    estimated_chunks = -(-total_to_process // args.chunk_size)
    print(f"  {total_to_process} entries to process in ~{estimated_chunks} chunks of {args.chunk_size}.\n")

    from catalogue_prompts import build_system_prompt
    client = authenticate_anthropic_client()
    system = build_system_prompt()

    processed = 0
    chunk_num = 0
    consecutive_failures = 0

    while processed < total_to_process:
        chunk_num += 1
        chunk_slice = pending_entries[processed: processed + args.chunk_size]
        chunk_data = [entry for _, entry in chunk_slice]

        print(f"Chunk {chunk_num}/{estimated_chunks} — "
              f"books {processed + 1}–{processed + len(chunk_slice)} of {total_to_process}")

        try:
            n = catalogue_chunk(client, chunk_data, catalog, system)
            print(f"  Catalogued {n}/{len(chunk_slice)} entries.")
            consecutive_failures = 0
        except Exception as e:
            print(f"  Error processing chunk: {e}")
            consecutive_failures += 1
            if consecutive_failures >= 3:
                save_catalog(catalog, args.catalog)
                print(f"  Saved → {args.catalog}")
                print("\n  3 consecutive chunk failures — rate limit likely saturated.")
                print("  Progress saved. Re-run the script to resume.")
                print_status(catalog)
                sys.exit(1)
            print("  Saving progress and continuing...")

        save_catalog(catalog, args.catalog)
        save_index(catalog, args.index)
        print(f"  Saved → {args.catalog} (+ {args.index})")

        processed += len(chunk_slice)
        remaining = total_to_process - processed
        if remaining > 0:
            print(f"  {remaining} entries remaining.")
            time.sleep(RATE_LIMIT_DELAY)

    save_index(catalog, args.index)
    print(f"  Wrote slim index → {args.index}")

    # Run the comparable_books sync at the tail so a fresh build always
    # lands canonical, reciprocated, and Claude-ranked.
    comparables_stats = sync_comparables(catalog, client=client)
    print_sync_summary(comparables_stats)
    save_catalog(catalog, args.catalog)
    save_index(catalog, args.index)

    print("\nCataloguing complete.")
    print_status(catalog)

    if args.sync:
        run_sync_export(
            catalog=catalog,
            library_sync_stats=library_sync_stats,
            comparables_stats=comparables_stats,
            pre_counts=pre_counts,
            sqlite_path=Path(args.sync_sqlite),
            audit_path=Path(args.sync_audit),
            push=not args.no_push,
        )


if __name__ == "__main__":
    main()
