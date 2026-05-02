#!/usr/bin/env python3
"""Encode / decode helper for `Library_Catalog.sqlite.encoded`.

The claude.ai Google Drive connector exposes only metadata for binary
files; SQLite therefore travels as a text-wrapped form. The encoding
is gzip + base64, with a single-line header identifying format and
version so consumers can detect drift.

File format:

    # library-playground-catalog v1 gzip+b64
    H4sIAAAA...<base64 body across one or more lines>...

Decode order: strip header → base64-decode → gunzip → SQLite bytes.

CLI:
    python3 -m webhelper.encoded_codec encode  in.sqlite  out.encoded
    python3 -m webhelper.encoded_codec decode  in.encoded out.sqlite
"""

from __future__ import annotations

import argparse
import base64
import gzip
import sys
from pathlib import Path

FORMAT_HEADER = "# library-playground-catalog v1 gzip+b64"
FORMAT_VERSION = "v1"


class FormatError(ValueError):
    """Raised when the encoded file's header is missing or unrecognized."""


def encode_bytes(raw: bytes) -> str:
    """Return header + base64-of-gzip-of-raw, newline-joined."""
    compressed = gzip.compress(raw, compresslevel=9)
    body = base64.b64encode(compressed).decode("ascii")
    # Wrap body to 76-column lines for human-readable git diffs.
    wrapped = "\n".join(body[i:i + 76] for i in range(0, len(body), 76))
    return f"{FORMAT_HEADER}\n{wrapped}\n"


def decode_text(text: str) -> bytes:
    """Inverse of `encode_bytes`. Raises FormatError on bad header /
    base64 / gzip."""
    lines = text.splitlines()
    if not lines:
        raise FormatError("empty encoded file")
    header = lines[0].strip()
    if not header.startswith("# library-playground-catalog "):
        raise FormatError(f"unexpected header: {header!r}")
    parts = header.split()
    if len(parts) < 4 or parts[3] != "gzip+b64":
        raise FormatError(f"unsupported encoding: {header!r}")
    if parts[2] != FORMAT_VERSION:
        raise FormatError(f"unsupported format version: {parts[2]!r}")
    body = "".join(lines[1:]).strip()
    try:
        compressed = base64.b64decode(body, validate=True)
    except Exception as e:
        raise FormatError(f"base64 decode failed: {e}") from e
    try:
        return gzip.decompress(compressed)
    except Exception as e:
        raise FormatError(f"gunzip failed: {e}") from e


def encode_file(src: Path, dst: Path) -> None:
    dst.write_text(encode_bytes(src.read_bytes()), encoding="utf-8")


def decode_file(src: Path, dst: Path) -> None:
    dst.write_bytes(decode_text(src.read_text(encoding="utf-8")))


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="encoded_codec")
    sub = p.add_subparsers(dest="cmd", required=True)
    enc = sub.add_parser("encode")
    enc.add_argument("src")
    enc.add_argument("dst")
    dec = sub.add_parser("decode")
    dec.add_argument("src")
    dec.add_argument("dst")
    args = p.parse_args(argv)

    if args.cmd == "encode":
        encode_file(Path(args.src), Path(args.dst))
    else:
        decode_file(Path(args.src), Path(args.dst))
    return 0


if __name__ == "__main__":
    sys.exit(main())
