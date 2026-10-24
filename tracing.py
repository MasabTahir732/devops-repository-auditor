"""Optional JSONL record of observable decisions and tool results, never raw reasoning."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from safety import redact


class Trace:
    def __init__(self, path: Path | None = None):
        self._stream = None
        if path is not None:
            path.parent.mkdir(parents=True, exist_ok=True)
            self._stream = path.open("w", encoding="utf-8")

    def write(self, event: str, **details) -> None:
        if self._stream is not None:
            record = redact({"time": datetime.now(UTC).isoformat(), "event": event, **details})
            self._stream.write(json.dumps(record, ensure_ascii=True, allow_nan=False) + "\n")
            self._stream.flush()

    def close(self) -> None:
        if self._stream is not None:
            self._stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
