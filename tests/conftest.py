import pytest


@pytest.fixture(autouse=True)
def _no_set_verify_delay(monkeypatch):
    """Parameter sets poll REST briefly to verify; skip the real sleep between polls in tests."""
    monkeypatch.setattr("resolume_mcp.server._SET_VERIFY_DELAY_S", 0)
