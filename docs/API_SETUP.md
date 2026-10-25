# API setup and free options

You need **one LLM API**, which gives this program access to an existing language model. The model chooses inspection tools, interprets their results, and submits its findings. You do not train or download a model for this project.

The repository tools run locally. Public GitHub repositories are downloaded with Git over HTTPS, so no GitHub API key or personal access token is required. No search API, vector database service, or agent orchestration platform is required.

## Choose a provider

The following options were checked against official documentation on **24 October 2026**. Model availability and quotas can change, and your account console is authoritative for access and limits.

| Provider | Supported project setting | Free option | Account action |
|---|---|---|---|
| Google Gemini | `gemini`, model `gemini-3.8-flash` | Its pricing page lists free input and output for the model's free tier | Create your key in [Google AI Studio](https://aistudio.google.com/api-keys) and check its available quota |
| Groq | `groq`, model `openai/gpt-oss-120b` | Groq offers a free plan with usage limits | Create a key in [Groq Console](https://console.groq.com/keys) and check your model permissions and limits |
| OpenAI | `openai`, model `gpt-4.1-mini` | Do not assume free API credits are available | Use your own API project with model access and sufficient quota or billing |

Gemini's free-tier model pricing and data-use terms are listed on its [pricing page](https://ai.google.dev/gemini-api/docs/pricing). Its [compatibility guide](https://ai.google.dev/gemini-api/docs/openai) documents tool calling through the basic OpenAI SDK. Some other Gemini models have no free tier; do not assume every model name in AI Studio is free.

Groq's [billing FAQ](https://console.groq.com/docs/billing-faqs) describes plan choices, and its [rate-limit guide](https://console.groq.com/docs/rate-limits) explains that your account's limits page supplies exact limits. `openai/gpt-oss-120b` supports local function tools according to [Groq's tool-use guide](https://console.groq.com/docs/tool-use/overview). The `openai/` prefix is part of this model ID; with `LLM_PROVIDER=groq`, requests go to Groq.

Start with Gemini. If your account has no usable free quota, try Groq with its matching configuration. A free plan is limited access, not unlimited execution: one audit may require many model requests and repeatedly send the accumulated observations. A larger repository can exceed request, daily token, or per-request limits even when the account itself is free.

## Configure Gemini

1. Sign in to [Google AI Studio](https://aistudio.google.com/api-keys).
2. Create an API key in your own project and check that the configured model has available free quota. Review billing state before making requests.
3. Open the project `.env` file locally. If it does not exist, copy `.env.example` once.
4. Set these values, replacing the placeholder with your own key:

```dotenv
LLM_PROVIDER=gemini
GEMINI_API_KEY=your-own-key-goes-here
LLM_MODEL=gemini-3.8-flash
AUDIT_MAX_STEPS=40
AUDIT_TIMEOUT=60
AUDIT_CLONE_TIMEOUT=120
```

The Gemini endpoint is `https://generativelanguage.googleapis.com/v1beta/openai/`. This project sets it for you. You do not need to add a base URL or install a second agent SDK.

## Configure Groq instead

Create your key in [Groq Console](https://console.groq.com/keys), then use:

```dotenv
LLM_PROVIDER=groq
GROQ_API_KEY=your-own-key-goes-here
LLM_MODEL=openai/gpt-oss-120b
AUDIT_MAX_STEPS=40
AUDIT_TIMEOUT=60
AUDIT_CLONE_TIMEOUT=120
```

The endpoint is `https://api.groq.com/openai/v1`, as documented in [Groq's compatibility guide](https://console.groq.com/docs/openai). The project supplies it automatically. Check your console's exact model permissions and rate limits before auditing. Do not copy older examples that assume Llama models are available on every free account.

## Configure OpenAI instead

If you already have suitable OpenAI API access, use:

```dotenv
LLM_PROVIDER=openai
OPENAI_API_KEY=your-own-key-goes-here
LLM_MODEL=gpt-4.1-mini
AUDIT_MAX_STEPS=40
AUDIT_TIMEOUT=60
AUDIT_CLONE_TIMEOUT=120
```

This adapter uses the [Responses API function-calling flow](https://developers.openai.com/api/docs/guides/function-calling). It is an optional provider; you do not need an OpenAI account to use the Gemini or Groq adapters. Access to a consumer chat product does not establish that your API project has quota.

## How settings are selected

Provider selection uses `--provider`, then `LLM_PROVIDER`, then `gemini` as the default. Model selection uses `--model`, then `LLM_MODEL`, then the selected provider's variable (`GEMINI_MODEL`, `GROQ_MODEL`, or `OPENAI_MODEL`), then that provider's default model. Existing shell variables take precedence over `.env` because `.env` does not overwrite them.

When switching providers, update `LLM_MODEL` too. Leaving a Gemini model in `LLM_MODEL` while selecting Groq requests a model name that Groq does not host. Alternatively, remove the generic `LLM_MODEL` setting and let the provider default apply.

You can override both values for one command:

```powershell
.\.venv\Scripts\python.exe agent.py --provider groq --model openai/gpt-oss-120b --repo https://github.com/owner/repository --output report.json
```

The corresponding provider key still needs to be configured.

## Check setup before a full audit

From the project folder, run:

```powershell
.\.venv\Scripts\python.exe scripts/check_setup.py
```

This checks local prerequisites, loads the selected settings, and reports whether a key is present without showing it. It does not contact the API. A present key may still be invalid or have no quota.

Then make one small real tool-calling request:

```powershell
.\.venv\Scripts\python.exe scripts/check_setup.py --live
```

The live check verifies a basic model/tool exchange using your account. It consumes provider quota and may be charged if you enabled paid access. It does not download or audit a repository. Both forms accept `--provider` and `--model` overrides.

For this existing workspace only, an installed virtual environment is also available in the parent assignment folder. From `D:\SEM 7\2. MlOps\devops-auditor`, you can replace `.\.venv\Scripts\python.exe` in these commands with `..\.venv\Scripts\python.exe`. A fresh clone should follow the standalone project environment instructions in the README.

## Generate the authentic assignment sample

After configuring your key, run this from the project folder, replacing the URL with a real public repository:

```powershell
.\.venv\Scripts\python.exe agent.py --repo https://github.com/owner/repository --output sample_report.json --trace sample_trace.jsonl
```

The command runs without interactive questions. A successful run writes the required report. A failed API call, invalid target, or exhausted agent budget returns a nonzero exit code. Do not replace that failure with an invented empty report.

Open the report and trace in your editor. Verify the evidence and severity of each finding against the inspected source, then check for sensitive values before publishing. The trace records selected actions and results; it is useful for demonstrating follow-up tool calls.

Check required submission files and the saved sample's structure:

```powershell
.\.venv\Scripts\python.exe scripts/verify_submission.py
```

The checker returns a nonzero result when the required sample is missing. It also checks a companion `sample_trace.jsonl` when present. It does not call the model, authenticate the origin of a report, or establish detection accuracy; those require a real run and evidence review. Use [the evaluation procedure](EVALUATION.md) for flawed and healthy examples, then publish the reviewed project, check hosted CI, and submit your public repository URL through the course channel.

## Errors to resolve

Free-tier audits can pause while bounded SDK retries wait for request/token quota
to reset. The Groq adapter reduces its requested output allowance on HTTP 413,
down to a bounded minimum. The agent also keeps a persistent model-written notebook
and a bounded recent conversation, with explicit notices when older source text
leaves model context. It retains full structured tool results in the trace and can
read exact evidence again. A result that still cannot fit fails explicitly; it is
never replaced by an invented clean report. Read pages contain at most 100 lines.

| Error | Action |
|---|---|
| Missing key | Check that `LLM_PROVIDER` matches the key variable you filled in |
| Authentication failure | Check the key in your local provider console; rotate it if exposed |
| Model not found or forbidden | Confirm current model access in the selected provider and update `LLM_MODEL` |
| Rate or quota limit | Check the account's exact limits and retry window; reduce scope or wait as instructed by the provider |
| Request too large | Start with a smaller repository; waiting does not fix a request that exceeds a per-request limit |
| Network or timeout failure | Check the connection and retry; adjust `--timeout` when appropriate |

Keep `.env` local and never paste a key into chat. The code can be developed and tested with scripted API responses, but a genuine audit and authentic sample report cannot be completed without working provider access. Account creation, any required verification, checking free quotas, and reviewing the final artifacts remain your tasks.
