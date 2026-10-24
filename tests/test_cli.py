"""End-to-end application wiring against a local Git fixture and a scripted model."""

import json
import os
import subprocess
from contextlib import contextmanager

import pytest

import agent
from llm_client import ModelTurn, ToolCall
from repository import _git_environment

URL = "https://github.com/example/cli-test"


@pytest.fixture(autouse=True)
def isolate_credentials(monkeypatch):
    import dotenv

    monkeypatch.setattr(dotenv, "load_dotenv", lambda *a, **k: False)
    monkeypatch.setenv("LLM_PROVIDER", "gemini")
    for name in ["GEMINI_API_KEY", "GROQ_API_KEY", "OPENAI_API_KEY", "LLM_MODEL"]:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture
def local_repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    (root / "config.py").write_text("# Production settings\nDEBUG = True\n", encoding="utf-8")
    options = [
        "git",
        "-C",
        str(root),
        "-c",
        "user.name=CLI Test",
        "-c",
        "user.email=cli@example.invalid",
        "-c",
        "commit.gpgsign=false",
        "-c",
        "core.hooksPath=" + os.devnull,
    ]
    for arguments in [
        ["init", "--initial-branch=main"],
        ["add", "--all"],
        ["commit", "-m", "Test fixture"],
    ]:
        subprocess.run(
            options + arguments, check=True, capture_output=True, timeout=10, env=_git_environment()
        )
    return root


class ScriptedModel:
    def __init__(self):
        self.index = 0

    def respond(self, messages, schemas):
        self.index += 1
        if self.index == 1:
            name, args = "list_files", {"prefix": "", "offset": 0, "limit": 500}
        elif self.index == 2:
            result = json.loads(messages[-1]["output"])
            assert result["files"][0]["path"] == "config.py"
            name, args = "read_file", {"path": "config.py", "start_line": 1, "end_line": 200}
        else:
            assert "DEBUG = True" in messages[-1]["output"]
            name, args = (
                "submit_report",
                {
                    "repository": URL,
                    "violations": [
                        {
                            "rule_id": "CFG-001",
                            "category": "configuration",
                            "severity": "medium",
                            "file": "config.py",
                            "line": 2,
                            "description": "Debug setting enabled",
                            "evidence": "DEBUG = True in production settings",
                            "recommendation": "Set production DEBUG to False.",
                        }
                    ],
                },
            )
        call_id, arguments = f"test-call-{self.index}", json.dumps(args)
        return ModelTurn(
            [{"type": "function_call", "name": name, "arguments": arguments, "call_id": call_id}],
            [ToolCall(name, arguments, call_id)],
        )


def test_cli_writes_validated_report_and_trace_with_real_tools(
    monkeypatch, local_repo, tmp_path, capsys
):
    monkeypatch.setenv("GEMINI_API_KEY", "test-cli-key-never-a-real-credential")

    @contextmanager
    def local_clone(url, timeout):
        assert url == URL
        assert timeout == 120.0
        yield local_repo

    monkeypatch.setattr(agent, "cloned_repository", local_clone)
    monkeypatch.setattr(agent, "create_client", lambda settings: ScriptedModel())
    output, trace = tmp_path / "result.json", tmp_path / "result.trace.jsonl"
    assert agent.main(["--repo", URL, "--output", str(output), "--trace", str(trace)]) == 0
    report = json.loads(output.read_text())
    assert report["violations"][0]["line"] == 2
    records = [json.loads(line) for line in trace.read_text().splitlines()]
    assert records[-1]["event"] == "completed"
    assert any(record["event"] == "report" for record in records)
    assert "test-cli-key" not in trace.read_text()
    assert capsys.readouterr().out == ""


def test_missing_key_is_noninteractive_and_does_not_overwrite_old_report(tmp_path, capsys):
    output = tmp_path / "result.json"
    output.write_text("old report", encoding="utf-8")
    assert agent.main(["--repo", URL, "--output", str(output)]) == 1
    assert "GEMINI_API_KEY is missing" in capsys.readouterr().err
    assert output.read_text() == "old report"


def test_invalid_url_rejected_without_echoing_url_credentials(tmp_path, capsys):
    assert (
        agent.main(
            [
                "--repo",
                "https://user:private-pass@github.com/example/cli-test",
                "--output",
                str(tmp_path / "result.json"),
            ]
        )
        == 1
    )
    assert "private-pass" not in capsys.readouterr().err


def test_trace_and_report_must_be_different_paths(tmp_path, capsys):
    path = str(tmp_path / "same.json")
    assert agent.main(["--repo", URL, "--output", path, "--trace", path]) == 1
    assert "different files" in capsys.readouterr().err
