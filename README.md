# Library Cataloguer

Autonomously builds `Library_Catalog.json` from your `Library.csv` using the Claude API.
Catalogues each book (summary, tone, pacing, themes, audio suitability, taste signals)
and audits CSV tags against known records in the same pass.
Designed to run in **Claude Code** without requiring human approval between chunks.

---

## Setup

Claude Code sets `ANTHROPIC_API_KEY` automatically. If running outside Claude Code:

```bash
export ANTHROPIC_API_KEY=your_key_here
pip install anthropic
```

---

## Usage

### First run — catalogue and audit everything
```bash
python catalogue.py --library Library.csv
```

### Check progress without processing
```bash
python catalogue.py --library Library.csv --status
```

### Resume after interruption
```bash
python catalogue.py --library Library.csv
```
Already-complete entries are skipped. Just re-run the same command.

### Generate the audit report from an existing catalog
```bash
python catalogue.py --library Library.csv --audit-report
```
Writes `Library_Audit_Report.md` without making any API calls.

### Add new books after the initial run
```bash
python catalogue.py --library Library.csv
```
Detects new books in the CSV, adds them as pending, processes and audits them.
Existing complete entries are never reprocessed.

### Re-audit entries processed before the audit feature existed
```bash
python catalogue.py --library Library.csv --re-audit
```
Reprocesses complete entries that have no audit data yet.

### Review low-confidence entries
```bash
python catalogue.py --library Library.csv --review-only
```
Reprocesses only entries marked `needs_review`.

### Adjust chunk size
```bash
python catalogue.py --library Library.csv --chunk-size 40
```
Default is 25. Use larger chunks (40–60) for well-known books to go faster.
Use smaller chunks (10–15) if many books need web searches.

---

## Outputs

### Library_Catalog.json
Written after every chunk — safe to interrupt at any time.

Each entry contains:
- **summary** — 1-2 sentence spoiler-free plot summary
- **tone / pacing / themes / setting** — for taste matching
- **comparable_books** — other library books with similar appeal
- **taste_signals** — positive and negative signals for recommendation filtering
- **audio_suitability** — format recommendation
- **content_flags** — meaningful content warnings only
- **confidence** — High / Medium / Low
- **status** — complete / needs_review / pending
- **audit** — result of tag verification against known records (see below)

### Library_Audit_Report.md
Generated at the end of every run (and on demand with `--audit-report`).

Flags are grouped by severity:
- 🔴 **Error** — clearly wrong (e.g. genre tagged Fantasy but it's Nonfiction)
- 🟡 **Warning** — likely wrong (e.g. series_status tagged Standalone for a 12-book series)
- 🔵 **Note** — minor or debatable (e.g. genre could go either way)

---

## Audit field in each catalog entry

```json
"audit": {
  "passed": true,
  "flags": [
    {
      "field": "series_status",
      "csv_value": "Short Series",
      "expected_value": "Long Series",
      "severity": "error",
      "reason": "Series has 14 books and ~2M words — well above Long Series thresholds"
    }
  ]
}
```

`passed` is false if there are any errors or warnings. Notes alone don't fail the audit.

---

## Scale expectations (5,000-book library)

- ~200 API calls at default chunk size 25
- Books needing web search take longer per chunk
- Estimated wall time: 2–6 hours depending on web search volume
- Audit report generated automatically at the end
- Safe to stop and resume at any time

---

## Using the catalog with the Librarian skill

Once `Library_Catalog.json` is in your Claude project, the librarian skill loads it
automatically at the start of recommendation sessions for deep knowledge of your collection.
For future small additions, use the **library-cataloguer skill** in Claude.ai instead of
this script.
