# Publish the finished assignment

The public project repository is now [MasabTahir732/devops-repository-auditor](https://github.com/MasabTahir732/devops-repository-auditor).
Use this repository for subsequent changes. The instructions below also describe
the setup process for a fresh copy; do not create a duplicate repository or remote.

First configure your LLM key, run the real audit, review the report and trace,
and run `python scripts/verify_submission.py`. See [API setup](API_SETUP.md).
The required `sample_report.json` must come from that real run.

## Create your GitHub repository

Create an **empty public** GitHub repository in your account. For example, name
it `devops-repository-auditor`. Do not initialize a second README or .gitignore
there; this project already has those files. The main project's root CI is safe
to enable; defective workflows under `tests/fixtures/` are inert nested data.

For publishing those fixtures as separate repositories, follow the different
Actions-disable procedure in [EVALUATION.md](EVALUATION.md).

## Review and commit your files

The existing workspace already has a local Git repository on branch `main`.
If working from an ordinary folder elsewhere, run `git init --initial-branch=main`
once. Then, from the project folder:

```powershell
git status --short
git check-ignore .env
```

The second command should print `.env`. Check that the files you intend to
publish contain no credentials. The local virtual environment, caches, build
artifacts, and `.env` are ignored. The reviewed sample report and
`sample_trace.jsonl` can be committed.

If Git asks for an author identity, set your actual identity for this repository:

```powershell
git config user.name "YOUR NAME"
git config user.email "YOUR GITHUB EMAIL OR NOREPLY ADDRESS"
```

After reviewing the files:

```powershell
git add .
git diff --cached --stat
git commit -m "Implement DevOps repository auditing agent"
git remote add origin https://github.com/YOUR_USERNAME/devops-repository-auditor.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your account name. If `origin` already exists,
inspect it with `git remote -v` and use your intended repository URL. Follow
GitHub's authentication prompt locally; do not put a token into the remote URL.

## Check the hosted result

1. Open your public repository and verify that `agent.py`, `tools.py`, tests,
   `.env.example`, documentation, and the authentic sample report are visible.
2. Open **Actions** and wait for the validation jobs to pass. CI runs offline
   application tests and packaging; it needs no provider key or Actions secret.
3. Confirm the repository page is accessible when signed out.
4. Submit the public repository URL through your course's submission channel.

Your API account setup, final report review, GitHub login, and course submission
require your participation. Local tests do not establish a hidden-test score.
