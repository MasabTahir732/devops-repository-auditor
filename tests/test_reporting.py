import copy
import json
from types import SimpleNamespace

import pytest

from reporting import ReportError, validate_report, write_report

URL = "https://github.com/example/project"


def finding(**changes):
    return {
        "rule_id": "CI-001",
        "category": "ci",
        "severity": "high",
        "file": ".github/workflows/ci.yml",
        "line": 8,
        "description": "Test failures are ignored",
        "evidence": "continue-on-error: true prevents this job from enforcing test success",
        "recommendation": "Remove continue-on-error from the test job.",
        **changes,
    }


def observations():
    path = ".github/workflows/ci.yml"
    return SimpleNamespace(
        files=[path], listed_files={path}, observed_lines={path: {8, 9}}, inventory_complete=True
    )


def test_valid_report_and_empty_report():
    report = {"repository": URL, "violations": [finding()]}
    assert validate_report(report, URL, observations()) == report
    assert (
        validate_report({"repository": URL, "violations": []}, URL, observations())["violations"]
        == []
    )


@pytest.mark.parametrize(
    "changes",
    [
        {"line": 7},
        {"line": True},
        {"line": -1},
        {"severity": "urgent"},
        {"file": "missing.yml"},
        {"file": "../outside"},
        {"file": "C:\\secret"},
        {"file": None, "line": 1},
        {"file": "./nested"},
        {"evidence": ""},
    ],
)
def test_invalid_or_unobserved_findings_are_rejected(changes):
    with pytest.raises(ReportError):
        validate_report(
            {"repository": URL, "violations": [finding(**changes)]}, URL, observations()
        )


def test_file_must_be_read_not_just_listed():
    tools = observations()
    tools.observed_lines = {}
    with pytest.raises(ReportError, match="read or search"):
        validate_report({"repository": URL, "violations": [finding(line=None)]}, URL, tools)


@pytest.mark.parametrize("complete,listed", [(False, True), (True, False)])
def test_absence_claim_requires_complete_observed_inventory(complete, listed):
    tools = observations()
    tools.inventory_complete = complete
    if not listed:
        tools.listed_files = set()
    with pytest.raises(ReportError, match="complete file inventory"):
        validate_report(
            {"repository": URL, "violations": [finding(file=None, line=None)]}, URL, tools
        )


def test_duplicates_removed_and_severity_ordered():
    first, second = (
        finding(),
        finding(
            rule_id="CFG-001",
            severity="low",
            line=9,
            description="A distinct configuration problem",
        ),
    )
    report = validate_report(
        {"repository": URL, "violations": [second, first, copy.deepcopy(first)]},
        URL,
        observations(),
    )
    assert [item["severity"] for item in report["violations"]] == ["high", "low"]


def test_secret_redacted_from_final_report(tmp_path):
    report = validate_report(
        {
            "repository": URL,
            "violations": [finding(evidence='API_KEY="do-not-include-this-literal"')],
        },
        URL,
        observations(),
    )
    output = tmp_path / "nested" / "report.json"
    write_report(report, output)
    assert "do-not-include-this-literal" not in output.read_text()
    assert json.loads(output.read_text())["repository"] == URL


def test_wrong_url_or_extra_fields_rejected():
    for report in [
        {"repository": "different", "violations": []},
        {"repository": URL, "violations": [], "extra": 1},
    ]:
        with pytest.raises(ReportError):
            validate_report(report, URL)
