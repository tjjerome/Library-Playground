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
- `PROJECT_INSTRUCTIONS.md` — copy-paste-ready content for the
  reader's claude.ai project instructions panel.  Contains the
  Drive file-ID slot and the seven hard rules.
- `/root/.claude/plans/include-all-fields-in-synchronous-peacock.md` —
  the approved implementation plan with frozen architecture decisions.

## Project owner's Drive setup (reference)

Catalog file ID in the maintainer's Drive:
`1QEe3-9Hv0CEe1lsT4C9aRFFYTFgKsjPy`.  Lives in the maintainer's
claude.ai project instructions as `DRIVE_CATALOG_FILE_ID`.  Triage
reads that ID at session start and skips folder/name search entirely.
Other forks set their own ID in their own project instructions; the
SKILL.md falls back to filename/folder discovery if the ID is absent.

## Files

### Source of truth on this branch (post-Step-6, post-2026-05-02 refactor)

- `Library_Catalog.sqlite` — queryable catalog (~12MB binary)
  generated from `Library_Catalog.json` via
  `catalogue.py --export-sqlite`.  Gitignored — regenerate locally.
- `Library_Catalog.sqlite.encoded` — gzip+base64 wrapped form (~5MB
  text) for the Drive connector to read.  Header line:
  `# library-playground-catalog v1 gzip+b64`.  Gitignored.
- `Library.csv`, `Reading_Log.csv` — user-provided inputs.
- `Profile.md`, `Reading_List.md` — live in **project knowledge** as
  the carry-across-sessions form, edited in `/tmp` during a session,
  surfaced via `present_files` at session end so the reader can
  re-upload.  Local files only for testing or as project-knowledge
  seeds.

### Storage split (2026-05-03 refactor — file-based)

| Layer | Holds | Mutability |
|---|---|---|
| Drive | `Library_Catalog.sqlite.encoded` | Read-only from chat; reader manually replaces the file at session end via the cataloguer's download-link flow |
| Project knowledge | `Reading_Log.csv`, optional `Profile.md`, `Reading_List.md`, `build_state.json`, `log_pending_updates.csv` | Reader re-uploads at the end of any session that changed them |
| Sandbox `/tmp/` (per session) | `Library_Catalog.sqlite`, `Profile.md`, `Reading_List.md`, `build_state.json`, `log_pending_updates.csv`, `catalog_edits.log` | Mutated freely; surfaced via `present_files` at session end |
| `picker` / `profile` / `reading-list` artifacts | Read-only renderers — content passed in via `seed` prop | None — no `window.storage`, no preflight, no persistence |

The artifacts are pure renderers.  The chat agent has no available
tool to write to a published artifact's storage by URL/UUID, so the
prior storage-based persistence model was unimplementable; /tmp files
plus session-end `present_files` is what actually works on Pro.

### Code-side reference (kept unchanged for parity)

- `Library_Catalog.json` — deprecated on this branch as the
  authoritative form; gitignored.  Stays as the one-time conversion
  input for `catalogue.py --export-sqlite`.
- `Library_Index.json` — slim browse index, Code-side only.
- `librarian-query.py` (repo root) — Code-side helper.  Untouched.
- `.claude/skills/librarian/`, `.claude/skills/library-cataloguer/` —
  Code-side skills.  Untouched.

### Catalog sync workflow (Code surface)

Bulk catalog work runs from a Claude Code session via:

```bash
python3 catalogue.py
```

Default flow (no flags): refresh CSV-authoritative fields, catalogue
new books, run comparables tail, apply flag gates, export SQLite +
encoded form, write `dist/sync_audit.md`, `git add -f` + commit +
push both artefacts to the current feature branch (refuses
`main`/`master`).  Pass `--no-push` for local-only runs.  Pass
`--status` for cheap inspection.  Pass `--dry-run` to skip API + writes.

Maintenance commands live in dedicated scripts so the catalogue.py
surface stays small:

| Script | Purpose |
|---|---|
| `backfill.py --entry-points` | LLM backfill `series_role` + `author_entry_point` on existing entries. |
| `audit_catalog.py --all` | Deterministic review queues over Library_Catalog.sqlite (entry-points consistency, comparables quality). |
| `audit_library.py` | Library.csv-side LLM audits → Library_new.csv (genres / series-type / pub-years / indie). |
| `canonicalize.py` | Closed-vocab remap of taste_signals / themes. |

