#!/usr/bin/env python3
"""Convert Library_Catalog.sqlite to Library_Catalog.json.

This script reads the SQLite database and reconstructs the JSON catalog,
ensuring the JSON file stays in sync with the live SQLite database.

Usage:
    python3 webhelper/sqlite_to_json.py Library_Catalog.sqlite Library_Catalog.json
    python3 webhelper/sqlite_to_json.py [--help]
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Optional

# Import reconstruction functions from sqlite_export
try:
    from sqlite_export import reconstruct_entry, load_meta
except ImportError:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from sqlite_export import reconstruct_entry, load_meta  # noqa: E402


def sqlite_to_json(
    sqlite_path: Path,
    json_path: Path,
    indent: Optional[int] = 2,
) -> None:
    """Convert SQLite catalog to JSON format.
    
    Args:
        sqlite_path: Path to Library_Catalog.sqlite
        json_path: Output path for Library_Catalog.json
        indent: JSON indent level (None for compact, 2 for pretty-print)
    """
    if not sqlite_path.exists():
        raise FileNotFoundError(f"SQLite file not found: {sqlite_path}")
    
    conn = sqlite3.connect(str(sqlite_path))
    try:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        
        # Load metadata
        meta = load_meta(conn)
        
        # Get all book keys
        keys = [r["key"] for r in cur.execute(
            "SELECT key FROM books ORDER BY key"
        )]
        
        # Reconstruct all entries
        entries = {}
        for key in keys:
            entries[key] = reconstruct_entry(conn, key)
        
        # Build complete catalog
        catalog = {
            "catalog_version": meta.get("catalog_version", 2),
            "last_updated": meta.get("last_updated", ""),
            "total_in_library": meta.get("total_in_library"),
            "total_catalogued": meta.get("total_catalogued"),
            "total_pending": meta.get("total_pending"),
            "entries": entries,
        }
        
        # Write JSON
        json_path.parent.mkdir(parents=True, exist_ok=True)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(catalog, f, indent=indent, ensure_ascii=False)
        
        print(f"✓ Exported {len(entries)} entries to {json_path}")
        print(f"  Version: {catalog['catalog_version']}")
        print(f"  Updated: {catalog['last_updated']}")
        print(f"  Total catalogued: {catalog.get('total_catalogued', 'N/A')}")
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Convert Library_Catalog.sqlite to Library_Catalog.json",
    )
    parser.add_argument(
        "sqlite",
        nargs="?",
        default="Library_Catalog.sqlite",
        help="Path to SQLite database (default: Library_Catalog.sqlite)",
    )
    parser.add_argument(
        "json",
        nargs="?",
        default="Library_Catalog.json",
        help="Output JSON path (default: Library_Catalog.json)",
    )
    parser.add_argument(
        "--compact",
        action="store_true",
        help="Output compact JSON (no pretty-printing)",
    )
    
    args = parser.parse_args()
    
    try:
        sqlite_to_json(
            Path(args.sqlite),
            Path(args.json),
            indent=None if args.compact else 2,
        )
        return 0
    except Exception as e:
        print(f"✗ Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
