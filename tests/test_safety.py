import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from resolume_mcp.client import ResolumeClient
from resolume_mcp.config import ResolumeConfig
from resolume_mcp.server import _destructive_reason


@pytest.mark.parametrize(
    ("verb", "path", "value"),
    [
        ("DELETE", "/composition/layers/1", None),
        ("remove", "/parameter/by-id/5", None),
        ("POST", "/composition/clear", None),
        ("POST", "/api/v1/composition/layers/2/clear", None),
        ("POST", "composition/layers/2/clearclips", None),
        ("POST", "/composition/disconnect-all", None),
        ("osc", "/composition/disconnectall", None),
        ("POST", "/composition/new", None),
        ("POST", "/composition/open", None),
        ("POST", "/composition/decks/2/close", None),
        ("trigger", "/composition/decks/by-id/77/close", None),
        ("POST", "/composition/layers/1/clips/2/connect", False),
        ("set", "/composition/layers/1/clips/2/connect", False),
        ("POST", "/Composition/CLEAR/", None),
    ],
)
def test_destructive_reason_flags_destructive_calls(verb, path, value):
    assert _destructive_reason(verb, path, value)


@pytest.mark.parametrize(
    ("verb", "path", "value"),
    [
        ("GET", "/composition/clear", None),
        ("get", "/composition/layers/1/clear", None),
        ("subscribe", "/composition/disconnect-all", None),
        ("POST", "/composition/layers/1/clips/2/connect", None),
        ("POST", "/composition/layers/1/clips/2/connect", True),
        ("POST", "/composition/layers/1/select", None),
        ("POST", "/composition/layers/1/clips/2/open", "file:///C:/a.mov"),
        ("POST", "/composition/decks/2/open", None),
        ("POST", "/composition/save", None),
        ("set", "/parameter/by-id/5", 0.5),
        ("trigger", "/composition/layers/1/clips/2/close", None),
    ],
)
def test_destructive_reason_allows_routine_calls(verb, path, value):
    assert _destructive_reason(verb, path, value) is None


def _fake_client():
    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True})
    fake.websocket_action = AsyncMock(return_value={"ok": True})
    fake.send_osc = MagicMock(return_value={"ok": True})
    return fake


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "args"),
    [
        ("new_composition", ()),
        ("open_composition", ()),
        ("close_deck", (2,)),
    ],
)
@patch("resolume_mcp.server._client")
async def test_new_named_gates_require_confirmation(mock_client_factory, tool_name, args):
    from resolume_mcp import server

    fake = _fake_client()
    mock_client_factory.return_value = fake

    payload = json.loads(await getattr(server, tool_name)(*args))
    assert payload["requires_confirmation"] is True
    assert payload["action"] == tool_name
    fake.request.assert_not_awaited()

    payload = json.loads(await getattr(server, tool_name)(*args, confirm_destructive=True))
    assert payload == {"ok": True}
    fake.request.assert_awaited_once()


