import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from resolume_mcp.client import ResolumeClient, build_osc_message, join_url, normalize_api_path
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
