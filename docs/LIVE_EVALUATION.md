# Live validation and remaining accuracy work

Date: **25 October 2026**. Provider: **Groq**. Successful sample model:
`openai/gpt-oss-20b`. No billing settings or account plan were changed.

## Authentic submission sample

The required `sample_report.json` and companion `sample_trace.jsonl` came from a
completed real model/tool run against `https://github.com/octocat/Hello-World`.
The successful run used three model turns: discover files, read the actual README,
and submit the report. The report contains an empty violations array. This small
repository contains only a README with `Hello World!`; it does not establish an
application, generated artifacts, or operations that require build/test/deployment
instructions. No demonstrated DevOps violation was found in that scope.

Reproduce the sample with your own configured Groq key:

```powershell
python agent.py --provider groq --model openai/gpt-oss-20b --repo https://github.com/octocat/Hello-World --output sample_report.json --trace sample_trace.jsonl --max-steps 12
python scripts/verify_submission.py
```

The sample was not manually edited to remove findings. An earlier real run
reported two low-severity hygiene findings about the missing .gitignore and short
README. Review found those claims unsupported for a content-only demonstration
repository. The general applicability policy was strengthened, and a fresh model
run produced the committed report. The earlier output is retained locally under
the ignored `reports/hello_world_initial.*` files.

This is a development case used to improve the prompt, not a held-out accuracy
test. Zero findings on this case is not evidence of high recall. With zero expected
defects and zero reported defects, precision and recall are undefined rather than
automatically 100%.

## Larger live attempts and fixes

Several real attempts against PyPA's `sampleproject` selected inspection tools and
read real repository content but did not complete. They encountered HTTP 413,
rate/quota errors, or HTTP 400. Their traces remain locally under the ignored
`reports/` directory. They are not represented as successful audits.

The application now uses compact numbered source, 100-line read pagination,
bounded recent context, explicit compaction notices, model-written evidence
checkpoints, bounded output-budget reduction, and bounded repair retries for
documented Groq tool-generation failures. The full structured evidence remains in
the trace. Offline regressions cover these behaviors, but the larger repository
has not yet been successfully re-evaluated with every final fix.

## Quiz-generator attempts

The requested application repository was
`MasabTahir732/AI-Intelligent-Reading-Comprehension-and-Quiz-Generator`.
A 20-turn `openai/gpt-oss-20b` run inspected source but exhausted its budget:
the model kept choosing inspection tools during finalization. The controller
blocked those calls; no completed report was written. A subsequent 12-turn run
with a provider-enforced named report tool reached finalization but received
HTTP 400. Its trace is retained locally as
`reports/quiz-generator-retry.trace.jsonl`. Neither attempt is a successful audit.

An alternative `llama-3.3-70b-versatile` request returned HTTP 404. The account's
live model list did not include that model. A subsequent run with the listed
`openai/gpt-oss-120b` model completed four inspection turns, then stopped at a
rate/quota error. Its trace is retained locally as
`reports/quiz-generator-120b.trace.jsonl`. No quiz-generator report was produced,
and no failed attempt replaced the authentic Hello-World submission sample.
Further retries were stopped to avoid repeatedly consuming the account's quota.

The separate [source review](QUIZ_GENERATOR_REVIEW.md) records concrete observations
without presenting manually authored findings as model output. The provider wire
regressions and full 204-test suite pass, but passing offline tests does not
establish that every hosted model will complete this investigation.

## What still needs evaluation

Run the controlled healthy, obvious-defect and subtle-defect cases described in
[EVALUATION.md](EVALUATION.md), review each finding against source, and compute
the location/category/keyword baseline metrics. Record false positives and misses
without adjusting expected answers merely to improve the score.

The application tests, passing hosted CI, and authentic smoke report establish
engineering and basic end-to-end behavior. They do not establish a hidden-repository
precision/recall score or predict an assignment grade. The instructor's hidden
repositories remain unavailable.
