# Understand and demonstrate your agent

This guide assumes you are new to agentic AI. Read the code alongside each step and run the project yourself before your demonstration.

## 1. The basic idea

A normal function receives input, runs its written logic, and returns output. An LLM can choose the next function based on what it has observed. The combination of a goal, model, tools, observations, and repeated decisions is the agent in this assignment.

Our goal is to find supported DevOps problems in a public repository. Our model is accessed through an API. Its four tools expose a limited view of the repository. The Python loop connects these pieces and decides when to stop accepting requests.

The model does not execute a Python function by itself. It proposes a function name and JSON arguments. Our program checks them, executes an allowed function, and sends back the result. Read the [official OpenAI function-calling guide](https://developers.openai.com/api/docs/guides/function-calling) for the provider's description of that interaction.

## 2. Learn the building blocks

| Term | Meaning in this project |
|---|---|
| LLM | A language model that interprets instructions and observations |
| API | The interface our Python process uses to send a request to a hosted model |
| SDK | A basic Python library that helps call that API |
| Prompt | Instructions and context supplied to the model |
| Tool | An ordinary Python function with a declared input schema |
| Observation | A tool's result returned to the model |
| Context | The conversation items available for the next model decision |
| Agent loop | The repeated model request, tool execution, and observation cycle |
| JSON schema | A contract describing required fields and valid value types |
| Trace | A log of actions and results useful for checking the run |
| Bare clone | A Git object database without a checked-out working tree |
| Virtual environment | A project-specific Python interpreter and package directory |

There is no model training step. We supply instructions and repository observations to an existing model.

## Which API do we need?

Only one hosted model API is needed. Our Python code sends it the current observations and tool definitions. Its response selects the next function to call or submits findings. Gemini is the default provider, Groq is an alternative with a free plan, and OpenAI is an optional provider. You configure one provider and one matching key, not all three. [API_SETUP.md](API_SETUP.md) gives the account links, free-tier limits to check, and exact settings.

The installed package is named `openai`, but Gemini and Groq document compatible endpoints that this basic SDK can call. Using that library does not mean requests to Gemini or Groq are billed by OpenAI. The provider selected in `.env` receives the requests. Our application supplies the agent loop; the SDK supplies HTTP and API conveniences.

Git downloads the public repository without a GitHub API token. We do not need a search API, vector database, or agent framework service for this assignment.

## 3. Follow one complete run

Read the following files in order:

1. `agent.py`: identify where command arguments and environment settings become configuration.
2. `repository.py`: find URL checks, Git clone construction, timeout handling, and cleanup.
3. `tools.py`: follow one file from Git's tracked-file list to numbered text returned by `read_file`.
4. `llm_client.py`: identify how tool definitions and the current conversation are sent to the API.
5. `agent_loop.py`: locate the loop, tool dispatch, error observations, stop conditions, and trace writes.
6. `reporting.py`: identify required report fields, valid severities, evidence checks, and duplicate handling.
7. `tests/`: read examples that exercise valid behavior and rejected input.

Do not try to memorize every line. Be able to explain each file's responsibility and follow a request across these boundaries.

## 4. Observe dynamic tool selection

This is a hypothetical teaching sequence, not a recorded run:

```text
list_files()
  -> sees pyproject.toml, tests/, and .github/workflows/check.yml
read_file(".github/workflows/check.yml")
  -> sees a command calling a named test tool
read_file("pyproject.toml")
  -> checks whether the declared dependencies support that command
search_code("the-observed-tool-name")
  -> checks alternative declarations before concluding anything
```

A different repository should lead to different investigations. A JavaScript repository might lead the model toward `package.json` and its lockfile instead. The loop must allow this choice; it should not always run the same four functions with fixed arguments and call the result agentic.

After a real audit, open its trace and find an actual example of an observation leading to a relevant follow-up call. If that relationship is unclear, inspect whether the prompt, tool descriptions, or step budget needs improvement. A trace shows chosen actions and returned observations; it does not expose hidden reasoning.

## 5. Understand evidence and false positives

Suppose a workflow runs a test command. That alone does not prove the tests are absent or the command fails. You need to investigate project configuration, test locations, and alternative dependency declarations.

Similarly:

- Missing `requirements.txt` is not necessarily a defect when another supported dependency format is present.
- A documentation-only repository need not have a package build pipeline.
- An example placeholder is different from a real hard-coded credential.
- A shallow or bounded history view cannot establish every historical collaboration practice.
- A tool result marked as incomplete cannot prove that a file is missing.
- Seeing CI configuration does not prove the hosted workflow passed.

A good finding names a concrete problem, cites inspected facts, explains impact, and recommends a correction. Its severity should match that impact. Do not label every missing convenience file as critical.

## 6. Run the checks and explain their limits

From PowerShell in the project folder:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m build
```

`pytest` checks expected behavior with controlled inputs. Scripted model responses let tests verify the loop without paying for an API or depending on variable model output. Those tests are not evidence that a real model detects every defect. `ruff` checks code conventions and common mistakes. `build` verifies that the project can be packaged.

## 7. Perform a real audit

After following [API setup](API_SETUP.md) and setting a valid provider key in `.env`, substitute an actual public repository URL:

```powershell
.\.venv\Scripts\python.exe agent.py --repo https://github.com/owner/repository --output sample_report.json --trace sample_trace.jsonl
```

For your demonstration, choose a manageable repository that you understand. Record its URL and inspected commit where available in the trace so you can discuss what the agent saw. Keep the report's assignment-mandated schema unchanged.

Open the JSON in your editor and verify every finding against the referenced source at that commit. Open the trace and identify the calls that supplied that evidence. Review both artifacts for sensitive content before committing them. Never manually invent findings to fill the sample report.

## 8. Evaluate precision and recall

Use at least a small, reviewed set of intentionally flawed and healthy examples. Decide the expected findings before looking at the agent's output. Record expectations and outcomes in a separate evaluation note so they are distinguishable from the generated report.

| Term | Meaning |
|---|---|
| True positive | A reported finding that your evidence review confirms |
| False positive | A reported finding that is unsupported or incorrect |
| False negative | A known, in-scope defect the audit missed |
| Precision | True positives divided by all reported findings |
| Recall | True positives divided by all known expected defects |

If a denominator is zero, mark the metric as undefined for that sample rather than inventing a percentage. A healthy example is valuable because unsupported allegations reduce precision. Run the same comparison after a meaningful prompt or tool change; do not claim benchmark accuracy from unit tests.

Start with the provided fixtures and [evaluation procedure](EVALUATION.md). After obtaining a real `reports/healthy.json`, for example:

```powershell
.\.venv\Scripts\python.exe scripts/evaluate.py --expected tests/fixtures/expectations/healthy.json --actual reports/healthy.json --output reports/healthy.metrics.json
```

The evaluator compares categories, paths, line tolerances, and optional keywords with one-to-one matching. Review its matches yourself: two statements can share a keyword and still differ in meaning.

## 9. Questions you should be ready to answer

**What makes your program an agent?** The model chooses subsequent inspection actions from observed tool results, and Python repeatedly carries them out until completion or a defined limit.

**Why write the loop explicitly?** It satisfies the assignment's framework constraint and makes dispatch, evidence, budgets, and errors visible in our own code.

**What does the SDK do?** It sends requests to the hosted model. Our code still owns tool execution, orchestration, and report validation.

**Why use four tools?** They expose the required repository structure, file content, code search, and history information through a small read-only interface.

**Why a bare clone?** We need Git objects and history for inspection without checking out or executing target files. Temporary storage is removed after the run.

**Can a repository tell the model to ignore its instructions?** Repository text is untrusted input. Instructions tell the model to treat it as data, and Python only permits the four inspection tools. These measures limit actions but cannot guarantee that the model never draws a wrong conclusion.

**How do you avoid hallucinated findings?** Require evidence, check file/line references against actual observations, reject malformed reports, remove duplicate findings, and evaluate output manually. These controls reduce errors; they do not make semantic accuracy automatic.

**Why not run target tests?** The required audit can inspect tracked configuration and code. Running another project's scripts introduces unnecessary execution and environment requirements. Reports therefore make no claim that target tests were run.

**Why does the project use an API?** The API supplies the existing language model that selects inspection tools and interprets observations. The four repository tools themselves run locally in Python.

**Do we need paid API access?** The code supports Gemini and Groq free options, subject to their current model access and account quotas. A free plan can still reject a long or frequent request. OpenAI access is optional. Review the provider console before a real audit.

**What could improve next?** Better controlled evaluation cases, richer bounded history views, and more efficient context handling for large repositories. Explain the present limitations before proposing extensions.

## 10. Your ownership before submission

Run the code yourself, read the core loop and tool implementations, generate a real report, and check its evidence. Follow your institution's rules on permitted AI assistance and attribution. Be able to explain the submitted implementation and any limitations with your own examples.
