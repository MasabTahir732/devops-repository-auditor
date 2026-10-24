"""Check submission files and saved report structure without calling a model.

This cannot establish that a saved report is an authentic LLM run, that findings
are true, or that the agent will perform well on hidden repositories.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path, PurePosixPath
from typing import Any

# Import only the trusted auditor modules beside this script. --root points to
# files to inspect; it must never cause us to import or execute candidate code.
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from reporting import ReportError, validate_report  # noqa: E402
from repository import RepositoryError, normalize_repo_url  # noqa: E402
from safety import redact  # noqa: E402

REQUIRED_FILES = (
    "agent.py",
    "tools.py",
    "agent_loop.py",
    "llm_client.py",
    "repository.py",
    "reporting.py",
    ".env.example",
    "README.md",
)
INSPECTION_TOOLS = {"list_files", "read_file", "search_code", "git_log"}
LIMITATION = (
    "Structure check only: this cannot prove authentic LLM execution, finding accuracy, "
    "or performance on hidden repositories. Review the real run and its evidence manually."
)


def _reject_constant(_value: str):
    raise ValueError("Non-finite JSON constants are not valid submission data.")


def _read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8-sig"), parse_constant=_reject_constant)


def _check_trace(path: Path, report: dict) -> list[str]:
    errors = []
    try:
        events = []
        for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
            if not line.strip():
                continue
            item = json.loads(line, parse_constant=_reject_constant)
            if not isinstance(item, dict) or not isinstance(item.get("event"), str):
                raise ValueError(f"Trace line {number} must be an event object.")
            events.append(item)
    except (OSError, UnicodeError, ValueError):
        return ["sample_trace.jsonl is unreadable or contains invalid JSONL event objects."]
    reports = [(i, item) for i, item in enumerate(events) if item["event"] == "report"]
    if not reports or reports[-1][1].get("report") != report:
        errors.append("The last report event in sample_trace.jsonl must match sample_report.json.")
    elif any(item["event"] == "fatal_error" for item in events[reports[-1][0] + 1 :]):
        errors.append("sample_trace.jsonl records a fatal error after its report event.")
    if not any(item["event"] == "model_turn" for item in events):
        errors.append("sample_trace.jsonl must contain a model_turn event.")
    successful = [
        item
        for item in events
        if item["event"] == "tool_result"
        and item.get("tool") in INSPECTION_TOOLS
        and isinstance(item.get("result"), dict)
        and item["result"].get("ok") is True
    ]
    if len(successful) < 2:
        errors.append(
            "sample_trace.jsonl should show at least two successful inspection tool results."
        )
    if redact(events) != events:
        errors.append(
            "sample_trace.jsonl contains likely credential values; redact before submission."
        )
    return errors


def _tracked_environment_files(root: Path) -> tuple[list[str], list[str]]:
    try:
        completed = subprocess.run(
            [
                "git",
                "-c",
                "core.fsmonitor=false",
                "-c",
                "core.hooksPath=" + os.devnull,
                "-C",
                str(root),
                "ls-files",
                "-z",
                "--cached",
                "--",
                ".",
            ],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            check=False,
            timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except (OSError, subprocess.TimeoutExpired):
        return [], ["Git was unavailable; the tracked environment-file check was skipped."]
    if completed.returncode:
        return [], ["Git metadata was unavailable; the tracked environment-file check was skipped."]
    paths = completed.stdout.decode("utf-8", errors="replace").split("\0")
    forbidden = [
        path
        for path in paths
        if PurePosixPath(path).name == ".env"
        or (
            PurePosixPath(path).name.startswith(".env.")
            and PurePosixPath(path).name != ".env.example"
        )
    ]
    # We inspect only tracked filenames, never .env file contents.
    if forbidden:
        return [
            "Real/local environment files are tracked by Git. Untrack .env and .env.* (keep .env.example)."
        ], []
    return [], []


def check_submission(root: Path) -> tuple[list[str], list[str]]:
    root = Path(root).resolve()
    errors, warnings = [], []
    if not root.is_dir():
        return ["Submission root must be an existing project directory."], []
    for name in REQUIRED_FILES:
        candidate = root / name
        if not candidate.is_file() or not candidate.stat().st_size:
            errors.append(f"Missing or empty required file: {name}")
    if not any(
        (root / name).is_file() and (root / name).stat().st_size
        for name in ("requirements.txt", "pyproject.toml")
    ):
        errors.append("Add installable dependencies in requirements.txt or pyproject.toml.")
    tests = root / "tests"
    if not tests.is_dir() or not any(tests.glob("test_*.py")):
        errors.append("Add tests/ with automated test_*.py files.")
    sample = root / "sample_report.json"
    report = None
    if not sample.is_file():
        errors.append(
            "Missing sample_report.json. Configure your own API key and run "
            "python agent.py --repo <public-GitHub-URL> --output sample_report.json "
            "--trace sample_trace.jsonl. Preserve actual output; do not invent a sample."
        )
    else:
        try:
            report = _read_json(sample)
            if not isinstance(report, dict):
                raise ReportError("Report must be an object.")
            canonical = normalize_repo_url(report.get("repository"))
            validate_report(report, canonical)
            if redact(report) != report:
                errors.append(
                    "sample_report.json contains likely credentials; redact before submission."
                )
        except (OSError, UnicodeError, ValueError, RepositoryError):
            errors.append(
                "sample_report.json is unreadable or violates the required JSON report contract."
            )
            report = None
    trace = root / "sample_trace.jsonl"
    if not trace.is_file():
        warnings.append(
            "Optional sample_trace.jsonl is absent; retaining a real tool trace helps review agent behavior."
        )
    elif report is not None:
        errors.extend(_check_trace(trace, report))
    git_errors, git_warnings = _tracked_environment_files(root)
    errors.extend(git_errors)
    warnings.extend(git_warnings)
    return errors, warnings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root", type=Path, default=PROJECT_ROOT, help="Submission project directory"
    )
    args = parser.parse_args(argv)
    try:
        errors, warnings = check_submission(args.root)
    except OSError:
        errors, warnings = (
            ["Cannot access one or more submission files; check filesystem permissions."],
            [],
        )
    print(LIMITATION)
    for message in warnings:
        print(f"WARNING: {message}")
    for message in errors:
        print(f"ERROR: {message}")
    if errors:
        print(f"Submission structure incomplete: {len(errors)} issue(s).")
        return 1
    print("Required submission files and saved report structure passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
