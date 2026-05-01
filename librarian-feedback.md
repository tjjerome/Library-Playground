# Librarian Skill — Smoke Test Feedback

Session: 2026-04-30 full Phase 0–5 build + Phase 4 swap
Model: claude-sonnet-4-6

---

## Summary Verdict

Workflow completed correctly — all invariants held, floors hit, exclusion gate never breached. But the session was substantially more expensive than it needed to be. Three root causes account for most of the waste: the AskUserQuestion multiSelect bug, the Fantasy indie slot thrashing, and cross-cutting ambiguities in CLAUDE.md that required mid-session clarification.

---

## Friction Points

### 1. AskUserQuestion multiSelect — broken, workaround expensive

`"multiSelect": true` produces `InputValidationError` every time. The workaround — split every 4-book batch into 4 individual yes/no questions — roughly 4× the tool calls per batch. This affected every Phase 2 batch and Phase 4 review.

**Fix options:**
- Document the workaround in SKILL.md so the model doesn't retry multiSelect first
- Or: present batches as a single `singleSelect` question with "all of the above / none / other" options
- Or: use prose + `AskUserQuestion` only for edge cases (author-entry-point conflicts, series scope)

### 2. Fantasy indie slot — 6 rejections before resolution

Took 6 rejected candidates across multiple batches before landing on Court of Assassins. Each rejection required re-explanation and a new candidate fetch. The root cause: the profile says "grimdark AND warm epic both live" but my initial indie Fantasy candidates skewed warm/YA (Blood Song, Theft of Swords, Unsouled, Six of Crows). I was pattern-matching "indie Fantasy" to a warmer register.

**Fix:** Profile.md should flag the *dominant* mood preference more explicitly. "Full range" without priority ordering causes drift toward the safer warm picks when the reader's actual preference is dark.

### 3. Dragon Mage tone misread — cost one round-trip

Rated Dragon Mage ★★ ("warm, sweeping, heartfelt — may not fit"). Reader corrected: "I loved Eragon!" Profile says full range, but I weighted the warm tone too heavily. Should have weighted the reader's 5★ Eragon signal and the profile's explicit "dark grimdark AND warm epic both live."

**Fix:** Profile.md could list exemplar warm epics the reader enjoyed alongside the grimdark examples, so comparisons are less ambiguous.

### 4. Cesare Aldo lookup failure

Searched by series name "Cesare Aldo" and missed the catalog entry (keyed under author D. V. Bishop, book title "City of Vengeance"). Required reader correction + second lookup.

**Fix:** `librarian-query.py` or a wrapper could support series-name search, not just title/author. Or: SKILL.md should note that catalog entries are keyed "Title - Author" and series names are a field, not a key.

### 5. Goals table stale artifact

"Standalone | majority | 2" persisted across multiple commits before being caught in the final cleanup pass. No one caught it because the goals table isn't validated — it's manually maintained.

**Fix:** The goals table should either be generated from the list (script), or Phase 4 review should include an explicit goals table audit step.

### 6. Long Series cross-counting confusion

Goals table showed Fantasy: 28, but Fantasy section had 25 rows. Took several messages to explain that 3 Cahill books cross-counted as Fantasy, 3 Red Rising as SciFi. This is the correct behavior but it's not documented.

**Fix:** Add a footnote to the goals table explaining cross-counting, or document the rule in SKILL.md under "Goals Tracking." Something like: "Long Series books count toward their genre goal; the Long Series row tracks commitment count only."

---

## Biggest Token Expenditures (estimated rank)

1. **AskUserQuestion workaround** — 4 tool calls per batch × ~10 batches = ~40 extra round-trips
2. **Fantasy indie slot thrashing** — 6 rejection cycles, each with candidate fetch + explanation + re-ask
3. **Phase 3 web search dead ends** — The Devils (already read), wrong Tana French sub-series, Clown House too far ahead in Slough House. 3 dead ends before 2 good picks.
4. **Catalog queries** — repeated Python inline queries into 9.4MB catalog, some redundant (same book checked multiple times across sessions)
5. **Cross-cutting clarifications** — cross-counting, cap waiver, Cesare Aldo lookup, Dragon Mage correction

---

## CLAUDE.md Ambiguities

