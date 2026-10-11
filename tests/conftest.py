import pytest


@pytest.fixture(autouse=True)
def _no_set_verify_delay(monkeypatch):
    """Parameter sets poll REST briefly to verify; skip the real sleep between polls in tests."""
    monkeypatch.setattr("resolume_mcp.server._SET_VERIFY_DELAY_S", 0)


@pytest.fixture(autouse=True)
def _audit_log_off(monkeypatch):
    """Keep tool calls from writing the real audit log; tests that check it set RESOLUME_AUDIT_LOG themselves."""
    monkeypatch.setenv("RESOLUME_AUDIT_LOG", "off")
