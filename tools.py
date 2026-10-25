"""The agent's four read-only tools, reading tracked HEAD blobs through Git."""

from __future__ import annotations

import re
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from pathlib import Path
from typing import Any

from repository import RepositoryError, _run_git
from safety import redact, redact_text

MAX_FILE_BYTES = 512 * 1024
MAX_LINE_CHARACTERS = 2000
MAX_READ_PAGE_LINES = 100
MAX_INVENTORY_FILES = 100_000
MAX_SEARCH_BYTES = 8 * 1024 * 1024
MAX_SEARCH_FILES = 2000
MAX_SEARCH_SECONDS = 15
MAX_CACHE_BYTES = 8 * 1024 * 1024


class _ToolInputError(ValueError):
    pass


def _integer(value: Any, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise _ToolInputError(f"{name} must be an integer from {minimum} to {maximum}.")
    return value


def _path(value: Any, *, allow_empty: bool = False, prefix: bool = False) -> str:
    if not isinstance(value, str):
        raise _ToolInputError("Paths must be strings relative to the repository root.")
    if prefix and value != "/":
        value = value.removesuffix("/")
    if not value and allow_empty:
        return value
    if (
        not value
        or len(value) > 4096
        or value.startswith("/")
        or "\\" in value
        or ":" in value
        or any(ord(character) < 32 or ord(character) == 127 for character in value)
        or any(part in {"", ".", "..", ".git"} for part in value.split("/"))
    ):
        raise _ToolInputError(
            "Use a relative repository path without traversal or special components."
        )
    return value


def _safe_result(function: Callable) -> Callable:
    @wraps(function)
    def wrapped(*args, **kwargs) -> dict[str, Any]:
        try:
            return redact(function(*args, **kwargs))
        except _ToolInputError as exc:
            return redact(
                {"ok": False, "error": {"code": "invalid_arguments", "message": str(exc)}}
            )
        except RepositoryError as exc:
            return redact({"ok": False, "error": {"code": "repository_error", "message": str(exc)}})

    return wrapped


@dataclass(frozen=True)
class _Entry:
    path: str
    mode: str
    kind: str
    oid: str
    size: int | None

    @property
    def skip_reason(self) -> str | None:
        if self.mode == "120000":
            return "symlink"
        if self.mode == "160000" or self.kind == "commit":
            return "submodule"
        if self.kind != "blob" or self.mode not in {"100644", "100755"}:
            return "unsupported_entry"
        if self.size is None or self.size > MAX_FILE_BYTES:
            return "large_file"
        try:
            _path(self.path)
        except _ToolInputError:
            return "unsupported_path"
        return None


class InspectionTools:
    """Inspect a bare or ordinary local Git repository's tracked HEAD snapshot.

    Missing-file conclusions are valid only when ``inventory_complete`` is
    true. ``observed_lines`` records the original line numbers actually returned
    by read_file/search_code; it is useful for validating report evidence.
    """

    def __init__(self, root: Path):
        self.root = Path(root).resolve()
        if not self.root.is_dir():
            raise RepositoryError("The local repository directory does not exist.")
        self.observed_lines: dict[str, set[int]] = {}
        self.listed_files: set[str] = set()
        self._cache: OrderedDict[str, tuple[list[str] | None, str | None, int]] = OrderedDict()
        self._cache_bytes = 0
        self.is_shallow = self._git(["rev-parse", "--is-shallow-repository"]).strip() == b"true"
        head = _run_git(
            ["-C", str(self.root), "rev-parse", "--verify", "--quiet", "HEAD^{commit}"],
            timeout=15,
            allowed_returncodes=frozenset({0, 1}),
        )
        self.head_commit = head.stdout.strip().decode("ascii") if head.returncode == 0 else None
        if self.head_commit is None:
            if self._git(["for-each-ref", "--format=%(objectname)"]):
                raise RepositoryError("The repository's default branch has no valid HEAD commit.")
            raw = b""
        else:
            if not re.fullmatch(r"[0-9a-f]{40,64}", self.head_commit):
                raise RepositoryError("Git returned an invalid HEAD commit identifier.")
            raw = self._git(
                ["ls-tree", "--full-tree", "-r", "-z", "-l", self.head_commit],
                max_output=32 * 1024 * 1024,
            )
        records = raw.split(b"\0")
        self.inventory_complete = len(records) - 1 <= MAX_INVENTORY_FILES
        self._entries: dict[str, _Entry] = {}
        for record in records[:MAX_INVENTORY_FILES]:
            if not record:
                continue
            try:
                metadata, raw_path = record.split(b"\t", 1)
                mode, kind, oid, size = metadata.split()
                path = raw_path.decode("utf-8", errors="strict")
                entry = _Entry(
                    path,
                    mode.decode("ascii"),
                    kind.decode("ascii"),
                    oid.decode("ascii"),
                    None if size == b"-" else int(size),
                )
                if not re.fullmatch(r"[0-9a-f]{40,64}", entry.oid):
                    raise ValueError("Invalid Git object identifier")
            except (UnicodeError, ValueError):
                # A filename we cannot represent safely makes absence claims
                # unreliable. Continue inspecting the remaining valid entries.
                self.inventory_complete = False
                continue
            self._entries[path] = entry
        self.files = sorted(self._entries)

    def _git(self, arguments: list[str], *, max_output: int = 2 * 1024 * 1024) -> bytes:
        return _run_git(
            ["-C", str(self.root), *arguments], timeout=15, max_output=max_output
        ).stdout

    def _text(self, entry: _Entry) -> tuple[list[str] | None, str | None]:
        if entry.skip_reason:
            return None, entry.skip_reason
        if entry.oid in self._cache:
            self._cache.move_to_end(entry.oid)
            lines, reason, _ = self._cache[entry.oid]
            return lines, reason
        blob = self._git(["cat-file", "blob", entry.oid], max_output=MAX_FILE_BYTES)
        if b"\0" in blob:
            lines, reason = None, "binary_file"
        else:
            try:
                # Redact before slicing or searching: a request for the middle
                # of a multiline private key must never expose its payload.
                lines, reason = (
                    redact_text(blob.decode("utf-8-sig", errors="strict")).splitlines(),
                    None,
                )
            except UnicodeDecodeError:
                lines, reason = None, "unsupported_encoding"
        weight = len(blob)
        self._cache[entry.oid] = (lines, reason, weight)
        self._cache_bytes += weight
        while self._cache_bytes > MAX_CACHE_BYTES or len(self._cache) > 256:
            _, (_, _, removed_weight) = self._cache.popitem(last=False)
            self._cache_bytes -= removed_weight
        return lines, reason

    def _line(self, path: str, number: int, text: str) -> dict[str, Any]:
        sanitized = redact_text(text)
        self.observed_lines.setdefault(path, set()).add(number)
        return {
            "line": number,
            "text": sanitized[:MAX_LINE_CHARACTERS],
            "truncated": len(sanitized) > MAX_LINE_CHARACTERS,
        }

    @_safe_result
    def list_files(self, prefix: str = "", offset: int = 0, limit: int = 500) -> dict[str, Any]:
        prefix = _path(prefix, allow_empty=True, prefix=True)
        offset = _integer(offset, "offset", 0, MAX_INVENTORY_FILES)
        limit = _integer(limit, "limit", 1, 500)
        paths = [path for path in self.files if not prefix or path.startswith(prefix)]
        selected = paths[offset : offset + limit]
        self.listed_files.update(selected)
        entries = []
        for path in selected:
            entry = self._entries[path]
            entries.append(
                {
                    "path": path,
                    "type": "symlink"
                    if entry.mode == "120000"
                    else "submodule"
                    if entry.mode == "160000"
                    else "file",
                    "size_bytes": entry.size,
                    "readable": entry.skip_reason is None,
                    "skip_reason": entry.skip_reason,
                }
            )
        more = offset + len(selected) < len(paths)
        return {
            "ok": True,
            "files": entries,
            "total_files": len(paths),
            "prefix": prefix,
            "offset": offset,
            "next_offset": offset + len(selected) if more else None,
            "truncated": more or not self.inventory_complete,
            "inventory_complete": self.inventory_complete,
            "scope": "tracked files at HEAD; untracked files and submodule contents are excluded",
        }

    @_safe_result
    def read_file(self, path: str, start_line: int = 1, end_line: int = 200) -> dict[str, Any]:
        path = _path(path)
        start_line = _integer(start_line, "start_line", 1, 10_000_000)
        end_line = _integer(end_line, "end_line", 1, 10_000_000)
        if end_line < start_line or end_line - start_line + 1 > 500:
            raise _ToolInputError(
                "Read at most 500 lines, with end_line greater than or equal to start_line."
            )
        if path not in self._entries:
            return {
                "ok": False,
                "error": {
                    "code": "file_not_found",
                    "message": "Path is absent from the cached HEAD inventory.",
                },
                "path": path,
            }
        entry = self._entries[path]
        lines, reason = self._text(entry)
        if reason:
            return {
                "ok": True,
                "path": path,
                "skipped": True,
                "reason": reason,
                "size_bytes": entry.size,
                "lines": [],
                "truncated": False,
            }
        assert lines is not None
        # An empty file is still inspected evidence: file-wide findings may
        # cite it with line=null, while no invented positive line is allowed.
        self.observed_lines.setdefault(path, set())
        stop = min(end_line, len(lines), start_line + MAX_READ_PAGE_LINES - 1)
        result = [
            self._line(path, index + 1, lines[index]) for index in range(start_line - 1, stop)
        ]
        more = stop < len(lines)
        return {
            "ok": True,
            "path": path,
            "skipped": False,
            "encoding": "utf-8",
            "start_line": start_line,
            "end_line": stop,
            "total_lines": len(lines),
            "lines": result,
            "next_start_line": stop + 1 if more else None,
            "truncated": more or any(line["truncated"] for line in result),
        }

    @_safe_result
    def search_code(
        self, pattern: str, path_prefix: str = "", offset: int = 0, limit: int = 50
    ) -> dict[str, Any]:
        if (
            not isinstance(pattern, str)
            or not 1 <= len(pattern) <= 2000
            or any(character in pattern for character in "\0\r\n")
        ):
            raise _ToolInputError(
                "pattern must be 1 to 2000 characters on one line; it is a literal, not a regular expression."
            )
        path_prefix = _path(path_prefix, allow_empty=True, prefix=True)
        offset = _integer(offset, "offset", 0, MAX_INVENTORY_FILES)
        limit = _integer(limit, "limit", 1, 100)
        paths = [path for path in self.files if not path_prefix or path.startswith(path_prefix)]
        needle = pattern.casefold()
        matches: list[dict[str, Any]] = []
        skipped: list[dict[str, str]] = []
        skipped_count = scanned = scanned_bytes = seen_matches = visited = 0
        search_complete = self.inventory_complete
        more_matches = False
        budget_exhausted = False
        started = time.monotonic()
        for path in paths:
            entry = self._entries[path]
            if scanned >= MAX_SEARCH_FILES or time.monotonic() - started >= MAX_SEARCH_SECONDS:
                search_complete = False
                budget_exhausted = True
                break
            if entry.skip_reason is None and scanned_bytes + (entry.size or 0) > MAX_SEARCH_BYTES:
                search_complete = False
                budget_exhausted = True
                break
            visited += 1
            lines, reason = self._text(entry)
            if reason:
                skipped_count += 1
                if len(skipped) < 100:
                    skipped.append({"path": path, "reason": reason})
                continue
            scanned += 1
            scanned_bytes += entry.size or 0
            assert lines is not None
            for number, text in enumerate(lines, 1):
                if needle not in text.casefold():
                    continue
                seen_matches += 1
                if seen_matches <= offset:
                    continue
                if len(matches) == limit:
                    more_matches = True
                    search_complete = False
                    break
                matches.append({"path": path, **self._line(path, number, text)})
            if more_matches:
                break
        # Skipped entries are outside the searchable content scope. Be explicit
        # so a zero-match result is never represented as proof of total absence.
        if skipped_count:
            search_complete = False
        return {
            "ok": True,
            "pattern": pattern,
            "literal": True,
            "case_sensitive": False,
            "path_prefix": path_prefix,
            "matches": matches,
            "offset": offset,
            "next_offset": offset + len(matches) if more_matches else None,
            "truncated": more_matches
            or budget_exhausted
            or any(match["truncated"] for match in matches),
            "search_complete": search_complete,
            "inventory_complete": self.inventory_complete,
            "scanned_files": scanned,
            "visited_files": visited,
            "candidate_files": len(paths),
            "scanned_bytes": scanned_bytes,
            "skipped_count": skipped_count,
            "skipped": skipped,
            "skipped_list_truncated": skipped_count > len(skipped),
            "budget_exhausted": budget_exhausted,
            "note": "Search covers readable UTF-8 tracked HEAD files within the reported budgets. Narrow path_prefix if a budget is exhausted.",
        }

    @_safe_result
    def git_log(self, limit: int = 20) -> dict[str, Any]:
        limit = _integer(limit, "limit", 1, 100)
        raw = (
            self._git(
                [
                    "log",
                    "--no-show-signature",
                    "-n",
                    str(limit + 1),
                    "--format=%H%x00%aI%x00%s%x00",
                    self.head_commit,
                ]
            )
            if self.head_commit is not None
            else b""
        )
        fields = raw.split(b"\0")
        commits = []
        for index in range(0, len(fields) - 2, 3):
            commit_hash = fields[index].strip().decode("ascii", errors="replace")
            if not re.fullmatch(r"[0-9a-f]{40,64}", commit_hash):
                raise RepositoryError("Git returned an invalid commit identifier.")
            subject = redact_text(fields[index + 2].decode("utf-8", errors="replace"))
            commits.append(
                {
                    "hash": commit_hash,
                    "date": fields[index + 1].decode("ascii", errors="replace"),
                    "subject": subject[:MAX_LINE_CHARACTERS],
                    "subject_truncated": len(subject) > MAX_LINE_CHARACTERS,
                }
            )
        more = len(commits) > limit
        return {
            "ok": True,
            "commits": commits[:limit],
            "shallow": self.is_shallow,
            "truncated": more,
            "history_complete": not self.is_shallow and not more,
            "note": "Only the cloned branch is inspected; a depth-100 clone may omit older commits and other branches.",
        }

    def dispatch(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Allow only these four functions and their documented arguments."""
        allowed = {
            "list_files": {"prefix", "offset", "limit"},
            "read_file": {"path", "start_line", "end_line"},
            "search_code": {"pattern", "path_prefix", "offset", "limit"},
            "git_log": {"limit"},
        }
        if not isinstance(name, str) or name not in allowed:
            return {
                "ok": False,
                "error": {"code": "unknown_tool", "message": "The requested tool is not allowed."},
            }
        if (
            not isinstance(arguments, dict)
            or any(not isinstance(key, str) for key in arguments)
            or set(arguments) - allowed[name]
        ):
            return {
                "ok": False,
                "error": {
                    "code": "invalid_arguments",
                    "message": "Tool arguments must be an object containing only documented parameters.",
                },
            }
        try:
            return getattr(self, name)(**arguments)
        except TypeError:
            return {
                "ok": False,
                "error": {
                    "code": "invalid_arguments",
                    "message": "A required tool argument is missing or invalid.",
                },
            }


def _schema(name: str, description: str, properties: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "function",
        "name": name,
        "description": description,
        "strict": True,
        "parameters": {
            "type": "object",
            "properties": properties,
            "required": list(properties),
            "additionalProperties": False,
        },
    }


TOOL_SCHEMAS = [
    _schema(
        "list_files",
        "List tracked HEAD files and sizes. Follow next_offset for all pages; prefix is a literal path prefix. Submodules and symlinks are never followed.",
        {
            "prefix": {
                "type": "string",
                "description": "Relative path prefix, or empty string for all files.",
            },
            "offset": {"type": "integer", "minimum": 0, "maximum": MAX_INVENTORY_FILES},
            "limit": {"type": "integer", "minimum": 1, "maximum": 500},
        },
    ),
    _schema(
        "read_file",
        "Read UTF-8 tracked HEAD contents with original line numbers and redacted secrets. Request a range of at most 500 lines; results paginate at 100 lines. Follow next_start_line when necessary.",
        {
            "path": {
                "type": "string",
                "description": "Exact relative path returned by list_files.",
            },
            "start_line": {"type": "integer", "minimum": 1, "maximum": 10_000_000},
            "end_line": {"type": "integer", "minimum": 1, "maximum": 10_000_000},
        },
    ),
    _schema(
        "search_code",
        "Find literal case-insensitive text in readable UTF-8 HEAD files. This is not regex. Results identify original lines; narrow the prefix when search budgets are exhausted.",
        {
            "pattern": {"type": "string", "minLength": 1, "maxLength": 2000},
            "path_prefix": {
                "type": "string",
                "description": "Relative literal path prefix, or empty string.",
            },
            "offset": {"type": "integer", "minimum": 0, "maximum": MAX_INVENTORY_FILES},
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        },
    ),
    _schema(
        "git_log",
        "Inspect recent commit hashes, dates, and subjects. The output declares shallow or truncated history; do not infer complete project history from a shallow clone.",
        {
            "limit": {"type": "integer", "minimum": 1, "maximum": 100},
        },
    ),
]
