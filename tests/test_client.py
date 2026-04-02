import pytest

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
