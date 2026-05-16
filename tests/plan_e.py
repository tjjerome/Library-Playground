#!/usr/bin/env python3
"""Plan E regression tests — catalog startup fix.

Self-contained: builds synthetic SQLite catalogs in-process (no
dependency on the gitignored Library_Catalog.sqlite) and checks:

  E-2  encoded_codec.decode_text() succeeds on the raw .encoded text,
       the bare inner object ({"content": "<b64>"}), and the full
       two-layer Drive JSON envelope alike; and on genuinely malformed
       JSON-looking input it fails with a message that names the
       envelope/unwrap cause — not a bare "unexpected header".

  E-1  fetch_catalog.fetch() turns each download shape into a valid
       Library_Catalog.sqlite with one short confirmation line;
       idempotent across re-runs; rejects an implausible book count
       instead of emitting a corrupt database.

Prints OK and exits 0 on success; prints failures and exits 1.
"""

from __future__ import annotations

import base64
import io
import json
import sqlite3
import sys
import tempfile
from contextlib import redirect_stdout
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from webhelper import encoded_codec as ec  # noqa: E402
from webhelper import fetch_catalog as fc  # noqa: E402
from webhelper import sqlite_export as se  # noqa: E402
from webhelper.book_identity import norm, title_short  # noqa: E402


def _make_sqlite_bytes(n_books: int) -> bytes:
    """A minimal but real SQLite catalog with `n_books` rows."""
    with tempfile.TemporaryDirectory() as d:
        path = Path(d) / "c.sqlite"
        conn = sqlite3.connect(str(path))
        for stmt in se.SCHEMA:
            conn.execute(stmt)
        for i in range(n_books):
            t, a = f"Book {i}", f"Author {i}"
            conn.execute(
                "INSERT INTO books (key, title, title_normalized, "
                "title_short, author, author_normalized, "
                "goodreads_rating, goodreads_reviews) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (f"k{i}", t, norm(t), title_short(t),
                 a, norm(a), 4.2, 1000))
        conn.commit()
        conn.close()
        return path.read_bytes()


def _full_envelope(encoded_text: str) -> str:
    """The two-layer Drive shape: outer list -> text part whose string
    is itself JSON with a base64 `content` field."""
    inner = json.dumps({
        "id": "1QEe3-9Hv0CEe1lsT4C9aRFFYTFgKsjPy",
        "title": "Library_Catalog.sqlite.encoded",
        "mimeType": "text/plain",
        "content": base64.b64encode(
            encoded_text.encode("utf-8")).decode("ascii"),
    })
    return json.dumps([{"type": "text", "text": inner}])


def _bare_inner(encoded_text: str) -> str:
    return json.dumps({
        "title": "Library_Catalog.sqlite.encoded",
        "content": base64.b64encode(
            encoded_text.encode("utf-8")).decode("ascii"),
    })


def main() -> int:  # noqa: C901
    fails: list[str] = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            fails.append(msg)

    sqlite_bytes = _make_sqlite_bytes(1500)
    encoded = ec.encode_bytes(sqlite_bytes)

    shapes = {
        "raw .encoded": encoded,
        "bare inner object": _bare_inner(encoded),
        "full Drive envelope": _full_envelope(encoded),
    }

    # ---- E-2: decode_text accepts all three shapes ----------------
    for name, payload in shapes.items():
        try:
            out = ec.decode_text(payload)
            check(out == sqlite_bytes,
                  f"E-2 decode_text({name}) byte mismatch")
        except Exception as e:  # noqa: BLE001
            check(False, f"E-2 decode_text({name}) raised {e!r}")

    # Malformed JSON-looking input -> actionable envelope message,
    # never a bare "unexpected header".
    for bad in ('[{"type": "text", "text": "no content here"}]',
                '{"mimeType": "text/plain"}',
                '[{"oops": true'):
        try:
            ec.decode_text(bad)
            check(False, f"E-2 malformed input did not raise: {bad[:30]!r}")
        except ec.FormatError as e:
            m = str(e).lower()
            check("envelope" in m or "unwrap" in m or "content" in m
                  or "fetch_catalog" in m,
                  f"E-2 message not actionable for {bad[:30]!r}: {e}")
            check("unexpected header" not in m,
                  f"E-2 bare 'unexpected header' for JSON input {bad[:30]!r}")
        except Exception as e:  # noqa: BLE001
            check(False, f"E-2 wrong exception type for {bad[:30]!r}: {e!r}")

    # Genuinely malformed non-JSON input keeps the bare header message.
    try:
        ec.decode_text("garbage line one\ngarbage line two\n")
        check(False, "E-2 non-JSON garbage did not raise")
    except ec.FormatError as e:
        check("unexpected header" in str(e),
              f"E-2 non-JSON garbage should say 'unexpected header': {e}")

    # ---- E-1: fetch_catalog end-to-end on every shape -------------
    for name, payload in shapes.items():
        with tempfile.TemporaryDirectory() as d:
            inp = Path(d) / "download.json"
            inp.write_text(payload, encoding="utf-8")
            outp = Path(d) / "Library_Catalog.sqlite"
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = fc.fetch(inp, outp)
            line = buf.getvalue().strip()
            check(rc == 0, f"E-1 fetch({name}) rc={rc}")
            check(outp.is_file(), f"E-1 fetch({name}) no output file")
            check(line.startswith("catalog OK: 1500 books"),
                  f"E-1 fetch({name}) bad confirmation: {line!r}")
            check("\n" not in line and len(line) < 200,
                  f"E-1 fetch({name}) confirmation not one short line")
            if outp.is_file():
                conn = sqlite3.connect(str(outp))
                cnt = conn.execute(
                    "SELECT COUNT(*) FROM books").fetchone()[0]
                conn.close()
                check(cnt == 1500,
                      f"E-1 fetch({name}) count {cnt} != 1500")

    # Idempotent: re-running on an already-produced output is fine, and
    # feeding the raw .encoded text again yields the same result.
    with tempfile.TemporaryDirectory() as d:
        inp = Path(d) / "in.encoded"
        inp.write_text(encoded, encoding="utf-8")
        outp = Path(d) / "out.sqlite"
        with redirect_stdout(io.StringIO()):
            rc1 = fc.fetch(inp, outp)
            first = outp.read_bytes()
            rc2 = fc.fetch(inp, outp)
            second = outp.read_bytes()
        check(rc1 == 0 and rc2 == 0, "E-1 idempotent run rc != 0")
        check(first == second == sqlite_bytes,
              "E-1 re-run not idempotent / bytes differ")

    # Sanity bound: an implausibly small catalog is refused, not
    # silently emitted.
    tiny = ec.encode_bytes(_make_sqlite_bytes(5))
    with tempfile.TemporaryDirectory() as d:
        inp = Path(d) / "tiny.encoded"
        inp.write_text(tiny, encoding="utf-8")
        outp = Path(d) / "tiny.sqlite"
        buf = io.StringIO()
        # _fail writes to stderr; just confirm rc and no output file.
        rc = fc.fetch(inp, outp)
        check(rc != 0, "E-1 implausible count not rejected")
        check(not outp.exists(),
              "E-1 corrupt catalog emitted despite bad count")

    if fails:
        print("FAILURES:")
        for f in fails:
            print("  -", f)
        return 1
    print("OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
