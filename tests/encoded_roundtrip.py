#!/usr/bin/env python3
"""Encode/decode parity test for `webhelper/encoded_codec`.

Steps:
  1. Export `Library_Catalog.json` to a temp SQLite.
  2. Encode the SQLite to `.encoded` text.
  3. Decode `.encoded` back to bytes.
  4. Compare decoded bytes to the original SQLite bytes.
  5. Open the decoded SQLite and run a few sanity queries.

Run via:
    python3 tests/encoded_roundtrip.py
    python3 tests/encoded_roundtrip.py --catalog Library_Catalog.json
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from webhelper.encoded_codec import (  # noqa: E402
    FORMAT_HEADER,
    decode_text,
    encode_bytes,
)
from webhelper.sqlite_export import export  # noqa: E402


def run(catalog_path: Path) -> int:
    with open(catalog_path, "r", encoding="utf-8") as f:
        catalog = json.load(f)

    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        sqlite_path = tmp_path / "Library_Catalog.sqlite"
        export(catalog, sqlite_path)

        original = sqlite_path.read_bytes()
        encoded = encode_bytes(original)

        # Header line
        first_line = encoded.splitlines()[0]
        assert first_line == FORMAT_HEADER, (
            f"header mismatch: {first_line!r} != {FORMAT_HEADER!r}"
        )

        decoded = decode_text(encoded)
        assert decoded == original, (
            f"byte mismatch after round-trip: "
            f"original={len(original)}B, decoded={len(decoded)}B"
        )

        # Confirm the decoded bytes form a valid SQLite that opens.
        roundtrip_path = tmp_path / "decoded.sqlite"
        roundtrip_path.write_bytes(decoded)
        conn = sqlite3.connect(str(roundtrip_path))
        try:
            ok = conn.execute("PRAGMA integrity_check").fetchone()[0]
            assert ok == "ok", f"integrity_check failed: {ok}"

            book_count = conn.execute("SELECT COUNT(*) FROM books").fetchone()[0]
            json_count = len(catalog["entries"])
            assert book_count == json_count, (
                f"books count mismatch after decode: "
                f"sqlite={book_count}, json={json_count}"
            )

            ts = conn.execute("SELECT COUNT(*) FROM taste_signals").fetchone()[0]
            af = conn.execute("SELECT COUNT(*) FROM audit_flags").fetchone()[0]
            cb = conn.execute("SELECT COUNT(*) FROM comparable_books").fetchone()[0]
        finally:
            conn.close()

        sizes = (
            f"raw={len(original):,}B  encoded={len(encoded.encode()):,}B  "
            f"ratio={len(encoded.encode()) / len(original):.2f}x"
        )

    print(f"OK: round-trip clean ({json_count} books, {ts} signals, "
          f"{af} audit flags, {cb} comp links).  {sizes}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--catalog", default="Library_Catalog.json")
    args = p.parse_args()
    return run(Path(args.catalog))


if __name__ == "__main__":
    sys.exit(main())
