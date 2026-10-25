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

## What still needs evaluation

Run the controlled healthy, obvious-defect and subtle-defect cases described in
[EVALUATION.md](EVALUATION.md), review each finding against source, and compute
the location/category/keyword baseline metrics. Record false positives and misses
without adjusting expected answers merely to improve the score.

The application tests, passing hosted CI, and authentic smoke report establish
engineering and basic end-to-end behavior. They do not establish a hidden-repository
precision/recall score or predict an assignment grade. The instructor's hidden
repositories remain unavailable.
