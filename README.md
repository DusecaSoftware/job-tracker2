# Afsheen Khan — private design job automation

Python background CLI, SQLite system of record and Excel reports. No web interface,
automatic submission, email sending or paid AI dependency. This project targets
**Graphic Design, UI/UX Design and Web Design**, plus related visual/brand/product
roles when the actual CV supports them. It does not target engineering roles.

## Current implementation and limits

1. Foundation: configuration, private directories, transactional SQLite, JSON logs,
   status history, source checkpoints, deduplication and automated tests.
2. Excel: six worksheets, tables, filters, frozen headers, status colours, chart,
   response/conversion formulas, historical daily snapshots, rolling weekly/monthly
   submission totals, source, arrangement and score breakdowns.
3. Sources: user-supplied JSON imports and an opt-in official WWR design RSS adapter
   with bounded retries, rate limiting and access-denial stops. Live WWR access has
   **not been validated**: the environment proxy returned HTTP 403 to CONNECT.
4. PDF/DOCX extraction, reviewed source excerpts, rule-based design matching,
   configurable weights, location eligibility, stale/deadline detection.
5. Deterministic tailored DOCX CVs and cover letters using reviewed CV excerpts.
   These are drafts for human review. No generative AI service is configured.
6. Idempotent pipeline, lock against concurrent runs, atomic document/report writes,
   Windows scheduling helper. Tested on Linux; Windows execution is not verified.
7. Explicit document approval and manual submission confirmation. Authorized local
   imports of reviewed email status events are supported. Direct Gmail/Outlook inbox
   integration and outbound notifications are **not implemented/configured**.

The actual master CV was not provided during implementation. No real candidate
matching or document generation has been validated. Synthetic test documents are
clearly labelled. Do not use synthetic fixtures as actual application data.

## Setup

Python 3.11+ (tested with 3.12):

```powershell
cd C:\path\to\job-tracker2
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[test]"
Copy-Item .env.example .env
.\.venv\Scripts\python.exe -m job_tracker.cli init
.\.venv\Scripts\python.exe -m pytest -q
```

Linux: `python -m venv .venv`, then `.venv/bin/python -m pip install -e '.[test]'`.
Always run commands from the repository root. `JOB_TRACKER_HOME` controls the data
root; `MASTER_CV_PATH` is relative to that root unless absolute. Environment values
override `.env`. Threshold is 0–100; stale days must be positive. No secrets are
required for the basic workflow. SQLite/report/log files contain private data.
Restrict OS access and protect backups yourself; SQLite is not encrypted.

`requirements.lock.txt` records the tested environment. For exact dependency
reproduction install it before installing this project with `pip install --no-deps -e .`.
TLS and package verification must remain enabled.

## Provide and verify the actual master CV

Copy the actual CV manually to `input/master_cv.pdf` (or set `MASTER_CV_PATH` to a
DOCX). Do not commit it. Run:

```powershell
.\.venv\Scripts\python.exe -m job_tracker.cli extract-cv
```

Read `input/master_cv.extracted.txt` privately and compare it with the original,
including selected projects, dates and contact details. Scanned PDFs need a
text-based replacement; OCR is not silently guessed. Create private
`input/profile.reviewed.json` with this schema (values below are placeholders):

```json
{
  "name": "Afsheen Khan",
  "reviewed": true,
  "master_sha256": "SHA256 printed by extract-cv",
  "contact": ["exact CV contact excerpt"],
  "skills": ["exact individual CV skill excerpt"],
  "experience": ["complete exact CV employment/date/responsibility excerpt"],
  "education": ["complete exact CV education/date excerpt"],
  "projects": ["exact CV project excerpt"]
}
```

Every supplied excerpt must occur in the actual CV (case and whitespace normalized).
A hash mismatch blocks reuse after a master CV change. Keep full context in each
excerpt; software cannot establish the meaning or completeness of a selected
fragment. Human review is required. No summary from the original request is used
to manufacture a master CV. Portfolio links are not proof of project content.

## Collect, match, prepare and report

```powershell
.\.venv\Scripts\python.exe -m job_tracker.cli collect --file input/jobs.json
.\.venv\Scripts\python.exe -m job_tracker.cli match
.\.venv\Scripts\python.exe -m job_tracker.cli generate
.\.venv\Scripts\python.exe -m job_tracker.cli sync-excel
.\.venv\Scripts\python.exe -m job_tracker.cli follow-ups
.\.venv\Scripts\python.exe -m job_tracker.cli run --file input/jobs.json
```

`run` executes collection → matching → drafts → follow-ups → Excel. With no source
flag it processes existing jobs. Missing CV/reviewed facts intentionally stop it;
collection checkpoints remain committed for recovery. Reports can independently
be rebuilt with `sync-excel`. Close Excel before overwriting the workbook on Windows.
Any command accepts `--dry-run`: validates config and describes the command without
network, database or file writes; it does not simulate the command or verify inputs.

Import schema: see `fixtures/jobs.synthetic.json`. Required fields: source,
source_id, URL, title, employer. Optional fields: description, location, arrangement
(`Remote`, `Hybrid`, `Onsite`), salary (verbatim), employment_type, published_at,
deadline (ISO dates/timestamps). Use authorized exports/manual records only. URLs
lose tracking parameters and fragments; source IDs and normalized URLs deduplicate.
Different URLs may still be duplicate jobs; identical normalized employer/title
pairs receive a potential-duplicate review warning. Payment/sensitive-data requests
and unencrypted URLs receive review warnings, never automatic fraud labels. No posting is automatically labelled fake. Never pay application fees or
provide sensitive information solely because a posting passed matching.

