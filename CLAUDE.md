# Library-Playground — `claude-ai-port` branch

You are working on the **claude.ai port** of the librarian agent.  This
branch ships a Pro-plan-ready implementation that runs entirely on
claude.ai chat, using six skills, a published React picker artifact,
and Google Drive for mutable state.

The original Claude-Code-side implementation on `main` is unchanged.
Both implementations stay side-by-side for comparison; do not migrate
features between branches without an explicit ask.

## Read this first

- `CONVERSION_PLAN.md` — original spec from the maintainer.
- `UX_DESIGN.md` — design rationale + folder layouts + failure modes.
- `SETUP.md` — user-facing install guide (sourced from UX_DESIGN.md).
- `/root/.claude/plans/include-all-fields-in-synchronous-peacock.md` —
  the approved implementation plan with frozen architecture decisions.

## Files

### Source of truth on this branch (post-Step-6)

- `Library_Catalog.sqlite` — queryable catalog (~12MB binary) generated
  from `Library_Catalog.json` via `catalogue.py --export-sqlite`.
  Gitignored — regenerate locally.
- `Library_Catalog.sqlite.encoded` — gzip+base64 wrapped form (~5MB
  text) for the Drive connector to read.  Header line:
  `# library-playground-catalog v1 gzip+b64`.  Gitignored.
- `Library.csv`, `Reading_Log.csv` — user-provided inputs.
- `Profile.md`, `Reading_List.md` — user-mutable; live in Drive
  in production, present locally only for testing.

### Code-side reference (kept unchanged for parity)

- `Library_Catalog.json` — deprecated on this branch as the
  authoritative form; gitignored.  Stays as the one-time conversion
  input for `catalogue.py --export-sqlite`.
- `Library_Index.json` — slim browse index, Code-side only.
- `librarian-query.py` (repo root) — Code-side helper.  Untouched.
- `.claude/skills/librarian/`, `.claude/skills/library-cataloguer/` —
  Code-side skills.  Untouched.

### claude.ai port (this branch's deliverables)

- `webhelper/sqlite_export.py` — JSON→SQLite writer + `norm()`.
- `webhelper/encoded_codec.py` — gzip+b64 codec with format header.
- `webhelper/librarian_query.py` — port of the Code helper to SQLite +
  stdin/stdout ledger.  Same subcommand surface.
- `artifacts/batch-picker.jsx` — React multi-select that owns
  window.storage build state.  Must be PUBLISHED for storage to work.
- `.claude.ai/skills/<name>/SKILL.md` — six skills:
  `librarian-triage`, `librarian-quickref`, `librarian-build-setup`,
  `librarian-build-batches`, `librarian-build-finish`,
  `library-cataloguer`.
- `Makefile` — `make skills` zips each into `dist/skills/<name>.zip`,
  bundling the three webhelper modules into each.
- `tests/sqlite_roundtrip.py`, `tests/encoded_roundtrip.py` — Step 1
  parity tests.

## Catalog reads + writes

Use `Library_Catalog.sqlite` directly:

```python
import sqlite3
conn = sqlite3.connect("Library_Catalog.sqlite")
conn.row_factory = sqlite3.Row
row = conn.execute("SELECT * FROM books WHERE key = ?", (key,)).fetchone()
```

For candidate generation, exclusion checks, lookup, profile-append, and
the shown-ledger, route through `webhelper/librarian_query.py`:

```bash
python3 webhelper/librarian_query.py candidates \
    --catalog Library_Catalog.sqlite \
    --log Reading_Log.csv \
    --reading-list Reading_List.md \
    --ledger - --genre Horror --batch-size 4 --deep-cut-slot < ledger.json
```

Ledger is stdin/stdout — the model owns persistence in the picker
artifact's `window.storage`.

## Hard invariants — librarian-build-batches/SKILL.md is canonical

The eight-plus-three librarian invariants live in
`.claude.ai/skills/librarian-build-batches/SKILL.md`.  Hard rules
non-negotiable:

1. Universal exclusion gate (helper-owned).
2. Core target = 100 fixed.
3. Conservative author-entry-point fallback.
4. Phase 0 unfinished-series gate before any genre batch.
5. Per-batch deep-cut floor; slot randomised; never labelled.
6. Open prose questions are turn-ending.
7. Anti-jargon contract — no internal vocabulary in chat, picker UI,
   Reading_List.md, or Profile.md.
8. Deep-cut silence — render identically across all batch positions.
9. Profile.md per-edit Drive flush.
10. Reading_List.md per-edit Drive flush.
11. React picker is the only multi-select surface for batch picks.

Translation map for reader-facing language is at the bottom of
`librarian-build-batches/SKILL.md`.

## Testing

Run the parity tests against the live catalog:

```bash
python3 catalogue.py --library Library.csv \
    --export-sqlite Library_Catalog.sqlite --emit-encoded
python3 tests/sqlite_roundtrip.py
python3 tests/encoded_roundtrip.py
```

Both should report `OK` on a clean export.  `make skills` builds the
six skill zips for upload to claude.ai.

## Output style

- Edit in place via Edit tool; no full-file rewrites in chat.
- Never add a book to `Reading_List.md` without explicit reader approval
  (a checked picker option, or a clear "add it" instruction).  Wish-list
  mention is not approval.
- Catalog edits go through `library-cataloguer` skill, not directly.
- Offer to commit memory-bank updates ("Want me to commit this?") —
  never commit without confirmation.  No push without explicit ask.

## Asking reader questions

`AskUserQuestion` is the default for any choice-shaped prompt with
discrete options.  Prose only for genuinely open-ended questions ("what
made that book work for you?").  Open prose questions are turn-ending —
no `AskUserQuestion` chain on the same turn.

`AskUserQuestion` is a deferred tool in Claude Code.  Load once:

```
ToolSearch(query="select:AskUserQuestion", max_results=1)
```

If unavailable, fall back to prose and tell the reader.

## Memory bank

The SQLite catalog is the librarian's long-term memory.  Reader
sentiment, ratings, and personal preferences NEVER enter the catalog —
those go to `Profile.md` (sentiment) and `Reading_Log.csv` (ratings).
See `library-cataloguer/SKILL.md` for the catalog/profile/log boundary.

Cataloguer rules:
1. Never silently mutate.  Confirm via `AskUserQuestion`.
2. ≤20 new books per chat batch.  Bulk → defer to `catalogue.py`.
3. `comparable_books` reciprocity is mandatory on every comp link write.
4. Catalog flush back to Drive: session-end only, never per-edit.
5. Profile.md / Reading_List.md flush: per-edit, every write.

Git history = audit trail.  Commits document what changed and when.

## Model routing

- Architecture, debugging, security review: Opus
- Implementation, standard coding: Sonnet
- File search, exploration, formatting: Haiku (use `researcher`
  sub-agent)

## Conventions

- Default Sonnet; escalate to Opus only when reasoning bottleneck.
- Use `offset`/`limit` on Read for large files.
- Run `/compact` at logical breakpoints (~60-70% context) instead of
  letting auto-compact fire.