### Cap behavior when reader waives it
CLAUDE.md: "hard cap 110." Reader said "don't worry about the cap for now." No guidance on what to do when reader explicitly waives the hard cap mid-build. Model should probably confirm once and proceed, but the current instructions imply the cap is non-negotiable.

**Fix:** Add: "If reader explicitly waives cap, document in list footer and proceed. Don't re-raise cap concern."

### Cross-counting not documented
Genre goal rows in the goals table cross-count Long Series books. Nowhere in CLAUDE.md or SKILL.md.

**Fix:** One sentence in Goals Tracking section.

### Session shown-ledger durability across /compact
CLAUDE.md: "session shown-ledger" owned by `librarian-query.py`. When `/compact` fires mid-session, the in-memory context compresses but the CLI ledger persists on disk (via `mark-shown`). This is fine — but SKILL.md doesn't confirm it. A model that doesn't know this might re-show books after compaction.

**Fix:** Explicit note: "shown-ledger persists on disk via librarian-query.py mark-shown; survives /compact."

### Audiobook flag (🎧) — no application rule
Some books have 🎧, some don't. No documented rule for when to apply it. Was applied to books the reader flagged as audiobook preferences in their profile, but the logic isn't in SKILL.md.

**Fix:** One line: "Apply 🎧 when book appears in reader's audio preferences or reader explicitly requests it."

### Phase 4 gate and removals
SKILL.md: "Phase 4 gate refuse to fire below 100." But what if list is at 99 after a removal request? The gate blocks and there's no documented path forward.

**Fix:** Add: "If removal request drops list below 100, flag to reader before removing. Gate blocks until reader confirms or replacement found."

---

## Sub-Skill Candidates

### 1. `librarian-batch-review` (high value)
Current: every batch presented as 4 individual yes/no questions due to multiSelect bug. A sub-skill could own the batch review pattern — standard prompt, known workaround, consistent format. Reduce boilerplate in the main skill prompt.

Scope: present 4 books → ask yes/no per book → collect results → route to mark-shown, accept, or defer.

### 2. `librarian-goals-tracker` (medium value)
Current: goals table updated manually after each batch, stale values persist. A sub-skill that recalculates genre counts from the actual list rows would eliminate staleness.

Scope: read Reading_List.md → count rows by section → update goals table → return diff. Could run at end of each phase.

### 3. `librarian-profile-match` (medium value, high ambiguity risk)
Current: star-rating candidates (★★–★★★★★) is done inline, inconsistently. The Dragon Mage misread is an example of profile-match failure.

Scope: given a book's catalog entry, score against Profile.md on tone/genre/comparable-books axes. Return star rating + brief rationale.

Risk: adds a round-trip per candidate. Only worth it for Phase 4 one-off queries, not batch builds.

### 4. `librarian-phase3-search` (low value)
Phase 3 (new/upcoming releases) is a small web-search step. Could be isolated, but it's simple enough that isolating it adds more structure than it saves.

---

## What Worked Well

- `librarian-query.py` as single chokepoint held throughout — no duplicate exclusion checks, no books slipping through unverified
- Universal exclusion gate caught The Devils (Abercrombie, already read in May 2025) before Phase 3 presentation
- Per-batch deep-cut floor maintained across all batches
- Indie floor (20) and Classics floor (10) both hit
- Phase 0 unfinished-series gate ran before genre batches
- Git commits at each milestone gave clean audit trail
- CLAUDE.md rule "Never add book without explicit approval" held — no books added without confirmed AskUserQuestion checklist or explicit instruction

---

## Recommended Priority Fixes

| Priority | Fix |
|----------|-----|
| P0 | Document AskUserQuestion multiSelect workaround in SKILL.md — eliminate retry overhead |
| P0 | Document cross-counting in Goals Tracking section |
| P1 | Clarify cap-waiver behavior |
| P1 | Add shown-ledger durability note |
| P1 | Sharpen Profile.md dominant-mood signal (warm vs. dark preference ordering) |
| P2 | Goals table validation step in Phase 4 checklist |
| P2 | Catalog series-name search support in librarian-query.py |
| P3 | `librarian-batch-review` sub-skill |
| P3 | `librarian-goals-tracker` sub-skill |
