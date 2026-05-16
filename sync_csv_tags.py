"""Force Library_new.csv tags to match indie/classic ground truth in the catalog.

Standalone:   python3 sync_csv_tags.py
catalogue.py: from sync_csv_tags import sync_tags_from_catalog
"""
import base64
import csv
import gzip
import io
import sqlite3
import tempfile
from pathlib import Path

SQLITE_PATH = Path("Library_Catalog.sqlite")
ENCODED_PATH = Path("Library_Catalog.sqlite.encoded")
FORMAT_HEADER = "# library-playground-catalog v1 gzip+b64"

INDIE_TAG = "Indie"
CLASSICS_TAG = "Classics"

_QUOTE_NORMALIZE = str.maketrans({
    "‘": "'", "’": "'", "‚": "'", "‛": "'",
    "“": '"', "”": '"', "„": '"', "‟": '"',
    "–": "-", "—": "-", "−": "-",
    "​": "", "‌": "", "‍": "", "﻿": "",
})


def book_key(title: str, author: str) -> str:
    return f"{title.strip()} - {author.strip()}"


def normalize_key(s: str) -> str:
    return " ".join(s.translate(_QUOTE_NORMALIZE).lower().split())


def get_db_path() -> Path:
    if SQLITE_PATH.exists() and SQLITE_PATH.stat().st_size > 0:
        return SQLITE_PATH
    text = ENCODED_PATH.read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == FORMAT_HEADER, f"Bad header: {lines[0]!r}"
    body = "".join(lines[1:])
    db_bytes = gzip.decompress(base64.b64decode(body, validate=True))
    tmp = tempfile.NamedTemporaryFile(suffix=".sqlite", delete=False)
    tmp.write(db_bytes)
    tmp.flush()
    return Path(tmp.name)


def build_catalog_index(db_path: Path) -> dict[str, tuple[bool, bool]]:
    """Return normalized_key -> (indie, classic) from SQLite."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("SELECT key, indie, classic FROM books").fetchall()
    conn.close()
    return {normalize_key(row["key"]): (bool(row["indie"]), bool(row["classic"])) for row in rows}


def sync_tags(raw_tags: str, indie: bool, classic: bool) -> str:
    tags = [t.strip() for t in raw_tags.split(",") if t.strip()]
    tags = [t for t in tags if t not in (INDIE_TAG, CLASSICS_TAG)]
    if indie:
        tags.append(INDIE_TAG)
    if classic:
        tags.append(CLASSICS_TAG)
    return ", ".join(tags)


def read_csv(path: Path) -> tuple[list[str], list[dict]]:
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        fieldnames = list(reader.fieldnames)
        rows = list(reader)
    return fieldnames, rows


def write_csv(path: Path, fieldnames: list[str], rows: list[dict]) -> None:
    with open(path, "wb") as f:
        f.write("﻿".encode("utf-8"))
        f.write((",".join(fieldnames) + "\n").encode("utf-8"))
        buf = io.StringIO()
        w = csv.DictWriter(buf, fieldnames=fieldnames, quoting=csv.QUOTE_ALL, lineterminator="\n")
        for row in rows:
            w.writerow(row)
        f.write(buf.getvalue().encode("utf-8"))


def _apply_sync(catalog_index: dict[str, tuple[bool, bool]], csv_path: Path) -> None:
    if not csv_path.exists():
        print(f"  sync_csv_tags: {csv_path} not found, skipping.")
        return
    fieldnames, rows = read_csv(csv_path)
    matched = unmatched = changed = 0
    for row in rows:
        raw_key = book_key(row.get("title", ""), row.get("authors", ""))
        nk = normalize_key(raw_key)
        if nk not in catalog_index:
            unmatched += 1
            continue
        matched += 1
        indie, classic = catalog_index[nk]
        old_tags = row.get("tags", "")
        new_tags = sync_tags(old_tags, indie, classic)
        if new_tags != old_tags:
            print(f"  CHANGED [{raw_key}]: {old_tags!r} -> {new_tags!r}")
            row["tags"] = new_tags
            changed += 1
    write_csv(csv_path, fieldnames, rows)
    print(f"  sync_csv_tags: matched={matched}, unmatched={unmatched}, changed={changed}")


def sync_tags_from_sqlite(db_path: Path, csv_path: Path) -> None:
    """Standalone entry point: reads indie/classic from SQLite."""
    _apply_sync(build_catalog_index(db_path), csv_path)


def sync_tags_from_catalog(catalog: dict, csv_path: Path) -> None:
    """catalogue.py integration: uses the in-memory catalog dict."""
    entries = catalog.get("entries") or {}
    catalog_index = {
        normalize_key(key): (bool(entry.get("indie")), bool(entry.get("classic")))
        for key, entry in entries.items()
    }
    _apply_sync(catalog_index, csv_path)


def main() -> None:
    db_path = get_db_path()
    csv_path = Path("Library_new.csv")
    print(f"Syncing tags: {csv_path} <- {db_path}")
    sync_tags_from_sqlite(db_path, csv_path)


if __name__ == "__main__":
    main()
