# Validation record

Validated on **24 October 2026**, using Windows, Python 3.14.0 and Git 2.45.1.
The exact installed versions are recorded in the runtime and development lock files.

| Check | Observed result |
|---|---|
| `python -m pytest -q` | **182 passed** in 47.23 seconds |
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

Tests cover real local Git objects, symlink/submodule exclusion, empty repositories,
timeouts, pagination, search limits, snapshot consistency, malformed requests,
evidence validation, redaction, evaluator metrics, submission checks and CLI wiring.
Provider tests use the actual SDK with an in-memory HTTP transport to exercise request
serialization and errors for Gemini, Groq and OpenAI. They make no network model calls.

## Expected incomplete checks

The local setup checker reports a missing `GEMINI_API_KEY` because no personal API
credential is configured. The submission checker reports one required missing file:
`sample_report.json`. Both return a useful nonzero result rather than inventing output.

These remain unverified:

- Authentication, quota, model access and an actual model/tool audit using the user's API account.
- The required authentic sample report and companion tool trace.
- Detection precision and recall from real model outputs, including false positives on healthy repositories.
- Hosted GitHub Actions on its Linux/Windows and Python 3.11/3.14 matrix.
- Public GitHub publication and course submission.

The authored fixture expectations are development examples, not instructor hidden answers.
Passing application tests does not establish hidden-test accuracy or guarantee a grade.
