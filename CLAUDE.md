# Library-Playground

This repo is two things at once:

1. **The librarian's runtime.** Skills in `.claude/skills/` auto-activate
   for recommendation, taste-matching, and catalog-write conversations.
2. **A maintenance shell** for the catalog: `catalogue.py` builds and
   refreshes `Library_Catalog.json` and `Library_Index.json` from `Library.csv`.

Read source on demand — don't preload docs here.

## Files

- `Library_Index.json` — slim browse index (~1.4MB). Load at session start
  when running the librarian. Fields: title, author, series, series_status,
  primary_genre, comparable_books.
- `Library_Catalog.json` — full per-book knowledge (~9.4MB). **Never read
  directly into context.** Query via Bash + Python: load → filter → return
  matches.
- `Library.csv` — raw library data. Used only for tag audits and as the
  source of truth for what's in the library.
- `Reading_Log.csv` and `Profile.md` — taste context (when present).
- `catalogue.py` — bulk cataloguing, audit, and index regeneration.

## Skills

- **`librarian`** (`.claude/skills/librarian/`) — recommendation and
  reading-list workflows. Triages small asks (single-book queries, list
  refinements) away from the full Step 1–7 build.
- **`library-cataloguer`** (`.claude/skills/library-cataloguer/`) — owns
  writes to `Library_Catalog.json` and `Library_Index.json`. Applies small
  in-chat changes directly via Python; defers bulk work to `catalogue.py`.

Both skills auto-trigger on description matching. To start a librarian
session: ask a librarian-shaped question ("what should I read next?",
"anything like X?", "build me a 2-year reading list"). To start cataloguer
work: "add this book", "fix this entry", "save those changes",
"what do you know about [book]?".

## Modes — match scope to the ask

The librarian skill triages before running anything heavy. Don't launch a
full reading-list workflow on a small ask.

- Single-book query → focused 1–3 paragraph answer, stop.
- Refine existing list → work off `Reading_List.md`, skip freshness/goals.
- Add a few books / fix entries → cataloguer skill takes over.
- Build a fresh 1–2 year list → full librarian workflow.

## Output style

- Keep `Reading_List.md` and `Profile.md` as files in the repo. Edit in
  place via the Edit tool — never rewrite the full content inline in chat.
  Chat replies stay brief and point at the file.
- Catalog edits apply directly via Python (no patch files). The cataloguer
  always regenerates the index in the same step:
  `python catalogue.py --library Library.csv --index-only`.
- Offer to commit memory-bank updates ("Want me to commit this?") but
  never commit without confirmation. Don't push without an explicit ask.

## Asking the reader questions

**For any choice-shaped question with discrete options, use the
`AskUserQuestion` tool — do not ask in prose.** This applies across both
the librarian and cataloguer flows: mode disambiguation, series handling,
genre/format goals, batch reviews, wish-list adoption, and confirmations
before writes. Reserve prose questions for genuinely open-ended interview
prompts ("what made that book work for you?"). The tool always offers an
"Other" free-text option, so the reader is never trapped.

### Loading the AskUserQuestion schema (one-time per session)

`AskUserQuestion` is a **deferred tool in Claude Code** — its schema is not
loaded at session start. Before the first choice-shaped question, fetch the
schema once:

```
ToolSearch(query="select:AskUserQuestion", max_results=1)
```

After that, the tool stays callable for the rest of the session. If
`ToolSearch` returns no match for `AskUserQuestion`, the tool genuinely
isn't available — say so to the reader and fall back to prose.

You can do the load eagerly at session start (recommended for librarian
sessions, since most steps need it) or lazily on first need.

## Memory bank

`Library_Catalog.json` is the librarian's long-term memory. As the reader
discusses books, new information may be worth persisting (corrected facts,
content_flags, post-read taste_signals updates, comparable_books links,
audit fixes, new books).

Rules:
1. Never silently mutate. Confirm changes explicitly.
2. Batch within a session. Flush a single update when the reader says "save
   those" or at end-of-chat — not after every individual correction.
3. Always regenerate the index after a catalog write.
4. For bulk work (initial build, many new books, full re-audit), point the
   reader at `catalogue.py` instead of editing in chat.

Git history is the audit trail — commits document what changed and when.

## Model routing

- Architecture, debugging, security review: Opus
- Implementation, standard coding: Sonnet
- File search, exploration, formatting, renaming: Haiku (use the
  `researcher` sub-agent)

## Conventions

- Default to Sonnet; only escalate to Opus when reasoning is the bottleneck.
- Use `offset`/`limit` on Read for large files.
- Run `/compact` at logical breakpoints (~60–70% context) instead of letting
  auto-compact fire.
