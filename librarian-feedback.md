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

---

## Addendum — Root-cause analysis of `user-feedback.md` issues

After review of the 19 reader-reported issues + the overseer's 7-group fix plan, my own commentary on root causes (agent's-eye view) and where I'd push beyond the overseer's recommendations. The overseer's groups are mostly right; this section adds causes the overseer didn't surface and a few different angles on shared causes.

### Cause: skill-prompt opacity to the running agent

The librarian skill prompt is injected by the harness but never appears in my visible context the way `CLAUDE.md` does. My behavior in this session was driven ~80% by `CLAUDE.md` conventions and ~20% by inferred patterns. This explains why **"Phase 1/2/3/4" felt undefined to me** (issue 13 root-cause, issue 17 root-cause): the phase contract presumably lives in the skill prompt, but I treated phases as soft conventions rather than hard gates with invariants. Concrete fix: hoist the phase contract — including the **"core target = 100 is fixed"** invariant — into `CLAUDE.md`, or add a `<librarian-contract>` block the skill prints inline at session start. Whatever lives only in the skill prompt is effectively half-loaded.

### Cause: in-context exclusion sets are rebuilt from scratch every Bash call

Issues 4, 8, 15 (the overseer's Group A) all share a deeper cause: **I never built a persistent exclusion artifact**. Every candidate-generation Python snippet rebuilt `already_read = {(norm(t), norm(a)) for r in log}` from scratch. If the normalization rule was wrong, it was wrong every time, and I had no in-session record of what I'd already shown the reader. The overseer correctly proposes a session-level invariant, but the implementation lever I'd push hardest is **a single helper script** (`librarian-query.py`) that owns:
- `Reading_Log.csv` parsing + canonical `norm()` (with leading-punct strip for `’Salem's Lot`, article strip for `The Book of the New Sun`, period-collapse for initials)
- `Reading_List.md` parsing for an `is_on_list` set (this is a separate gate from `is_already_read` — I never built it at all)
- a "shown this session" ledger written to a tmp file

Code-level invariants beat prose-level instructions every time. Once `librarian-query.py` is the only path to candidates, the gate can't be skipped. The overseer's "redundant pre-write check on every Edit" is the belt; this is the suspenders.

### Cause: candidate ranking has no diversity term

Issue 10 (safe recommendations) and issue 12 (indie/classics not interspersed) share a cause: my ranking function was effectively `sort by goodreads_rating desc` with author/genre filters layered on top. There was no diversity bonus, no deep-cut floor, no cross-cutting-tag boost. The overseer's "1 deep cut per 4-pick batch" is the right answer for issue 10. For issue 12, I'd push slightly further than the overseer: **at session start, compute the catalog distribution of cross-cutting tags within each genre** ("75% of indie in catalog is fantasy") and use it to set per-batch floors ("if filling fantasy, ≥2 of 4 picks must be indie until indie floor met"). Otherwise the cross-cutting axes lose to genre-internal ranking every time.

### Cause: Phase 1 has no "unfinished business" sub-step

Issue 18 (never surfaced Book of the New Sun continuation) is the most damning bug in the session: a 5-star series the reader is halfway through, and the librarian never offered the next book. The overseer's Group B point 3 (unfinished-series enforcement gate) is correct, but I want to name the structural cause: **Phase 1 as I ran it sourced candidates from "wishlist + obvious comps" only**. There was no algorithmic pass over `Reading_Log.csv` asking "what's open?". An `unfinished_series_check` should run **before Phase 1 candidates are even generated**, produce a numbered list, and the librarian must explicitly route every entry (offer / decline / defer to stretch) before any genre-fill batch fires. Make this a hard gate, not an enforcement-after-the-fact.

### Cause: rejections aren't signals — they're noise

Issue 11 (resurfacing rejected picks) and issue 3 (not adapting based on responses) share this. My internal model treated each `AskUserQuestion` answer as an independent transaction: selected → add, not-selected → discard for now. There's no *accumulation*. A book passed over twice has no different status than a book passed over once. The overseer's "soft escalating negative weight" is right; I'd add: **whole-batch skips should be treated as a different signal class** — not weighted votes against each pick, but a meta-signal that the whole frame is wrong. The librarian should pause batch generation, ask a probe ("none of these landed — what's off about the framing?"), and update Profile.md before resuming. Issue 11 explicitly calls this out; the workflow needs an explicit "all-skip handler" branch.

### Cause: description templates default to plot-sketch, not personal anchor

Issues 3 and 9 share this. My `description` field structure was approximately: `[author] — [one-line plot] [tone tag]. [GR rating] / [reviews]. [pages]p.` That's efficient but impersonal. The overseer's `[why you specifically — named anchor] — [what the book is] — [page count]` is the right template. The deeper cause: **I treated `Profile.md` as reference material to consult occasionally, not as the source of every description's lead clause**. Each pick's `description` should be sourced *from* the profile (a 5-star, a stated taste, a profile flag) before any plot summary is written. If I can't write the personal-first clause, the candidate isn't a good enough fit and shouldn't be in the batch.

### Cause: author-entry-point check was never run

Issue 7 (Assassin's Apprentice mis-labeled standalone) and issue 14 (entry-point logic) share this. For issue 7 specifically: I wrote the description quickly without re-checking the catalog's `series` field against my prose. The overseer's pre-write series-scope gate would have caught it. Beyond that, issue 14's deeper concern — "is this book a *good* place to start with this author?" — isn't a single-field check. It needs catalog metadata that doesn't exist yet (`author_entry_point` / `series_role`). The overseer flags this as cataloguer-skill work; I'd add: **until that metadata exists, the librarian should refuse to recommend a non-Standalone book by an author the reader hasn't read unless `series_position` is exactly "Book 1"** — a conservative fallback that's strict but correct.

### Cause: Phase 4 (upcoming releases) coverage was author-only

Issue 16 (didn't search highly-anticipated 2026 releases in favorite genres) — I ran six author-name web searches and stopped. There was no second pass for "most-anticipated 2026 fantasy releases," "best 2026 sci-fi debut," etc. Easy fix: **Phase 3** (the overseer's renumbered Phase 3, formerly 4) should source from at least three pools in parallel: (1) author backlog/sequels, (2) genre-anticipated lists, (3) comp-driven from 5-star anchors. The agent picks across pools deliberately. The overseer covers this in Group E final bullet; just emphasizing it doesn't get lost.

### Cause: the workflow is front-loaded interview + back-loaded build, with no mid-build probes

Several issues (1, 2, 11, partially 3) share a meta-cause: the workflow assumes taste is captured up front and then mechanically applied. In practice, taste *clarifies* during the build — when the reader rejects a pick, that's signal; when they enthusiastically accept, that's signal too. The current build phase has no scheduled "reflect" beats. I'd add: **between every 2-3 batches, run an inline reflection** — what's been accepted, what's been skipped, has the implicit profile shifted? This isn't an `AskUserQuestion`, it's the librarian thinking out loud in chat for 2-3 sentences, then maybe asking a clarifying question. This is also the natural place to commit progress (which fixes the stop-hook nag from the original feedback).

### Cause: the swap pass + capstone should be one continuous "deliverable" phase

Issues 17 and 19 read separately but I think they're one fix: the current **Phase 3 (swap) → Phase 4 (stretch) → done** ordering has the wrong shape. The reader can't make good swap decisions without seeing the stretch picks first. And the list ends without a "what should I read first?" answer. The overseer's reorder + Top-5 capstone is right; my framing: treat the whole back-half as one "**Deliverable** phase" with three beats — show stretch → swap with full context → name the Top 5. Frame it that way and the reader experiences a single arc instead of three sequential passes.

### Cause: the stop-hook nag is signal, not noise

Tangential to user-feedback but worth flagging: the stop-hook fired four times in this session about uncommitted changes. Each fire happened because I was mid-phase with no natural commit point. **Each phase end is a natural checkpoint.** Building "offer to commit at phase boundaries" into the workflow would (a) silence the hook nag, (b) give git history that mirrors the workflow phases (useful for debugging future smoke tests), and (c) satisfy the existing CLAUDE.md rule "Offer to commit memory-bank updates."

### What I'd build first

If I could only ship three things from the overseer's plan + this addendum, in order:

1. **`librarian-query.py` helper** that owns canonical normalization, `is_already_read`, `is_on_list`, and shown-this-session ledger. Eliminates Group A bugs structurally and saves the largest token line item from the original feedback.
2. **Unfinished-series check as Phase 0** (before Phase 1 candidate sourcing). Fixes issue 18 immediately and is a one-time `Reading_Log` query, not a workflow-wide refactor.
3. **Description template enforcement.** Refuse to author a `description` that doesn't contain a named anchor from `Profile.md`. This forces personal-fit *during* batch construction, not as a polish step.

Everything else in the overseer plan is correct and worth doing, but those three are the highest-leverage fixes per unit of skill-prompt complexity added.
