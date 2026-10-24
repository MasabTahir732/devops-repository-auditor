"""Repository access tests use mocks/local Git only; never a network call."""

import subprocess
import sys
import time
from pathlib import Path

import pytest

import repository
from repository import RepositoryError, cloned_repository, normalize_repo_url


@pytest.mark.parametrize(
    "url, expected",
    [
        ("https://github.com/example/project", "https://github.com/example/project"),
        ("https://github.com/example/project.git/", "https://github.com/example/project"),
        ("https://GITHUB.COM/Example/my-project_2", "https://github.com/Example/my-project_2"),
    ],
)
def test_normalize_root_url(url, expected):
    assert normalize_repo_url(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "http://github.com/owner/repo",
        "https://evil.example/owner/repo",
        "https://github.com.evil.example/owner/repo",
        "git@github.com:owner/repo.git",
        "file:///tmp/repo",
        "https://user:secret@github.com/owner/repo",
        "https://github.com:443/owner/repo",
        "https://github.com/owner/repo/tree/main",
        "https://github.com/owner/repo?token=secret",
        "https://github.com/owner/repo#readme",
        "https://github.com/owner/%2E%2E",
        "https://github.com/owner/..",
        " https://github.com/owner/repo",
        "https://github.com/owner/repo\n",
        "https://github.com/owner/repo?",
        "https://github.com/owner/repo#",
        "https://github.com/owner\\repo",
        "https://github.com/-owner/repo",
        "https://github.com/owner/",
        "https://github.com/owner/repo//",
        None,
    ],
)
def test_reject_nonpublic_or_ambiguous_urls(url):
    with pytest.raises(RepositoryError):
        normalize_repo_url(url)


def test_clone_is_bare_bounded_and_cleaned_up(monkeypatch):
    captured = {}

    def fake_git(arguments, **kwargs):
        captured.update(arguments=arguments, kwargs=kwargs)
        Path(arguments[-1]).mkdir()
        return repository.GitResult(b"", b"")

    monkeypatch.setattr(repository, "_run_git", fake_git)
    with cloned_repository("https://github.com/owner/repo.git", timeout=42) as root:
        assert root.is_dir()
        assert root.name == "repository.git"
        assert "--bare" in captured["arguments"]
        assert "--depth" in captured["arguments"]
        assert "--no-tags" in captured["arguments"]
        assert "--template=" in captured["arguments"]
        assert captured["arguments"][-2] == "https://github.com/owner/repo.git"
        assert captured["kwargs"]["timeout"] == 42
        assert captured["kwargs"]["size_guard"] == root.parent
    assert not root.exists()


def test_clone_cleanup_after_failure_inside_context(monkeypatch):
    def fake_git(arguments, **kwargs):
        Path(arguments[-1]).mkdir()
        return repository.GitResult(b"", b"")

    monkeypatch.setattr(repository, "_run_git", fake_git)
    with pytest.raises(RuntimeError), cloned_repository("https://github.com/owner/repo") as root:
        raise RuntimeError("inspection failed")
    assert not root.exists()


@pytest.mark.parametrize("timeout", [0, -1, 601, True, "120", float("nan"), float("inf")])
def test_invalid_timeout_is_rejected_before_clone(timeout):
    with pytest.raises(RepositoryError, match="timeout"):
        with cloned_repository("https://github.com/owner/repo", timeout=timeout):
            pytest.fail("Invalid timeout should not reach a clone")


@pytest.mark.parametrize("timeout", [120.0, 0.5, 600])
def test_positive_floating_clone_timeouts_are_supported(monkeypatch, timeout):
    def fake_git(arguments, **kwargs):
        assert kwargs["timeout"] == timeout
        Path(arguments[-1]).mkdir()
        return repository.GitResult(b"", b"")

    monkeypatch.setattr(repository, "_run_git", fake_git)
    with cloned_repository("https://github.com/owner/repo", timeout=timeout) as root:
        assert root.is_dir()


def test_timeout_stops_started_process(monkeypatch):
    real_popen = subprocess.Popen
    launched = []

    def sleeping_process(arguments, **kwargs):
        if arguments[0] == "taskkill":
            return real_popen(arguments, **kwargs)
        process = real_popen([sys.executable, "-c", "import time; time.sleep(30)"], **kwargs)
        launched.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", sleeping_process)
    started = time.monotonic()
    try:
        with pytest.raises(RepositoryError, match="timed out"):
            repository._run_git(["--version"], timeout=0.01)
        assert launched[0].poll() is not None
        assert time.monotonic() - started < 10
    finally:
        for process in launched:
            if process.poll() is None:
                process.kill()
            process.wait()


def test_inherited_git_settings_cannot_change_access(monkeypatch):
    monkeypatch.setenv("GIT_DIR", "outside-repository")
    monkeypatch.setenv("GIT_CONFIG_COUNT", "1")
    monkeypatch.setenv("GIT_CONFIG_KEY_0", "credential.helper")
    monkeypatch.setenv("GIT_CONFIG_VALUE_0", "dangerous-helper")
    monkeypatch.setenv("GIT_ASKPASS", "dangerous-askpass")
    monkeypatch.setenv("SSH_ASKPASS", "dangerous-ssh-askpass")
    env = repository._git_environment()
    assert "GIT_DIR" not in env
    assert "GIT_CONFIG_COUNT" not in env
    assert "GIT_ASKPASS" not in env
    assert "SSH_ASKPASS" not in env
    assert env["GIT_TERMINAL_PROMPT"] == "0"
    assert env["GIT_ALLOW_PROTOCOL"] == "https"
    assert env["GIT_CONFIG_NOSYSTEM"] == "1"


def test_git_output_budget_is_enforced():
    with pytest.raises(RepositoryError, match="output exceeded"):
        repository._run_git(["--version"], max_output=1)


def test_missing_git_has_actionable_error(monkeypatch):
    def missing_git(*args, **kwargs):
        raise FileNotFoundError("git")

    monkeypatch.setattr(subprocess, "Popen", missing_git)
    with pytest.raises(RepositoryError, match="not installed"):
        repository._run_git(["--version"])


def test_git_failure_does_not_expose_remote_stderr():
    with pytest.raises(RepositoryError) as caught:
        repository._run_git(["--not-a-git-option-secret-123"])
    assert "secret-123" not in str(caught.value)


def test_directory_budget_checks_files_without_following_symlinks(tmp_path):
    (tmp_path / "data").write_bytes(b"x" * 20)
    assert repository._directory_size_exceeds(tmp_path, 19)
    assert not repository._directory_size_exceeds(tmp_path, 20)
