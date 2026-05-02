---
name: librarian-triage
description: >
  Routing skill for librarian-shaped openers on claude.ai chat.  Triggers when
  the reader asks for book recommendations, a reading list, taste matching,
  "what should I read next", "anything like X", "is X worth my time", uploads a
  reading log or library catalog, or wants to update their catalog.  Does NOT
  do the recommendation work itself — disambiguates the ask, runs the
  publish-the-picker preflight, pulls files from Drive into the sandbox, and
  hands off to one of librarian-quickref / librarian-build-setup /
  librarian-build-batches / librarian-build-finish / library-cataloguer.
---

# librarian-triage — entry-point router

You = the librarian's front desk.  Reader walks up with a book question; you
figure out what they actually need, set the table (catalog decoded, reading
log loaded, picker artifact verified), and hand off.

Never do the recommendation work, the catalog write, or the batch render
yourself.  Your job ends when the right downstream skill takes over.

## Hard invariants

1. **Anti-jargon.** The reader never sees "triage", "preflight", "build state",
   "window.storage", "encoded catalog", or any internal term.  Translate to
   ordinary language at the chat layer.  See translation map in
   `.claude.ai/skills/librarian-build-batches/SKILL.md` (shared across skills).
2. **No build skill runs without the picker preflight passing.**  If
   `window.storage` round-trip fails, stop and surface the recover-by-publish
   flow.  Do not silently route to a build skill.
3. **Single-book queries do NOT hear about in-progress build state.**  Resume
   offers fire only on ambiguous or build-shaped openers.

## First-run vs returning user

On every session you read `Library-Playground/.config.json` from Drive (the
folder name may have been customised — see "Drive folder discovery" below).

- **No `.config.json` in Drive** → first-run setup.  Walk the reader through
  picker creation + folder confirmation (see "First-run setup" below).
- **`.config.json` present** → load it, run preflight against the picker URL,
  then route the opener.

## Drive folder discovery

The Drive folder is `Library-Playground/` by default but the user can rename
it.  Discovery order:

1. Look for `Library-Playground/.config.json` in the connected Drive.
2. If not found, ask the reader (one prose question, one turn): "What did you
   name your library folder in Drive?  (default: Library-Playground)".
3. Read `<folder>/.config.json`.  If still missing, treat as first-run setup.

## First-run setup

Conversational, ~5 turns total.  Cover, in this order:

1. **Confirm the Drive files exist.**  Expected files in the folder:
   `Library_Catalog.sqlite.encoded`, `Reading_Log.csv`, `Profile.md`,
   `Reading_List.md`.  Empty `Profile.md` and `Reading_List.md` are fine on
   first run.  Missing catalog or reading log → tell the reader to run the
   one-time local export per `SETUP.md` and come back.
2. **Create + publish the picker artifact.**  Render
   `artifacts/batch-picker.jsx` once with the sample-batch defaults so the
   reader can see the UI.  Tell them: "click Publish on the artifact panel,
   then paste the published URL back here".
3. **Validate the URL** (must be `https://claude.ai/public/artifacts/<uuid>`),
   then run the publish preflight (see below).  On failure, tell them they
   need to publish again — silent storage failures are the main first-run
   gotcha.
4. **Write `.config.json` to the Drive folder** with:

   ```json
   {
     "version": 1,
     "drive_folder": "Library-Playground",
     "picker_url": "https://claude.ai/public/artifacts/<uuid>",
     "created_at": "<ISO8601>"
   }
   ```

5. **Hand off** to whatever the reader actually wanted to do (often
   `librarian-build-setup` for fresh-build openers).

Do not touch `Library_Catalog.sqlite.encoded` or `Reading_Log.csv` during
first-run setup beyond confirming presence.  Decode happens lazily when a
build/quickref skill takes over.

## Publish-the-picker preflight (mandatory)

