#!/usr/bin/env python3
"""
Library Cataloguer
Autonomously builds Library_Catalog.json from a Library CSV,
including an inline audit of CSV tags against known records.
Designed to run in Claude Code without requiring human approval between chunks.

Usage:
    python catalogue.py --library Library.csv
    python catalogue.py --library Library.csv --chunk-size 40
    python catalogue.py --library Library.csv --status
    python catalogue.py --library Library.csv --audit-report
    python catalogue.py --library Library.csv --re-audit     # reprocess for audit only
    python catalogue.py --library Library.csv --review-only  # reprocess needs_review entries

Requirements:
    pip install anthropic
    ANTHROPIC_API_KEY must be set (Claude Code handles this automatically)
"""

import anthropic
import argparse
import csv
import json
import os
import sys
import time
from datetime import date
from pathlib import Path

from catalogue_prompts import (
    build_system_prompt,
    build_batch_prompt,
    parse_catalog_response,
    generate_audit_report,
)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

CATALOG_FILE = "Library_Catalog.json"
AUDIT_REPORT_FILE = "Library_Audit_Report.md"
MODEL = "claude-haiku-4-5-20251001"
MAX_TOKENS = 8000
DEFAULT_CHUNK_SIZE = 10
RATE_LIMIT_DELAY = 1.5   # seconds between API calls
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


def book_key(title: str, author: str) -> str:
    return f"{title.strip()} - {author.strip()}"

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


def sync_library_to_catalog(books: list[dict], catalog: dict) -> int:
    """Add pending stubs for any library books not yet in the catalog."""
    added = 0
    for book in books:
        key = book_key(book["title"], book["authors"])
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
                "audit": None
            }
            added += 1
    return added


def get_book_csv_data(books: list[dict], key: str) -> dict:
    """Look up the original CSV row for a book by its catalog key."""
    for book in books:
        if book_key(book["title"], book["authors"]) == key:
            return book
    return {}

# ---------------------------------------------------------------------------
# API call with tool-use loop
# ---------------------------------------------------------------------------

def call_api_with_tools(client: anthropic.Anthropic, messages: list, system: str) -> str:
    """Runs the multi-turn tool-use loop. Returns final assistant text."""
    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=MAX_TOKENS,
                system=system,
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
                    system=system,
                    tools=[WEB_SEARCH_TOOL],
                    messages=messages
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
    client: anthropic.Anthropic,
    chunk: list[dict],
    catalog: dict,
    system: str
) -> tuple[int, int]:
    """
    Send a chunk of book dicts (with CSV data included) to Claude.
    Updates catalog entries in place.
    Returns (n_catalogued, n_audit_flags).
    """
    print(f"\n  Sending {len(chunk)} books to Claude...")

    prompt = build_batch_prompt(chunk)
    messages = [{"role": "user", "content": prompt}]

    raw = call_api_with_tools(client, messages, system)
    results = parse_catalog_response(raw)

    if not results:
        print("  Warning: could not parse response. Entries remain pending.")
        return 0, 0

    catalogued = 0
    audit_flags = 0

    for key, entry_data in results.items():
        matched_key = None
        if key in catalog["entries"]:
            matched_key = key
        else:
            for ck in catalog["entries"]:
                if entry_data.get("title", "").lower() in ck.lower():
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
            # Count audit flags
            audit = entry_data.get("audit", {})
            if audit and not audit.get("passed", True):
                flags = audit.get("flags", [])
                audit_flags += len(flags)
            catalogued += 1
        else:
            print(f"  Warning: couldn't match '{key}' to a catalog entry — skipping.")

    return catalogued, audit_flags

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

    # Audit stats
    audited = sum(1 for e in entries.values() if e.get("audit") is not None)
    audit_failures = sum(
        1 for e in entries.values()
        if e.get("audit") and not e["audit"].get("passed", True)
    )

    print(f"\n{'='*55}")
    print(f"  Library Catalog Status")
    print(f"{'='*55}")
    print(f"  Total in library : {total}")
    print(f"  Complete         : {complete}")
    print(f"  Needs review     : {needs_review}")
    print(f"  Pending          : {pending}")
    print(f"  Progress         : {pct}%")
    print(f"  Audited entries  : {audited}")
    print(f"  Audit failures   : {audit_failures}")
    print(f"  Last updated     : {catalog.get('last_updated', 'never')}")
    print(f"{'='*55}\n")


