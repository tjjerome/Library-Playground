# Claude Cowork Port — Spinoff Plan

A future port of the librarian agent from Claude Code to Claude Cowork. Captured here so the work can be picked up later without re-deriving context.

---

## Why port

Two smoke-tests of the librarian skill on Claude Code surfaced a class of friction that the Claude Code surface itself contributes to, independent of skill-spec quality:

- **Tool calls bleed into the reader's view.** Bash output, file diffs, commit messages, `librarian-query.py` invocations — the reader sees the machinery, which breaks the "talking to a librarian" feel and leaks internal vocabulary (Phase 0, ledger, mark-shown, Bk 1, series_role) into chat.
- **`AskUserQuestion(multiSelect=True)` errors at the tool surface.** Forces a degraded fallback (single-select with batch-as-option) that's tolerable but not as clean as native multi-select chips.
- **Mobile rendering of `AskUserQuestion` truncates option `description` text.** Forces the librarian to keep descriptions ≤ 140 characters and offload context to a chat prelude — workable, but loses the ability to use the picker as the primary information surface.
- **Voice flattens at the moment of recommendation** because the tool-call output competes with the librarian's chat for visual real estate.

Claude Cowork (Anthropic's agentic-workflow product, launched January 2026) hides tool calls by design. Cowork plugins (February 2026) port skills cleanly. Both are covered by the Claude Pro plan — no separate Anthropic API credits required.

The class of friction Cowork solves cleanly: surface noise, tool-call jargon leak, voice flattening at recommendation time. The class it doesn't solve: spec / instruction issues (deep-cut labeling, Profile.md not evolving, sparse pitches, rejection learning) — those are addressed by the current Claude Code spec and port unchanged.

Net: Cowork is a real upgrade for the user-facing experience. Worth doing **after** Claude Code's residual friction has been quantified by a third smoke-test against the post-test-2 spec.

---

## Sequencing

This is **Phase B** work. Phase A is the spec/code fixes already shipped on `main`. Order:

1. ✅ Phase A — ship spec fixes on Claude Code (this branch's commits).
2. ⏳ Smoke-test 3 on Claude Code with Phase A changes. Measure residual friction.
3. ⏳ If residual friction is dominantly surface (jargon leak, multiSelect, mobile truncation) → start Phase B. If it's still spec-dominant, more spec work first.
4. **Phase B — Cowork port (this plan).**
5. ⏳ Smoke-test 4 on Cowork.

Do not start Phase B before step 3 confirms the surface-friction case empirically. Skipping ahead risks building a wrapper for problems the spec actually fixed.

---

## Pre-flight: spike before commit

Cowork's local file access model ("files you grant it") is built for cloud integrations (Slack, Notion, Jira). Whether it handles arbitrary local files cleanly — including a 9.4 MB `Library_Catalog.json` and a 411-row `Reading_Log.csv` with freeform `Profile.md` writes — is **unverified**. Confirm before committing to the port.

15-minute spike test, decisive answer:

1. Stand up a minimal Cowork plugin from the existing `librarian` skill (just the SKILL.md, no helper integration yet).
2. Verify three operations:
   - **Read `Library_Catalog.json` (9.4 MB)** without truncation or per-read approval prompts.
   - **Run `librarian-query.py` as a tool** (Cowork plugin invokes the local script via subprocess or MCP).
   - **Edit `Profile.md` mid-conversation** (multiple sequential writes, no per-write approval friction).
3. If all three work → port. Massive UX win.
4. If any blocked → stay on Claude Code, revisit when Cowork's file model loosens.

The spike is read-only on `Library_Catalog.json` first; only attempt writes after reads work.

---

## Architecture (after spike passes)

```
Claude Cowork (desktop)
└── Plugin: "Personal Librarian"
    ├── system prompt = .claude/skills/librarian/SKILL.md (verbatim)
    ├── trigger description = current SKILL.md preamble
    ├── tools (declared in plugin manifest):
    │     ├── filesystem_read   — Library_Catalog.json, Reading_Log.csv,
    │     │                        Profile.md, Reading_List.md
    │     ├── filesystem_write  — Profile.md, Reading_List.md (NOT catalog)
    │     ├── librarian_query   — wraps `python3 librarian-query.py <subcmd>` via subprocess;
    │     │                        same JSON contract as today
    │     ├── web_search        — for Phase 3 upcoming releases
    │     └── git              — commits at phase boundaries
    └── conversation surface = Cowork chat (tool calls hidden by default)
```

What does NOT change:

- `librarian-query.py` — same script, same subcommands, same JSON contract.
- `catalogue.py` and `catalogue_prompts.py` — bulk cataloguing stays a CLI workflow on Claude Code or terminal.
- `.claude/skills/librarian/SKILL.md` — content unchanged. The plugin loads it as the system prompt.
- `.claude/skills/library-cataloguer/SKILL.md` — same. Becomes a second Cowork plugin OR stays a Claude Code skill (cataloguing is bulk + technical; less reader-facing surface, less benefit from Cowork's tool-call hiding).
- `Library_Catalog.json` schema, `Library_Index.json`, all Python helpers.

What changes:

- The skill's `AskUserQuestion` invocations. Cowork's question UI may render differently; spec the fallback chain in case multiSelect support differs (single-select with batch-as-option remains the right contract).
- The "tool calls visible in chat" assumption in the spec. The "anti-jargon contract" invariant becomes much easier to honor when tool calls don't render at all, but the spec keeps the rule because nothing in the rule depends on visibility.
- Phase-boundary git commits — Cowork's git integration handles this if available; otherwise the librarian invokes git via the plugin's tool layer.

---

## Files / artifacts to produce

When Phase B starts:

```
docs/
  cowork-port-plan.md          ← this file
plugins/
  cowork-librarian/            ← new directory
    plugin.json                ← Cowork plugin manifest (skills, tools, triggers)
    SKILL.md                   ← symlink or copy of .claude/skills/librarian/SKILL.md
    tools/
      librarian_query.py       ← thin wrapper that invokes the existing librarian-query.py
                                 via subprocess and returns its JSON output
      git_commit.py             ← optional, only if Cowork doesn't have native git
    README.md                  ← install + invocation instructions for the plugin
```

The Cowork plugin manifest format will be whatever Anthropic documents at the time of port. Plugin docs page: https://support.claude.com/en/articles/13837440-use-plugins-in-claude-cowork.

---

## Spec changes required for the port

These are SKILL.md tweaks, all minor, applied during port (not before):

1. **Replace `librarian-query.py` invocations** that are written as Bash commands (`python3 librarian-query.py candidates ...`) with the plugin's tool-call shape. The semantic contract is identical; only the syntax shifts.
2. **Drop `Bash` references** from the spec where they describe how to run helper commands. Plugin tool-call surface replaces them.
3. **Keep the anti-jargon contract invariant.** Even with tool calls hidden, the rule still applies — the librarian shouldn't say "Phase 0" or "ledger" in chat regardless of surface.
4. **Keep the multiSelect fallback spec.** Cowork's question UI is unverified; the single-select with batch-as-option fallback stays as belt-and-suspenders.
5. **Reframe the `Reading_List.md` description quality rule** — Cowork has richer rendering, so the table cell could carry more text than the Claude Code mobile constraint. Keep the three-part pitch shape; relax the length cap.

No re-architecture. No core logic moves.

---

## Migration data path

Reader workflow during the transition:

1. Reader runs Phase A on Claude Code. Phase 0–5 build produces `Reading_List.md`, `Profile.md`, and an updated `Library_Catalog.json`.
2. All four files (catalog, log, list, profile) live in the same git repo.
3. Cowork plugin reads from the same repo. No data migration needed — same files on disk.
4. Reader can switch between Cowork (for recommendation conversations) and Claude Code (for bulk catalog audits, refines on `Reading_List.md`, custom Python work) on the same data.

Both surfaces share the same source-of-truth files. Git history captures all changes regardless of which surface made them.

---

## Open questions to resolve at port time

- **Does Cowork's plugin tool layer support subprocess invocation?** If not, `librarian-query.py` needs to be ported to whatever Cowork allows (likely an HTTP shim or an MCP server).
- **Does Cowork have native git tooling?** If yes, drop the custom git tool. If no, the plugin needs one.
- **What's Cowork's question UI?** If it has native multi-select chips that work reliably, the multiSelect fallback drops to "rare backup". If it's the same `AskUserQuestion` widget as Claude Code, fallback stays primary.
- **How does Cowork handle long-running conversations?** A full reading-list build is many turns over many days. Cowork's Project / persistence model needs to carry conversation state.
- **Per-write approval prompts?** Cowork's "files you grant it" model may require per-file (or per-write) approval. The librarian's edit cadence is high; if approval is required on every write, that's a UX blocker.

These get answered during the spike (Pre-flight section) and the port itself.

---

## What gets thrown away if Cowork doesn't work

If the spike fails or Cowork can't carry the catalog:

- Spike harness — couple hours.
- This plan — 30 minutes.

Everything else (helper script, skill spec, catalog, audit) stays on Claude Code and continues to evolve. **The port is purely additive — no Claude Code work is on the critical path of any Phase B outcome.**

---

## References

- [Claude Cowork product page](https://claude.com/product/cowork)
- [Use plugins in Claude Cowork](https://support.claude.com/en/articles/13837440-use-plugins-in-claude-cowork)
- [Pro plan coverage](https://support.claude.com/en/articles/8325606-what-is-the-pro-plan)
- Smoke-test 2 friction analysis (cross-test patterns) — captured in commit history of `claude/improve-recommendation-engine-EhQA1`.
