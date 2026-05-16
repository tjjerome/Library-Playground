#!/usr/bin/env python3
"""Bootstrap helper: raw Drive download artifact -> queryable SQLite.

The claude.ai Google Drive connector's `download_file_content` returns
the catalog base64-encoded inside a JSON envelope, two layers deep:

    [ { "type": "text",
        "text": "{ \"title\": \"...encoded\", \"content\": \"<BASE64>\" }" } ]

This script takes whatever `download_file_content` produced and emits a
ready-to-query `Library_Catalog.sqlite`, doing all unwrapping and
decoding in one process so no intermediate (a multi-megabyte JSON blob)
ever routes through the agent's context. It reads the input file from
disk directly and never prints its body — a failure stays a single
short line so a failed run cannot reintroduce the context blow-up.

Usage:
    python3 fetch_catalog.py <input-path> <output-sqlite-path>

Stdlib only. The actual decode (header strip -> base64 -> gunzip) and
envelope unwrapping are delegated to encoded_codec, bundled alongside.
"""

from __future__ import annotations

import os
import sqlite3
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from encoded_codec import FormatError, decode_text  # type: ignore
except ImportError:  # running from the repo (webhelper is a package)
    sys.path.insert(
        0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    from webhelper.encoded_codec import FormatError, decode_text

# The live catalog is ~4,637 books; anything wildly outside this band is
# a corrupt/wrong-file decode, not a real catalog.
MIN_BOOKS = 1000
MAX_BOOKS = 20000


def _fail(msg: str) -> int:
    # One short line, no payload bodies, ever.
    print(f"catalog FAILED: {msg}", file=sys.stderr)
    return 1


def fetch(input_path: Path, output_path: Path) -> int:
    if not input_path.is_file():
        return _fail(f"input not found: {input_path}")

    try:
        text = input_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:  # pragma: no cover - filesystem edge
        return _fail(f"could not read input: {type(e).__name__}")

    # decode_text auto-detects the JSON envelope / bare inner object and
    # the raw .encoded text alike; idempotent across re-downloads.
    try:
        raw = decode_text(text)
    except FormatError as e:
        return _fail(str(e))
    except Exception as e:  # pragma: no cover - defensive
        return _fail(f"decode error: {type(e).__name__}")

    # Write atomically so a partial decode never leaves a half SQLite.
    try:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fd, tmp = tempfile.mkstemp(
            dir=str(output_path.parent), suffix=".sqlite.tmp")
        with os.fdopen(fd, "wb") as fh:
            fh.write(raw)
    except Exception as e:  # pragma: no cover - filesystem edge
        return _fail(f"could not write output: {type(e).__name__}")

    try:
        conn = sqlite3.connect(tmp)
        try:
            integrity = conn.execute(
                "PRAGMA integrity_check").fetchone()[0]
            if integrity != "ok":
                return _fail(f"integrity_check: {integrity}")
            count = conn.execute(
                "SELECT COUNT(*) FROM books").fetchone()[0]
        finally:
            conn.close()
    except Exception as e:
        os.unlink(tmp)
        return _fail(f"not a valid catalog database: {type(e).__name__}")

    if not (MIN_BOOKS <= count <= MAX_BOOKS):
        os.unlink(tmp)
        return _fail(
            f"implausible book count {count} (expected ~4,637); "
            "refusing to emit a corrupt catalog")

    os.replace(tmp, output_path)
    print(f"catalog OK: {count} books -> {output_path}")
    return 0


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 2:
        return _fail(
            "usage: fetch_catalog.py <input-path> <output-sqlite-path>")
    return fetch(Path(argv[0]), Path(argv[1]))


if __name__ == "__main__":
    sys.exit(main())
