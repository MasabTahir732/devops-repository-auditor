import json
import time

import pytest

from safety import REDACTED, redact, redact_text, register_secret


@pytest.mark.parametrize(
    "source,hidden",
    [
        ('API_KEY = "an-unusual-provider-credential"', "an-unusual-provider-credential"),
        ("password: hunter-example-password", "hunter-example-password"),
        ('{"client_secret": "example-sensitive-value"}', "example-sensitive-value"),
        ('PASSWORD = "12345678"', "12345678"),
        ("password: 24681357", "24681357"),
        ("Authorization: Bearer example-authorization-token", "example-authorization-token"),
        ("https://user:private-pass@host.test/path", "private-pass"),
        ("https://host.test/path?token=confidentialvalue", "confidentialvalue"),
        ("ghp_" + "A" * 36, "ghp_" + "A" * 36),
        ("gsk_" + "A" * 40, "gsk_" + "A" * 40),
        ("AQ." + "A" * 40, "AQ." + "A" * 40),
    ],
)
def test_redaction_of_common_formats(source, hidden):
    result = redact_text(source)
    assert hidden not in result
    assert REDACTED in result


def test_private_key_redacted_before_line_slicing_and_preserves_line_count():
    source = (
        "header\n-----BEGIN PRIVATE KEY-----\nFAKE-KEY-PAYLOAD\n-----END PRIVATE KEY-----\nfooter"
    )
    result = redact_text(source)
    assert "FAKE-KEY-PAYLOAD" not in result
    assert result.count("\n") == source.count("\n")
    assert result.splitlines()[-1] == "footer"


def test_environment_references_remain_observable():
    for text in [
        "API_KEY=${MY_KEY}",
        "token: ${{ secrets.GITHUB_TOKEN }}",
        'password = os.getenv("DB_PASSWORD")',
    ]:
        assert redact_text(text) == text


def test_registered_secret_is_removed_from_nested_outputs():
    value = "unstructured-test-credential-987654321"
    register_secret(value)
    result = redact({"outer": [{"message": f"Exception contained {value}"}]})
    assert value not in json.dumps(result)
    assert REDACTED in json.dumps(result)


def test_source_evidence_remains_useful():
    assert (
        redact_text("continue-on-error: true\nDEBUG = True")
        == "continue-on-error: true\nDEBUG = True"
    )


def test_structured_credential_fields_are_redacted_without_hiding_usage_counts():
    result = redact(
        {
            "password": 12345678,
            "api_key": "sensitive-test-value",
            "input_tokens": 100,
            "output_tokens": 50,
        }
    )
    assert result["password"] == REDACTED
    assert result["api_key"] == REDACTED
    assert result["input_tokens"] == 100
    assert result["output_tokens"] == 50


def test_provider_usage_counters_stay_numeric_but_secrets_stay_hidden():
    result = redact(
        {
            "prompt_tokens": 321,
            "completion_tokens": 123,
            "reasoning_tokens": 12,
            "token": 12345678,
            "prompt_tokens_override": "sensitive-value",
        }
    )
    assert result["prompt_tokens"] == 321
    assert result["completion_tokens"] == 123
    assert result["reasoning_tokens"] == 12
    assert result["token"] == REDACTED
    assert result["prompt_tokens_override"] == REDACTED


@pytest.mark.parametrize(
    "source",
    [
        'PASSWORD = os.getenv("PASSWORD", "sensitive-default-literal")',
        'PASSWORD = os.environ.get("PASSWORD", "sensitive-default-literal")',
        'value = os.getenv("DB_PASSWORD", "sensitive-default-literal")',
    ],
)
def test_environment_fallback_credentials_are_hidden(source):
    assert "sensitive-default-literal" not in redact_text(source)
    assert REDACTED in redact_text(source)


def test_escaped_quotes_do_not_leave_credential_suffix_visible():
    value = 'PASSWORD = "escaped\\"credential-suffix"'
    assert "credential-suffix" not in redact_text(value)


def test_repeated_literal_in_same_text_is_hidden():
    value = 'PASSWORD="repeat-sensitive-value"\n# copied repeat-sensitive-value'
    assert "repeat-sensitive-value" not in redact_text(value)


def test_yaml_block_credentials_hidden_without_changing_line_numbers():
    value = "database:\n  password: |-\n    block-credential-literal\n    another-sensitive-line\n  debug: false\n"
    result = redact_text(value)
    assert "block-credential-literal" not in result
    assert "another-sensitive-line" not in result
    assert result.count("\n") == value.count("\n")
    assert "  debug: false" in result


def test_long_benign_tokens_redact_without_pathological_backtracking():
    source = "payload = " + "x" * 50000
    start = time.perf_counter()
    assert redact_text(source) == source
    assert time.perf_counter() - start < 2.0
