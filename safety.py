"""Redact likely credentials at every output boundary.

This is a defensive heuristic, not a complete secret scanner. Preserve variable
names and line breaks so redacted source is still useful as audit evidence.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

REDACTED = "[REDACTED]"
_KNOWN: set[str] = set()
_USAGE_COUNTS = {
    "input_tokens",
    "output_tokens",
    "total_tokens",
    "prompt_tokens",
    "completion_tokens",
    "reasoning_tokens",
    "cached_tokens",
    "audio_tokens",
    "accepted_prediction_tokens",
    "rejected_prediction_tokens",
}
_NAME = r"(?:[\w.-]*(?:api[_-]?key|secret|password|passwd|token|credential|private[_-]?key)[\w.-]*)"
_ASSIGNMENT = re.compile(
    rf"(?im)(?<![\w.-])(?P<prefix>[\"']?{_NAME}[\"']?\s*[:=]\s*)"
    r"(?P<value>\"(?:\\.|[^\"\\\r\n])*\"|'(?:\\.|[^'\\\r\n])*'|[^\s,;#}\]\r\n]+)"
)
_ENV_DEFAULT = re.compile(
    rf"(?i)(?P<prefix>(?:os\.)?(?:getenv|environ\.get)\(\s*['\"]{_NAME}['\"]\s*,\s*)"
    r"(?P<value>\"(?:\\.|[^\"\\\r\n])*\"|'(?:\\.|[^'\\\r\n])*'|[0-9]+)"
)
_YAML_BLOCK = re.compile(
    rf"(?i)^(?P<indent>[ \t]*)(?:['\"]?{_NAME}['\"]?\s*:\s*)[|>][+-]?[0-9]*\s*(?:#.*)?$"
)
_PATTERNS = [
    re.compile(
        r"-----BEGIN (?:[A-Z0-9 ]+ )?PRIVATE KEY-----.*?"
        r"(?:-----END (?:[A-Z0-9 ]+ )?PRIVATE KEY-----|\Z)",
        re.S,
    ),
    re.compile(
        r"\b(?:sk-(?:proj-|svcacct-)?[A-Za-z0-9_-]{16,}|"
        r"gsk_[A-Za-z0-9_-]{16,}|AQ\.[A-Za-z0-9_-]{24,}|"
        r"gh[pousr]_[A-Za-z0-9_]{16,}|github_pat_[A-Za-z0-9_]{16,}|"
        r"AKIA[A-Z0-9]{16}|ASIA[A-Z0-9]{16}|AIza[A-Za-z0-9_-]{30,}|"
        r"xox[baprs]-[A-Za-z0-9-]{10,})\b"
    ),
    re.compile(r"(?i)(?<=bearer )[A-Za-z0-9._~+/-]{8,}=*"),
    re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b"),
    re.compile(r"(?i)(?<=://)[^\s/:@]+:[^\s/@]+(?=@)"),
    re.compile(r"(?i)([?&](?:token|key|api_key|password|secret)=)[^&#\s]+"),
]


def register_secret(value: str | None) -> None:
    """Remember a configured secret so even an unfamiliar format is redacted."""
    if value and len(value) >= 4:
        _KNOWN.add(value)


def _assignment(match: re.Match[str]) -> str:
    value = match.group("value")
    bare = value.strip("\"'")
    quoted = value.startswith(("'", '"'))
    # Environment references and schema declarations are evidence, not values.
    if (
        not bare
        or bare.startswith(("${", "$env:", "os.getenv(", "os.environ[", "os.environ.get("))
        or bare == "[REDACTED]"
        or (not quoted and bare in {"null", "None", "true", "false", "True", "False"})
    ):
        return match.group(0)
    # Do not mistake prose about a token budget for a credential assignment.
    name = match.group("prefix").split(":", 1)[0].split("=", 1)[0].strip(" \t\"'").lower()
    if bare.isdecimal() and re.fullmatch(
        r"(?:max_|input_|output_|total_)?tokens(?:_limit|_budget)?", name
    ):
        return match.group(0)
    quote = value[0] if value.startswith(("'", '"')) else ""
    register_secret(bare)
    return match.group("prefix") + quote + REDACTED + quote


def _redact_yaml_blocks(value: str) -> str:
    lines = value.splitlines(keepends=True)
    active_indent = None
    for index, line in enumerate(lines):
        if active_indent is not None and line.strip():
            indent = line[: len(line) - len(line.lstrip(" \t"))]
            if len(indent) > active_indent:
                register_secret(line.strip())
                newline = "\r\n" if line.endswith("\r\n") else "\n" if line.endswith("\n") else ""
                lines[index] = indent + REDACTED + newline
                continue
            active_indent = None
        match = _YAML_BLOCK.match(line.rstrip("\r\n"))
        if match:
            active_indent = len(match.group("indent"))
    return "".join(lines)


def redact_text(value: str) -> str:
    for secret in sorted(_KNOWN, key=len, reverse=True):
        value = value.replace(secret, REDACTED)
    value = _redact_yaml_blocks(value)
    value = _ENV_DEFAULT.sub(_assignment, value)
    value = _ASSIGNMENT.sub(_assignment, value)
    # Also hide repeated literal occurrences learned from assignments in this text.
    for secret in sorted(_KNOWN, key=len, reverse=True):
        value = value.replace(secret, REDACTED)
    for pattern in _PATTERNS:
        if pattern is _PATTERNS[-1]:
            value = pattern.sub(lambda m: m.group(1) + REDACTED, value)
        else:
            value = pattern.sub(lambda m: REDACTED + "\n" * m.group(0).count("\n"), value)
    return value


def redact(value: Any) -> Any:
    if isinstance(value, str):
        return redact_text(value)
    if isinstance(value, Mapping):
        result = {}
        for key, item in value.items():
            name = str(key)
            if (
                re.fullmatch(_NAME, name, re.I)
                and item is not None
                and isinstance(item, (str, int, float))
                and not (name in _USAGE_COUNTS and type(item) is int and item >= 0)
                and not re.fullmatch(
                    r"(?:max_|input_|output_|total_)?tokens(?:_limit|_budget)?", name, re.I
                )
            ):
                result[redact_text(name)] = REDACTED
            else:
                result[redact_text(name)] = redact(item)
        return result
    if isinstance(value, (list, tuple)):
        return [redact(v) for v in value]
    return value