The in-chat `library-cataloguer` skill on claude.ai is intentionally
scoped to **single-book / short-series** in-the-moment edits.  When
the reader proposes bulk work it bounces them to `python catalogue.py`
on the Code side.

### claude.ai port (this branch's deliverables)

- `webhelper/sqlite_export.py` — JSON→SQLite writer + `norm()`.
- `webhelper/encoded_codec.py` — gzip+b64 codec with format header.
- `webhelper/librarian_query.py` — port of the Code helper to SQLite +
  stdin/stdout ledger.  Same subcommand surface.
- `artifacts/batch-picker.jsx` — pure React renderer for richer batch
  preview (cover-style cards, content flags).  No storage.  Opt-in
  alternative to native `AskUserQuestion(multiSelect)`.
- `artifacts/profile.jsx` — read-only markdown renderer for
  `Profile.md` content via `seed` prop.  No storage.
- `artifacts/reading-list.jsx` — read-only markdown renderer for
  `Reading_List.md` content via `seed` prop.  No storage.
- `.claude.ai/skills/<name>/SKILL.md` — six skills:
  `librarian-triage`, `librarian-quickref`, `librarian-build-setup`,
  `librarian-build`, `librarian-build-finish`,
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

For candidate generation, status, series scope, and the
unfinished-series gate, route through `webhelper/librarian_query.py`:

```bash
python3 webhelper/librarian_query.py recommend \
    --catalog Library_Catalog.sqlite \
    --log Reading_Log.csv \
    --profile Profile.md \
    --reading-list Reading_List.md \
    --build-state build_state.json \
    --genre Horror --n 6
```

The helper exposes four subcommands (`recommend`, `status`,
`series-fit`, `unfinished-series`) plus `norm` for shared use by the
cataloguer. Picks live exclusively in `Reading_List.md`; the model
owns rejection events, scope decisions, and taste-vector edits in
`build_state.json`.

## Hard invariants — librarian-build/SKILL.md is canonical

The eleven librarian invariants live in
`.claude.ai/skills/librarian-build/SKILL.md`.  Hard rules
non-negotiable:

1. Universal exclusion gate (helper-owned via `recommend`).
2. Working range = 100-110 before stretch picks; 110-125 after. Genre
   goals are floors that guide direction, not numbers to hit.
3. Conservative author-entry-point fallback.
4. Series scope is a hard gate — `series-fit` runs before the next
   pitch round whenever a confirmed pick is part of a multi-book
   series.
5. Open prose questions are turn-ending.
6. Anti-jargon contract — no internal vocabulary in chat, picker UI,
   Reading_List.md, or Profile.md.
7. `/tmp/Profile.md` per-edit write — silent; consolidated diff
   surfaces at session end alongside the catalog download.
8. `/tmp/Reading_List.md` per-edit write — user-visible; one-line
   acknowledgement on each confirmed pick.
9. Pick state lives in `/tmp/Reading_List.md` only; `build_state`
   carries goals, floors, vectors, events, scope decisions, rejected
   candidates — never selected picks.
10. `AskUserQuestion` is not the default turn shape. Use it for
    genuine multi-axis decisions; most pitches go reader → prose
    reply.
11. Process narration is structurally absent — `status` returns only
    what's actionable for the next decision.
12. Catalog flush is manual: cataloguer encodes in sandbox at session
    end and presents a download link; the reader replaces their Drive
    file.  Drive connector's write path is intentionally unused.
13. Working state (`/tmp/Reading_List.md`, `/tmp/Profile.md`,
    `/tmp/build_state.json`, `/tmp/log_pending_updates.csv`) is
    surfaced via `present_files` at session end; reader re-uploads to
    project knowledge to carry into the next session.

Translation map for reader-facing language is at the bottom of
`librarian-build/SKILL.md`.

## Testing

Run the parity tests against the live catalog:

```bash
python3 catalogue.py --no-push
python3 tests/sqlite_roundtrip.py --catalog Library_Catalog.json
python3 tests/encoded_roundtrip.py --catalog Library_Catalog.json
python3 tests/taste_vectors_export.py --catalog Library_Catalog.json
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
4. Catalog flush is **manual download**: session-end only, never
   per-edit, never via the Drive write API.  Reader replaces the
   Drive file from the link.
5. `/tmp/Profile.md`: per-edit file write, **silent** in chat;
   consolidated diff surfaced at session end alongside catalog
   download.
6. `/tmp/Reading_List.md`: per-edit file write, **user-visible**
   one-line acknowledgement on every confirmed pick.

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
