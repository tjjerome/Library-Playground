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
                "series_role": None,
                "author_entry_point": None,
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
    args = parser.parse_args()

    catalog = load_catalog(args.catalog)

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
    sync_stats = sync_comparables(catalog, client=client)
    print_sync_summary(sync_stats)
    save_catalog(catalog, args.catalog)
    save_index(catalog, args.index)

    print("\nCataloguing complete.")
    print_status(catalog)


if __name__ == "__main__":
    main()
