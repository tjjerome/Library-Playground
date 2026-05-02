# Library-Playground (claude.ai port) — User-Experience Design

Companion to `CONVERSION_PLAN.md`. The plan covers *what* to build; this
document covers *what the user sees and does* end to end. It is the
blueprint Step 10's `SETUP.md` will be written from.

Audience for this doc: the maintainer (you) reviewing UX choices before
Step 1 starts. Audience for `SETUP.md` (later): a Pro-plan reader with a
Goodreads export, no Claude Code, no prior context on this repo.

> **Status:** Design ratified 2026-05-02. The OPEN decision points are
> resolved in the "Decisions resolved" section near the bottom; the UX
> below reflects the resolved architecture. The verification pass
> surfaced four constraints that change how the plan executes; see
> "Architectural impact of the verification pass" at the bottom.

---

## Required: publish three artifacts (one-time, mandatory)

**Hard prerequisite for every build session.** Three React artifacts
must be published before any build skill runs.  Each one owns a slice
of mutable state via `window.storage`:

| Artifact | Source file | Stores |
|---|---|---|
| `picker` | `artifacts/batch-picker.jsx` | Build state, ledger, batch selections, edit-locks, pending log updates |
| `profile` | `artifacts/profile.jsx` | Live `Profile.md` content (markdown) |
| `reading-list` | `artifacts/reading-list.jsx` | Live `Reading_List.md` content (markdown) |

`window.storage` has two non-negotiable rules verified against current
Anthropic docs:

1. **Storage operations only succeed on PUBLISHED artifacts.**  On
   unpublished artifacts the calls silently no-op.
2. **Storage data is permanently deleted the moment the artifact is
   unpublished.**

**Setup-flow integration.**  First-run setup walks through publishing
all three artifacts.  Each one:

- Skill renders the `.jsx` once.  If a project-file seed exists
  (`Profile.md`, `Reading_List.md`), it's passed as the `seed` prop so
  the artifact starts populated.
- User clicks **Publish** on the artifact panel.
- User pastes the URL back to chat.  The skill validates, runs a
  `set/get` round-trip preflight, writes the URL into Drive's
  `.config.json`.

Leave all three published.  Do not unpublish any of them.

**Preflight check on every build session.**  Triage performs the
`set/get` round-trip on each artifact URL before invoking any build
skill.  Failure on any one stops the session and surfaces the
recovery flow under F6 below.

**Why split into three artifacts.**  Profile and Reading_List are
reader-visible — putting them in their own artifacts means the reader
can browse / view-raw / (for Profile) edit them from the artifact
pane between or during sessions.  Build state stays bundled with the
picker because it's tightly coupled to batch UX.  Storage budget per
artifact is ~20MB text-only — plenty for any single concern; trying
to fit all three into one artifact would mix concerns and complicate
the recovery flow when only one fails.

---

## Storage layout

| Layer | Holds | Mutability |
|---|---|---|
| Drive | `Library_Catalog.sqlite.encoded` (gzip+b64) | Mutable; cataloguer flushes at session end. |
| Project knowledge (uploaded once per project) | `Library_Browse_Index.json` (~800KB), `Reading_Log.csv`, optional `Profile.md` / `Reading_List.md` seeds | Static — re-upload to refresh. |
| `picker` artifact storage | Build state (`build:<id>`), ledger, batch selections (`batch:<id>`), `catalog_edit_lock`, `log_pending_updates` | Per-edit writes during build sessions. |
| `profile` artifact storage | `profile` key with `{version, content, updated_at}` | Per-edit on Profile-write triggers. |
| `reading-list` artifact storage | `reading_list` key with `{version, content, updated_at}` | Per-edit on every confirmed pick / removal. |
| Sandbox `/tmp/` (per session) | Decoded catalog, mirrored Profile/Reading_List for helper, scratch I/O | Discarded at session end. |

Drive holds one file (the big mutable catalog).  Project knowledge
holds reads (the slim browse index for fast presence checks, plus the
reading log).  Artifacts hold the live mutable user-facing surfaces
(profile + reading list).  Picker artifact storage holds invisible
build mechanics.

---

## North-star UX principles

These are the rules every concrete UX decision below resolves against.

1. **One mental model: "the librarian on claude.ai".** The reader does
   not think about skills, artifacts, sandboxes, Drive, or SQLite. They
   open a chat, say something library-shaped, and the system routes.
2. **Setup is one sitting, ≤30 minutes after the one-time bulk catalogue.**
   Anything longer is a UX failure — the spec must adapt, not the user.
