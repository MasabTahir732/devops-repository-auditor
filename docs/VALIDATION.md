# Validation record

Validated on **24 October 2026**, using Windows, Python 3.14.0 and Git 2.45.1.
The exact installed versions are recorded in the runtime and development lock files.

| Check | Observed result |
|---|---|
| Initial `python -m pytest -q` | **182 passed** in 47.23 seconds on 24 October |
| Latest full `python -m pytest -q` | **198 passed** in 59.40 seconds on 25 October |
| `python -m ruff check .` | Passed |
| `python -m ruff format --check .` | Passed after formatting the final regression tests |
| Final redaction regression subset | 20 passed after that formatting change |
| `python -m pip check` | No broken requirements found |
| `python -m build --no-isolation` | Source archive and wheel built |
| Wheel installation | Installed without dependencies into a clean temporary target; isolated CLI import/help passed using the verified runtime environment |
| Source archive inspection | Included evaluation scripts and fixtures; excluded real `.env` |
| Public repository access | Cloned `https://github.com/pypa/sampleproject` bare; listed 12 tracked files, read README, returned three commit records |
| Target execution | No target dependencies installed, scripts run, tests run, or checkout performed |
| Temporary clone cleanup | Confirmed removed after inspection |
| `.env` ignore rule | `git check-ignore .env` returned `.env` |
| Public project publication | Six component commits pushed to `MasabTahir732/devops-repository-auditor` |
| Hosted CI | All four Linux/Windows and Python 3.11/3.14 jobs passed for implementation commit `845ab1f`; [run 40117376441](https://github.com/MasabTahir732/devops-repository-auditor/actions/runs/40117376441) |

Tests cover real local Git objects, symlink/submodule exclusion, empty repositories,
timeouts, pagination, search limits, snapshot consistency, malformed requests,
evidence validation, redaction, evaluator metrics, submission checks and CLI wiring.
Provider tests use the actual SDK with an in-memory HTTP transport to exercise request
serialization and errors for Gemini, Groq and OpenAI. They make no network model calls.

## Expected incomplete checks

The initial checks on 24 October reported a missing API key. On 25 October, a local
Gemini key was configured and model-list access succeeded without exposing the key.
Actual generation requests returned HTTP 403 with Google's message:
"Your project has been denied access. Please contact support."
Model listing does not prove inference eligibility, as described in the
[Gemini troubleshooting guide](https://ai.google.dev/gemini-api/docs/troubleshooting).
Gemini project access remains restricted. Groq was subsequently configured and
passed a real API/tool-call check. A real three-turn Groq audit of the small
`octocat/Hello-World` repository completed and produced the authentic submission
sample and trace. See [LIVE_EVALUATION.md](LIVE_EVALUATION.md) for scope, earlier
failed attempts, the false-positive review, and remaining accuracy work.

These remain unverified:

- Completion and accuracy on larger repositories under the selected free-tier limits.
- Detection precision and recall from real model outputs, including false positives on healthy repositories.
- Course submission of the public GitHub URL.

The authored fixture expectations are development examples, not instructor hidden answers.
Passing application tests does not establish hidden-test accuracy or guarantee a grade.
