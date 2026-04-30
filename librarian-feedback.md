# Librarian Skill — Session Feedback

_Smoke-test retrospective from a full 100-book reading-list build (2026-04-30)._

## Biggest token expenditures (rough rank)

1. **Phase 2 genre-lane question rounds.** ~7 separate `AskUserQuestion` batches (one per lane: SF, Fantasy, Horror, Crime, Historical, NF, Lit) plus 2-3 follow-ups for indie / fill slots. Each batch carried 4 questions × ~4 options × prose descriptions. Single biggest line item.
2. **Repeated catalog-filter Bash + Python invocations.** Same pattern — load JSON, filter by genre, exclude already-read, sort by GR, format — re-derived ~15-20 times. Body grew slightly each time but the core logic was identical.
3. **`Reading_List.md` Read-then-Edit cycles.** ~25 edits across the session. The file grew to 200+ lines, so each Read-into-context was substantial.
4. **2026 release web searches.** 6 separate `WebSearch` calls for "Author X 2026 release" — each result block carries a lot of unrelated text.
5. **Tone-breadth probe + Profile.md drafting.** Front-loaded but produced a reusable artifact, so probably justified.

## Workflow friction / ambiguity

- **"Phase 1/2/3/4" was never named in the skill prompt** (or wasn't surfaced). I inferred them from context. A named-mode contract — "build = phase 1 high-conf → phase 2 lane fill → phase 3 swap → phase 4 stretch" — with explicit handoff prompts would remove improvisation.
- **The "never read `Library_Catalog.json` directly" rule is correct** but forces re-running Python for every lookup. A sidecar helper (e.g. `librarian-query.py --genre X --exclude-read --min-gr 4.0`) would eliminate the inline-script tax.
- **"Approval = AskUserQuestion checked box" is the right rule** but I leaned on it even for picks that were near-auto-adds (e.g. Bennett finale, Buehlman sequel in Phase 4). For obvious picks, "I'm adding these unless you say stop" would save a round-trip.
- **Stop-hook fired 4 times** about uncommitted changes. Either the workflow should bake in a "commit per phase" beat, or the hook should be quieter mid-session.
- **The `<system-reminder>` claudeMd block repeated on every turn** — framework-level, but worth noting it dominates per-turn overhead.

## Sub-skill candidates

- **`librarian-candidates`** — input: genre, tags, page cap, GR floor, exclude-read=true. Output: ranked candidate list. Removes ~80% of the inline Python.
- **`reading-list-writer`** — input: structured picks (title/author/section/blurb). Output: appends to right table, regenerates the tracking stats block automatically. Removes most of the Read-then-Edit dance and the manual recount of genre/indie/classics counters.
- **`upcoming-releases-scan`** — input: list of series/authors from `Reading_List.md`. Output: confirmed releases in the next 12-18 months. Worth running once at session-start so Phase 4 is already cached when needed.
- **`librarian-stats`** — even simpler than the writer: just recompute and emit the tracking table from the current `Reading_List.md`. The recount-by-hand was mechanical and error-prone.

## What worked well

- Triaging "small ask vs full workflow" up front — clear in the skill prompt.
- `AskUserQuestion` as the universal choice mechanism — no ambiguity about what's being approved.
- `Profile.md` as a persistent artifact — Phase 2 batches could reference taste rules ("the tone palette") without re-explaining.
- Page count + GR rating + review count in every option — let the reader scan-and-decide fast.

## One specific recommendation

The single biggest savings would be **collapsing Phase 2 from ~7 lane-by-lane rounds into 2-3 wider rounds with more options per question**. `AskUserQuestion` supports 4 questions × 4 options = 16 choices per call. This session averaged ~4 picks per call. Rougher cut: do all 7 lanes in 3-4 calls, accepting more cognitive load per call.
