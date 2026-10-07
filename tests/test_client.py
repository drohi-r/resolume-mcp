import json

import httpx
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from resolume_mcp.client import (
    ResolumeClient,
    ResolumeConnectionError,
    build_osc_message,
    join_url,
    message_matches_parameter,
    normalize_api_path,
)
from resolume_mcp.config import ResolumeConfig


def test_normalize_api_path_adds_prefix():
    assert normalize_api_path("/composition") == "/api/v1/composition"


def test_normalize_api_path_keeps_api_prefix():
    assert normalize_api_path("/api/v1/composition") == "/api/v1/composition"


def test_join_url():
    assert join_url("http://127.0.0.1:8080", "/api/v1/composition") == "http://127.0.0.1:8080/api/v1/composition"


def test_build_osc_message_has_address_prefix():
    packet = build_osc_message("/composition/layers/1/clear", [])
    assert packet.startswith(b"/composition/layers/1/clear")


def test_websocket_url_uses_api_v1():
    assert ResolumeConfig().websocket_url == "ws://127.0.0.1:8080/api/v1"


def test_config_exposes_advanced_output_xml_paths():
    config = ResolumeConfig()
    assert config.advanced_output_xml_path.endswith("/Documents/Resolume Arena/Preferences/AdvancedOutput.xml")
    assert config.slices_xml_path.endswith("/Documents/Resolume Arena/Preferences/slices.xml")


@pytest.mark.asyncio
async def test_drain_websocket_bootstrap_reads_initial_messages():
    class FakeWebSocket:
        def __init__(self):
            self.messages = ['{"bootstrap":1}', '{"bootstrap":2}', '{"bootstrap":3}']

        async def recv(self):
            return self.messages.pop(0)

    client = ResolumeClient(ResolumeConfig())
    bootstrap = await client._drain_websocket_bootstrap(FakeWebSocket())
    assert bootstrap == [{"bootstrap": 1}, {"bootstrap": 2}, {"bootstrap": 3}]


@pytest.mark.asyncio
async def test_drain_websocket_bootstrap_stops_on_timeout():
    class FakeWebSocket:
        async def recv(self):
            raise TimeoutError

    client = ResolumeClient(ResolumeConfig())
    bootstrap = await client._drain_websocket_bootstrap(FakeWebSocket())
    assert bootstrap == []


@pytest.mark.asyncio
async def test_request_sends_plain_text_for_string_body():
    client = ResolumeClient(ResolumeConfig())
    response = MagicMock()
    response.headers = {"content-type": "text/plain"}
    response.text = ""
    response.is_success = True
    response.status_code = 204

    async_client = MagicMock()
    async_client.request = AsyncMock(return_value=response)
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=False)

    with patch("resolume_mcp.client.httpx.AsyncClient", return_value=async_client):
        await client.request("POST", "/composition/layers/1/clips/1/open", body="file:///Users/test/video.mp4")

    async_client.request.assert_awaited_once_with(
        "POST",
        "http://127.0.0.1:8080/api/v1/composition/layers/1/clips/1/open",
        params=None,
        content="file:///Users/test/video.mp4",
        headers={"content-type": "text/plain"},
    )


@pytest.mark.asyncio
async def test_request_sends_json_for_array_body():
    client = ResolumeClient(ResolumeConfig())
    response = MagicMock()
    response.headers = {"content-type": "application/json"}
    response.json.return_value = {"ok": True}
    response.is_success = True
    response.status_code = 200

    async_client = MagicMock()
    async_client.request = AsyncMock(return_value=response)
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=False)

    with patch("resolume_mcp.client.httpx.AsyncClient", return_value=async_client):
        await client.request("POST", "/files", body=["file:///Users/test/video.mp4"])

    async_client.request.assert_awaited_once_with(
        "POST",
        "http://127.0.0.1:8080/api/v1/files",
        params=None,
        json=["file:///Users/test/video.mp4"],
    )


@pytest.mark.asyncio
async def test_request_handles_invalid_json_body():
    """When response has JSON content-type but body is not valid JSON, falls back to text."""
    client = ResolumeClient(ResolumeConfig())
    response = MagicMock()
    response.headers = {"content-type": "application/json"}
    response.json.side_effect = Exception("Invalid JSON")
    response.text = "Internal Server Error"
    response.is_success = False
    response.status_code = 500

    async_client = MagicMock()
    async_client.request = AsyncMock(return_value=response)
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=False)

    with patch("resolume_mcp.client.httpx.AsyncClient", return_value=async_client):
        result = await client.request("GET", "/composition")

    assert result["ok"] is False
    assert result["status_code"] == 500
    assert result["body"] == "Internal Server Error"


class _FakeWebSocket:
    """Replays queued server messages; raises TimeoutError once drained so waits end immediately."""

    def __init__(self, messages):
        self.messages = list(messages)
        self.sent = []

    async def recv(self):
        if not self.messages:
            raise TimeoutError
        return self.messages.pop(0)

    async def send(self, raw):
        self.sent.append(json.loads(raw))


