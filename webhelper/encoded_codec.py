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
import json
import sys
from pathlib import Path

FORMAT_HEADER = "# library-playground-catalog v1 gzip+b64"
FORMAT_VERSION = "v1"
HEADER_PREFIX = "# library-playground-catalog "


class FormatError(ValueError):
    """Raised when the encoded file's header is missing or unrecognized."""


def _looks_like_encoded(text: str) -> bool:
    return text.lstrip().startswith(HEADER_PREFIX)


def _looks_like_json(text: str) -> bool:
    return text.lstrip()[:1] in ("[", "{")


def _b64_to_encoded(s: str) -> str | None:
    """If `s` is base64 that decodes to the `.encoded` text, return that
    text; otherwise None."""
    try:
        raw = base64.b64decode("".join(s.split()), validate=False)
    except Exception:
        return None
    for enc in ("utf-8", "latin-1"):
        try:
            decoded = raw.decode(enc)
        except Exception:
            continue
        if _looks_like_encoded(decoded):
            return decoded
    return None


def _locate_encoded(obj: object) -> str | None:
    """Walk a parsed-JSON structure looking for a base64 field that
    decodes to the `.encoded` text. Tolerant of envelope nesting and of
    JSON-encoded string values (the Drive `outer[0]["text"]` shape)."""
    if isinstance(obj, dict):
        val = obj.get("content")
        if isinstance(val, str):
            found = _b64_to_encoded(val)
            if found is not None:
                return found
        for v in obj.values():
            found = _locate_encoded(v)
            if found is not None:
                return found
    elif isinstance(obj, list):
        for v in obj:
            found = _locate_encoded(v)
            if found is not None:
                return found
    elif isinstance(obj, str):
        s = obj.strip()
        if _looks_like_encoded(s):
            return s
        if s[:1] in ("[", "{"):
            try:
                return _locate_encoded(json.loads(s))
            except Exception:
                return None
        # A loose base64 string is only treated as content when it
        # actually decodes to the encoded text (cheap, exact check).
        return _b64_to_encoded(s)
    return None


def unwrap_envelope(text: str) -> str:
    """Given the raw Drive download (JSON envelope, bare inner object,
    or a nested JSON string), return the `.encoded` text. Raises
    FormatError with an actionable message if it cannot be unwrapped."""
    try:
        obj = json.loads(text)
    except Exception as e:
        raise FormatError(
            "input looks like the Drive JSON envelope but is not valid "
            f"JSON ({e}); expected the .encoded text or a wrapper with a "
            "base64 'content' field — unwrap it first, or use "
            "fetch_catalog.py"
        ) from e
    found = _locate_encoded(obj)
    if found is None:
        raise FormatError(
            "input looks like the Drive JSON envelope, not the .encoded "
            "text; could not locate a base64 'content' field to unwrap "
            "(use fetch_catalog.py, or base64-decode the 'content' field "
            "first)"
        )
    return found


def encode_bytes(raw: bytes) -> str:
    """Return header + base64-of-gzip-of-raw, newline-joined."""
    compressed = gzip.compress(raw, compresslevel=9)
    body = base64.b64encode(compressed).decode("ascii")
    # Wrap body to 76-column lines for human-readable git diffs.
    wrapped = "\n".join(body[i:i + 76] for i in range(0, len(body), 76))
    return f"{FORMAT_HEADER}\n{wrapped}\n"


def decode_text(text: str) -> bytes:
    """Inverse of `encode_bytes`. Accepts the `.encoded` text directly,
    or the raw Drive JSON envelope / bare inner object, which it
    unwraps first. Raises FormatError on bad header / base64 / gzip."""
    if not _looks_like_encoded(text) and _looks_like_json(text):
        text = unwrap_envelope(text)
    lines = text.splitlines()
    if not lines:
        raise FormatError("empty encoded file")
    header = lines[0].strip()
    if not header.startswith(HEADER_PREFIX):
        if _looks_like_json(text):
            raise FormatError(
                "input looks like the Drive JSON envelope, not the "
                ".encoded text; unwrap the base64 'content' field first "
                "(or use fetch_catalog.py)"
            )
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