3. **The reader never sees jargon mid-session.** "Phase 0", "ledger",
   "deep cut", "build-id", "window.storage", "artifact published" — all
   stay internal. The setup doc is allowed brief mentions only when the
   reader has to take a click action that depends on the term.
4. **State recovery is the reader's responsibility *only* when something
   failed.** Happy path: triage skill detects in-progress build state
   and offers to resume by name ("you were 6 batches into the horror
   genre, want me to pick up there?"), no phrase to remember.
5. **Failure modes degrade gracefully, never silently.** Drive
   disconnect, missing SQLite, corrupted state, usage limits — all
   produce a plain-English explanation and a one-step recovery path.
6. **Files in Drive remain human-readable.** Profile.md and
   Reading_List.md stay markdown — readers can read them in Drive
   without claude.ai. SQLite is the one binary, and it has dedicated
   handling (see "The catalog distribution problem" below).

---

## Local folder structure (after first-time setup)

```
~/Library-Playground/                  # the user's clone of the repo
├── Library.csv                        # user-provided (Goodreads export)
├── Reading_Log.csv                    # user-provided (Goodreads export)
├── Library_Catalog.json               # generated by catalogue.py (one-time)
├── Library_Catalog.sqlite             # generated by catalogue.py --export-sqlite
├── Library_Catalog.sqlite.encoded     # gzip+base64 wrapped copy for Drive upload
├── Profile.md                         # empty placeholder for first-time
├── Reading_List.md                    # empty placeholder for first-time
├── catalogue.py                       # bulk cataloguer (unchanged)
├── librarian-query.py                 # CODE-side helper (unchanged on this branch)
├── webhelper/
│   └── librarian_query.py             # claude.ai-port helper (Step 2)
├── .claude.ai/
│   └── skills/                        # source of skills the user will zip + upload
│       ├── librarian-triage/
│       ├── librarian-quickref/
│       ├── librarian-build-setup/
│       ├── librarian-build-batches/
│       ├── librarian-build-finish/
│       └── library-cataloguer/
├── artifacts/
│   └── batch-picker.jsx               # the published-artifact React component
└── dist/
    └── skills/                        # zip files generated by `make skills`
        ├── librarian-triage.zip
        ├── librarian-quickref.zip
        ├── ...
        └── library-cataloguer.zip
```

**What stays on the user's machine and what doesn't:**

| File | Local? | Drive? | Why |
|---|---|---|---|
| `Library.csv` | ✓ | optional | Source of truth for bulk cataloguer; stays local. Optional Drive copy if user wants offsite backup. |
| `Reading_Log.csv` | ✓ | ✓ | Pulled from Drive into sandbox each session — log is small enough to be the live copy. |
| `Library_Catalog.json` | ✓ | — | Intermediate artifact. After SQLite export it becomes inert — keep on disk for re-export if schema changes. |
| `Library_Catalog.sqlite` | ✓ | ✓ (`.encoded`, gzip+base64) | Decoded into sandbox once per session as the catalog query target. |
| `Profile.md` | ✓ (last sync) | ✓ (live) | Drive is authoritative; local is for inspection / git. |
| `Reading_List.md` | ✓ (last sync) | ✓ (live) | Drive is authoritative; local is for inspection / git. |
| Skill directories | ✓ | — | Uploaded to claude.ai once via Settings > Features. |
| `dist/skills/*.zip` | ✓ (build output) | — | Generated for upload, can be regenerated. |

**Why `Library_Catalog.sqlite.encoded`?** Verified during the
verification pass: the claude.ai Google Drive connector reads
text-based files only and exposes only metadata for binary files.
SQLite ships as a gzip + base64 wrapped text file (~1–1.5MB after
encoding the ~3MB raw binary). The wrapper is added by
`catalogue.py --export-sqlite --emit-encoded` and skills decode it in
the sandbox once at session start (no mid-session re-fetch). See "The
catalog distribution problem" below for the format spec.

---

## Google Drive folder structure

```
My Drive/
└── Library-Playground/                # the user creates this folder
    ├── Library_Catalog.sqlite.encoded   # the catalog (text-wrapped)
    ├── Reading_Log.csv                  # current reading history
    ├── Profile.md                       # taste profile (live memory)
    ├── Reading_List.md                  # the TBR pool (the deliverable)
    └── archive/
        ├── Profile.md.2026-04-12        # automatic snapshots before flushes
        └── Reading_List.md.2026-04-12   # ditto
```

**Why one folder, flat?** Three reasons:

1. The Drive connector requires the user to grant access per file or
   per folder when adding content to a chat. Flat layout means one
   selection per session start ("Add the Library-Playground folder")
   rather than four ("add Profile.md, add Reading_List.md, add ...").
2. The reader can browse Profile.md and Reading_List.md directly in
   Drive's UI between sessions — they're plain markdown.
3. `archive/` gives a no-effort rollback path. Every flush snapshots
   the previous version with an ISO date suffix; the cataloguer skill
   knows how to restore from a named snapshot if the reader asks.

**Folder name is configurable.** If the reader has a different naming
convention, the triage skill asks once at first-run setup and remembers
the name in `window.storage`.

**`.archive/` size policy.** Snapshots accumulate; UX_DESIGN.md doesn't
prescribe automatic cleanup, but the build-finish skill offers "want me
to prune snapshots older than 90 days?" once per session.

**Resolved:** Drive folder name is asked once on first run and
written to `.config.json`. No mid-session reconfiguration. If the
user wants to rename the folder later, they edit `.config.json`
manually or delete it to re-trigger first-run setup.

---

## Skills installation flow on claude.ai (Pro plan)

**Verified mechanism (May 2026):** Custom Skills install on Pro/Max/
Team/Enterprise plans via *Settings > Features > Skills*. Each skill is
a directory containing a `SKILL.md` file with YAML frontmatter; the
user uploads it as a zip. Skills are per-user (not org-shared), and
require code execution to be enabled in the same Settings panel.

**Build step we ship:**

```
make skills    # zips each .claude.ai/skills/<name>/ into dist/skills/<name>.zip
```

The Makefile target is trivial (`for d in .claude.ai/skills/*/; do
zip -r dist/skills/$$(basename $$d).zip $$d; done`) but having it as a
named target eliminates a class of "did I zip it right?" support
questions.

**Setup walkthrough the user follows:**

1. In claude.ai, click the avatar → **Settings** → **Features**.
2. Toggle on **Code execution and file creation**.
3. Scroll to **Skills**. Confirm "Custom skills" is enabled.
4. Click the **+** button.
5. Drag `dist/skills/librarian-triage.zip` from the local repo. Wait
   for the "Skill installed" toast.
6. Repeat steps 4–5 for the other five zips. Order doesn't matter;
   they auto-trigger on description match.
7. (Optional) Click each skill's name in the list to confirm
   description text is what the reader expects to see in chat.

**Verification step the user runs once after install:** Open a new
chat and type "what should I read next?". The triage skill should
activate (visible as a skill chip near the input) and immediately ask
the routing question. If no skill activates, return to Settings and
verify code execution is enabled.

**Resolved:** `make skills` produces six separate zips, no combined
archive.

---

## The catalog distribution problem (verification-driven)

The verification pass found that the Drive connector cannot read binary
file content (only metadata). The catalog therefore travels as a
text-wrapped form. **Encoding format: gzip then base64.**

**Format spec.**

```
# library-playground-catalog v1 gzip+b64
H4sIAAAAAAAAA<base64-encoded-gzipped-sqlite-bytes-on-one-or-many-lines>
```

- Line 1 is a literal comment header identifying format and version
  so consumers can detect drift.
- Lines 2+ are the gzip-of-SQLite bytes, base64-encoded.
- Decode order at the consumer: strip header → base64-decode → gunzip
  → SQLite bytes.
- File suffix: `.encoded` (neutral, format-agnostic).
- Target size: ~1–1.5MB (the ~3MB raw SQLite compresses well).
- Producer: `python3 catalogue.py --export-sqlite Library_Catalog.sqlite --emit-encoded`.

**Why gzip + base64 instead of raw base64.** A raw `.b64.txt` of a
3MB binary is ~4MB after expansion — ~3× the size of the gzip+b64
form, with no benefit. gzip first compresses the SQLite payload's
predictable structure; base64 then makes the result text-safe for
the Drive connector.

**Read cadence.** Skills load the encoded catalog **once at session
start** in triage. The decoded `.sqlite` lives in the sandbox for
the rest of the session. Skills never re-fetch from Drive
mid-session.

**Write cadence.** The cataloguer skill mutates the in-sandbox
SQLite during the session and re-encodes + flushes to Drive **only
at session end** (or on explicit "save catalog"). Per-edit flushes
are rejected as round-trip-race risk. Concurrent sessions are
prevented via a `window.storage` lock on the picker artifact (see
"Known risks" in the plan).

**Failure mode.** Header missing/wrong, base64 decode fails, gunzip
fails, or `PRAGMA integrity_check` fails after restore — any of
these triggers F2 below ("Catalog SQLite file missing or
corrupted"). The recovery message points at re-running the export
locally.

**Alternatives rejected:**

| Option | Why rejected |
|---|---|
| Paperclip re-upload each session | Violates setup-once principle |
| Sharded JSON in Drive | Gives up SQLite query perf; complicates cataloguer writes |
| Raw base64 (no gzip) | ~3× the size for no benefit |
| GitHub raw URL fetch | claude.ai code execution sandbox network access is unreliable |
| GitHub connector read | Read-only and binary unsupported (verified May 2026) |

---

## The helper-script distribution problem (verification-driven)

Plan Step 2 says: "host the script at a stable raw GitHub URL ... 
fetched at session start." The verification pass found that the
claude.ai code execution sandbox has *varying* network access depending
on user/admin settings, and the documented restriction "the tool
cannot fetch arbitrary URLs that Claude generates ... from
container-based server tools" makes raw-GitHub fetch unreliable across
users.

**Resolution:** **Bundle `librarian_query.py` inside each skill that
needs it.** Skills are filesystem-based on the sandbox VM; the model
runs `python3 .claude/skills/<skill>/scripts/librarian_query.py ...`
directly. No network fetch.

**Tradeoff:** Updating the helper requires re-zipping and re-uploading
every skill that uses it. We mitigate by:

1. Putting `librarian_query.py` in a single `webhelper/` directory
   that `make skills` symlinks (or copies) into each skill's
   `scripts/` subdirectory at zip time. One source, six destinations.
2. Including a `--version` flag on the helper so the cataloguer skill
   can detect skew between skills if the user uploaded different
   versions and warn.

**Resolved:** Skill-bundled only. No URL-fetch fallback. Keep it
simple; sandbox network is unreliable across users.

---

## The artifact-storage problem (verification-driven)

The full design and prerequisite are documented at the top of this
file under "**Required: publish the picker artifact**". Quick
recap of the three constraints that section addresses:

1. Persistence works only on **published** artifacts.
2. Unpublishing **permanently deletes** the storage.
3. Storage is per-artifact, not per-user-globally; ~20MB total,
   text-only.

**Resolved decisions:**

- The published artifact URL is stored in
  `Library-Playground/.config.json` in Drive (not in Profile.md
  frontmatter).
- The triage skill performs a `set/get` preflight round-trip on
  every session that routes to a build skill, before any build skill
  is invoked.
- Accidental unpublish is handled by failure mode F6 below.

---

## First-session experience

There are two distinct "first sessions" the design has to handle. Both
matter.

### Session A: Fresh setup (empty Profile.md, empty Reading_List.md)

Pre-conditions met: skills installed, code execution enabled, Drive
connected, Library-Playground folder created with the four files
(catalog `.encoded`, Reading_Log.csv, empty Profile.md, empty
Reading_List.md), picker artifact published.

**Reader types:** "I want to build a reading list."

**Triage skill activates.** It reads the file presence check, sees an
empty Profile.md (size 0 or only the bootstrap header) and empty
Reading_List.md, and routes:

> "Got it — fresh start. Before we begin, a quick check: I'll be
> reading from your `Library-Playground` Drive folder and writing
> back to it. The picker artifact at <stored URL> is what I'll use to
> show you batches of books. If you ever lose track of where we are,
> just say "where are we" and I'll bring up the build state.
>
> Ready when you are. Want me to start with the taste interview, or
> do you want to talk goals first?"

(`AskUserQuestion`: Taste interview first / Goals first / Other.)

**Why this exact opener?** Three things land in the first reply:

1. *State of the world transparency* — the reader knows where data
   lives without us using the words "Drive" or "artifact" beyond what
   they already understand from setup.
2. *Recovery signal pre-armed* — "say 'where are we'" is a documented
   recovery phrase, said before the reader is in trouble. This is the
   only memorized phrase we ask the reader to know.
3. *Choice of entry point* — the original spec's "interview always
   first" is a Code-era artifact of needing the profile before
   candidate scoring. With state in artifact storage, goals can come
   first if the reader prefers that shape.

**Then** the build-setup skill takes over (handed off automatically;
the reader does not pick it). It runs Phase 0 (unfinished series),
the taste interview, the goals conversation, the wishlist pass — all
the same shape as the Code spec but with the picker artifact for
multi-select wishlist adoption.

**Session A ends when:** The reader is told "you've got a profile, a
goals table, and a Phase 0 result captured. When you're ready to start
the batches, open a new chat and say 'let's start the batches' — or
just open a new chat and the triage skill will offer to resume."

The phrase is documented but not required to memorize — see "Resuming
a build" below for why.

### Session B: Returning user (Profile.md + Reading_List.md exist)

Pre-conditions met (same as Session A).

**Reader types:** "anything like *Between Two Fires*?"

**Triage skill activates.** Single-book query shape detected. It does
NOT walk through the full setup ritual. It pulls the catalog,
Profile.md, and Reading_Log.csv, and routes to the **quickref skill**
which produces a 1–3 paragraph answer.

**No state mutation, no Drive write, no window.storage read.** The
reader gets their answer and moves on.

**Reader types instead:** "what should I read next?"

**Triage skill activates.** Ambiguous shape (could be quickref or full
build). It checks `window.storage` for in-progress build state. Two
sub-cases:

#### B.1 — In-progress build detected

```
"You're 6 batches into the horror build I started with you on April
12 — 23 books in the pool, classic floor met, indie floor at 4 of 8.
Want to pick up where we left off, or start something new?"
```

(`AskUserQuestion`: Resume the horror build / Start fresh / Quick
single-book question / Other.)

The "April 12" date is human-readable, not a build-id. The "23 books
in the pool" is information the reader actually wants. The phrase
"horror build" is paraphrased from the in-progress phase metadata
(`current_phase: "Phase 2"`, `current_batch_genre: "Horror"`) — the
internal vocabulary stays internal.

#### B.2 — No in-progress build

```
"I don't have a build in progress for you. Want me to walk you through
a fresh build (taste interview, goals, then batches), or is there a
single book you wanted me to weigh in on?"
```

(`AskUserQuestion`: Build a list / Single-book question / Refine my
existing list / Update my catalog / Other.)

The "Refine my existing list" option is the path for "swap X for Y"
or "add 3 nonfiction picks" — refine-mode reads `Reading_List.md` as
authoritative and skips the interview.

### What "session start" loads from where

| Resource | Source | When |
|---|---|---|
| Routing decision | `AskUserQuestion` to reader (or shape-match) | Always, in triage |
| Build state (current phase, ledger, goals) | `window.storage` (via picker artifact) | When triage routes to a build skill |
| Catalog | `Library_Catalog.sqlite.encoded` from Drive → decode in sandbox | When any skill needs catalog data |
| Reading log | `Reading_Log.csv` from Drive | When any skill needs log data |
| Profile.md | Drive → live-edit in artifact storage during session → flush back | Build skills only |
| Reading_List.md | Drive → live-edit in artifact storage during session → flush back | Build skills only |
| Picker artifact URL | `Library-Playground/.config.json` in Drive | Triage and build skills |

---

## Active-skill awareness and switching

**The reader sees which skill is active via the skill chip near the
input** — claude.ai surfaces this automatically when a skill triggers.
We don't add chrome on top of it.

**The reader does NOT need to remember a phrase to switch skills.**
The triage skill is the always-on router; it activates on librarian-
shaped openers. Within a session, the active skill keeps control until
its work is done — then it hands back to triage with a brief "where
to next?" prompt if more work is plausibly pending.

**Resuming a build mid-session:** The build-batches skill stays active
across multiple turns. The reader does not need to say "still in the
build" or anything like it; the skill keeps state and continues until
the reader changes shape (single-book query, or "I'm done for now").

**Resuming a build across sessions:** Triage detects in-progress build
state in `window.storage` and offers resume — the reader does not need
to know a phrase. The legacy "say 'let's start the batches'" pattern
from `librarian-build-setup` is documented as a fallback only; the
detection-driven offer is the primary path.

**Resolved:** Resume offer fires only on ambiguous or build-shaped
openers. Single-book queries route directly to quickref without
mention of in-progress build state.

---

## Failure modes

These are the scenarios where the happy path breaks. Every one ends
with a single-step recovery the reader can take.

### F1. Drive disconnects mid-session

**Detection:** A Drive read or write fails with an auth error.

**Active-skill response:**
> "Drive lost connection mid-session. The work we've done is still in
> the picker artifact's storage; it'll write back to Drive as soon as
> Drive reconnects. To reconnect: click your avatar → Settings →
> Connectors → Google Drive → Reconnect. Then say 'flush now' and I'll
> push everything to Drive."

**Why this works:** All session edits are staged in `window.storage`;
Drive is the eventual destination. Disconnect doesn't lose work as
long as the artifact is still published.

### F2. Catalog SQLite file missing or corrupted

**Detection:** Decode produces a non-sqlite file, or
`PRAGMA integrity_check` fails.

**Active-skill response:**
> "The catalog file in your Drive looks corrupted. Quickest fix:
> from your local repo, run `python3 catalogue.py --export-sqlite
> --emit-encoded` and re-upload `Library_Catalog.sqlite.encoded` to your
> Library-Playground Drive folder. Then come back and say 'continue'."

**Edge case:** If the catalog has been mutated in-session by the
cataloguer skill but the session-end Drive flush has not yet
happened (e.g. F4 usage-limit cutoff, F1 Drive disconnect), the
build skill should refuse to re-decode from Drive on the next
session-start without first checking for an in-sandbox `.sqlite`
that hasn't been flushed. Tell the reader:

> "I made some catalog edits earlier this session that haven't been
> flushed to Drive yet. Re-decoding from the broken Drive copy would
> lose those. Save the in-session catalog snapshot first by saying
> 'save catalog'."

### F3. Build state in `window.storage` is corrupted or missing

**Detection:** JSON parse error on read, or expected keys missing.

**Active-skill response:**
> "I can't read the in-progress build state — looks like it got
> corrupted or the artifact was unpublished. The Reading_List.md in
> your Drive has the books we'd already committed, so we don't lose
> the committed picks. We do lose: the shown-ledger (so books I'd
> already pitched might re-appear), the goals table, and the indie/
> classic floor counters. Want to start fresh from the existing
> Reading_List, or restart the build entirely?"

(`AskUserQuestion`: Resume from existing Reading_List / Start fresh
build / Other.)

**Why this is recoverable:** Reading_List.md in Drive is the
authoritative deliverable; build state in `window.storage` is the
*conversation history* around producing that deliverable. Losing
build state is annoying but not destructive.

### F4. Reader hits Pro plan usage limit mid-build

**Detection:** Claude.ai surfaces a "you've used your messages" toast.
The skill itself can't detect this directly — it sees the conversation
end abruptly.

**Mitigation built into the design:**

1. **Every batch flushes to Drive.** The picker artifact's "Save
   selections" button writes to `window.storage` *and* triggers the
   skill on the reader's next turn to flush Profile.md and
   Reading_List.md to Drive. Worst case: one batch's worth of
   conversation context is lost.
2. **Phase boundaries always flush.** Plan Step 7–9 call this out;
   reinforced here.

**Reader-facing recovery (in `SETUP.md`):**
> "If you hit the message limit mid-build, your committed picks and
> profile updates are safely in Drive. Wait out the cooldown, open a
> new chat, and the triage skill will offer to resume. The state in
> the picker artifact survives across the reset."

**Edge case:** If the reset happens *between* the picker save and the
follow-up turn that would flush to Drive, you lose the picks the
reader just selected. Mitigation: the picker artifact itself does a
best-effort "queue selections to flush" write to a separate
`pending_flush` key in `window.storage`; on the next session the
triage skill detects that key and tells the reader:

> "I see selections from your last session that didn't make it to
> Drive — let me flush them now."

### F5. Skill doesn't trigger on the expected opener

**Detection:** Reader-facing — the reader says something library-
shaped and the chat replies as the default Claude.ai assistant
without the skill chip appearing.

**Reader recovery (documented in `SETUP.md`):**

> Open Settings → Features → Skills. Confirm all six are listed and
> enabled. If any are missing, re-upload from `dist/skills/`. If all
> are present and a librarian-shaped query still doesn't trigger,
> the description text on the triage skill may have drifted — open
> the skill to inspect, and re-zip / re-upload from the latest repo.

### F6. Picker artifact unpublished accidentally

**Detection:** First storage read fails with the "not published"
error pattern.

**Reader-facing response:** See "The artifact-storage problem" above.

### F7. Multiple users on the same Pro account

**Out of scope for this UX.** Pro is per-user; shared accounts get
shared `window.storage` per artifact, which collides build state.
`SETUP.md` will note this in the troubleshooting section as
unsupported.

### F8. Reader uploads a Library.csv mid-session via paperclip

**Detection:** The reader pastes a CSV expecting it to "update the
catalog."

**Active-skill response (cataloguer):**
> "I see a CSV upload — that's the bulk catalogue path, which has to
> run on your local machine because it makes a lot of API calls. To
> add new books from this CSV: save it locally as
> Library.csv, run `python3 catalogue.py --library Library.csv`,
> then `--export-sqlite --emit-encoded`, and upload the new
> Library_Catalog.sqlite.encoded to Drive. For 1–10 new books, just
> tell me the titles and I'll add them in chat."

---

## Maintenance flow — adding new books later

Two sub-flows, depending on volume.

### M1. Adding 1–10 books

The reader stays in chat:

> "I just bought *The Lesser Dead* by Christopher Buehlman and *Mountain Fast* by Brian Lerner."

Triage routes to **library-cataloguer skill**. The skill:

1. Confirms titles + authors via `AskUserQuestion`.
2. For each book: looks up via web search if needed, fills catalog
   fields (taste_signals, comparable_books, content_flags, etc.),
   shows the proposed entry in chat for reader confirmation.
3. After confirmation: writes to the in-session SQLite (decoded copy
   in sandbox), regenerates affected indices.
4. On session end (or explicit "save"): re-encodes SQLite as base64,
   uploads to Drive, archives the prior version.

Reader confirms each entry with `AskUserQuestion` ("Apply this entry?
Yes / Hold / Cancel"). Once approved, the change is staged. Saving is
a single batch upload at session end.

### M2. Adding more than ~10 books (bulk)

The reader has to leave claude.ai briefly:

> "I added 80 new books to my Goodreads list and want them in the catalog."

Cataloguer skill response:

> "Bulk additions go through the local cataloguer because it makes
> dozens of API calls. Steps:
>
> 1. Export the updated CSV from Goodreads to your local
>    `~/Library-Playground/Library.csv`.
> 2. Run `python3 catalogue.py --library Library.csv` — takes 30 mins
>    to a few hours depending on book count. New rows get processed;
>    already-catalogued books are skipped.
> 3. Run `python3 catalogue.py --export-sqlite --emit-encoded`.
> 4. Upload the new `Library_Catalog.sqlite.encoded` to your
>    `Library-Playground` Drive folder, replacing the old one.
> 5. Come back here, say 'catalog refreshed', and I'll re-decode and
>    confirm the new book count."

**Verification** that the catalog refresh worked:

```
"Catalog now has 4,683 books (up from 4,603). Most-recent additions:
- Mountain Fast — Brian Lerner (Horror)
- The Lesser Dead — Christopher Buehlman (Horror)
- ...
Looks right? Want to bring any of the new ones into your current
build?"
```

This connects bulk-add to in-progress builds organically: the new
books become eligible for upcoming batches without the reader having
to say so.

### M3. Updating the reading log

After finishing a book and rating it:

> "I just finished *Hyperion* — 5 stars."

Cataloguer (which owns reading-log writes):

1. Confirms via `AskUserQuestion`: "Add to log? Title=Hyperion,
   author=Dan Simmons, rating=5, date=today (2026-05-02). Yes / Edit /
   Cancel."
2. On approval, appends a row to the in-sandbox `Reading_Log.csv` and
   re-encodes for Drive flush.
3. If the book is currently in `Reading_List.md`, removes it (it's no
   longer "to be read") with a notification.

**Bulk reading-log refresh** (if the reader exports a fresh
`Reading_Log.csv` from Goodreads):

```
"Drop the new Reading_Log.csv into the Library-Playground Drive folder
(replacing the old one). Then say 'log refreshed' here and I'll re-
read it. Note: any rated reads from your last session that I haven't
saved yet will be merged with the new export."
```

---

## What the user types — the documented phrase set

The reader memorizes nothing. But the documented phrases — the ones
`SETUP.md` mentions explicitly as "if you ever want to" — are short:

| Phrase | What it does |
|---|---|
| `where are we` | Triage replays the build state ("phase 2, 47 books in pool, indie floor at 6 of 10") |
| `flush now` | Force a Drive flush of Profile.md + Reading_List.md (also auto-fires at phase boundaries) |
| `save catalog` | Cataloguer flushes in-session catalog edits to Drive |
| `continue` | After a recovery prompt, resume the prior flow |
| `start fresh` | Discard build state in `window.storage`, keep Profile.md and Reading_List.md in Drive |

Everything else is shape-detected. The phrase list lives in
`SETUP.md` under "Reader cheat sheet" and in a same-folder
`PHRASES.md` that the reader can keep open in another tab.

---

## What lands in `SETUP.md` (Step 10) from this design

Mapped one-to-one:

| `SETUP.md` section | Source in this doc |
|---|---|
| Prerequisites | "Local folder structure" + plan's stated prerequisites |
| One-time local setup | "Local folder structure" + plan Step 10 list |
| Drive setup | "Google Drive folder structure" + "The catalog distribution problem" |
| Skills install | "Skills installation flow on claude.ai" |
| First session walkthrough | "First-session experience" — Session A |
| Returning user walkthrough | "First-session experience" — Session B |
| Reader cheat sheet | "What the user types" |
| Maintenance | "Maintenance flow" |
| Troubleshooting | "Failure modes" F1–F8 |

---

## Architectural impact of the verification pass — summary

These are the five constraints that the verification pass surfaced
which differ from the plan's casual assumptions. All are absorbed
into the UX above.

1. **Drive connector reads text only.** SQLite ships gzip+base64
   wrapped as `Library_Catalog.sqlite.encoded` (~1–1.5MB). Reader
   never sees the encoding; setup adds one flag to the export
   command. See "The catalog distribution problem".
2. **GitHub connector on claude.ai is read-only and binary-
   unsupported.** Cannot replace Drive for the cataloguer's write
   path. GitHub remains the canonical source for read-only repo
   content (skills, helper, catalogue.py); Drive is the only mutable
   store on the claude.ai surface.
3. **Helper script can't reliably fetch from raw GitHub.** Bundled
   inside each skill that needs it via `make skills` symlink. See
   "The helper-script distribution problem".
4. **`window.storage` requires a published artifact, persists per-
   artifact-per-user, text-only, ~20MB total. Unpublishing wipes
   data permanently.** Setup includes a "publish the picker once"
   step plus a triage preflight check on every build session. Full
   detail at top of file under "Required: publish the picker
   artifact".
5. **Code execution sandbox network access varies.** No part of the
   architecture above requires arbitrary HTTPS fetches. Catalog
   comes via Drive (text-wrapped), helper comes bundled in skill,
   web search for upcoming releases (Phase 3) goes through Claude's
   native `WebSearch` tool.
6. **Mutable-state split** (refactor 2026-05-02 second pass): Drive
   narrows to one binary file; Profile + Reading_List move to their
   own published artifacts; Reading_Log + slim browse index move to
   project knowledge.  See "Storage layout" table above and the
   13-18 rows of the resolved-decisions table for the full split.

---

## Decisions resolved (2026-05-02)

| # | Question | Resolution |
|---|---|---|
| 1 | Drive folder name | First-run only. Stored in `.config.json` in Drive. |
| 2 | `make skills` packaging | Six separate zips. No combined `all-skills.zip`. |
| 3 | Catalog (SQLite) write cadence | Flush to Drive at session end only. |
| 4 | Profile.md / Reading_List.md cadence | Per-edit flush to Drive. |
| 5 | Helper distribution | Skill-bundled only. No URL-fetch fallback. |
| 6 | Picker artifact URL location | `.config.json` in Drive. |
| 7 | Triage resume-offer trigger | Ambiguous or build-shaped openers only. |
| 8 | GitHub vs Drive primacy | Drive primary (mutable). GitHub canonical for read-only repo content. |
| 9 | Catalog JSON deprecation | Deprecated after Step 6. SQLite is sole source of truth. JSON gitignored thereafter. |
| 10 | Bulk catalog without Code | Cataloguer skill accepts ≤20 books per chat batch. User repeats as needed. |
| 11 | All catalog fields in SQLite | Yes — all 36 fields, including `secondary_genre`, `audio_notes`, `research_source`, `audit.passed`, full `audit.flags[]` row table, plus catalog metadata. |
| 12 | Encoded format | gzip + base64, `Library_Catalog.sqlite.encoded`, header line `# library-playground-catalog v1 gzip+b64`, decode once at session start. |
| 13 | Storage budget | ~20MB per artifact.  Three artifacts × 20MB = 60MB total; build state is tens-to-hundreds of KB, profile ≤100KB, reading_list ≤500KB.  Plenty of headroom. |
| 14 | Mutable storage split | Drive holds catalog only.  Project knowledge holds reads (browse index, reading log).  Artifacts hold mutable user-facing files (profile, reading-list).  Picker artifact holds invisible build mechanics. |
| 15 | Project-file Profile.md handling | Triage seeds the profile artifact from `PROJECT_PROFILE` on first session.  Build-setup honours existing profile via partial-interview / fresh-interview prompt. |
| 16 | Project-file Reading_List.md handling | Triage seeds the reading-list artifact from `PROJECT_LIST` on first session.  Refine-vs-fresh prompt at triage when content exists. |
| 17 | Project-file Reading_Log.csv handling | Read-only path.  In-chat rate updates queue to `log_pending_updates` on the picker artifact; reader merges to project file via re-upload. |
| 18 | Slim browse index | `python3 catalogue.py --library Library.csv --export-browse-index Library_Browse_Index.json` — single-letter field codes, no comparable_books, ~800KB at 5,000 books.  Lives in project knowledge for fast presence checks. |

---

## What this doc explicitly is NOT

- **It is not a re-spec of the librarian invariants.** Those live in
  the original `librarian/SKILL.md` and `library-cataloguer/SKILL.md`
  on `main`, and the new `.claude.ai/skills/*/SKILL.md` files (Steps
  4–9) re-encode them.
- **It is not a build plan.** That's `CONVERSION_PLAN.md`.
- **It is not the user-facing setup guide.** That's `SETUP.md`,
  written in Step 10, sourced from this doc.
- **It is not a binding contract.** Every UX choice above is open to
  revision based on what we learn building Steps 1–3.
