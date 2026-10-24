"""Read-only, bounded access to an unauthenticated public GitHub repository.

Repositories are cloned bare: no files are checked out and no target code,
build scripts, hooks, or submodules are executed.
"""

from __future__ import annotations

import math
import os
import re
import signal
import subprocess
import tempfile
import threading
import time
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit


class RepositoryError(Exception):
    """A repository cannot be accessed safely or within its resource budget."""


@dataclass(frozen=True)
class GitResult:
    stdout: bytes
    stderr: bytes
    returncode: int = 0


MAX_CLONE_BYTES = 256 * 1024 * 1024


def _stop_process_tree(process: subprocess.Popen) -> None:
    """Stop our Git process and its transport helpers before temporary cleanup."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            # Git for Windows starts git-remote-https as a child. Killing only
            # git.exe leaves that helper holding files and pipes open.
            subprocess.run(
                ["taskkill", "/PID", str(process.pid), "/T", "/F"],
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=5,
                check=False,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        else:
            os.killpg(process.pid, signal.SIGKILL)
    except (OSError, subprocess.TimeoutExpired):
        pass
    if process.poll() is None:
        try:
            process.kill()
        except OSError:
            pass


def normalize_repo_url(url: str) -> str:
    """Accept only an ordinary HTTPS public github.com owner/repository URL."""
    if not isinstance(url, str) or not url or url != url.strip():
        raise RepositoryError("Use an HTTPS GitHub URL without surrounding whitespace.")
    if any(ord(character) < 33 or ord(character) == 127 for character in url):
        raise RepositoryError("Repository URLs must not contain spaces or control characters.")
    try:
        parsed = urlsplit(url)
        port = parsed.port
    except ValueError as exc:
        raise RepositoryError("The repository URL is malformed.") from exc
    if (
        parsed.scheme.lower() != "https"
        or parsed.netloc.lower() != "github.com"
        or parsed.hostname != "github.com"
        or parsed.username is not None
        or parsed.password is not None
        or port is not None
        or parsed.query
        or parsed.fragment
        or "?" in url
        or "#" in url
        or "%" in url
        or "\\" in url
    ):
        raise RepositoryError("Only https://github.com/owner/repository URLs are supported.")
    path = parsed.path.removesuffix("/")
    parts = path.split("/")
    if len(parts) != 3 or parts[0] != "":
        raise RepositoryError("Use the repository root URL, without /tree/ or /blob/ paths.")
    owner, name = parts[1:]
    if name.endswith(".git"):
        name = name[:-4]
    if (
        not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?", owner)
        or not re.fullmatch(r"[A-Za-z0-9._-]{1,100}", name)
        or name in {".", ".."}
    ):
        raise RepositoryError("The GitHub owner or repository name is invalid.")
    return f"https://github.com/{owner}/{name}"


def _git_environment() -> dict[str, str]:
    # Inherited Git settings can change the repository, transport, config, or
    # command execution. Keep ordinary OS variables, then set our own Git ones.
    env = {key: value for key, value in os.environ.items() if not key.upper().startswith("GIT_")}
    env.pop("SSH_ASKPASS", None)
    env.update(
        {
            "GIT_CONFIG_NOSYSTEM": "1",
            "GIT_CONFIG_SYSTEM": os.devnull,
            "GIT_CONFIG_GLOBAL": os.devnull,
            "GIT_TERMINAL_PROMPT": "0",
            "GCM_INTERACTIVE": "never",
            "GIT_OPTIONAL_LOCKS": "0",
            "GIT_NO_REPLACE_OBJECTS": "1",
            "GIT_ALLOW_PROTOCOL": "https",
            "GIT_PROTOCOL_FROM_USER": "0",
            "LC_ALL": "C",
        }
    )
    return env


def _directory_size_exceeds(path: Path, maximum: int) -> bool:
    total = 0
    for base, directories, files in os.walk(path, followlinks=False):
        directories[:] = [name for name in directories if not (Path(base) / name).is_symlink()]
        for name in files:
            try:
                total += (Path(base) / name).lstat().st_size
            except FileNotFoundError:
                continue  # Git atomically renames pack files while cloning.
            if total > maximum:
                return True
    return False


def _run_git(
    arguments: Sequence[str],
    *,
    timeout: float = 20,
    max_output: int = 2 * 1024 * 1024,
    size_guard: Path | None = None,
    allowed_returncodes: frozenset[int] = frozenset({0}),
) -> GitResult:
    """Run a Git builtin with bounded output/time and no shell or credentials.

    Drain both pipes concurrently, retaining at most ``max_output`` bytes per
    stream. A clone's disk usage is checked while it runs as an additional cap.
    """
    command = [
        "git",
        "--no-pager",
        "--no-replace-objects",
        "-c",
        "credential.helper=",
        "-c",
        "core.askPass=",
        "-c",
        "core.fsmonitor=false",
        "-c",
        "core.hooksPath=" + os.devnull,
        "-c",
        "protocol.allow=never",
        "-c",
        "protocol.https.allow=always",
        "-c",
        "http.followRedirects=false",
        "-c",
        "http.sslVerify=true",
        *arguments,
    ]
    try:
        process = subprocess.Popen(
            command,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=_git_environment(),
            shell=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            start_new_session=os.name != "nt",
        )
    except FileNotFoundError as exc:
        raise RepositoryError("Git is not installed or is not available on PATH.") from exc
    except OSError as exc:
        raise RepositoryError("Git could not be started.") from exc

    output_limit = threading.Event()
    buffers: list[bytearray] = [bytearray(), bytearray()]

    def drain(stream, buffer: bytearray) -> None:
        try:
            while block := stream.read(65536):
                remaining = max_output - len(buffer)
                buffer.extend(block[: max(remaining, 0)])
                if len(block) > remaining:
                    output_limit.set()
                    _stop_process_tree(process)
                    break
        finally:
            stream.close()

    readers = [
        threading.Thread(target=drain, args=(process.stdout, buffers[0]), daemon=True),
        threading.Thread(target=drain, args=(process.stderr, buffers[1]), daemon=True),
    ]
    for reader in readers:
        reader.start()
    deadline = time.monotonic() + timeout
    failure: str | None = None
    try:
        while process.poll() is None:
            if time.monotonic() >= deadline:
                failure = "Git timed out. Try a smaller repository or check your connection."
                break
            if size_guard is not None and _directory_size_exceeds(size_guard, MAX_CLONE_BYTES):
                failure = "The repository exceeds the 256 MiB clone disk budget."
                break
            try:
                process.wait(timeout=0.15)
            except subprocess.TimeoutExpired:
                pass
    finally:
        if process.poll() is None:
            _stop_process_tree(process)
        process.wait()
        for reader in readers:
            reader.join(timeout=5)
    if failure:
        raise RepositoryError(failure)
    if output_limit.is_set():
        raise RepositoryError("Git output exceeded the allowed size; this repository is too large.")
    if process.returncode not in allowed_returncodes:
        # Remote stderr may contain target-controlled strings or secrets. Keep
        # diagnostics generic; callers may log their own sanitized context.
        raise RepositoryError(
            "Git could not read the repository. Check that it is public, exists, "
            "and is reachable over HTTPS."
        )
    return GitResult(bytes(buffers[0]), bytes(buffers[1]), process.returncode)


@contextmanager
def cloned_repository(url: str, timeout: float = 120) -> Iterator[Path]:
    """Yield a temporary bare clone and always remove it when inspection ends."""
    canonical = normalize_repo_url(url)
    if (
        isinstance(timeout, bool)
        or not isinstance(timeout, (int, float))
        or not math.isfinite(timeout)
        or not 0 < timeout <= 600
    ):
        raise RepositoryError("Clone timeout must be a finite positive number up to 600 seconds.")
    with tempfile.TemporaryDirectory(prefix="devops-audit-") as temporary:
        temporary_root = Path(temporary)
        target = temporary_root / "repository.git"
        _run_git(
            [
                "clone",
                "--quiet",
                "--bare",
                "--depth",
                "100",
                "--single-branch",
                "--no-tags",
                "--template=",
                "--",
                canonical + ".git",
                str(target),
            ],
            timeout=timeout,
            size_guard=temporary_root,
        )
        if _directory_size_exceeds(temporary_root, MAX_CLONE_BYTES):
            raise RepositoryError("The repository exceeds the 256 MiB clone disk budget.")
        yield target
