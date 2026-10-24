"""Compare an audit report with independently authored fixture expectations.

This script does not invoke an LLM, execute repository code, or assess meaning.
Location and keyword matching are deliberately transparent and reproducible.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

CATEGORY_ALIASES = {
    "ci cd": "ci",
    "continuous integration": "ci",
    "continuous integration and delivery": "ci",
    "dependencies": "dependency management",
    "dependency": "dependency management",
    "build release": "build and release",
    "release": "build and release",
    "repo hygiene": "repository hygiene",
    "config": "configuration",
}


def normalize_category(value: str) -> str:
    normalized = re.sub(r"[^a-z0-9]+", " ", value.casefold()).strip()
    return CATEGORY_ALIASES.get(normalized, normalized)


def normalize_file(value: str | None) -> str | None:
    if value is None:
        return None
    if not value.strip():
        raise ValueError("Finding file paths must be nonempty strings or null")
    normalized = value.replace("\\", "/")
    while normalized.startswith("./"):
        normalized = normalized[2:]
    if normalized.startswith("/") or re.match(r"^[A-Za-z]:", normalized):
        raise ValueError("Finding file paths must be relative to the repository")
    if ".." in normalized.split("/"):
        raise ValueError("Finding file paths must not contain '..'")
    return normalized


def require_line(value: Any, label: str) -> None:
    if value is not None and (type(value) is not int or value < 1):
        raise ValueError(f"{label} must be a positive integer or null")


def read_object(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return value


def validate_expected(data: dict[str, Any]) -> list[dict[str, Any]]:
    findings = data.get("findings")
    if not isinstance(findings, list):
        raise ValueError("Expected JSON must contain a 'findings' list")
    seen: set[str] = set()
    for index, finding in enumerate(findings):
        label = f"Expected finding {index}"
        if not isinstance(finding, dict):
            raise ValueError(f"{label} must be an object")
        for key in ("id", "category"):
            if not isinstance(finding.get(key), str) or not finding[key].strip():
                raise ValueError(f"{label}.{key} must be a nonempty string")
        if finding["id"] in seen:
            raise ValueError(f"Duplicate expected id: {finding['id']}")
        seen.add(finding["id"])
        if "file" not in finding or (
            finding["file"] is not None and not isinstance(finding["file"], str)
        ):
            raise ValueError(f"{label}.file must be a string or null")
        normalize_file(finding["file"])
        if "line" not in finding:
            raise ValueError(f"{label}.line is required (use null for any line)")
        require_line(finding["line"], f"{label}.line")
        if finding["file"] is None and finding["line"] is not None:
            raise ValueError(f"{label}.line must be null when file is null")
        tolerance = finding.get("line_tolerance", 0)
        if type(tolerance) is not int or tolerance < 0:
            raise ValueError(f"{label}.line_tolerance must be a nonnegative integer")
        for key in ("keywords", "rule_ids"):
            values = finding.get(key, [])
            if not isinstance(values, list) or any(
                not isinstance(value, str) or not value.strip() for value in values
            ):
                raise ValueError(f"{label}.{key} must be a list of nonempty strings")
    return findings


def validate_actual(data: dict[str, Any]) -> list[dict[str, Any]]:
    # The assignment's normal report key is violations. 'findings' also allows
    # independently authored reports to be evaluated without rewriting them.
    violations = data.get("violations", data.get("findings"))
    if not isinstance(violations, list):
        raise ValueError("Actual report must contain a 'violations' list")
    for index, violation in enumerate(violations):
        label = f"Actual violation {index}"
        if not isinstance(violation, dict):
            raise ValueError(f"{label} must be an object")
        for key in ("rule_id", "category", "severity", "description", "recommendation"):
            if not isinstance(violation.get(key), str) or not violation[key].strip():
                raise ValueError(f"{label}.{key} must be a nonempty string")
        if violation["severity"] not in {"critical", "high", "medium", "low"}:
            raise ValueError(f"{label}.severity must be critical, high, medium, or low")
        if (
            "evidence" not in violation
            or not isinstance(violation["evidence"], str)
            or not violation["evidence"].strip()
        ):
            raise ValueError(f"{label}.evidence must be a nonempty string")
        if "file" not in violation or (
            violation["file"] is not None and not isinstance(violation["file"], str)
        ):
            raise ValueError(f"{label}.file must be a string or null")
        normalize_file(violation["file"])
        if "line" not in violation:
            raise ValueError(f"{label}.line is required")
        require_line(violation["line"], f"{label}.line")
        if violation["file"] is None and violation["line"] is not None:
            raise ValueError(f"{label}.line must be null when file is null")
    return violations


def matches(expected: dict[str, Any], actual: dict[str, Any]) -> bool:
    if normalize_category(expected["category"]) != normalize_category(actual["category"]):
        return False
    if normalize_file(expected["file"]) != normalize_file(actual["file"]):
        return False
    if expected["line"] is not None:
        if actual["line"] is None:
            return False
        if abs(expected["line"] - actual["line"]) > expected.get("line_tolerance", 0):
            return False
    if expected.get("rule_ids") and actual["rule_id"] not in expected["rule_ids"]:
        return False
    searchable = " ".join(
        actual[field] for field in ("description", "evidence", "recommendation")
    ).casefold()
    keywords = expected.get("keywords", [])
    return not keywords or any(word.casefold() in searchable for word in keywords)


def evaluate(expected: list[dict[str, Any]], actual: list[dict[str, Any]]) -> dict[str, Any]:
    # Maximum bipartite matching avoids order-sensitive undercounting when a
    # broad location expectation and a narrow one share candidate findings.
    candidates = [
        [i for i, finding in enumerate(actual) if matches(target, finding)] for target in expected
    ]
    owner: dict[int, int] = {}

    def assign(expected_index: int, visited: set[int]) -> bool:
        for actual_index in candidates[expected_index]:
            if actual_index in visited:
                continue
            visited.add(actual_index)
            previous = owner.get(actual_index)
            if previous is None or assign(previous, visited):
                owner[actual_index] = expected_index
                return True
        return False

    for expected_index in sorted(range(len(expected)), key=lambda i: len(candidates[i])):
        assign(expected_index, set())
    paired = {expected_index: actual_index for actual_index, expected_index in owner.items()}
    true_positives = len(paired)
    false_positives = len(actual) - true_positives
    false_negatives = len(expected) - true_positives
    # Null means undefined, rather than calling a healthy empty report 100% recall.
    precision = true_positives / len(actual) if actual else None
    recall = true_positives / len(expected) if expected else None
    f1 = (
        2 * true_positives / (2 * true_positives + false_positives + false_negatives)
        if true_positives + false_positives + false_negatives
        else None
    )
    return {
        "true_positives": true_positives,
        "false_positives": false_positives,
        "false_negatives": false_negatives,
        "precision": precision,
        "recall": recall,
        "f1": f1,
        "matches": [
            {
                "expected_id": expected[i]["id"],
                "actual_index": paired[i],
                "actual_rule_id": actual[paired[i]]["rule_id"],
            }
            for i in sorted(paired)
        ],
        "missed_expected_ids": [
            target["id"] for i, target in enumerate(expected) if i not in paired
        ],
        "unmatched_actual_indices": [i for i in range(len(actual)) if i not in owner],
        "limitation": "Mechanical location/keyword comparison; review semantics manually.",
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--expected", type=Path, required=True)
    parser.add_argument("--actual", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output and args.output.resolve() in {
            args.expected.resolve(),
            args.actual.resolve(),
        }:
            raise ValueError("Metrics output must not overwrite expected or actual input")
        expected_data = read_object(args.expected)
        actual_data = read_object(args.actual)
        result = evaluate(validate_expected(expected_data), validate_actual(actual_data))
        result["fixture"] = expected_data.get("fixture")
        rendered = json.dumps(result, indent=2, ensure_ascii=False)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(rendered + "\n", encoding="utf-8")
        print(rendered)
    except (ValueError, OSError) as exc:
        print(f"Evaluation error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
