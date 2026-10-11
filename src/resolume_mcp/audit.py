"""Append-only JSONL audit log of write and destructive tool calls, for post-show review."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Fields of a tool result worth keeping for review. Payload bodies are never logged.
_SUMMARY_KEYS = (
    "requires_confirmation",
    "ok",
    "status_code",
    "skipped",
    "verified",
    "value_before",
    "value_after",
    "cleared",
    "disconnected",
    "method",
    "note",
)
_MAX_ARGUMENT_CHARS = 1000


def summarize_result(result: Any) -> dict[str, Any] | None:
    """The review-relevant fields of a tool's JSON result, or None when it is not a JSON object."""
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (TypeError, ValueError):
            return None
    if not isinstance(result, dict):
        return None
    return {key: result[key] for key in _SUMMARY_KEYS if key in result}


def _compact(value: Any) -> Any:
    if isinstance(value, str) and len(value) > _MAX_ARGUMENT_CHARS:
        return value[:_MAX_ARGUMENT_CHARS] + "...[truncated]"
    return value


def record_call(
    path: str,
    *,
    tool: str,
    arguments: dict[str, Any],
    outcome: str,
    target: str,
    duration_ms: int,
    result: Any = None,
    error: str | None = None,
) -> bool:
    """Append one JSON line for a tool call. Returns False when logging is disabled (empty path) or the write failed; never raises."""
    if not path:
        return False
    now = datetime.now(timezone.utc)
    record: dict[str, Any] = {
        "ts": now.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "tool": tool,
        "target": target,
        "arguments": {name: _compact(value) for name, value in arguments.items()},
        "outcome": outcome,
        "duration_ms": duration_ms,
    }
    if error is not None:
        record["error"] = error
    else:
        summary = summarize_result(result)
        if summary is not None:
            record["summary"] = summary
    try:
        file = Path(path)
        file.parent.mkdir(parents=True, exist_ok=True)
        with file.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, default=str) + "\n")
    except OSError as exc:
        logger.warning("Could not append to the audit log %s: %s", path, exc)
        return False
    return True
