"""Real local Git fixtures exercise HEAD evidence, exclusions, and tool limits."""

import json
import os
import subprocess
from pathlib import Path

import pytest

import tools as tools_module
from repository import _git_environment
from tools import MAX_FILE_BYTES, TOOL_SCHEMAS, InspectionTools


def git(root: Path, *arguments: str, input: bytes | None = None) -> bytes:
    # Fixture creation may clone our own local temporary repository. Production
    # transport policy remains HTTPS-only; this exception exists only in tests.
    environment = _git_environment()
    environment["GIT_ALLOW_PROTOCOL"] = "https:file"
    result = subprocess.run(
        [
            "git",
            "-C",
            str(root),
            "-c",
            "user.name=Test Auditor",
            "-c",
            "user.email=auditor@example.invalid",
            "-c",
            "commit.gpgsign=false",
            "-c",
            "core.autocrlf=false",
            "-c",
            "core.hooksPath=" + os.devnull,
            *arguments,
        ],
        input=input,
        capture_output=True,
        check=True,
        timeout=20,
        env=environment,
    )
    return result.stdout


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "repo"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    (root / "src").mkdir()
    (root / "README.md").write_text("# Example\nRun pytest\nMore docs\n", encoding="utf-8")
    (root / "src" / "app.py").write_text(
        'print("hello")\n# TODO: tests\n# todo: docs\n# x.* is literal\n', encoding="utf-8"
    )
    (root / ".env").write_text('PASSWORD="super-sensitive-value"\n', encoding="utf-8")
    (root / "private.pem").write_text(
        "-----BEGIN PRIVATE KEY-----\nprivate-body-line-one\nprivate-body-line-two\n-----END PRIVATE KEY-----\nafter\n",
        encoding="utf-8",
    )
    (root / "large.txt").write_bytes(b"x" * (MAX_FILE_BYTES + 1))
    (root / "binary.bin").write_bytes(b"abc\0def")
    (root / "legacy.txt").write_bytes(b"caf\xe9")
    git(root, "add", "--all")
    git(root, "commit", "-m", "Initial test snapshot")
    # Index-only objects work on Windows without granting symlink privileges.
    link_oid = (
        git(root, "hash-object", "-w", "--stdin", input=b"../../outside-secret").strip().decode()
    )
    git(root, "update-index", "--add", "--cacheinfo", f"120000,{link_oid},outside-link")
    commit = git(root, "rev-parse", "HEAD").strip().decode()
    git(root, "update-index", "--add", "--cacheinfo", f"160000,{commit},vendor/lib")
    git(root, "commit", "-m", "Track symlink and submodule without following either")
    return root


def test_inventory_is_tracked_head_and_honest_about_pagination(repo):
    (repo / "untracked.txt").write_text("ignore me")
    (repo / "README.md").write_text("dirty working tree should be ignored")
    tool = InspectionTools(repo)
    assert tool.listed_files == set()
    assert "untracked.txt" not in tool.files
    assert tool.inventory_complete
    first = tool.list_files(limit=2)
    assert tool.listed_files == {entry["path"] for entry in first["files"]}
    assert first["truncated"]
    assert first["next_offset"] == 2
    second = tool.list_files(offset=2)
    names = [entry["path"] for entry in first["files"] + second["files"]]
    assert names == tool.files
    assert tool.listed_files == set(tool.files)
    assert not second["truncated"]
    assert tool.read_file("README.md")["lines"][0]["text"] == "# Example"


def test_read_reports_original_line_numbers_and_next_page(repo):
    tool = InspectionTools(repo)
    result = tool.read_file("src/app.py", 2, 2)
    assert result["lines"] == [{"line": 2, "text": "# TODO: tests", "truncated": False}]
    assert result["next_start_line"] == 3
    assert result["truncated"]
    assert tool.observed_lines == {"src/app.py": {2}}
    final = tool.read_file("src/app.py", 3, 200)
    assert not final["truncated"]
    assert final["next_start_line"] is None
    assert tool.observed_lines["src/app.py"] == {2, 3, 4}


def test_secrets_redacted_in_reads_searches_and_partial_private_keys(repo):
    tool = InspectionTools(repo)
    read = tool.read_file(".env")
    assert "super-sensitive-value" not in json.dumps(read)
    assert "[REDACTED]" in json.dumps(read)
    search = tool.search_code("password")
    assert "super-sensitive-value" not in json.dumps(search)
    assert search["matches"][0]["line"] == 1
    middle = tool.read_file("private.pem", 2, 3)
    assert "private-body" not in json.dumps(middle)
    assert [line["line"] for line in middle["lines"]] == [2, 3]
    assert tool.search_code("private-body")["matches"] == []
    assert tool.read_file("private.pem", 5, 5)["lines"][0]["text"] == "after"


def test_search_is_literal_case_insensitive_and_tracks_only_returned_lines(repo):
    tool = InspectionTools(repo)
    first = tool.search_code("ToDo", path_prefix="src/", limit=1)
    assert first["matches"][0]["line"] == 2
    assert first["next_offset"] == 1
    assert first["truncated"]
    assert tool.observed_lines["src/app.py"] == {2}
    second = tool.search_code("TODO", path_prefix="src", offset=1, limit=1)
    assert second["matches"][0]["line"] == 3
    assert second["next_offset"] is None
    assert second["search_complete"]
    assert tool.search_code("x.*", "src")["matches"][0]["line"] == 4
    assert tool.search_code("[.*", "src")["matches"] == []


