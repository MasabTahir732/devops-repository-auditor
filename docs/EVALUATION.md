# Evaluate an actual audit

The fixtures are independently authored miniature repositories, not actual LLM
outputs. Their expectations live outside the fixture repository roots so the
auditor does not simply read the answer key. No API accuracy measurement has
been performed merely by creating these files or running unit tests.

| Fixture directory | Baseline findings | Purpose |
| --- | ---: | --- |
| `tests/fixtures/healthy` | 0 | Accept valid pyproject-based dependency management and a small library's limited scope. |
| `tests/fixtures/obvious-defects` | 6 | Unpinned dependency, production debug, machine-specific path, nonblocking tests, moving container image, and development server deployment. |
| `tests/fixtures/subtle-defects` | 3 | Untrusted PR-head code in a privileged workflow, missing test extra, and incorrect string-to-boolean parsing. |

The fixtures contain no real or imitation API credentials. The deliberately
flawed code is inspection material; the auditing process must not execute it.
The healthy library intentionally has no requirements.txt, Dockerfile, hosted
service, or release workflow. These absences should not automatically become
findings. A lockfile is not automatically required for a dependency-free library.

## 1. Prepare separate public evaluation repositories

For assignment evidence, audit actual public GitHub URLs with the normal agent.
Create three empty public repositories in your own GitHub account, for example:

* `audit-fixture-healthy`
* `audit-fixture-obvious-defects`
* `audit-fixture-subtle-defects`

For each empty repository, disable GitHub Actions in Settings -> Actions -> General
**before the first push** of fixture workflows. Confirm that Actions are disabled
on the GitHub repository page before running the commands below. The workflows intentionally describe unsafe
or failing configurations; they do not need to run for a source audit. A source
finding is not proof that a disabled workflow was exploited. Never place secrets
in these repositories or enable the flawed workflows on a valuable repository.

Copy only the relevant fixture directory into a separate working directory.
Do not publish the outer `expectations` directory inside the audited repository.
Example PowerShell commands, run from the auditor project root:

```powershell
$fixtureSource = (Resolve-Path '.\tests\fixtures\healthy').Path
$fixtureCopy = Join-Path (Split-Path (Get-Location).Path -Parent) 'audit-fixture-healthy'
New-Item -ItemType Directory -Path $fixtureCopy
Get-ChildItem -LiteralPath $fixtureSource -Force | Copy-Item -Destination $fixtureCopy -Recurse -Force
Set-Location $fixtureCopy
git init
git add .
git commit -m "Add independent healthy audit fixture"
git branch -M main
git remote add origin https://github.com/YOUR-USERNAME/audit-fixture-healthy.git
git push -u origin main
```

Replace YOUR-USERNAME and choose the corresponding source/destination names
for the other two fixtures. These commands are instructions for the user; the
project has not created or published any remote repository. Git may request your
identity or GitHub authentication. Never paste credentials into terminal commands
or the report. A single initial commit is sufficient for these source checks;
these miniature fixtures are not evidence of realistic collaboration history.

## 2. Run genuine model audits

Return to the `devops-auditor` project and activate its virtual environment.
Configure the supported model provider and credentials according to README.md.
Use your own public fixture URL and save the actual report and agent trace:

```powershell
python agent.py --repo https://github.com/YOUR-USERNAME/audit-fixture-healthy --output reports/healthy.json --trace reports/healthy.trace.jsonl
python agent.py --repo https://github.com/YOUR-USERNAME/audit-fixture-obvious-defects --output reports/obvious-defects.json --trace reports/obvious-defects.trace.jsonl
python agent.py --repo https://github.com/YOUR-USERNAME/audit-fixture-subtle-defects --output reports/subtle-defects.json --trace reports/subtle-defects.trace.jsonl
```

Record the provider, exact model, run date, fixture commit SHA, model settings,
and any tool or budget limit for each run. Verify the audit completed successfully
before computing metrics. An error or an incomplete investigation is not a
healthy repository result. Preserve the trace showing tool decisions that react
to earlier observations. Redact secrets from any shared artifacts.