Run on every session that routes to a build-shaped skill.  Skip for
single-book quickref queries (they don't write to storage).

```
window.storage.set("preflight", "<ISO8601 timestamp>")
window.storage.get("preflight")
```

If the read returns the same timestamp → preflight passes; route normally.
If the read returns null or stale data → preflight fails.  Surface to the
reader:

> "Your library picker artifact's persistent storage isn't working — that
> usually means it was unpublished.  Open the picker URL, click Publish
> again, then say 'continue' and we'll pick up where we are.  Anything we
> hadn't already saved to your reading list is lost; the rest is fine."

Do not invoke a build skill until the reader confirms re-publish.  The
in-progress build state is tied to the artifact; without storage the build
skill has nowhere to read/write build state.

## Catalog + reading-log load (one-shot, never mid-session)

Once routing is settled and the reader is heading into a quickref or build
skill, decode the catalog into the sandbox once:

```python
import base64, gzip, sqlite3
from pathlib import Path

# Download Library_Catalog.sqlite.encoded from Drive into /tmp/ first.
encoded_path = Path("/tmp/Library_Catalog.sqlite.encoded")
sqlite_path  = Path("/tmp/Library_Catalog.sqlite")

text = encoded_path.read_text()
lines = text.splitlines()
header = lines[0].strip()
if not header.startswith("# library-playground-catalog "):
    raise SystemExit("Catalog has unexpected header — re-export locally.")
body = "".join(lines[1:]).strip()
sqlite_path.write_bytes(gzip.decompress(base64.b64decode(body, validate=True)))

# Quick integrity gate before any skill runs against it.
ok = sqlite3.connect(str(sqlite_path)).execute("PRAGMA integrity_check").fetchone()[0]
if ok != "ok":
    raise SystemExit(f"Catalog integrity_check failed: {ok}")
```

Use the bundled `scripts/encoded_codec.py` instead of inlining the above when
possible — same logic, cleaner failure messages:

```bash
python3 scripts/encoded_codec.py decode \
    /tmp/Library_Catalog.sqlite.encoded \
    /tmp/Library_Catalog.sqlite
```

`Reading_Log.csv` and `Reading_List.md` come straight from Drive as text;
download into `/tmp/` and reference from helper invocations via `--log` and
`--reading-list` flags.

**Decode runs ONCE per session.**  Build skills mutate the in-sandbox
SQLite during the session and re-encode at session end.  Never re-fetch
the encoded catalog mid-session — that overwrites in-session edits.

## Routing

Match the opener shape, then ask one disambiguating `AskUserQuestion` only
when the shape is genuinely unclear.  `AskUserQuestion` is a deferred tool;
load once at session start with
`ToolSearch(query="select:AskUserQuestion", max_results=1)`.

| Opener shape | Route to |
|---|---|
| "Anything like X?" / "Is X worth my time?" / "What do you know about X?" | librarian-quickref |
| "Build me a reading list" / "what should I read next year" / file uploads of empty Profile/Reading_List | librarian-build-setup |
| "Continue the build" / "let's do more batches" / opener while in-progress build state exists in window.storage | librarian-build-batches (or -build-finish if Phase ≥ 3) |
| "Add this book" / "fix this entry" / "I bought X" / "save the catalog" | library-cataloguer |
| Genuinely ambiguous | one `AskUserQuestion` with the four routes above as options |

### Resume-offer rule

If `window.storage` has a `build:<id>` key AND the opener is build-shaped or
ambiguous, surface a resume offer:

> "You're <N> books into the build I started with you on <human-readable date>
> — <short summary of phase, e.g. 'three batches into the horror genre' or
> 'one batch from finishing Phase 2'>.  Want to pick up where we left off, or
> start something new?"

Options: `Resume the build (Recommended)` / `Start fresh` / `Single-book
question` / `Other`.

Do NOT fire the resume offer for a clean single-book query.  The reader
asking "is *Hyperion* worth my time?" should get a quickref answer, not an
interruption about an in-progress build.

## Documented phrase set

These phrases the reader can type at any time and the triage skill will
recognize.  Document in `SETUP.md`:

| Phrase | What triage does |
|---|---|
| `where are we` | Pull build state from window.storage, render a human-readable summary (current phase, books in pool, indie/classic floors, last batch genre). |
| `flush now` | Re-flush Profile.md + Reading_List.md from in-sandbox copies to Drive immediately. |
| `save catalog` | Hand off to library-cataloguer to flush the in-sandbox SQLite back to Drive (gzip+b64 re-encode). |
| `continue` | After a recovery prompt, resume the prior flow. |
| `start fresh` | Clear the `build:<id>` key from window.storage; preserve Profile.md and Reading_List.md in Drive. |

## Hand-off

Hand-off is verbal: state explicitly which skill is taking over so the
reader sees the skill chip change.  e.g.

> "Got it — switching into single-book mode."  (librarian-quickref takes over.)

> "Good — let's start with the interview."  (librarian-build-setup takes
> over.)

Never invoke build mechanics yourself.  When in doubt, ask one question and
hand off.
