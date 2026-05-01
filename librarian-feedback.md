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

---

## Smoke Test 2 — Root Cause Analysis

*Review of `overseer-assessment.md` + `user-feedback.md` from second smoke test. Technical bugs investigated against source code. Commentary below.*

---

### Bug 1 — Phase 0 False Positive (Dresden Files Side Jobs, Lawrence completed series)

**Overseer finding (GROUP A–D):** Phase 0 surfaced Side Jobs (Bk 12.5) as an unread continuation despite it being in Reading_Log. Similarly, Lawrence's Library trilogy was flagged as unfinished despite all three books being read.

**Root cause confirmed via code inspection:**

`cmd_unfinished_series` resolves log entries to catalog entries via `_index_catalog_by_pair`, which indexes on `norm(catalog_entry["title"])`. The catalog title for Side Jobs is `"Side Jobs: Stories from the Dresden Files"` — normalized to `"side jobs stories from dresden files"`. But Reading_Log (a Goodreads import) has `title="Side Jobs"` — normalized to `"side jobs"`. These don't match. The log entry is never resolved to a catalog entry, never added to `series_log_rows`, and Side Jobs is therefore invisible in the `read_pairs` check. The next-book iterator finds it unread and surfaces it.

Same mechanism for the Lawrence trilogy: if any book in the trilogy has a subtitle-truncated title in the log, the catalog pair-lookup fails and that book is treated as unread.

**Fix:** `_index_catalog_by_pair` should index on two keys per entry: `norm(full_title)` AND `norm(title_before_colon)`. Lookup should check both. One-line change per entry:

```python
def _index_catalog_by_pair(entries):
    out = {}
    for k, e in entries.items():
        full_pair = (norm(e.get("title", "")), norm(e.get("author", "")))
        short_title = e.get("title", "").split(":")[0].strip()
        short_pair = (norm(short_title), norm(e.get("author", "")))
        if full_pair not in out:
            out[full_pair] = {"key": k, **e}
        if short_pair not in out:   # only if distinct
            out[short_pair] = {"key": k, **e}
    return out
```

This is also why `is-read --title "Side Jobs" --author "Jim Butcher"` returns `hit=true` correctly — `cmd_is_read` compares against the raw log (which has the short title), so it works. The mismatch only affects the catalog pair-index path used by `unfinished-series`.

**Severity:** Medium (reader catches it, but will happen again on any Goodreads-truncated title).

---

### Bug 2 — Deep-Cut Labeling Violation (GROUP L)

**Overseer finding:** Deep-cut picks labeled in user-facing Reading_List descriptions ("Indie deep cut," "deep cut"). Spec: "never label the deep cut in user-facing output."

**Root cause:** Ambiguous spec wording in SKILL.md. The rule says "randomize slot, never label" — but the model interprets "deep cut" as useful flavor text for the reader (explaining *why* a book is less-known), not as a labeling violation. There's no example of what constitutes a label violation vs. acceptable description framing.

The phrase "Indie deep cut" in a description is functionally a label. The reader can trivially identify the deep-cut slot. This defeats the anti-bias mechanism entirely.

**Fix:** SKILL.md needs an explicit example of the violation. Current rule: `≥1 deep cut per batch, slot randomized, never labeled`. Add: *"Labeling includes: 'deep cut,' 'hidden gem,' 'under-known,' 'indie deep cut,' or any phrase flagging discovery value. Descriptions for deep-cut slots must read identically in tone to non-deep-cut slots. The slot position alone is the signal."*

---

### Bug 3 — Profile.md Not Created or Evolved (GROUP K / GROUP U)

**Overseer finding:** Profile.md not committed after Step 2 interview, and never updated throughout build. Adaptive candidate generation ran against stale data.

**Root cause:** Two separate failures.

**Failure A (creation):** SKILL.md says profile should be written after Step 2, but doesn't make it a blocking precondition for Phase 1. Under Claude Code workflow pressure, the file creation step gets deferred and then skipped. There's no gate that refuses to run Phase 1 without a committed Profile.md.

**Failure B (evolution):** SKILL.md says "Profile.md is live — written throughout the build" but this is aspirational prose, not a procedural checkpoint. No SKILL.md step says "update Profile.md after this batch." There are no reflection checkpoint prompts after batch skips or surprising selections.

**Fix A:** Add a Phase 1 precondition: `Profile.md must exist and be committed before Phase 1 fires`. If missing, create and commit first.

**Fix B:** Add explicit Profile update triggers to the phase checklist:
- After any whole-batch skip: add a one-sentence note why those books missed
- After any book that surprises (reader picks something outside pattern): ask why, record answer
- After every 3 batches: brief profile update commit alongside Reading_List commit

---

### Bug 4 — multiSelect Fallback Wrong (GROUP E / GROUP N)

**Overseer finding:** multiSelect failures forced fallback to yes/no binary per-book decisions. Should fall back to single-select instead.

**Root cause:** The `AskUserQuestion` `multiSelect: true` option fails with `InputValidationError` in Claude Code environment — this appears to be an environment constraint (tool backend rejects the parameter), not a schema issue. The model correctly detects the failure and falls back — but falls back to the wrong pattern (yes/no per book instead of single-select per batch).

**Why yes/no is wrong:** Yes/no per book destroys the key mechanism — the reader can't compare books against each other in a batch. Batch comparison is the whole point. With yes/no, each book is evaluated in isolation with no relative weighting.

