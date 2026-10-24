"""Explicit observe -> select -> execute -> interpret loop with bounded dispatch."""

from __future__ import annotations

import json
from collections import Counter

from prompts import SYSTEM_PROMPT
from reporting import REPORT_TOOL, ReportError, validate_report
from safety import redact
from tools import TOOL_SCHEMAS
from tracing import Trace


class AgentError(RuntimeError):
    pass


def _reject_constant(value: str):
    raise ValueError("Non-finite JSON constants are forbidden.")


def run_audit(
    repository: str, tools, client, *, max_steps: int = 40, trace: Trace | None = None
) -> dict:
    if type(max_steps) is not int or max_steps < 1:
        raise AgentError("max_steps must be a positive integer.")
    trace = trace or Trace()
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": json.dumps(
                {
                    "repository": repository,
                    "task": "Investigate this repository with the tools, then submit your report.",
                    "limits": {"model_turns": max_steps, "max_tool_calls": max_steps * 4},
                }
            ),
        },
    ]
    schemas = [*TOOL_SCHEMAS, REPORT_TOOL]
    repeated = Counter()
    successful_tools = 0
    inventory_requested = False
    tool_count = 0
    for step in range(1, max_steps + 1):
        # Bounds runaway context/cost instead of silently dropping evidence the model relies on.
        if len(json.dumps(messages, ensure_ascii=True)) > 450_000:
            raise AgentError(
                "Inspection context limit reached; narrow the audit or inspect a smaller repository."
            )
        turn = client.respond(messages, schemas)
        messages.extend(turn.items)
        trace.write(
            "model_turn",
            step=step,
            usage=turn.usage,
            tool_calls=[
                {"name": c.name, "arguments": c.arguments, "call_id": c.call_id} for c in turn.calls
            ],
        )
        if not turn.calls:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Choose an inspection tool or submit_report. Text alone does not complete the audit."
                    ),
                }
            )
            continue
        if tool_count + len(turn.calls) > max_steps * 4:
            raise AgentError("Tool-call budget exhausted before a validated report was submitted.")
        for call in turn.calls:
            tool_count += 1
            try:
                arguments = json.loads(call.arguments, parse_constant=_reject_constant)
                if not isinstance(arguments, dict):
                    raise ValueError("Arguments must be a JSON object.")
            except (ValueError, TypeError, RecursionError):
                result = {"ok": False, "error": "Invalid tool arguments; supply a JSON object."}
            else:
                if call.name == "submit_report":
                    try:
                        if not inventory_requested or not successful_tools:
                            raise ReportError(
                                "Inspect the repository with list_files before submitting."
                            )
                        if tools.files and not tools.observed_lines:
                            raise ReportError(
                                "Read relevant source/configuration before submitting a report."
                            )
                        report = validate_report(arguments, repository, tools)
                    except ReportError as exc:
                        result = {
                            "ok": False,
                            "error": str(exc),
                            "next_action": "Gather missing evidence or revise the report.",
                        }
                    else:
                        trace.write("report", step=step, report=report, tool_calls=tool_count)
                        return report
                else:
                    identity = (call.name, json.dumps(arguments, sort_keys=True))
                    repeated[identity] += 1
                    if repeated[identity] > 3:
                        result = {
                            "ok": False,
                            "error": (
                                "Repeated identical request. Interpret previous results and choose another action."
                            ),
                        }
                    else:
                        result = tools.dispatch(call.name, arguments)
                        if result.get("ok"):
                            successful_tools += 1
                            if call.name == "list_files":
                                inventory_requested = True
            result = redact(result)
            trace.write(
                "tool_result", step=step, call_id=call.call_id, tool=call.name, result=result
            )
            messages.append(
                {
                    "type": "function_call_output",
                    "call_id": call.call_id,
                    "output": json.dumps(result, ensure_ascii=True, allow_nan=False),
                }
            )
        if step == max_steps - 3:
            messages.append(
                {
                    "role": "user",
                    "content": (
                        "Three model turns remain. Resolve your strongest supported findings and submit_report. "
                        "Do not invent claims to compensate for uninspected files."
                    ),
                }
            )
    raise AgentError(
        "Maximum agent steps reached before a validated report. Increase --max-steps and retry."
    )