Do not relabel fabricated JSON, mocked SDK responses, or scripted unit-test
outputs as real audits. A real sample_report.json must come from an actual
completed audit. Creating fixtures and passing tests cannot establish detection
accuracy or a real model's ability to choose tools.

## 3. Compute transparent baseline metrics

From the project root:

```powershell
python scripts/evaluate.py --expected tests/fixtures/expectations/healthy.json --actual reports/healthy.json --output reports/healthy.metrics.json
python scripts/evaluate.py --expected tests/fixtures/expectations/obvious-defects.json --actual reports/obvious-defects.json --output reports/obvious-defects.metrics.json
python scripts/evaluate.py --expected tests/fixtures/expectations/subtle-defects.json --actual reports/subtle-defects.json --output reports/subtle-defects.metrics.json
```

The script uses only the Python standard library. It reads the saved files;
it does not call a model or execute fixture code. Exit status 0 means valid
evaluation inputs were processed, not that a particular accuracy threshold passed.
Invalid input returns status 2. It validates finding fields for comparison, not
every application-specific report metadata field or the truth of the evidence.
Severity must be one of critical, high, medium, or low, and evidence must be
nonempty. A finding with file=null must also have line=null. Metrics output is
refused if it would overwrite either input file.

Each expected item has:

```json
{
  "id": "INDEPENDENT-EXPECTATION-ID",
  "category": "ci",
  "file": ".github/workflows/ci.yml",
  "line": 15,
  "line_tolerance": 1,
  "keywords": ["continue-on-error", "failure"]
}
```

An expected item matches an actual finding when:

1. Category matches after case/punctuation normalization and documented common
   aliases such as CI/CD -> ci.
2. Repository-relative file path matches after normalizing slashes and `./`.
3. If an expected line is specified, the actual positive line is within the
   stated tolerance. An expected null line accepts any valid line at that file.
4. If keywords are specified, at least one appears, case-insensitively, in the
   actual description, evidence, or recommendation.
5. If optional `rule_ids` are specified, the actual rule_id belongs to that list.
   The supplied expectations omit this restriction because independently
   generated rule IDs need not use the same numbering.

Each expected item and each actual finding can match only once. Maximum
bipartite matching prevents order-sensitive undercounting. Duplicate findings
therefore count as unmatched extras, not extra true positives. The file paths
must be relative; missing-file findings may use a null line. A null expected
file matches only a null actual file, not every repository file.

The script reports TP, FP, FN, precision, recall, F1, matched indices, missed
expectation IDs, and unmatched actual indices. It uses null for an undefined
ratio: a healthy empty report has zero FP and FN, but undefined precision and
recall. Sum TP/FP/FN across all runs before computing micro-averaged metrics;
do not average undefined values as zeros or ones.

## 4. Review the mechanical comparison

Location and substring matching are reproducible heuristics, not semantic
judgment. A correct finding may cite a nearby line or choose a different
reasonable category. A misleading finding might contain a matching keyword.
Review every missed expectation and unmatched actual finding against the
source. Preserve raw scores and record any adjudication with a reason.

The baselines are an independently authored starting point, not an assertion
that no other defensible findings exist. Do not silently rewrite expectations
until the model scores well. If an additional finding is valid, document it and
version the expectation set before another comparison. Findings about inactive
deployment configuration should say that they concern the declared source
configuration, rather than claim that an actual deployed service is vulnerable.

Check whether the model explains the full subtle-workflow chain: the
pull_request_target event provides the privileged context, contents:write grants
token privileges, checkout selects untrusted PR-head code, and pip installation
can execute that code. Also check that missing test dependencies are based on
reading both the CI installation command and pyproject's dev extra.

For the final assignment, include the genuine sample report, actual traces,
recorded configuration, metric artifacts, and a short discussion of misses,
false positives, and fixture limitations. Passing local scripted tests alone
is evidence of implementation behavior, not real-model detection accuracy.