def _patch_websocket(fake):
    connection = MagicMock()
    connection.__aenter__ = AsyncMock(return_value=fake)
    connection.__aexit__ = AsyncMock(return_value=False)
    return patch("resolume_mcp.client.websockets.connect", return_value=connection)


BOOTSTRAP = ['{"layers": []}', '{"type": "sources_update"}', '{"type": "effects_update"}']


@pytest.mark.asyncio
async def test_websocket_get_skips_unrelated_messages_and_omits_bootstrap():
    fake = _FakeWebSocket(
        BOOTSTRAP
        + [
            '{"type": "parameter_update", "id": 999, "value": 1}',
            '{"type": "parameter_get", "id": 2002, "path": "/parameter/by-id/2002", "value": 0.5}',
        ]
    )
    with _patch_websocket(fake) as connect:
        result = await ResolumeClient(ResolumeConfig()).websocket_action("get", "/parameter/by-id/2002")

    assert result["response"]["value"] == 0.5
    assert result["reply_timed_out"] is False
    assert result["skipped_message_count"] == 1
    assert result["bootstrap_message_count"] == 3
    assert "bootstrap" not in result
    assert connect.call_args.kwargs["max_size"] is None


@pytest.mark.asyncio
async def test_websocket_get_times_out_instead_of_hanging():
    fake = _FakeWebSocket(BOOTSTRAP + ['{"type": "parameter_update", "id": 999}'])
    with _patch_websocket(fake):
        result = await ResolumeClient(ResolumeConfig()).websocket_action("get", "/parameter/by-id/2002", reply_timeout_s=0.1)

    assert result["response"] is None
    assert result["reply_timed_out"] is True
    assert result["skipped_message_count"] == 1


@pytest.mark.asyncio
async def test_websocket_get_matches_error_reply_by_path():
    fake = _FakeWebSocket(BOOTSTRAP + ['{"path": "/composition/tempocontroller/tempo", "error": "Invalid parameter path"}'])
    with _patch_websocket(fake):
        result = await ResolumeClient(ResolumeConfig()).websocket_action("get", "/composition/tempocontroller/tempo")

    assert result["response"]["error"] == "Invalid parameter path"


@pytest.mark.asyncio
async def test_websocket_set_is_fire_and_forget():
    fake = _FakeWebSocket(BOOTSTRAP + ['{"leftover": true}'])
    with _patch_websocket(fake):
        result = await ResolumeClient(ResolumeConfig()).websocket_action("set", "/parameter/by-id/2002", value=0.5)

    assert fake.sent == [{"action": "set", "parameter": "/parameter/by-id/2002", "value": 0.5}]
    assert result["response"] is None
    assert "reply_timed_out" not in result
    assert fake.messages == ['{"leftover": true}']


@pytest.mark.asyncio
async def test_websocket_watch_collects_updates_then_unsubscribes():
    fake = _FakeWebSocket(
        BOOTSTRAP
        + [
            '{"type": "parameter_subscribed", "id": 2002, "value": 0.5}',
            '{"type": "parameter_update", "id": 3003, "value": 0.1}',
            '{"type": "parameter_update", "id": 2002, "value": 0.7}',
            '{"type": "composition_update"}',
        ]
    )
    with _patch_websocket(fake):
        result = await ResolumeClient(ResolumeConfig()).websocket_watch(
            ["/parameter/by-id/2002", "/parameter/by-id/3003", "/parameter/by-id/2002"], duration_s=0.5
        )

    assert result["parameters"] == ["/parameter/by-id/2002", "/parameter/by-id/3003"]
    assert [m["value"] for m in result["updates"]["/parameter/by-id/2002"]] == [0.5, 0.7]
    assert result["update_count"] == 3
    assert result["unmatched_message_count"] == 1
    assert [m["action"] for m in fake.sent] == ["subscribe", "subscribe", "unsubscribe", "unsubscribe"]


@pytest.mark.asyncio
async def test_websocket_connection_failure_is_actionable():
    with patch("resolume_mcp.client.websockets.connect", side_effect=ConnectionRefusedError("refused")):
        with pytest.raises(ResolumeConnectionError, match="Could not reach Resolume at ws://127.0.0.1:8080/api/v1"):
            await ResolumeClient(ResolumeConfig()).websocket_action("get", "/parameter/by-id/1")


@pytest.mark.asyncio
async def test_request_connection_failure_is_actionable():
    async_client = MagicMock()
    async_client.request = AsyncMock(side_effect=httpx.ConnectError("All connection attempts failed"))
    async_client.__aenter__ = AsyncMock(return_value=async_client)
    async_client.__aexit__ = AsyncMock(return_value=False)

    with patch("resolume_mcp.client.httpx.AsyncClient", return_value=async_client):
        with pytest.raises(ResolumeConnectionError, match="web server enabled"):
            await ResolumeClient(ResolumeConfig()).request("GET", "/product")


def test_message_matches_parameter():
    assert message_matches_parameter({"path": "/a/b"}, "/a/b")
    assert message_matches_parameter({"id": 12}, "/parameter/by-id/12")
    assert not message_matches_parameter({"id": 13}, "/parameter/by-id/12")
    assert not message_matches_parameter({"id": 12}, "/a/b")
    assert not message_matches_parameter("text", "/a/b")
