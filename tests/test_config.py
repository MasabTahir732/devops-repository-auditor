from types import SimpleNamespace

import pytest

from config import ConfigError, Settings


@pytest.fixture(autouse=True)
def clean_settings_environment(monkeypatch):
    for name in [
        "LLM_PROVIDER",
        "LLM_MODEL",
        "GEMINI_API_KEY",
        "GROQ_API_KEY",
        "OPENAI_API_KEY",
        "GEMINI_MODEL",
        "GROQ_MODEL",
        "OPENAI_MODEL",
        "AUDIT_MAX_STEPS",
        "AUDIT_TIMEOUT",
        "AUDIT_CLONE_TIMEOUT",
    ]:
        monkeypatch.delenv(name, raising=False)


def args(**updates):
    return SimpleNamespace(
        provider=None, model=None, max_steps=None, timeout=None, clone_timeout=None, **updates
    )


@pytest.mark.parametrize(
    "provider,model",
    [
        ("gemini", "gemini-3.8-flash"),
        ("groq", "openai/gpt-oss-120b"),
        ("openai", "gpt-4.1-mini"),
    ],
)
def test_only_selected_provider_key_is_needed_and_hidden(monkeypatch, provider, model):
    monkeypatch.setenv("LLM_PROVIDER", provider)
    monkeypatch.setenv(provider.upper() + "_API_KEY", "test-configuration-key-123456")
    result = Settings.from_environment(args())
    assert result.provider == provider
    assert result.model == model
    assert "test-configuration-key" not in repr(result)


def test_default_gemini_missing_key_is_actionable():
    with pytest.raises(ConfigError, match="GEMINI_API_KEY is missing"):
        Settings.from_environment(args())


def test_model_precedence_cli_then_generic_then_provider(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-for-model-precedence")
    monkeypatch.setenv("GEMINI_MODEL", "provider-model")
    assert Settings.from_environment(args()).model == "provider-model"
    monkeypatch.setenv("LLM_MODEL", "generic-model")
    assert Settings.from_environment(args()).model == "generic-model"
    command_args = args()
    command_args.model = "cli-model"
    assert Settings.from_environment(command_args).model == "cli-model"


@pytest.mark.parametrize(
    "name,value",
    [
        ("AUDIT_MAX_STEPS", "0"),
        ("AUDIT_MAX_STEPS", "1.2"),
        ("AUDIT_TIMEOUT", "nan"),
        ("AUDIT_TIMEOUT", "inf"),
        ("AUDIT_TIMEOUT", "-1"),
        ("AUDIT_CLONE_TIMEOUT", "abc"),
    ],
)
def test_invalid_numbers_fail_before_network(monkeypatch, name, value):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-for-invalid-numbers")
    monkeypatch.setenv(name, value)
    with pytest.raises(ConfigError):
        Settings.from_environment(args())


def test_invalid_provider_is_not_a_custom_credential_endpoint(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "https://not-a-provider.invalid")
    with pytest.raises(ConfigError, match="LLM_PROVIDER"):
        Settings.from_environment(args())
