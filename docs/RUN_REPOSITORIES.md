# Run the auditor and read the results

Your existing workspace already has dependencies installed in the parent `.venv`.
The local `.env` selects Groq and the tested `openai/gpt-oss-20b` model. Keep your
key local; you do not need another key for each repository.

**Recorded result on 25 October:** the quiz-generator attempts did not complete:
the 20B model exhausted its steps or received HTTP 400, and the 120B model reached
a rate/quota limit. There is no completed quiz-generator JSON report yet. Keep
the existing authentic Hello-World submission sample. See
[live evaluation](LIVE_EVALUATION.md) and the separate
[manual source review](QUIZ_GENERATOR_REVIEW.md). Wait for the applicable quota
reset before another run; do not enable billing to follow these instructions.

## Audit your quiz-generator repository

Open PowerShell and run:

```powershell
Set-Location "D:\SEM 7\2. MlOps\devops-auditor"
$auditPython = "..\.venv\Scripts\python.exe"

& $auditPython agent.py --repo https://github.com/MasabTahir732/AI-Intelligent-Reading-Comprehension-and-Quiz-Generator --output reports/quiz-generator.json --trace reports/quiz-generator.trace.jsonl --max-steps 20

if ($LASTEXITCODE -eq 0) {
    $auditResult = Get-Content reports/quiz-generator.json -Raw | ConvertFrom-Json
    Write-Host "Repository:" $auditResult.repository
    Write-Host "Reported findings:" $auditResult.violations.Count
    $auditResult.violations | Format-List rule_id, severity, category, file, line, description, evidence, recommendation
} else {
    Write-Host "The audit did not complete. Inspect the error and reports/quiz-generator.trace.jsonl."
}
```

The application checks DevOps/software engineering practices. It does not train
models, evaluate quiz quality or model accuracy, execute the target's code, or
load its pickle/model files.

On a fresh clone, follow README.md to create a project `.venv`; use
`.\.venv\Scripts\python.exe` instead of the parent-environment path.

## Test another repository

Use a public repository root URL and a new result name:

```powershell
& $auditPython agent.py --repo https://github.com/OWNER/REPOSITORY --output reports/another-repo.json --trace reports/another-repo.trace.jsonl --max-steps 20
```

Replace `OWNER/REPOSITORY`. Avoid `/tree/`, `/blob/`, private URLs, or credentials
in the URL. Run one audit at a time to share the free quota predictably.

Twenty model turns is a useful initial budget. The last two turns are reserved
for submitting/correcting a validated report; earlier tool choices are model-led.
A higher budget can improve investigation coverage but takes longer and consumes
more quota. Waiting helps temporary rate limits, not a request that is too large
or daily quota that has not reset. No billing upgrade is required by this code.

## Interpret success and failure

- **Exit 0 / "Audit completed"**: a validated JSON report was written. Findings
  do not make the command fail.
- **Exit nonzero / "Error"**: no new completed report was produced. A previous
  report at the same path is preserved; do not mistake it for the failed run's output.
- **Empty violations**: no supported finding was reported in this investigation;
  it does not certify the repository as defect-free.

Open the JSON and trace in your editor. Confirm every finding's path, line,
mechanism, applicability and recommendation. A skipped binary or unavailable
check is not a defect by itself. The trace records real tool results and model
calls, including invalid requests and context compaction where applicable.

## Use a reviewed successful run for submission

After the quiz-generator run completes successfully and its findings have been
reviewed, preserve the exact matching report/trace pair:

```powershell
Copy-Item reports/quiz-generator.json sample_report.json
Copy-Item reports/quiz-generator.trace.jsonl sample_trace.jsonl
& $auditPython scripts/verify_submission.py
```

Do not manually invent or remove findings and label the result raw agent output.
Document disputed findings separately. If replacing the committed smoke sample,
update the live evaluation notes to describe the new target and its limits.

Publish reviewed files using [PUBLISHING.md](PUBLISHING.md), check GitHub Actions,
and submit the public auditor repository URL through your course channel. Do not
submit only the target repository URL or an isolated JSON report.