LinkedIn, Indeed and Wellfound are priority sources for **manual discovery and
permitted exports**. No undocumented scraper or API is included. Their authenticated
search, CAPTCHA and anti-bot protections are not bypassed. Official API access,
licenses or approved integrations would be prerequisites for further automation.
WWR is opt-in after checking current feed terms:

```powershell
.\.venv\Scripts\python.exe -m job_tracker.cli collect --wwr
```

Required network destinations: `registry/pypi` dependencies use `pypi.org` and
`files.pythonhosted.org`; Git uses the platform GitHub proxy; optional RSS uses
`weworkremotely.com`. A 401/403/429 stops collection; do not bypass access controls.
No web preview is used.

## Matching interpretation

Weights default to skills 30, tools 15, specialization 20, responsibilities 10,
seniority 10, location 10 and portfolio 5. Pass `--weights input/weights.json`
containing all seven keys to change them. The explanation stores component values.
Skills/tools use transparent text overlap; responsibility overlap is a heuristic,
seniority and portfolio start at partial credit pending review. Scores are relevance
estimates, **not ATS success probabilities**. Unknown requirements are not invented.

Explicit worldwide/Pakistan eligibility is prioritized. Unclear remote eligibility
stays `Needs review` and is not auto-shortlisted. Local hybrid/onsite roles must name
Islamabad or Rawalpindi. Explicit country restrictions override worldwide text.
This is a conservative language heuristic, not a complete geography parser; verify
country, timezone, visa, seniority, salary and employment terms manually. Salary and
employment type are preserved for filtering in Excel; no salary is inferred.
Stale or past-deadline postings are marked Expired by policy, not claimed fraudulent.

## Approval and truthful outcomes

Inspect both generated files in `output/documents/job-ID-VERSION/`. Then:

```powershell
.\.venv\Scripts\python.exe -m job_tracker.cli approve --job-id 1
# Apply manually outside this system, then record actual evidence:
.\.venv\Scripts\python.exe -m job_tracker.cli status --job-id 1 --to Submitted --confirmed --evidence "Receipt reference" --follow-up 2026-12-10
.\.venv\Scripts\python.exe -m job_tracker.cli status --job-id 1 --to "Recruiter Response" --evidence "Actual recruiter response reference"
```

Approval never submits. Submitted requires prior document approval, explicit
confirmation and evidence. Outcomes require a confirmed submission. Dates, offers
and interview invitations are never invented. `follow-ups` outputs due submitted
applications; it sends no messages. Interview time/notes can be recorded via reviewed
email-event imports. This command is a local-file authorization only:

```powershell
.\.venv\Scripts\python.exe -m job_tracker.cli import-email-status --file input/email-events.json --authorized
```

Example event shape: `{"job_id":1,"status":"Interview Scheduled","evidence":"actual message reference","interview_at":"2026-12-10T10:00:00+05:00"}`
inside a JSON list. Supply only facts you reviewed and are authorized to process.
No inbox connection occurs. Duplicate imported evidence is ignored.

## Reports, recovery and scheduling

`output/Afsheen_Job_Tracker.xlsx` is rebuilt from SQLite. Applications submitted
counts only actual confirmed submission timestamps; generated CVs are separate.
Daily Metrics snapshots preserve prior days. Events preserve lifecycle history even
when the current status changes. Rates use unique jobs reaching the recorded event;
responses, interviews and offers are separate observations. Workbook formulas
recalculate when Excel opens it; openpyxl does not calculate formula caches.
Timestamps in SQLite are UTC; follow-up days use the machine's configured calendar.

Back up `data/tracker.sqlite3` using SQLite's backup API while running, or stop all
commands before copying the DB and WAL files. Restore private files with the same
relative paths. Source batches commit atomically with checkpoints; rerun failed
commands safely. An interrupted draft may leave orphan files but does not create a
submitted application. A stale `data/pipeline.lock` must be removed only after
confirming no tracker process is running. JSON logs omit CV contents and credentials.
Do not schedule overlapping tasks. No infinite retry loops are used.

Windows Task Scheduler: create a daily task for your local timezone, with program
`powershell.exe`, arguments `-NoProfile -File "C:\path\to\job-tracker2\scripts\daily.ps1"`,
and Start in `C:\path\to\job-tracker2`. Configure **Do not start a new instance**,
run only under your intended Windows account, and verify its Last Run Result and
`logs/events.jsonl`. The helper preserves the CLI exit status. It processes stored
jobs by default; opt into a permitted source only after reviewing its access terms.
Credentials for future inbox/notification services must be entered securely, never
in source control or command examples. No paid optional service is enabled.

## Verification audit

See [AUDIT.md](AUDIT.md) for the actual verification results, reproduced bugs and
fixes, current source-access limits, exact CV prerequisites and a small real-listing
test procedure. Date-only deadlines remain open through their UTC calendar day;
verify employer timezone details manually. Submitted dates/evidence cannot be
replaced by returning a later-stage application to Submitted.