**Why single-select is better:** `"Which of these four would you most like to read?"` still forces a comparison. The reader sees all four options and picks the winner. This preserves batch coherence even without multi-select.

**Even better fallback (if single-select is also unreliable):** Present the four books as a numbered prose list and ask the reader to reply with the numbers of books they want. Parse the reply. Zero tool calls. Maximally robust. Loses the structured confirmation but the ledger can still be updated from the reply.

**Fix:** SKILL.md should document a fallback priority chain:
1. `multiSelect: true` (preferred)
2. `singleSelect` with "Add all / Add some / Skip all" option
3. Prose list with numbered reply parsing

---

### Bug 5 — Series Continuation Gap (Abercrombie Age of Madness Bk 2, GROUP J)

**Overseer finding:** A Little Hatred (Age of Madness Bk 1) offered but The Trouble with Peace (Bk 2) never surfaced.

**Root cause (verified via catalog):** The Trouble with Peace is in catalog with `series_position = "Book 8 (Age of Madness #2)"` and `author_entry_point = False`. It won't surface via `author_entry_point_strict` candidate generation because it's mid-series. And `unfinished-series` won't flag it because A Little Hatred hasn't been *read* — it was just added to the list.

There is **no automatic mechanism** to surface Book 2 after Book 1 is added to the reading list. The librarian has to manually check "is there a Book 2 in catalog?" after each Book 1 acceptance. This manual step is easy to skip under batch pressure.

**Fix:** After any Book 1 acceptance, `librarian-query.py` should have a `series-continuation` subcommand:
```
python librarian-query.py series-continuation --title "A Little Hatred" --author "Joe Abercrombie"
```
Returns the next unread book(s) in the same sub-series. Run this automatically after each Book 1 is added to the list; if there's a Bk 2, add it to the candidate pool for the next batch.

This is distinct from `unfinished-series` (which checks the reading log for partially-read series). This is "list-continuation" — books that follow what's already on the list.

---

### Bug 6 — Tone Signal Recency Bias (GROUP S / GROUP T)

**Overseer finding:** Candidate generation skewed toward recent grimdark reads despite profile stating "full range." Older 5★ warm epics didn't pull equal weight.

**Root cause:** `librarian-query.py candidates` doesn't currently implement time-weighted signal averaging. Candidates are ranked by catalog rating, author-in-pocket match, and genre goal proximity. If recent reads (used to seed comparable_books lookups) skew grimdark, the comparable_books chains will surface more grimdark candidates. Older warm reads have lower chain weight simply because fewer recent seeds point at them.

**Fix (two-part):**

1. In `Profile.md`, list 2–3 favorite warm epics alongside favorite grimdark — not as a separate category but as peers. This directly seeds the comparable_books lookup with warm-epic anchors.

2. The Step 2 interview probe should capture multiple taste dimensions explicitly (pacing, character scope, context — per GROUP T). More dimensions = more seed vectors = less chance of mono-culture candidate generation.

The overseer's additional note about reductive tone probes (GROUP T) is correct: dark/warm is one axis. Pacing and character-focus probes are at least as important for matching candidate tone to context. These dimensions should be captured explicitly in the interview and stored in Profile.md.

---

### Note on Claude Code Environment Mismatch

**Overseer finding:** Claude Code optimized for code editing + bash; conversational book-recommendation workflows create friction (tool schema loading, jargon leakage, file state management).

**My view:** The overseer is right about the friction sources but the conclusion (migrate to web chat) deserves more nuance.

The actual blockers are:
1. multiSelect bug — fixable if the tool backend is patched, otherwise a real environment constraint
2. Jargon leakage — a SKILL.md guardrail issue, not a Claude Code issue
3. Profile.md creation discipline — a process issue, not an environment issue

The `librarian-query.py` design (catalog isolation, exclusion gate, shown-ledger) depends on a local filesystem. Web chat doesn't have access to these. Migrating to web chat would require either: (a) uploading catalog JSON per session (impractical at 9.4MB), or (b) a local server the web chat calls (complex, breaks Pro-only accessibility requirement).

Claude Code on the web (claude.ai/code) satisfies the Pro-only constraint and preserves the local tool access. The environment friction is real but fixable at the SKILL.md + tooling layer without migrating the architecture.

**Recommendation:** Fix multiSelect fallback chain first. Audit SKILL.md for jargon guardrails. Add Profile.md creation gate. These three changes address ~80% of the environment-friction complaints without architectural migration.

---

### Summary of Root Causes

| Issue | Root Cause Type | Fixable Where |
|-------|----------------|---------------|
| Phase 0 false positives (subtitle truncation) | Code bug — `_index_catalog_by_pair` doesn't index short titles | `librarian-query.py` |
| Deep-cut labeling | Spec ambiguity — "never label" not defined | `SKILL.md` |
| Profile.md not created/evolved | Process discipline — no blocking gate | `SKILL.md` phase checklist |
| multiSelect fallback to yes/no | Tool environment constraint + wrong fallback choice | `SKILL.md` fallback chain |
| Series continuation gap (Bk 2) | Missing feature — no list-continuation subcommand | `librarian-query.py` + `SKILL.md` |
| Tone signal recency bias | Profile design + interview probe depth | `Profile.md` + `SKILL.md` Step 2 |
| Jargon in user-facing output | No guardrail in skill prompt | `SKILL.md` |
