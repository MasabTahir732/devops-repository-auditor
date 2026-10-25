"""Scripted clients exercise application behavior; they do not measure LLM accuracy."""

import json

import pytest

from agent_loop import AgentError, model_tool_output, run_audit
from llm_client import ModelTurn, ToolCall
from tracing import Trace

URL = "https://github.com/example/project"


def test_compact_model_output_preserves_source_numbers_and_truncation():
    result = {
        "ok": True,
        "path": "app.py",
        "lines": [
            {"line": 17, "text": "DEBUG = True", "truncated": False},
            {"line": 18, "text": "long source", "truncated": True},
        ],
        "truncated": True,
        "next_start_line": 19,
    }
    serialized = model_tool_output(result)
    compact = json.loads(serialized)
    assert compact["lines"] == ["17: DEBUG = True", "18: long source [line truncated]"]
    assert compact["next_start_line"] == 19
    assert compact["truncated"] is True
    assert result["lines"][0]["line"] == 17  # Full structured trace is not mutated.
    assert len(serialized) < len(json.dumps(result)) + 70


class MemoryTools:
    def __init__(self):
        self.files = [".github/workflows/ci.yml", "pyproject.toml"]
        self.listed_files = set()
        self.observed_lines = {}
        self.inventory_complete = True
        self.calls = []

    def dispatch(self, name, arguments):
        self.calls.append((name, arguments))
        if name == "list_files":
            self.listed_files.update(self.files)
            return {"ok": True, "files": self.files}
        if name == "read_file":
            path = arguments["path"]
            self.observed_lines[path] = {1, 2, 3}
            if path.endswith("ci.yml"):
                return {"ok": True, "lines": [{"line": 2, "text": "pip install -e ."}]}
            return {"ok": True, "lines": [{"line": 1, "text": '[project]\nname="demo"'}]}
        return {"ok": False, "error": "Unknown tool"}


def turn(name, args, number):
    arguments = args if isinstance(args, str) else json.dumps(args)
    call_id = f"call-{number}"
    return ModelTurn(
        [{"type": "function_call", "name": name, "arguments": arguments, "call_id": call_id}],
        [ToolCall(name, arguments, call_id)],
        usage={"input_tokens": 1, "output_tokens": 1},
    )


def tool_result(messages):
    return json.loads(
        next(
            item["output"]
            for item in reversed(messages)
            if item.get("type") == "function_call_output"
        )
    )


class AdaptiveClient:
    """A fake decision maker whose follow-up depends on the prior tool's contents."""

    def __init__(self):
        self.count = 0

    def respond(self, messages, tools):
        self.count += 1
        if self.count == 1:
            return turn("list_files", {}, self.count)
        result = tool_result(messages)
        if "files" in result:
            assert ".github/workflows/ci.yml" in result["files"]
            return turn("read_file", {"path": ".github/workflows/ci.yml"}, self.count)
        if "pip install -e ." in json.dumps(result):
            return turn("read_file", {"path": "pyproject.toml"}, self.count)
        return turn("submit_report", {"repository": URL, "violations": []}, self.count)


def test_tool_result_drives_followup_and_trace_records_actual_execution(tmp_path):
    tools = MemoryTools()
    path = tmp_path / "trace.jsonl"
    with Trace(path) as trace:
        result = run_audit(URL, tools, AdaptiveClient(), max_steps=5, trace=trace)
    assert result == {"repository": URL, "violations": []}
    assert [args.get("path") for name, args in tools.calls if name == "read_file"] == [
        ".github/workflows/ci.yml",
        "pyproject.toml",
    ]
    records = [json.loads(line) for line in path.read_text().splitlines()]
    assert len([r for r in records if r["event"] == "tool_result"]) == 3
    assert records[-1]["event"] == "report"


class SequenceClient:
    def __init__(self, turns):
        self.turns = iter(turns)
        self.messages = []

    def respond(self, messages, tools):
        self.messages.append(list(messages))
        return next(self.turns)


def test_premature_report_gets_feedback_and_can_recover():
    report = {"repository": URL, "violations": []}
    client = SequenceClient(
        [
            turn("submit_report", report, 1),
            turn("list_files", {}, 2),
            turn("read_file", {"path": "pyproject.toml"}, 3),
            turn("submit_report", report, 4),
        ]
    )
    assert run_audit(URL, MemoryTools(), client, max_steps=5) == report
    assert tool_result(client.messages[1])["ok"] is False


def test_malformed_json_and_unknown_tool_do_not_execute_arbitrary_actions():
    client = SequenceClient([turn("read_file", "{bad json", 1), turn("os.system", {}, 2)])
    tools = MemoryTools()
    with pytest.raises(AgentError, match="Maximum agent steps"):
        run_audit(URL, tools, client, max_steps=2)
    assert tools.calls == [("os.system", {})]
    assert tool_result(client.messages[1])["ok"] is False


def test_budget_exhaustion_is_not_an_empty_success_report():
    client = SequenceClient([turn("list_files", {}, i) for i in range(1, 3)])
    with pytest.raises(AgentError, match="Maximum agent steps"):
        run_audit(URL, MemoryTools(), client, max_steps=2)
