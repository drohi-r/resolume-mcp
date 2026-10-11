import json
from pathlib import Path

from resolume_mcp.audit import record_call, summarize_result


def _records(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_record_call_appends_jsonl_and_creates_parent(tmp_path):
    log = tmp_path / "Logs" / "audit.jsonl"

    assert record_call(
        str(log),
        tool="clear_clip",
        arguments={"layer_index": 1, "clip_index": 2, "confirm_destructive": False},
        outcome="confirmation_required",
        target="http://127.0.0.1:8080",
        duration_ms=3,
        result='{"action": "clear_clip", "requires_confirmation": true, "message": "..."}',
    ) is True
    record_call(
        str(log),
        tool="trigger_clip",
        arguments={"layer_index": 1, "clip_index": 2},
        outcome="ok",
        target="http://127.0.0.1:8080",
        duration_ms=12,
        result='{"ok": true, "status_code": 204, "body": {"huge": "payload"}}',
    )

    first, second = _records(log)
    assert first["tool"] == "clear_clip"
    assert first["outcome"] == "confirmation_required"
    assert first["arguments"] == {"layer_index": 1, "clip_index": 2, "confirm_destructive": False}
    assert first["summary"] == {"requires_confirmation": True}
    assert first["target"] == "http://127.0.0.1:8080"
    assert first["duration_ms"] == 3
    assert first["ts"].endswith("Z")
    assert second["summary"] == {"ok": True, "status_code": 204}


def test_record_call_is_a_noop_when_disabled(tmp_path):
    assert record_call("", tool="x", arguments={}, outcome="ok", target="t", duration_ms=0) is False
    assert list(tmp_path.iterdir()) == []


def test_record_call_truncates_long_arguments(tmp_path):
    log = tmp_path / "audit.jsonl"
    record_call(str(log), tool="insert_clip", arguments={"body_json": "x" * 5000}, outcome="ok", target="t", duration_ms=0)
    (record,) = _records(log)
    assert record["arguments"]["body_json"].endswith("...[truncated]")
    assert len(record["arguments"]["body_json"]) < 1100


def test_record_call_records_errors_without_a_summary(tmp_path):
    log = tmp_path / "audit.jsonl"
    record_call(str(log), tool="trigger_clip", arguments={}, outcome="error", target="t", duration_ms=1, error="boom")
    (record,) = _records(log)
    assert record["error"] == "boom"
    assert "summary" not in record


def test_record_call_swallows_io_errors(tmp_path):
    blocker = tmp_path / "blocker"
    blocker.write_text("x", encoding="utf-8")
    assert record_call(str(blocker / "audit.jsonl"), tool="x", arguments={}, outcome="ok", target="t", duration_ms=0) is False


def test_summarize_result_keeps_only_review_fields():
    raw = '{"ok": true, "status_code": 204, "body": {"huge": 1}, "verified": false, "value_before": 1.0, "value_after": 0.5, "note": "n"}'
    assert summarize_result(raw) == {"ok": True, "status_code": 204, "verified": False, "value_before": 1.0, "value_after": 0.5, "note": "n"}
    assert summarize_result("not json") is None
    assert summarize_result("[1, 2]") is None
    assert summarize_result('{"body": 1}') == {}
