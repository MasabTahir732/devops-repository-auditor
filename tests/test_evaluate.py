"""Unit tests for mechanical evaluation, never for real-model detection accuracy."""

import json
from pathlib import Path

import pytest

from scripts.evaluate import (
    evaluate,
    main,
    matches,
    read_object,
    validate_actual,
    validate_expected,
)


def expected(**changes):
    return {
        "id": "expected-ci",
        "category": "ci",
        "file": ".github/workflows/ci.yml",
        "line": 10,
        "keywords": ["failure"],
        **changes,
    }


def actual(**changes):
    return {
        "rule_id": "CI-001",
        "category": "ci",
        "severity": "high",
        "file": ".github/workflows/ci.yml",
        "line": 10,
        "description": "Test failure is ignored",
        "evidence": "continue-on-error: true",
        "recommendation": "Require successful test execution",
        **changes,
    }


def test_duplicate_findings_count_as_false_positives():
    metrics = evaluate([expected()], [actual(), actual()])
    assert metrics["true_positives"] == 1
    assert metrics["false_positives"] == 1
    assert metrics["false_negatives"] == 0
    assert metrics["precision"] == 0.5
    assert metrics["recall"] == 1


def test_maximum_matching_reassigns_earlier_ambiguous_matches():
    targets = [
        expected(id="first", keywords=["shared", "only-first"]),
        expected(id="second", keywords=["shared", "only-other"]),
        expected(id="third", keywords=["shared", "only-other"]),
    ]
    findings = [actual(description=value) for value in ["shared", "only-first", "only-other"]]
    metrics = evaluate(targets, findings)
    assert metrics["true_positives"] == 3
    assert len({pair["actual_index"] for pair in metrics["matches"]}) == 3


def test_healthy_empty_inputs_have_undefined_ratios():
    metrics = evaluate([], [])
    assert (
        metrics["true_positives"] == metrics["false_positives"] == metrics["false_negatives"] == 0
    )
    assert metrics["precision"] is metrics["recall"] is metrics["f1"] is None


def test_empty_actual_report_records_missed_expectations():
    metrics = evaluate([expected()], [])
    assert metrics["false_negatives"] == 1
    assert metrics["precision"] is None
    assert metrics["recall"] == 0
    assert metrics["missed_expected_ids"] == ["expected-ci"]


@pytest.mark.parametrize("category", ["CI/CD", "continuous integration", "CI"])
def test_documented_category_aliases_are_accepted(category):
    assert matches(expected(), actual(category=category))


def test_unknown_categories_are_compared_exactly_not_guessed():
    assert matches(expected(category="Custom_Control"), actual(category="custom-control"))
    assert not matches(expected(category="custom control"), actual(category="custom controls"))
    assert not matches(expected(), actual(category="CI security"))


def test_keyword_line_tolerance_path_and_optional_rule_filters():
    target = expected(line_tolerance=2, rule_ids=["CI-accepted"])
    assert matches(
        target, actual(rule_id="CI-accepted", line=12, file="./.github\\workflows\\ci.yml")
    )
    assert not matches(target, actual(rule_id="other", line=12))
    assert not matches(target, actual(rule_id="CI-accepted", line=13))
    assert not matches(target, actual(rule_id="CI-accepted", description="Unrelated issue"))
    assert matches(expected(line=None), actual(line=100))
    assert not matches(expected(line=10), actual(line=None))


@pytest.mark.parametrize(
    "changes",
    [
        {"severity": "urgent"},
        {"evidence": ""},
        {"evidence": "  "},
        {"line": True},
        {"line": 0},
        {"line": -1},
        {"file": "../../outside"},
        {"file": "C:\\outside"},
        {"file": "/outside"},
        {"file": None, "line": 10},
        {"file": ""},
        {"category": None},
    ],
)
def test_actual_input_rejects_invalid_report_fields(changes):
    with pytest.raises(ValueError):
        validate_actual({"violations": [actual(**changes)]})


def test_expected_input_rejects_duplicate_ids_and_invalid_match_rules():
    with pytest.raises(ValueError, match="Duplicate expected id"):
        validate_expected({"findings": [expected(), expected()]})
    for changes in [
        {"line_tolerance": True},
        {"line_tolerance": -1},
        {"keywords": "failure"},
        {"keywords": [""]},
        {"rule_ids": [None]},
        {"file": None, "line": 3},
    ]:
        with pytest.raises(ValueError):
            validate_expected({"findings": [expected(**changes)]})


@pytest.mark.parametrize("content", ["[1,2]", "{malformed", '"report"'])
def test_read_object_rejects_malformed_or_nonobject_json(tmp_path, content):
    path = tmp_path / "input.json"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError):
        read_object(path)


def test_cli_writes_metrics_and_does_not_overwrite_inputs(tmp_path, capsys):
    expected_path, actual_path, output = [
        tmp_path / name for name in ["expected.json", "actual.json", "metrics.json"]
    ]
    expected_path.write_text(json.dumps({"fixture": "test", "findings": [expected()]}))
    actual_path.write_text(
        json.dumps({"repository": "https://github.com/example/repo", "violations": [actual()]})
    )
    arguments = ["--expected", str(expected_path), "--actual", str(actual_path)]
    assert main([*arguments, "--output", str(output)]) == 0
    assert json.loads(output.read_text())["true_positives"] == 1
    original = actual_path.read_bytes()
    assert main([*arguments, "--output", str(actual_path)]) == 2
    assert actual_path.read_bytes() == original
    assert "must not overwrite" in capsys.readouterr().err


def test_cli_invalid_input_returns_error_status(tmp_path, capsys):
    invalid = tmp_path / "invalid.json"
    invalid.write_text("[]")
    assert main(["--expected", str(invalid), "--actual", str(invalid)]) == 2
    assert "Evaluation error" in capsys.readouterr().err


@pytest.mark.parametrize(
    "fixture,count", [("healthy", 0), ("obvious-defects", 6), ("subtle-defects", 3)]
)
def test_authored_fixture_expectation_locations_exist_without_executing_source(fixture, count):
    root = Path(__file__).parent / "fixtures"
    expectations = validate_expected(read_object(root / "expectations" / f"{fixture}.json"))
    assert len(expectations) == count
    for item in expectations:
        if item["file"] is not None:
            source = root / fixture / item["file"]
            assert source.is_file()
            if item["line"] is not None:
                assert item["line"] <= len(source.read_text(encoding="utf-8").splitlines())