def write_audit_report(catalog: dict, path: str):
    report = generate_audit_report(catalog)
    with open(path, "w", encoding="utf-8") as f:
        f.write(report)
    print(f"Audit report written → {path}")

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Autonomously catalogue a book library.")
    parser.add_argument("--library", required=True, help="Path to Library.csv")
    parser.add_argument("--catalog", default=CATALOG_FILE)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--status", action="store_true", help="Print progress and exit")
    parser.add_argument("--audit-report", action="store_true",
                        help="Generate audit report from existing catalog and exit")
    parser.add_argument("--re-audit", action="store_true",
                        help="Reprocess all complete entries to add/refresh audit data")
    parser.add_argument("--review-only", action="store_true",
                        help="Only reprocess needs_review entries")
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)
    books = load_library(args.library)

    if not books:
        print(f"Error: no books found in {args.library}. Check CSV format.")
        sys.exit(1)

    # Sync library
    added = sync_library_to_catalog(books, catalog)
    if added:
        print(f"  Added {added} new pending entries from library.")
        save_catalog(catalog, args.catalog)

    print_status(catalog)

    # Early exits
    if args.status:
        sys.exit(0)

    if args.audit_report:
        write_audit_report(catalog, AUDIT_REPORT_FILE)
        sys.exit(0)

    # Determine which entries to process
    if args.review_only:
        target_statuses = {"needs_review"}
        print("Mode: reprocessing needs_review entries.\n")
    elif args.re_audit:
        # Re-audit: reprocess complete entries that have no audit data yet
        target_statuses = {"complete"}
        catalog["entries"] = {
            k: v for k, v in catalog["entries"].items()
            if v.get("audit") is None or v["status"] == "pending"
        }
        print("Mode: re-auditing entries without audit data.\n")
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
        write_audit_report(catalog, AUDIT_REPORT_FILE)
        sys.exit(0)

    total_to_process = len(pending_entries)
    estimated_chunks = -(-total_to_process // args.chunk_size)
    print(f"  {total_to_process} entries to process in ~{estimated_chunks} chunks of {args.chunk_size}.\n")

    # Support Claude Code OAuth when no API key is set
    if not os.environ.get("ANTHROPIC_API_KEY") and not os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        creds_path = Path.home() / ".claude" / ".credentials.json"
        if creds_path.exists():
            with open(creds_path) as _f:
                _tok = json.load(_f).get("claudeAiOauth", {}).get("accessToken", "")
            if _tok:
                os.environ["ANTHROPIC_AUTH_TOKEN"] = _tok
    client = anthropic.Anthropic()
    system = build_system_prompt()

    processed = 0
    chunk_num = 0
    total_audit_flags = 0

    while processed < total_to_process:
        chunk_num += 1
        chunk_slice = pending_entries[processed: processed + args.chunk_size]
        chunk_data = [entry for _, entry in chunk_slice]

        print(f"Chunk {chunk_num}/{estimated_chunks} — "
              f"books {processed + 1}–{processed + len(chunk_slice)} of {total_to_process}")

        try:
            n, flags = catalogue_chunk(client, chunk_data, catalog, system)
            total_audit_flags += flags
            flag_note = f", {flags} audit flag(s)" if flags else ""
            print(f"  Catalogued {n}/{len(chunk_slice)} entries{flag_note}.")
        except Exception as e:
            print(f"  Error processing chunk: {e}")
            print("  Saving progress and continuing...")

        save_catalog(catalog, args.catalog)
        print(f"  Saved → {args.catalog}")

        processed += len(chunk_slice)
        remaining = total_to_process - processed
        if remaining > 0:
            print(f"  {remaining} entries remaining.")
            time.sleep(RATE_LIMIT_DELAY)

    print("\nCataloguing complete.")
    print_status(catalog)

    # Always write audit report at the end
    write_audit_report(catalog, AUDIT_REPORT_FILE)
    if total_audit_flags:
        print(f"\n  ⚠️  {total_audit_flags} total audit flags found. Review {AUDIT_REPORT_FILE}.")
    else:
        print(f"\n  ✅  No audit flags. {AUDIT_REPORT_FILE} written.")


if __name__ == "__main__":
    main()