@pytest.mark.parametrize(
    "path, reason",
    [
        ("outside-link", "symlink"),
        ("vendor/lib", "submodule"),
        ("binary.bin", "binary_file"),
        ("large.txt", "large_file"),
        ("legacy.txt", "unsupported_encoding"),
    ],
)
def test_unreadable_entries_are_explicitly_skipped(repo, path, reason):
    tool = InspectionTools(repo)
    result = tool.read_file(path)
    assert result["ok"]
    assert result["skipped"]
    assert result["reason"] == reason
    assert result["lines"] == []
    assert path not in tool.observed_lines


@pytest.mark.parametrize(
    "path",
    ["../README.md", "/README.md", "C:/secret", "a\\b", ".git/config", "a/../README.md", "a\0b"],
)
def test_paths_cannot_escape_repository_or_inject_git_arguments(repo, path):
    tool = InspectionTools(repo)
    assert tool.read_file(path)["error"]["code"] == "invalid_arguments"


def test_absolute_prefix_is_rejected_and_missing_file_is_explicit(repo):
    tool = InspectionTools(repo)
    assert tool.list_files("/")["error"]["code"] == "invalid_arguments"
    assert tool.read_file("missing.txt")["error"]["code"] == "file_not_found"


def test_search_budget_reports_incomplete_result(repo, monkeypatch):
    tool = InspectionTools(repo)
    monkeypatch.setattr(tools_module, "MAX_SEARCH_BYTES", 1)
    result = tool.search_code("not present")
    assert result["matches"] == []
    assert result["budget_exhausted"]
    assert result["truncated"]
    assert not result["search_complete"]


def test_skipped_search_content_prevents_claim_of_complete_absence(repo):
    result = InspectionTools(repo).search_code("not present")
    assert result["skipped_count"] == 5
    assert not result["search_complete"]
    assert not result["budget_exhausted"]


def test_git_history_declares_limits_and_reads_bare_repositories(repo, tmp_path):
    normal = InspectionTools(repo)
    history = normal.git_log(limit=1)
    assert len(history["commits"]) == 1
    assert history["truncated"]
    assert not history["history_complete"]
    assert not history["shallow"]
    bare = tmp_path / "bare.git"
    git(repo, "clone", "--bare", str(repo), str(bare))
    tool = InspectionTools(bare)
    assert tool.files == normal.files
    assert tool.read_file("README.md")["lines"][0]["text"] == "# Example"
    assert tool.git_log()["history_complete"]


def test_dispatch_rejects_unauthorized_actions_and_malformed_arguments(repo):
    tool = InspectionTools(repo)
    assert tool.dispatch("__class__", {})["error"]["code"] == "unknown_tool"
    assert (
        tool.dispatch("read_file", {"path": "README.md", "shell": True})["error"]["code"]
        == "invalid_arguments"
    )
    assert tool.dispatch("read_file", {})["error"]["code"] == "invalid_arguments"
    assert tool.dispatch("list_files", {"limit": True})["error"]["code"] == "invalid_arguments"
    assert tool.dispatch("search_code", {"pattern": ""})["error"]["code"] == "invalid_arguments"
    assert (
        tool.dispatch("read_file", {"path": "README.md", "end_line": 501})["error"]["code"]
        == "invalid_arguments"
    )
    assert tool.dispatch("git_log", {"limit": 101})["error"]["code"] == "invalid_arguments"


def test_all_tool_schemas_are_closed_and_required():
    assert {schema["name"] for schema in TOOL_SCHEMAS} == {
        "list_files",
        "read_file",
        "search_code",
        "git_log",
    }
    for schema in TOOL_SCHEMAS:
        assert schema["strict"]
        parameters = schema["parameters"]
        assert parameters["additionalProperties"] is False
        assert set(parameters["required"]) == set(parameters["properties"])


def test_empty_repository_has_complete_empty_inventory_and_history(tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    tool = InspectionTools(root)
    assert tool.files == []
    assert tool.inventory_complete
    assert tool.list_files()["files"] == []
    assert tool.listed_files == set()
    history = tool.git_log()
    assert history["commits"] == []
    assert history["history_complete"]
    assert tool.search_code("anything")["search_complete"]


def test_snapshot_history_stays_pinned_after_new_local_commit(repo):
    tool = InspectionTools(repo)
    original = tool.git_log()["commits"][0]["hash"]
    (repo / "after-snapshot.txt").write_text("later commit")
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "Later commit")
    assert "after-snapshot.txt" not in tool.files
    assert tool.git_log()["commits"][0]["hash"] == original


def test_long_reads_use_honest_small_pages_for_provider_budgets(repo):
    (repo / "paged.txt").write_text(
        "\n".join(f"source {i}" for i in range(1, 181)), encoding="utf-8"
    )
    git(repo, "add", "--all")
    git(repo, "commit", "-m", "Add paginated source fixture")
    tool = InspectionTools(repo)
    first = tool.read_file("paged.txt", 6, 400)
    assert len(first["lines"]) == 100
    assert first["lines"][-1]["line"] == 105
    assert first["next_start_line"] == 106
    assert first["truncated"]
    assert tool.observed_lines["paged.txt"] == set(range(6, 106))
    rest = tool.read_file("paged.txt", 106, 400)
    assert rest["lines"][-1]["line"] == 180
    assert rest["next_start_line"] is None


def test_read_empty_file_records_file_observation_without_inventing_lines(repo):
    (repo / "empty.md").write_text("")
    git(repo, "add", "empty.md")
    git(repo, "commit", "-m", "Add empty file")
    tool = InspectionTools(repo)
    assert tool.read_file("empty.md")["lines"] == []
    assert tool.observed_lines["empty.md"] == set()
