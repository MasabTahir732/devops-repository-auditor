"""Validate the required output and reject references the agent never inspected."""

from __future__ import annotations

import json
import os
import re
import tempfile
from pathlib import Path, PurePosixPath

from safety import redact

FIELDS = {
    "rule_id",
    "category",
    "severity",
    "file",
    "line",
    "description",
    "evidence",
    "recommendation",
}
VIOLATION_SCHEMA = {
    "type": "object",
    "properties": {
        "rule_id": {"type": "string"},
        "category": {"type": "string"},
        "severity": {"type": "string", "enum": ["critical", "high", "medium", "low"]},
        "file": {"type": ["string", "null"]},
        "line": {"type": ["integer", "null"]},
        "description": {"type": "string"},
        "evidence": {"type": "string"},
        "recommendation": {"type": "string"},
    },
    "required": sorted(FIELDS),
    "additionalProperties": False,
}
REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "repository": {"type": "string"},
        "violations": {"type": "array", "items": VIOLATION_SCHEMA},
    },
    "required": ["repository", "violations"],
    "additionalProperties": False,
}
REPORT_TOOL = {
    "type": "function",
    "name": "submit_report",
    "description": (
        "Finish the investigation by submitting only supported violations. An empty violations "
        "array is valid after inspection. Rejected reports return feedback; investigate or revise."
    ),
    "strict": True,
    "parameters": REPORT_SCHEMA,
}


class ReportError(ValueError):
    pass


def _normal_category(value: str) -> str:
    key = re.sub(r"[_/\s-]+", " ", value.strip().lower())
    return {
        "ci cd": "ci",
        "github actions": "ci",
        "github actions ci": "ci",
        "dependencies": "dependency management",
        "dependency": "dependency management",
        "hygiene": "repository hygiene",
        "build release": "build and release",
        "build": "build and release",
        "release": "build and release",
    }.get(key, key)


def validate_report(report: object, repository: str, tools=None) -> dict:
    """Schema/evidence checks improve grounding; semantic truth still needs model judgment."""
    if not isinstance(report, dict) or set(report) != {"repository", "violations"}:
        raise ReportError("Report must contain exactly repository and violations.")
    if report["repository"] != repository:
        raise ReportError("Report repository must match the supplied canonical URL.")
    if not isinstance(report["violations"], list):
        raise ReportError("violations must be an array.")
    if len(report["violations"]) > 200:
        raise ReportError("Too many violations; consolidate duplicate root causes (maximum 200).")
    violations = []
    seen = set()
    for index, finding in enumerate(report["violations"]):
        prefix = f"Violation {index + 1}: "
        if not isinstance(finding, dict) or set(finding) != FIELDS:
            raise ReportError(
                prefix + "all specified violation fields are required, with no extras."
            )
        for field in FIELDS - {"file", "line"}:
            if not isinstance(finding[field], str) or not finding[field].strip():
                raise ReportError(prefix + f"{field} must be a nonempty string.")
            if len(finding[field]) > 8000:
                raise ReportError(prefix + f"{field} is too long.")
        if finding["severity"] not in {"critical", "high", "medium", "low"}:
            raise ReportError(prefix + "invalid severity.")
        path, line = finding["file"], finding["line"]
        if line is not None and (type(line) is not int or line < 1):
            raise ReportError(prefix + "line must be a positive integer or null.")
        if path is None:
            if line is not None:
                raise ReportError(prefix + "a repository-wide finding must use line=null.")
            if tools is not None and (
                not tools.inventory_complete or not set(tools.files).issubset(tools.listed_files)
            ):
                raise ReportError(
                    prefix + "repository-wide claims require a complete file inventory."
                )
        else:
            if (
                not isinstance(path, str)
                or not path
                or "\\" in path
                or PurePosixPath(path).is_absolute()
                or ".." in PurePosixPath(path).parts
                or ":" in path
                or str(PurePosixPath(path)) != path
            ):
                raise ReportError(prefix + "file must be a relative POSIX repository path or null.")
            if tools is not None:
                if path not in tools.files:
                    raise ReportError(
                        prefix + "file was not found; use file=null for an absent file."
                    )
                if path not in tools.observed_lines:
                    raise ReportError(prefix + "read or search the cited file before reporting it.")
                if line is not None and line not in tools.observed_lines[path]:
                    raise ReportError(
                        prefix + "the cited line has not been observed; read that range."
                    )
        cleaned = redact({**finding, "category": _normal_category(finding["category"])})
        # Keep distinct problems at the same location, suppress exact repeated descriptions.
        identity = (
            cleaned["category"],
            path,
            line,
            re.sub(r"\W+", "", cleaned["description"].lower()),
        )
        if identity not in seen:
            seen.add(identity)
            violations.append(cleaned)
    rank = {"critical": 0, "high": 1, "medium": 2, "low": 3}
    violations.sort(
        key=lambda v: (rank[v["severity"]], v["file"] or "", v["line"] or 0, v["rule_id"])
    )
    return {"repository": repository, "violations": violations}


def write_report(report: dict, destination: Path) -> None:
    """Atomically replace a report only after validation and successful serialization."""
    serialized = json.dumps(redact(report), indent=2, ensure_ascii=True, allow_nan=False) + "\n"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=destination.parent,
            prefix=".audit-",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
            stream.write(serialized)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)
