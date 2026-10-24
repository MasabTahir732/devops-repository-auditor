"""Tests use synthetic artifacts and do not claim authentic model execution."""

import json
import subprocess
from types import SimpleNamespace

import pytest

from scripts import verify_submission as checker


def sample_report():
    return {"repository": "https://github.com/example/project", "violations": []}


def prepare_root(root, *, sample=True):
    for name in checker.REQUIRED_FILES:
        (root / name).write_text("fixture content\n", encoding="utf-8")
    (root / "requirements.txt").write_text("openai>=2,<3\n")
    (root / "tests").mkdir()
    (root / "tests" / "test_example.py").write_text("# Not executed by checker\n")
    if sample:
        (root / "sample_report.json").write_text(json.dumps(sample_report()))
    return root


def trace_events():
    return [
        {"event": "model_turn", "step": 1},
        {"event": "tool_result", "tool": "list_files", "result": {"ok": True}},
        {"event": "model_turn", "step": 2},
        {"event": "tool_result", "tool": "read_file", "result": {"ok": True}},
        {"event": "report", "report": sample_report()},
        {"event": "completed", "findings": 0},
    ]


def write_trace(root, events):
    (root / "sample_trace.jsonl").write_text("\n".join(json.dumps(item) for item in events))


@pytest.fixture(autouse=True)
def git_unavailable_by_default(monkeypatch):
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=128, stdout=b""),
    )


def test_complete_structure_without_optional_trace_passes_with_candid_warning(tmp_path, capsys):
    prepare_root(tmp_path)
    assert checker.main(["--root", str(tmp_path)]) == 0
    output = capsys.readouterr().out
    assert "Structure check only" in output
    assert "cannot prove authentic LLM execution" in output
    assert "Optional sample_trace.jsonl is absent" in output


def test_missing_sample_is_actionable_and_is_never_created(tmp_path, capsys):
    prepare_root(tmp_path, sample=False)
    assert checker.main(["--root", str(tmp_path)]) == 1
    output = capsys.readouterr().out
    assert "--output sample_report.json" in output
    assert "do not invent" in output
    assert not (tmp_path / "sample_report.json").exists()


def test_missing_code_dependencies_and_tests_are_reported(tmp_path):
    errors, _ = checker.check_submission(tmp_path)
    assert any("agent.py" in message for message in errors)
    assert any("installable dependencies" in message for message in errors)
    assert any("automated test_*.py" in message for message in errors)


def test_pyproject_is_an_acceptable_dependency_alternative(tmp_path):
    prepare_root(tmp_path)
    (tmp_path / "requirements.txt").unlink()
    (tmp_path / "pyproject.toml").write_text("[project]\nname='example'\n")
    errors, _ = checker.check_submission(tmp_path)
    assert not errors


@pytest.mark.parametrize(
    "content",
    [
        "{bad",
        "[]",
        '{"repository":"https://example.com/project","violations":[]}',
        '{"repository":"https://github.com/example/project","violations":"none"}',
        '{"repository":"https://github.com/example/project","violations":[],"extra":NaN}',
    ],
)
def test_invalid_sample_report_is_rejected_without_printing_content(tmp_path, content):
    prepare_root(tmp_path)
    (tmp_path / "sample_report.json").write_text(content)
    errors, _ = checker.check_submission(tmp_path)
    assert any("report contract" in message for message in errors)


def test_optional_trace_supports_review_but_does_not_prove_authenticity(tmp_path):
    prepare_root(tmp_path)
    write_trace(tmp_path, trace_events())
    errors, warnings = checker.check_submission(tmp_path)
    assert not errors
    assert not any("trace" in message.lower() for message in warnings)


@pytest.mark.parametrize(
    "change", ["mismatch", "no-model", "one-tool", "fatal-after-report", "invalid-event"]
)
def test_optional_trace_must_be_consistent_when_present(tmp_path, change):
    prepare_root(tmp_path)
    events = trace_events()
    if change == "mismatch":
        events[-2]["report"] = {"repository": "https://github.com/example/other", "violations": []}
    elif change == "no-model":
        events = [item for item in events if item["event"] != "model_turn"]
    elif change == "one-tool":
        events = [item for item in events if item.get("tool") != "read_file"]
    elif change == "fatal-after-report":
        events.append({"event": "fatal_error"})
    else:
        events.append({"event": 123})
    write_trace(tmp_path, events)
    errors, _ = checker.check_submission(tmp_path)
    assert any("sample_trace.jsonl" in message for message in errors)


def test_invalid_jsonl_trace_is_rejected(tmp_path):
    prepare_root(tmp_path)
    (tmp_path / "sample_trace.jsonl").write_text("{bad\n")
    errors, _ = checker.check_submission(tmp_path)
    assert any("invalid JSONL" in message for message in errors)


def test_tracked_environment_filenames_are_detected_without_reading_values(tmp_path, monkeypatch):
    prepare_root(tmp_path)
    # No actual .env exists. Detection must use filenames reported by Git only.
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=b".env\0nested/.env.production\0.env.example\0"
        ),
    )
    errors, _ = checker.check_submission(tmp_path)
    assert any("environment files are tracked" in message for message in errors)
    assert not (tmp_path / ".env").exists()


def test_tracked_env_examples_are_allowed(tmp_path, monkeypatch):
    prepare_root(tmp_path)
    monkeypatch.setattr(
        checker.subprocess,
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=b".env.example\0tests/fixtures/subtle-defects/.env.example\0"
        ),
    )
    assert not checker.check_submission(tmp_path)[0]


def test_git_timeout_is_a_warning_not_an_unhandled_exception(tmp_path, monkeypatch):
    prepare_root(tmp_path)

    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 15)

    monkeypatch.setattr(checker.subprocess, "run", timeout)
    errors, warnings = checker.check_submission(tmp_path)
    assert not errors
    assert any("Git was unavailable" in message for message in warnings)


def test_candidate_code_is_not_imported_or_executed(tmp_path):
    prepare_root(tmp_path)
    (tmp_path / "reporting.py").write_text("raise RuntimeError('must never execute')\n")
    assert checker.main(["--root", str(tmp_path)]) == 0


def test_nonexistent_root_returns_failure(tmp_path):
    errors, _ = checker.check_submission(tmp_path / "missing")
    assert errors == ["Submission root must be an existing project directory."]
