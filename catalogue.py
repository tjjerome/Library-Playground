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
    pip install anthropic
    Must be run inside a Claude Code session — authenticates via the session
    ingress token at $CLAUDE_SESSION_INGRESS_TOKEN_FILE. Refuses to run if
    ANTHROPIC_API_KEY is set (to avoid accidental external billing).
"""

import argparse
import csv
import json
import os
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


# Library.csv is the source of truth for these three fields. The cataloguer
# never asks the LLM for them and never lets stale catalog values stand:
# every sync re-applies whatever the CSV currently says.
CSV_AUTHORITATIVE_FIELDS = ("pages", "goodreads_rating", "goodreads_reviews")


def csv_authoritative_values(book: dict) -> dict:
    """Pull pages / goodreads_rating / goodreads_reviews out of a CSV row.

    Only fields the CSV actually provides are returned, so callers can
    distinguish "CSV says this" from "CSV is silent" and leave existing
    catalog values alone in the latter case.
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

    # Goodreads rating lives inside the comma-joined identifiers field as
    # "grrating:3.99" rather than its own column.
    for piece in (book.get("identifiers") or "").split(","):
        piece = piece.strip()
        if piece.startswith("grrating:"):
            try:
                out["goodreads_rating"] = float(piece.split(":", 1)[1])
            except ValueError:
                pass
            break

    return out


def sync_library_to_catalog(books: list[dict], catalog: dict) -> tuple[int, int]:
    """Add stubs for new library books and re-apply CSV-authoritative fields.

    Returns (added, refreshed): how many new pending stubs were created and
    how many existing entries had a pages/goodreads field updated to match
    the CSV.
    """
    added = 0
    refreshed = 0
    for book in books:
        key = book_key(book["title"], book["authors"])
        csv_fields = csv_authoritative_values(book)
        if key not in catalog["entries"]:
            catalog["entries"][key] = {
                "title": book["title"],
                "author": book["authors"],
                "series": book.get("series") or None,
                "series_position": None,
                "genre": book.get("genre") or None,
                "series_status": book.get("series_type") or None,
                "indie": None,
                "classic": None,
                "status": "pending",
                "summary": None,
                "tone": None,
                "pacing": None,
                "themes": [],
                "setting": None,
                "comparable_books": [],
                "taste_signals": {"positive": [], "negative": []},
                "audio_suitability": None,
                "audio_notes": None,
                "content_flags": [],
                "confidence": None,
                "research_source": None,
                **csv_fields,
            }
            added += 1
        else:
            entry = catalog["entries"][key]
            for field, value in csv_fields.items():
                if entry.get(field) != value:
                    entry[field] = value
                    refreshed += 1
    return added, refreshed


def get_book_csv_data(books: list[dict], key: str) -> dict:
    """Look up the original CSV row for a book by its catalog key."""
    for book in books:
        if book_key(book["title"], book["authors"]) == key:
            return book
    return {}

# ---------------------------------------------------------------------------
# API call with tool-use loop
# ---------------------------------------------------------------------------

def call_api_with_tools(client, messages: list, system: str) -> str:
    """Runs the multi-turn tool-use loop. Returns final assistant text."""
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
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=cached_system,
                tools=[WEB_SEARCH_TOOL],
                messages=messages
            )

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
                response = client.messages.create(
                    model=MODEL,
                    max_tokens=MAX_TOKENS,
                    system=cached_system,
                    tools=[WEB_SEARCH_TOOL],
                    messages=messages
                )

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

    normalized_index = {normalize_key(ck): ck for ck in catalog["entries"]}

    for key, entry_data in results.items():
        matched_key = None
        if key in catalog["entries"]:
            matched_key = key
        elif normalize_key(key) in normalized_index:
            matched_key = normalized_index[normalize_key(key)]
        else:
            title_norm = normalize_key(entry_data.get("title", ""))
            if title_norm:
                for nck, ck in normalized_index.items():
                    if title_norm in nck:
                        matched_key = ck
                        break

        if matched_key:
            existing = catalog["entries"][matched_key]
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
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)

    if args.index_only:
        save_index(catalog, args.index)
        print(f"  Wrote slim index → {args.index} ({len(catalog['entries'])} entries)")
        sys.exit(0)

    books = load_library(args.library)

    if not books:
        print(f"Error: no books found in {args.library}. Check CSV format.")
        sys.exit(1)

    # Sync library — adds pending stubs for new books and re-applies CSV-authoritative
    # fields (pages, goodreads_rating, goodreads_reviews) onto every existing entry.
    added, refreshed = sync_library_to_catalog(books, catalog)
    if added:
        print(f"  Added {added} new pending entries from library.")
    if refreshed:
        print(f"  Refreshed {refreshed} CSV-authoritative field values on existing entries.")
    if added or refreshed:
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

    # Heavy imports only needed for the API path
    import anthropic
    from catalogue_prompts import build_system_prompt

    # Auth: only the Claude Code session ingress token is supported.
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
    client = anthropic.Anthropic()
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

    print("\nCataloguing complete.")
    print_status(catalog)


if __name__ == "__main__":
    main()
