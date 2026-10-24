# Assignment requirements and final checks

This checklist separates implementation responsibilities from work that requires your API access, human review, and final submission. Check an item only after verifying it in your copy of the project. The presence of code alone does not establish that a live model audit works or meets a detection score.

Recorded development checks and the actual remaining work are in
[WORK_STATUS.md](../WORK_STATUS.md) and [VALIDATION.md](VALIDATION.md).
Follow [PUBLISHING.md](PUBLISHING.md) for the Git/GitHub commands after the real sample is reviewed.

## Required implementation

- [ ] `python agent.py --repo https://github.com/owner/repository --output report.json` runs unattended.
- [ ] Public GitHub URL validation and temporary repository access work.
- [ ] All four required tools are present: `list_files`, `read_file`, `search_code`, and `git_log`.
- [ ] The explicit Python loop lets the model choose follow-up tools from observations.
- [ ] The only model dependency is a basic provider SDK; no prohibited orchestration framework is used.
- [ ] Prompts cover hygiene, dependencies, code quality, testing, CI/CD, security, configuration, collaboration, and build/release practices.
- [ ] Findings allow valid alternatives and repository-specific applicability.
- [ ] The JSON has the exact required top-level structure and mandatory finding fields.
- [ ] File and line references are supported by inspected evidence.
- [ ] Duplicate findings are handled and severity values are constrained.
- [ ] Target repository code is never executed and the remote repository is never modified.
- [ ] Tool output, reports, traces, and error messages are checked for leaked secrets.
- [ ] Invalid URLs, missing files, bad tool arguments, clone errors, API failures, and exhausted budgets have controlled outcomes.
- [ ] Fatal failures return a nonzero process exit code.
- [ ] Temporary resources are cleaned up after success and failure.

## Rubric mapping

| Grading component | Weight | Where to inspect | Evidence you should present |
|---|---:|---|---|
| Architecture and dynamic tool selection | 20% | `agent_loop.py`, `llm_client.py`, tool definitions | A genuine trace showing relevant follow-up inspection |
| Tool implementation | 15% | `tools.py`, `repository.py`, tool tests | Numbered file reads, bounded search/history, useful error results |
| Detection precision and recall | 30% | Auditing instructions, controlled evaluation notes, real outputs | Reviewed flawed and healthy cases, known misses and false positives |
| Evidence, severity, recommendations | 15% | `reporting.py`, real report | Every finding supported and severity justified |
| Reliability and safety | 10% | CLI/repository lifecycle, dispatch validation, redaction, error tests | Controlled failure behavior and no target code execution |
| JSON, tests, documentation | 10% | Report validation, `tests/`, README and guides | Valid JSON, passing checks, reproducible setup instructions |

Unit tests and a clean linter result do not establish the 30% detection component. That requires reviewing actual model output against known expectations.

## Run locally

- [ ] Install Git and Python; create the virtual environment.
- [ ] Install `requirements-dev.txt`.
- [ ] Use `requirements-dev-lock.txt` instead if you want the exact recorded development dependency versions.
- [ ] Run `python -m pytest -q` using the virtual environment.
- [ ] Run `python -m ruff check .` using the virtual environment.
- [ ] Run `python -m build` using the virtual environment.
- [ ] Read `docs/LEARNING_GUIDE.md` and understand the four tools and loop.

## Requires your API account or manual review

- [ ] Follow `docs/API_SETUP.md` and configure one provider with its matching `GEMINI_API_KEY`, `GROQ_API_KEY`, or `OPENAI_API_KEY` in `.env` without sharing or committing it.
- [ ] Confirm the selected model supports tools and is available on your account; review free quotas and any enabled billing before a live run.
- [ ] Run `python scripts/check_setup.py` for local prerequisites and hidden key-presence checks.
- [ ] Run `python scripts/check_setup.py --live` for one small real tool-call check; this uses account quota and does not audit a repository.
- [ ] Run a real audit and generate an authentic `sample_report.json`.
- [ ] Save its companion `sample_trace.jsonl` to demonstrate dynamic tool use.
- [ ] Verify every reported file, line, description, severity, and recommendation.
- [ ] Check both artifacts for sensitive content before publishing.
- [ ] Evaluate representative flawed and healthy repositories and record expected versus reported findings.
- [ ] Follow `docs/EVALUATION.md` to audit the supplied fixtures without exposing their separate expectation files.
- [ ] Confirm no empty report is described as proof that a repository has no problems.
- [ ] Be able to explain a real tool sequence and a limitation during your demonstration.
- [ ] Run `python scripts/verify_submission.py` after saving the real sample; resolve missing files and structural errors. This check does not prove authenticity or finding accuracy.

The project does not include an invented `sample_report.json`. If no valid API credential is available during development, generating and reviewing this required artifact remains a submission prerequisite.

## Public repository submission

- [ ] Create or choose your public GitHub repository.
- [ ] Set your own Git author identity if necessary.
- [ ] Review `git status` and the files to be committed; keep `.env`, virtual environments, caches, and unreviewed reports out.
- [ ] Commit the implementation, tests, configuration template, documentation, and reviewed authentic sample report.
- [ ] Push to GitHub and inspect the rendered README and repository contents.
- [ ] Confirm the GitHub Actions checks pass.
- [ ] Verify the public repository is accessible while signed out.
- [ ] Follow your course's attribution and academic integrity rules.
- [ ] Submit the public repository URL as instructed by the assignment.

An assistant can prepare code and documentation and run local checks. It cannot supply your personal API credentials, make an evidence review on your behalf meaningful for your viva, or guarantee a hidden-test detection score. Account configuration, final artifact review, and submitting the repository URL need your participation.
