# Library-Playground

Repo do two thing:

1. **The librarian's runtime.** Skills in `.claude/skills/` auto-activate for recommendation, taste-matching, catalog-write convos.
2. **Maintenance shell** for catalog: `catalogue.py` build/refresh `Library_Catalog.json` and `Library_Index.json` from `Library.csv`.

Read source on demand. No preload.

## Files

- `Library_Index.json` — slim browse index (~1.4MB). Load at session start for librarian. Fields: title, author, series, series_status, primary_genre, comparable_books.
- `Library_Catalog.json` — full per-book knowledge (~9.4MB). **Never read direct into context.** Query via `librarian-query.py` (preferred) or inline Bash + Python.
- `Library.csv` — raw data. Tag audits + source of truth only.
- `Reading_Log.csv` and `Profile.md` — taste context (when present).
- `Reading_List.md` — reader-controlled TBR pool. Librarian write only on explicit reader pick.
- `catalogue.py` — bulk cataloguing, audit, index regen.
- `librarian-query.py` — single chokepoint for candidate gen, exclusion checks, shown-this-session ledger. All batch generation go through here. No duplicate gates in inline Python.

## Skills

- **`librarian`** (`.claude/skills/librarian/`) — recommendation + reading-list workflows. Triage small asks away from full Step 1–7 build.
- **`library-cataloguer`** (`.claude/skills/library-cataloguer/`) — own writes to `Library_Catalog.json` and `Library_Index.json`. Small in-chat changes via Python; bulk work defer to `catalogue.py`.

Both skills auto-trigger on description match. Librarian session: ask librarian-shaped question ("what should I read next?", "anything like X?", "build me a 2-year reading list"). Cataloguer work: "add this book", "fix this entry", "save those changes", "what do you know about [book]?".

## Librarian hard invariants

These survive even when librarian skill prompt not visible. Full spec at `.claude/skills/librarian/SKILL.md`. Rules non-negotiable:

1. **Universal exclusion gate.** Every candidate reaching `AskUserQuestion` clear `is_already_read` (Reading_Log.csv) AND `is_on_list` (Reading_List.md) AND session shown-ledger. Owned by `librarian-query.py`. Never duplicate inline.
2. **Core target = 100 fixed.** Mid-build cap reductions trigger redistribution `AskUserQuestion`; never lower 100. Phase 4 gate refuse to fire below 100.
3. **Conservative author-entry-point fallback.** No non-Standalone book by author not in `Reading_Log.csv` unless `series_position == "Book 1"`. Cite rule when declining.
4. **Phase 0 unfinished-series gate.** Run `librarian-query.py unfinished-series --min-rating 4.0` before any genre batch; route every entry via `AskUserQuestion`.
5. **Per-batch deep-cut floor.** Every 4-pick batch has ≥1 deep cut, slot randomized, never labeled.
6. **Open prose questions are turn-ending.** No `AskUserQuestion` same turn after prose question.
7. **Anti-jargon contract.** No internal vocabulary in chat, `AskUserQuestion` text, or `Reading_List.md`. Translate "Phase 0/1/…", "ledger", "candidate", "deep cut", "is-read", "Bk 1" to reader-facing language before output. Full map in `SKILL.md`.
8. **Deep-cut silence.** Deep-cut slot is mechanism, not label. Never named, parenthesised, or formatted differently. `librarian-query.py` randomises position; reader sees only the book.

**Live memory.** `Profile.md` is written throughout the session, not just at interview time. Every reflection beat, probe answer, surprising selection, or reader correction triggers a write same-turn via `librarian-query.py profile-append`.

Workflow phases: **Phase 0** unfinished-series gate → **Phase 1** highest-confidence → **Phase 2** checklist batches → **Phase 3** new/upcoming → **Phase 4** final review → **Phase 5** Top 5 capstone.

## Modes — match scope to ask

Librarian triage before running anything heavy. No full workflow for small ask.

- Single-book query → focused 1–3 paragraph answer, stop.
- Refine existing list → work off `Reading_List.md`, skip freshness/goals.
- Add few books / fix entries → cataloguer skill takes over.
- Build fresh 1–2 year list → full librarian workflow.

## Output style

- Keep `Reading_List.md` and `Profile.md` as repo files. Edit in place via Edit tool — no full-content rewrites in chat. Chat replies brief, point at file.
- **Never add book to `Reading_List.md` without explicit reader approval.** Approval = `AskUserQuestion` checklist with box checked, or clear "add it" instruction. Discussion not approval. Enthusiasm not approval. Wish-list mention not approval. Unchecked books deferred, never written. Uncertain → don't write.
- Catalog edits apply via Python (no patch files). Cataloguer always regenerate index same step: `python catalogue.py --library Library.csv --index-only`.
- Offer to commit memory-bank updates ("Want me to commit this?") — never commit without confirmation. No push without explicit ask.

## Asking reader questions

**Any choice-shaped question with discrete options: use `AskUserQuestion` tool — no prose.** Apply across librarian + cataloguer: mode disambiguation, series handling, genre/format goals, batch reviews, wish-list adoption, confirmations before writes. Prose only for genuinely open-ended prompts ("what made that book work for you?"). Tool always offer "Other" free-text option — reader never trapped.

### Loading AskUserQuestion schema (one-time per session)

`AskUserQuestion` = **deferred tool in Claude Code** — schema not loaded at session start. Before first choice-shaped question, fetch schema once:

```
ToolSearch(query="select:AskUserQuestion", max_results=1)
```

Tool stay callable rest of session. If `ToolSearch` return no match, tool genuinely unavailable — tell reader, fall back to prose.

Load eagerly at session start (recommended for librarian sessions) or lazily on first need.

## Memory bank

`Library_Catalog.json` = librarian long-term memory. New info worth persisting: corrected facts, content_flags, post-read taste_signals, comparable_books links, audit fixes, new books.

Rules:
1. Never silently mutate. Confirm changes explicitly.
2. Batch within session. Flush single update when reader say "save those" or end-of-chat — not after every correction.
3. Always regenerate index after catalog write.
4. Bulk work → point reader at `catalogue.py` instead of editing in chat.

Git history = audit trail — commits document what changed and when.

## Model routing

- Architecture, debugging, security review: Opus
- Implementation, standard coding: Sonnet
- File search, exploration, formatting, renaming: Haiku (use `researcher` sub-agent)

## Conventions

- Default Sonnet; escalate to Opus only when reasoning bottleneck.
- Use `offset`/`limit` on Read for large files.
- Run `/compact` at logical breakpoints (~60–70% context) instead of letting auto-compact fire.