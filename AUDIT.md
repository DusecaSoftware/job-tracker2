# Verification audit — 3 November 2026 (Asia/Karachi)

Audited the existing `/workspace/job-tracker2` checkout without creating a new
project or adding integrations. Synthetic checks run in pytest temporary directories,
not in the application's live database. No real job applications or emails were sent.

## Actual checks

- Initial complete suite: **31 passed in 0.64s**.
- Additional audit cases first exposed **4 failures, with 36 passing**. After fixes
  and PDF ingestion checks, final complete suite: **43 passed in 1.21s**, no skipped,
  failed or expected-failure cases. Command: `.venv/bin/python -m pytest -ra`.
- `.venv/bin/python -m pip check`: **No broken requirements found**.
- SQLite `PRAGMA integrity_check`: **ok**.
- `output/Afsheen_Job_Tracker.xlsx`: ZIP integrity passed and openpyxl reopened it
  before and after two actual CLI exports. Exactly six sheets: Dashboard,
  Job Listings, Applications, Interview Tracker, Daily Metrics, Configuration.
  Five data/configuration tables, one dashboard chart, and the three rate formulas
  were found. Formula evaluation and Microsoft Excel rendering were not tested;
  no Excel/Windows application is running in this cloud environment.
- Actual DB before and after repeated exports: **0 jobs, 0 applications, 0 events,
  1 daily snapshot**, with identical persisted rows.
- A separate synthetic audit exported two applications three times: one with a
  confirmed submission, response, interview and rejection history; another only
  prepared. Job/application IDs remained unique, all application and event rows
  were unchanged, and a historical daily snapshot survived. Rerunning the CLI full
  pipeline twice also produced just one job/application and zero submissions.
- PDF and DOCX text extraction/reviewed profile flow were checked with synthetic
  documents; corrupt PDF/DOCX files return CLI errors, and textless PDFs are rejected.
  No actual Afsheen CV was available for testing.

## Bugs reproduced and fixed

1. Returning an already submitted application to Submitted after a recruiter response
   could overwrite its original timestamp and evidence. This is now rejected;
   repeated confirmation of a currently Submitted record remains idempotent.
2. Date-only application deadlines were treated as midnight at the start of the day.
   They now remain open through that UTC calendar day. Explicit timestamp deadlines
   retain their supplied timezone. Verify the employer's timezone manually.
3. An empty scoring-weight object silently selected defaults. It now fails validation.
4. Corrupt DOCX files raised uncaught ZIP errors. Known PDF/DOCX parse failures now
   produce a clear CLI error instead of a traceback.

All fixes have regression tests. No email integration or new feature was added.

## Sources and authorization

| Source/method | Evidence and current state |
| --- | --- |
| Authorized JSON import | Tested with synthetic records through the actual CLI; deduplication and reruns verified. No real listing import has been performed. |
| WWR design RSS | Parser tested synthetically. A fresh call to the actual adapter with one attempt failed: `URLError: Tunnel connection failed: 403 Forbidden`. No live jobs collected. |
| LinkedIn, Indeed, Wellfound | No direct adapters exist. Use permitted manual records/exports. Their live pages/APIs were not tested, so no HTTP result is asserted. Automated API integration would require approved access and implementation. |
| Gmail/Outlook | No inbox adapter or credentials configured. Reviewed local status-event imports only; authorization is checked. No inbox read or email send occurs. |

Current runtime policy is enforced and does not allow `weworkremotely.com`. The
previously saved domain addition is a draft, not proof of an applied network change.
Review/apply the environment network setting before retesting; a subsequent source
403 would still require respecting the source's access controls.

Source inspection found no submission POST, SMTP/email sender, browser application
bot, or inbox client. The only remote request path is the opt-in RSS read. Offline
pipeline tests fail on unexpected socket connections. Submission recording requires
prior document approval, explicit `--confirmed`, and nonempty evidence; negative CLI
cases were tested. These checks do not verify an external receipt's authenticity.

## Exact missing CV prerequisites

Both of these files are currently absent:

- `/workspace/job-tracker2/input/master_cv.pdf`
- `/workspace/job-tracker2/input/profile.reviewed.json`

1. Manually copy Afsheen's **actual full CV** to the private input folder:

   ```bash
   cd /workspace/job-tracker2
   mkdir -p input
   cp "/actual/path/to/Afsheen-CV.pdf" input/master_cv.pdf
   .venv/bin/python -m job_tracker.cli extract-cv
   ```

   Replace the source path with the real local file. For DOCX or another location,
   set `MASTER_CV_PATH=input/master_cv.docx` in `.env` or the command environment.
   No CV has been supplied or copied by this audit.

2. Read `input/master_cv.extracted.txt` and compare it against the actual CV,
   including dates, education, selected projects and contact information. The command
   prints its SHA256. Image-only PDFs need a text-based replacement; no OCR is provided.
3. Create `input/profile.reviewed.json` using the schema in README.md. Supply the
   exact printed SHA256, `reviewed: true`, name `Afsheen Khan`, and exact full-context
   CV excerpts in skills, experience, education, projects and contact arrays. Skills
   and experience are required. Do not paste placeholder facts or invent missing data.
   The profile is manually reviewed; the system does not structure a CV automatically.
4. Run `.venv/bin/python -m job_tracker.cli match`. A missing profile, hash mismatch,
   wrong candidate name or excerpt absent from the source blocks processing.

Git ignore checks passed for the master CV, reviewed profile, generated workbook,
SQLite DB and logs. Do not force-add private files. No credentials are needed for
manual imports, rule matching or deterministic document drafts.

## Small real end-to-end test

After completing the CV steps, manually choose **2–3 real design job postings** you
are permitted to use. Prefer an explicitly worldwide/Pakistan remote role and/or a
suitable Islamabad/Rawalpindi role. Verify that each is still open. Copy only its
actual fields into private `input/jobs.real.json`, a JSON list with objects shaped as:

```json
[
  {
    "source": "actual source name",
    "source_id": "actual posting ID or stable manual identifier",
    "url": "https://actual-employer.example/replace-with-real-job-url",
    "title": "exact role title",
    "employer": "exact employer name",
    "description": "actual requirements and eligibility text",
    "location": "actual location/country wording",
    "arrangement": "Remote"
  }
]
```

This is a **schema example, not a real listing**. Replace every placeholder. Set
arrangement accurately to Remote, Hybrid or Onsite. Include salary/employment_type
and ISO published_at/deadline only when known; do not guess.

```bash
cd /workspace/job-tracker2
.venv/bin/python -m job_tracker.cli run --file input/jobs.real.json
.venv/bin/python -m job_tracker.cli run --file input/jobs.real.json
```

Inspect `output/Afsheen_Job_Tracker.xlsx` and the draft documents under
`output/documents/`. The second run should add no jobs or application drafts.
Only jobs passing the threshold and explicit eligibility criteria generate drafts;
Needs review/low-score/ineligible jobs must not be forced into the shortlist merely
to produce documents. Prepared applications must have a blank Submitted column.
Review the matching explanation and documents against the actual CV and listing.
Do **not** run approve/status/email-import commands for this dry application rehearsal.
No need to enable RSS or buy an AI API to perform this test.

## Limits and workspace status

- Real CV processing, real-listing matching/drafting, live RSS collection and Windows
  Task Scheduler execution remain unverified. Missing CV/reviewed facts block the
  real candidate pipeline; WWR network access blocks that optional collector.
- Matching is a heuristic: seniority/portfolio and country-language ambiguities
  require human review. CV excerpts are checked for source presence, not semantic
  completeness. No portfolio content has been reviewed. There is no external AI API.
- Active workbook, database and logs resolve inside `/workspace/job-tracker2`.
  Synthetic audit outputs are in pytest temporary directories under `/tmp`.
- Git branch `work` has **no commits**. The implementation, tests, documentation and
  audit fixes are all untracked/uncommitted. Nothing has been pushed by this audit.