def test_restore_advanced_output_requires_confirmation(tmp_path):
    from resolume_mcp.server import restore_advanced_output_preferences

    with patch("resolume_mcp.server.restore_advanced_output_bundle") as restore:
        payload = json.loads(restore_advanced_output_preferences(str(tmp_path / "AdvancedOutput.xml")))
        assert payload["requires_confirmation"] is True
        restore.assert_not_called()

        restore.return_value = {"restored": True}
        payload = json.loads(
            restore_advanced_output_preferences(str(tmp_path / "AdvancedOutput.xml"), confirm_destructive=True)
        )
        assert payload == {"restored": True}
        restore.assert_called_once()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("tool_name", "gated_args", "routine_args", "client_attr"),
    [
        ("rest_request", ("POST", "/composition/clear"), ("POST", "/composition/layers/1/select"), "request"),
        ("rest_post", ("/composition/disconnect-all",), ("/composition/layers/1/select",), "request"),
        ("rest_put", ("/composition/new",), ("/composition/layers/1",), "request"),
        ("rest_delete", ("/composition/layers/3",), None, "request"),
        ("websocket_action", ("trigger", "/composition/decks/2/close"), ("trigger", "/composition/layers/1/select"), "websocket_action"),
        ("websocket_set", ("/composition/layers/1/clips/1/connect", "false"), ("/parameter/by-id/5", "0.5"), "websocket_action"),
        ("websocket_trigger", ("/composition/layers/1/clear",), ("/composition/layers/1/select",), "websocket_action"),
        ("websocket_post", ("/composition/clear",), ("/composition/layers/1/select",), "websocket_action"),
        ("websocket_remove", ("/composition/layers/1/clips/1",), None, "websocket_action"),
        ("set_param", ("/composition/layers/1/clips/1/connect", "false"), ("/parameter/by-id/5", "0.5"), "websocket_action"),
        ("trigger_param", ("/composition/clearclips",), ("/composition/layers/1/select",), "websocket_action"),
        ("trigger_deck_action", (2, "close"), (2, "select"), "websocket_action"),
    ],
)
@patch("resolume_mcp.server._client")
async def test_generic_tools_gate_destructive_paths(mock_client_factory, tool_name, gated_args, routine_args, client_attr):
    from resolume_mcp import server

    fake = _fake_client()
    mock_client_factory.return_value = fake
    tool = getattr(server, tool_name)

    payload = json.loads(await tool(*gated_args))
    assert payload["requires_confirmation"] is True
    assert payload["action"] == tool_name
    getattr(fake, client_attr).assert_not_awaited()

    await tool(*gated_args, confirm_destructive=True)
    getattr(fake, client_attr).assert_awaited_once()

    if routine_args is not None:
        getattr(fake, client_attr).reset_mock()
        payload = json.loads(await tool(*routine_args))
        assert "requires_confirmation" not in payload
        getattr(fake, client_attr).assert_awaited_once()


@patch("resolume_mcp.server._client")
def test_osc_send_gates_destructive_address(mock_client_factory):
    from resolume_mcp.server import osc_send

    fake = _fake_client()
    mock_client_factory.return_value = fake

    payload = json.loads(osc_send("/composition/disconnectall"))
    assert payload["requires_confirmation"] is True
    fake.send_osc.assert_not_called()

    osc_send("/composition/disconnectall", confirm_destructive=True)
    fake.send_osc.assert_called_once()

    fake.send_osc.reset_mock()
    payload = json.loads(osc_send("/composition/layers/1/clips/1/connect", "[1]"))
    assert "requires_confirmation" not in payload
    fake.send_osc.assert_called_once()


def test_config_check_host_allowed_accepts_explicit_host():
    config = ResolumeConfig(allowed_hosts=frozenset({"127.0.0.1", "10.0.0.5"}))
    config.check_host_allowed("10.0.0.5")
    with pytest.raises(ValueError, match="'10.0.0.9' is not in RESOLUME_ALLOWED_HOSTS"):
        config.check_host_allowed("10.0.0.9")


@patch("resolume_mcp.client.socket.socket")
def test_send_osc_rejects_override_host_outside_allowlist(mock_socket):
    client = ResolumeClient(ResolumeConfig(allowed_hosts=frozenset({"127.0.0.1"})))

    with pytest.raises(ValueError, match="RESOLUME_ALLOWED_HOSTS"):
        client.send_osc("/composition/tempocontroller/tempo", [120.0], host="10.0.0.9")
    mock_socket.assert_not_called()

    result = client.send_osc("/composition/tempocontroller/tempo", [120.0], host="127.0.0.1")
    assert result["host"] == "127.0.0.1"


@patch("resolume_mcp.client.socket.socket")
def test_send_osc_wildcard_allowlist_accepts_any_host(mock_socket):
    client = ResolumeClient(ResolumeConfig(allowed_hosts=frozenset({"*"})))
    result = client.send_osc("/composition/tempocontroller/tempo", [120.0], host="10.0.0.9")
    assert result["host"] == "10.0.0.9"
