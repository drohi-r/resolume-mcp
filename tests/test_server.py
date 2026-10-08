import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, call, patch

import pytest

from resolume_mcp.server import api_primitives, get_server_config, mcp


ADVANCED_OUTPUT_XML = """<?xml version="1.0" encoding="utf-8"?>
<ScreenSetup name="ScreenSetup">
  <versionInfo name="Resolume Arena" majorVersion="7" minorVersion="25" microVersion="3" revision="2905"/>
  <CurrentCompositionTextureSize width="1920" height="1080"/>
  <screens>
    <Screen name="Screen 1" uniqueId="1">
      <Params name="Params">
        <Param name="Name" T="STRING" default="" value="Screen 1"/>
      </Params>
      <guides>
        <ScreenGuide name="ScreenGuide" type="0"/>
      </guides>
      <layers>
        <Slice uniqueId="2">
          <Params name="Common">
            <Param name="Name" T="STRING" default="Layer" value="Slice A"/>
          </Params>
          <InputRect orientation="0"><v x="0" y="0"/></InputRect>
          <OutputRect orientation="0"><v x="1" y="1"/></OutputRect>
          <Warper>
            <BezierWarper controlWidth="4" controlHeight="4"><vertices><v x="0" y="0"/></vertices></BezierWarper>
            <Homography><src><v x="0" y="0"/></src><dst><v x="2" y="2"/></dst></Homography>
          </Warper>
        </Slice>
      </layers>
      <OutputDevice>
        <OutputDeviceVirtual name="Screen 1" deviceId="VirtualScreen 1" width="1920" height="1080"/>
      </OutputDevice>
    </Screen>
  </screens>
  <SoftEdging>
    <Params name="Soft Edge">
      <ParamRange name="Power" T="DOUBLE" default="2" value="2.0"/>
    </Params>
  </SoftEdging>
</ScreenSetup>
"""

SLICES_XML = """<?xml version="1.0" encoding="utf-8"?>
<ScreenSetupInspector name="ScreenSetupInspector">
  <versionInfo name="Resolume Arena" majorVersion="7" minorVersion="25" microVersion="3" revision="2905"/>
  <List><Items/></List>
</ScreenSetupInspector>
"""


def _rest_by_path(responses):
    """client.request mock: GETs answer from a path -> payload map, other methods are acknowledged."""

    async def handler(method, path, **kwargs):
        if method == "GET":
            return responses[path]
        return {"ok": True, "method": method, "path": f"/api/v1{path}"}

    return AsyncMock(side_effect=handler)


def test_server_name():
    assert mcp.name == "Resolume MCP"


def test_config_tool_returns_json():
    payload = json.loads(get_server_config())
    assert "http_base_url" in payload
    assert "websocket_url" in payload


def test_api_primitives_resource():
    payload = json.loads(api_primitives())
    assert "rest_tools" in payload
    assert "websocket_tools" in payload


def test_api_primitives_mentions_output_helpers():
    payload = json.loads(api_primitives())
    assert any("output screen/slice parameter helpers" in note for note in payload["notes"])


@pytest.mark.asyncio
async def test_batch_set_output_slice_parameter_requires_array():
    from resolume_mcp.server import batch_set_output_slice_parameter

    with pytest.raises(ValueError, match="slice_indices_json must decode to a JSON array."):
        await batch_set_output_slice_parameter(1, "{\"bad\":true}", "opacity", "0.5")


@pytest.mark.asyncio
async def test_prepare_multiple_output_screens_requires_array():
    from resolume_mcp.server import prepare_multiple_output_screens

    with pytest.raises(ValueError, match="screen_indices_json must decode to a JSON array."):
        await prepare_multiple_output_screens("{\"bad\":true}")


@pytest.mark.asyncio
async def test_trigger_clips_requires_array():
    from resolume_mcp.server import trigger_clips

    with pytest.raises(ValueError, match="clip_indices_json must decode to a JSON array."):
        await trigger_clips(1, "{\"bad\":true}")


@pytest.mark.asyncio
async def test_clear_layers_requires_array():
    from resolume_mcp.server import clear_layers

    with pytest.raises(ValueError, match="layer_indices_json must decode to a JSON array."):
        await clear_layers("{\"bad\":true}", confirm_destructive=True)


@pytest.mark.asyncio
async def test_monitor_playback_state_requires_clip_pair_fields():
    from resolume_mcp.server import monitor_playback_state

    with pytest.raises(ValueError, match="Each clip pair must include layer_index and clip_index."):
        await monitor_playback_state(clip_pairs_json='[{"layer_index":1}]')


@pytest.mark.asyncio
async def test_subscribe_playback_state_requires_clip_pair_fields():
    from resolume_mcp.server import subscribe_playback_state

    with pytest.raises(ValueError, match="Each clip pair must include layer_index and clip_index."):
        await subscribe_playback_state(clip_pairs_json='[{"layer_index":1}]')


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_rest_get(mock_client_factory):
    from resolume_mcp.server import rest_get

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition"})
    mock_client_factory.return_value = fake

    payload = json.loads(await rest_get("/composition"))
    assert payload["ok"] is True
    fake.request.assert_awaited_once_with("GET", "/composition", params=None)


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_composition_overview(mock_client_factory):
    from resolume_mcp.server import get_composition_overview

    fake = MagicMock()
    fake.request = AsyncMock(return_value={
        "path": "/api/v1/composition",
        "body": {"name": {"value": "Show"}, "layers": [{"id": 11}], "columns": [{"id": 22}], "layergroups": [{"id": 33}], "decks": [{"id": 1}]},
    })
    mock_client_factory.return_value = fake

    payload = json.loads(await get_composition_overview())
    assert payload["composition"]["path"] == "/api/v1/composition"
    assert payload["composition"]["body"] == {"name": {"value": "Show"}}
    assert payload["decks"]["body"] == [{"id": 1}]
    assert payload["layers"]["fallback_used"] is True
    assert payload["layers"]["body"] == [{"id": 11}]
    assert payload["groups"]["body"] == [{"id": 33}]
    fake.request.assert_awaited_once_with("GET", "/composition")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_audit_composition(mock_client_factory):
    from resolume_mcp.server import audit_composition

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition", "body": {"tempocontroller": {"tempo": {"id": 1001, "value": 0}}, "layers": [], "columns": [], "layergroups": []}},
        {"path": "/api/v1/composition/layers", "status_code": 404, "ok": False, "content_type": "application/json", "body": "Not Found", "url": "http://127.0.0.1:8080/api/v1/composition/layers"},
        {"path": "/api/v1/composition", "body": {"tempocontroller": {"tempo": {"id": 1001, "value": 0}}, "layers": [], "columns": [], "layergroups": []}},
        {"path": "/api/v1/composition/columns", "status_code": 404, "ok": False, "content_type": "application/json", "body": "Not Found", "url": "http://127.0.0.1:8080/api/v1/composition/columns"},
        {"path": "/api/v1/composition", "body": {"tempocontroller": {"tempo": {"id": 1001, "value": 0}}, "layers": [], "columns": [], "layergroups": []}},
        {"path": "/api/v1/composition/layergroups", "status_code": 404, "ok": False, "content_type": "application/json", "body": "Not Found", "url": "http://127.0.0.1:8080/api/v1/composition/layergroups"},
        {"path": "/api/v1/composition", "body": {"tempocontroller": {"tempo": {"id": 1001, "value": 0}}, "layers": [], "columns": [], "layergroups": []}},
        {"body": {"decks": []}},
        {"body": {"tempocontroller": {"tempo": {"id": 1001, "value": 0}}}},
    ])
    fake.websocket_action = AsyncMock(return_value={"response": {"value": 0}})
    mock_client_factory.return_value = fake

    payload = json.loads(await audit_composition())
    assert payload["summary"]["finding_count"] >= 4
    assert "Composition tempo is unset or zero." in payload["findings"]


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_composition_parameter(mock_client_factory):
    from resolume_mcp.server import get_composition_parameter

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"body": {"tempocontroller": {"tempo": {"id": 1001}}}})
    fake.websocket_action = AsyncMock(return_value={"response": {"value": 120}})
    mock_client_factory.return_value = fake

    payload = json.loads(await get_composition_parameter("tempocontroller/tempo"))
    assert payload["request"]["parameter"] == "/parameter/by-id/1001"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_subscribe_composition_parameter(mock_client_factory):
    from resolume_mcp.server import subscribe_composition_parameter

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"body": {"tempocontroller": {"tempo": {"id": 1001}}}})
    fake.websocket_watch = AsyncMock(return_value={"update_count": 1})
    mock_client_factory.return_value = fake

    payload = json.loads(await subscribe_composition_parameter("tempocontroller/tempo", duration_s=1.5))
    assert payload["request"]["action"] == "subscribe"
    assert payload["request"]["parameter"] == "/parameter/by-id/1001"
    assert payload["response"] == {"update_count": 1}
    fake.websocket_watch.assert_awaited_once_with(["/parameter/by-id/1001"], duration_s=1.5)


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_websocket_set(mock_client_factory):
    from resolume_mcp.server import websocket_set

    fake = MagicMock()
    fake.websocket_action = AsyncMock(return_value={"request": {"action": "set"}})
    mock_client_factory.return_value = fake

    payload = json.loads(await websocket_set("/composition/tempocontroller/tempo", "128"))
    assert payload["request"]["action"] == "set"
    fake.websocket_action.assert_awaited_once_with("set", "/composition/tempocontroller/tempo", value=128)


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_list_columns(mock_client_factory):
    from resolume_mcp.server import list_columns

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition/columns", "status_code": 404, "ok": False, "content_type": "application/json", "body": "Not Found", "url": "http://127.0.0.1:8080/api/v1/composition/columns"},
        {"path": "/api/v1/composition", "body": {"columns": [{"id": 22}]}}
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await list_columns())
    assert payload["path"] == "/api/v1/composition/columns"
    assert payload["fallback_used"] is True
    assert payload["body"] == [{"id": 22}]


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_list_layers_falls_back_to_composition(mock_client_factory):
    from resolume_mcp.server import list_layers

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition/layers", "status_code": 404, "ok": False, "content_type": "application/json", "body": "Not Found", "url": "http://127.0.0.1:8080/api/v1/composition/layers"},
        {"path": "/api/v1/composition", "body": {"layers": [{"id": 11}]}}
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await list_layers())
    assert payload["fallback_used"] is True
    assert payload["body"] == [{"id": 11}]


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_list_clips_falls_back_to_layer(mock_client_factory):
    from resolume_mcp.server import list_clips

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition/layers/2/clips", "status_code": 404, "ok": False, "content_type": "application/json", "body": "Not Found", "url": "http://127.0.0.1:8080/api/v1/composition/layers/2/clips"},
        {"path": "/api/v1/composition/layers/2", "body": {"clips": [{"id": 4004}]}}
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await list_clips(2))
    assert payload["fallback_used"] is True
    assert payload["body"] == [{"id": 4004}]


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_layer_parameter(mock_client_factory):
    from resolume_mcp.server import set_layer_parameter

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"body": {"video": {"opacity": {"id": 2002}}}})
    fake.websocket_action = AsyncMock(return_value={"response": {"value": 0.5}})
    mock_client_factory.return_value = fake

    payload = json.loads(await set_layer_parameter(2, "video/opacity", "0.5"))
    assert payload["request"]["parameter"] == "/parameter/by-id/2002"
    assert payload["request"]["value"] == 0.5


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_layer_snapshot(mock_client_factory):
    from resolume_mcp.server import get_layer_snapshot

    fake = MagicMock()
    fake.request = AsyncMock(return_value={
        "path": "/api/v1/composition/layers/2",
        "body": {"clips": [{"id": 4004}], "video": {"opacity": {"id": 2002, "value": 1.0}}, "bypassed": {"id": 2003, "value": False}},
    })
    mock_client_factory.return_value = fake

    payload = json.loads(await get_layer_snapshot(2))
    assert payload["layer"]["path"] == "/api/v1/composition/layers/2"
    assert "clips" not in payload["layer"]["body"]
    assert payload["clips"]["fallback_used"] is True
    assert payload["clips"]["body"] == [{"id": 4004}]
    assert payload["opacity"]["request"]["parameter"] == "/parameter/by-id/2002"
    assert payload["opacity"]["value"] == 1.0
    assert payload["bypassed"]["value"] is False
    fake.request.assert_awaited_once_with("GET", "/composition/layers/2")
    fake.websocket_action.assert_not_called()


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_audit_layer(mock_client_factory):
    from resolume_mcp.server import audit_layer

    fake = MagicMock()
    fake.request = AsyncMock(return_value={
        "path": "/api/v1/composition/layers/1",
        "body": {"clips": [], "video": {"opacity": {"id": 2002, "value": 0}}, "bypassed": {"id": 2003, "value": True}},
    })
    mock_client_factory.return_value = fake

    payload = json.loads(await audit_layer(1))
    assert "Layer contains no clips." in payload["findings"]
    assert "Layer opacity is zero." in payload["findings"]
    assert "Layer is bypassed." in payload["findings"]
    fake.request.assert_awaited_once_with("GET", "/composition/layers/1")
    fake.websocket_action.assert_not_called()


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_disconnect_clip(mock_client_factory):
    """When the clip state cannot be read, send connect=false but never fall back to clearing the layer."""
    from resolume_mcp.server import disconnect_clip

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": {"connected": {"id": 3001}}},
        {"ok": True, "path": "/api/v1/composition/layers/1/clips/2/connect"},
        {"body": {"connected": {"id": 3001}}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await disconnect_clip(1, 2, confirm_destructive=True))
    assert payload["response"]["ok"] is True
    assert payload["before_state"] is None and payload["after_state"] is None
    assert payload["method"] == "connect=false"
    assert payload["fallback_response"] is None
    assert payload["disconnected"] is False
    fake.request.assert_any_await("POST", "/composition/layers/1/clips/2/connect", body=False)


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_subscribe_clip_parameter(mock_client_factory):
    from resolume_mcp.server import subscribe_clip_parameter

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"body": {"transport": {"position": {"id": 3003}}}})
    fake.websocket_watch = AsyncMock(return_value={"update_count": 4})
    mock_client_factory.return_value = fake

    payload = json.loads(await subscribe_clip_parameter(1, 2, "transport/position"))
    assert payload["request"]["parameter"] == "/parameter/by-id/3003"
    fake.websocket_watch.assert_awaited_once_with(["/parameter/by-id/3003"], duration_s=2.0)


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_clip_snapshot(mock_client_factory):
    from resolume_mcp.server import get_clip_snapshot

    fake = MagicMock()
    clip_body = {
        "connected": {"id": 3001, "value": "Connected"},
        "selected": {"id": 3002, "value": True},
        "transport": {"position": {"id": 3003, "value": 0.5}, "controls": {"speed": {"id": 3004, "value": 1.0}}},
    }
    fake.request = AsyncMock(return_value={"path": "/api/v1/composition/layers/1/clips/2", "body": clip_body})
    mock_client_factory.return_value = fake

    payload = json.loads(await get_clip_snapshot(1, 2))
    assert payload["clip"]["path"] == "/api/v1/composition/layers/1/clips/2"
    assert payload["speed"]["request"]["parameter"] == "/parameter/by-id/3004"
    assert payload["speed"]["value"] == 1.0
    assert payload["connected"]["value"] == "Connected"
    fake.request.assert_awaited_once()


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_audit_clip(mock_client_factory):
    from resolume_mcp.server import audit_clip

    fake = MagicMock()
    fake.request = AsyncMock(return_value={
        "path": "/api/v1/composition/layers/2/clips/4",
        "body": {
            "connected": {"id": 3001, "value": "Disconnected"},
            "selected": {"id": 3002, "value": False},
            "transport": {"position": {"id": 3003, "value": 0.1}, "controls": {"speed": {"id": 3004, "value": 0}}},
        },
    })
    mock_client_factory.return_value = fake

    payload = json.loads(await audit_clip(2, 4))
    assert "Clip is disconnected." in payload["findings"]
    assert "Clip speed is zero." in payload["findings"]
    assert "error" in payload["bypassed"]
    fake.request.assert_awaited_once()


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_trigger_clips(mock_client_factory):
    from resolume_mcp.server import trigger_clips

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition/layers/1/clips/2/connect"},
        {"path": "/api/v1/composition/layers/1/clips/3/connect"},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await trigger_clips(1, "[2,3]"))
    assert len(payload["results"]) == 2
    assert payload["results"][1]["response"]["path"] == "/api/v1/composition/layers/1/clips/3/connect"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_disconnect_clips(mock_client_factory):
    from resolume_mcp.server import disconnect_clips

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        # clip 2: connect=false is ignored, so the layer clear fallback runs
        {"body": {"connected": {"id": 3001, "value": "Connected"}}},
        {"path": "/api/v1/composition/layers/1/clips/2/connect"},
        {"body": {"connected": {"id": 3001, "value": "Connected"}}},
        {"path": "/api/v1/composition/layers/1/clear"},
        {"body": {"connected": {"id": 3001, "value": "Disconnected"}}},
        # clip 3: connect=false works
        {"body": {"connected": {"id": 3002, "value": "Connected"}}},
        {"path": "/api/v1/composition/layers/1/clips/3/connect"},
        {"body": {"connected": {"id": 3002, "value": "Disconnected"}}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await disconnect_clips(1, "[2,3]", confirm_destructive=True))
    first, second = payload["results"]
    assert first["method"] == "layer clear"
    assert first["disconnected"] is True
    assert second["method"] == "connect=false"
    assert second["fallback_response"] is None
    assert second["disconnected"] is True
    fake.request.assert_any_await("POST", "/composition/layers/1/clips/2/connect", body=False)
    fake.request.assert_any_await("POST", "/composition/layers/1/clear")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_disconnect_clip_never_clears_layer_for_a_clip_that_is_not_playing(mock_client_factory):
    from resolume_mcp.server import disconnect_clip

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"body": {"connected": {"id": 3001, "value": "Disconnected"}}})
    mock_client_factory.return_value = fake

    payload = json.loads(await disconnect_clip(1, 2, confirm_destructive=True))
    assert payload["method"] == "none"
    assert payload["disconnected"] is True
    # only the state read: no connect=false (Arena might treat it as a trigger) and no layer clear
    fake.request.assert_awaited_once_with("GET", "/composition/layers/1/clips/2")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_disconnect_selected_clip_skips_clip_that_is_not_playing(mock_client_factory):
    from resolume_mcp.server import disconnect_selected_clip

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"body": {"connected": {"value": "Empty"}}})
    mock_client_factory.return_value = fake

    payload = json.loads(await disconnect_selected_clip(confirm_destructive=True))
    assert payload["disconnected"] is True
    fake.request.assert_awaited_once_with("GET", "/composition/clips/selected")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_event_parameter_is_fired_once_without_read_back(mock_client_factory):
    from resolume_mcp.server import set_composition_parameter

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"body": {"tempocontroller": {"tempo_push": {"id": 9, "valuetype": "ParamEvent", "value": False}}}})
    fake.websocket_action = AsyncMock(return_value={"response": None})
    mock_client_factory.return_value = fake

    payload = json.loads(await set_composition_parameter("tempocontroller/tempo_push", "true"))
    assert payload["verified"] is None
    assert fake.websocket_action.await_count == 1
    assert fake.request.await_count == 1


@pytest.mark.asyncio
async def test_wait_for_resolume_rejects_long_interval():
    from resolume_mcp.server import wait_for_resolume

    with pytest.raises(ValueError, match="interval_s in"):
        await wait_for_resolume(timeout_s=60, interval_s=120)


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_clear_layers(mock_client_factory):
    from resolume_mcp.server import clear_layers

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition/layers/1/clear"},
        {"path": "/api/v1/composition/layers/4/clear"},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await clear_layers("[1,4]", confirm_destructive=True))
    assert len(payload["results"]) == 2
    assert payload["results"][0]["layer_index"] == 1


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_clear_clip_reports_verified_state(mock_client_factory):
    from resolume_mcp.server import clear_clip

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": {"name": {"value": "Loaded"}, "connected": {"value": "Disconnected"}, "video": {}, "audio": {}}},
        {"ok": True, "path": "/api/v1/composition/layers/1/clips/2/clear"},
        {"body": {"name": {"value": ""}, "connected": {"value": "Empty"}, "video": {}, "audio": {}}},
        {"body": {"name": {"value": ""}, "connected": {"value": "Empty"}}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await clear_clip(1, 2, confirm_destructive=True))
    assert payload["response"]["ok"] is True
    assert payload["cleared"] is True


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_clear_selected_clip_reports_verified_state(mock_client_factory):
    from resolume_mcp.server import clear_selected_clip

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": {"id": 1001, "name": {"value": "Loaded"}, "connected": {"value": "Disconnected"}, "video": {}, "audio": {}}},
        {"ok": True, "path": "/api/v1/composition/clips/selected/clear"},
        {"body": {"id": 1001, "name": {"value": ""}, "connected": {"value": "Empty"}, "video": {}, "audio": {}}},
        {"body": {"id": 1001, "name": {"value": ""}, "connected": {"value": "Empty"}}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await clear_selected_clip(confirm_destructive=True))
    assert payload["response"]["ok"] is True
    assert payload["clip_id"] == 1001
    assert payload["cleared"] is True


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_prepare_layer(mock_client_factory):
    from resolume_mcp.server import prepare_layer

    fake = MagicMock()
    fake.request = _rest_by_path({
        "/composition/layers/3": {"body": {"bypassed": {"id": 2003, "value": False}, "video": {"opacity": {"id": 2002, "value": 0.9}}}},
    })
    fake.websocket_action = AsyncMock(return_value={"response": None})
    mock_client_factory.return_value = fake

    payload = json.loads(await prepare_layer(3, opacity=0.9, unbypass=True))
    assert len(payload["results"]) == 2
    assert payload["results"][1]["action"] == "set_layer_opacity"
    assert payload["results"][1]["response"]["verified"] is True
    assert fake.websocket_action.await_args_list == [
        call("set", "/parameter/by-id/2003", value=False),
        call("set", "/parameter/by-id/2002", value=0.9),
    ]


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_prepare_multiple_layers(mock_client_factory):
    from resolume_mcp.server import prepare_multiple_layers

    fake = MagicMock()
    fake.request = _rest_by_path({
        "/composition/layers/1": {"body": {"bypassed": {"id": 2001, "value": False}}},
        "/composition/layers/2": {"body": {"bypassed": {"id": 2002, "value": False}}},
    })
    fake.websocket_action = AsyncMock(return_value={"response": None})
    mock_client_factory.return_value = fake

    payload = json.loads(await prepare_multiple_layers("[1,2]", unbypass=True))
    assert payload["layer_count"] == 2
    assert fake.websocket_action.await_count == 2


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_prepare_playback(mock_client_factory):
    from resolume_mcp.server import prepare_playback

    fake = MagicMock()
    fake.request = _rest_by_path({
        "/composition": {"body": {"tempocontroller": {"tempo": {"id": 1001, "value": 128}}}},
        "/composition/layers/1": {"body": {"bypassed": {"id": 2001, "value": False}, "video": {"opacity": {"id": 2002, "value": 1.0}}}},
        "/composition/layers/2": {"body": {"bypassed": {"id": 2003, "value": False}, "video": {"opacity": {"id": 2004, "value": 1.0}}}},
    })
    fake.websocket_action = AsyncMock(return_value={"response": None})
    mock_client_factory.return_value = fake

    payload = json.loads(
        await prepare_playback(
            playing=True,
            bpm=128,
            layer_indices_json="[1,2]",
            layer_opacity=1.0,
            unbypass_layers=True,
        )
    )
    assert payload["results"][0]["skipped"] is True
    assert payload["results"][1]["response"]["verified"] is True
    assert payload["results"][2]["action"] == "prepare_multiple_layers"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_select_clips(mock_client_factory):
    from resolume_mcp.server import select_clips

    fake = MagicMock()
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/composition/layers/1/clips/2/selected", "value": True}},
        {"request": {"parameter": "/composition/layers/1/clips/3/selected", "value": True}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await select_clips(1, "[2,3]"))
    assert len(payload["results"]) == 2


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_select_layers(mock_client_factory):
    from resolume_mcp.server import select_layers

    fake = MagicMock()
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/composition/layers/1/selected", "value": True}},
        {"request": {"parameter": "/composition/layers/2/selected", "value": True}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await select_layers("[1,2]"))
    assert len(payload["results"]) == 2


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_select_columns(mock_client_factory):
    from resolume_mcp.server import select_columns

    fake = MagicMock()
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/composition/columns/4/selected", "value": True}},
        {"request": {"parameter": "/composition/columns/5/selected", "value": True}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await select_columns("[4,5]"))
    assert len(payload["results"]) == 2


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_monitor_playback_state(mock_client_factory):
    from resolume_mcp.server import monitor_playback_state

    fake = MagicMock()
    fake.request = _rest_by_path({
        "/composition": {"body": {"tempocontroller": {"tempo": {"id": 1001, "value": 128}}}},
        "/composition/layers/1": {"body": {"video": {"opacity": {"id": 2002, "value": 1.0}}, "bypassed": {"id": 2003, "value": False}}},
        "/composition/layers/1/clips/2": {"body": {"connected": {"id": 3001, "value": "Connected"}, "transport": {"position": {"id": 3003, "value": 0.25}, "controls": {"speed": {"id": 3004, "value": 1.0}}}}},
    })
    mock_client_factory.return_value = fake

    payload = json.loads(
        await monitor_playback_state(
            layer_indices_json="[1]",
            clip_pairs_json='[{"layer_index":1,"clip_index":2}]',
        )
    )
    assert payload["tempo"]["request"]["parameter"] == "/parameter/by-id/1001"
    assert payload["tempo"]["value"] == 128
    assert payload["layers"][0]["layer_index"] == 1
    assert payload["clips"][0]["clip_index"] == 2
    assert payload["clips"][0]["position"]["value"] == 0.25
    assert "composition" not in payload
    assert fake.request.await_count == 3
    fake.websocket_action.assert_not_called()


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_subscribe_playback_state(mock_client_factory):
    from resolume_mcp.server import subscribe_playback_state

    fake = MagicMock()
    fake.request = _rest_by_path({
        "/composition": {"body": {"tempocontroller": {"tempo": {"id": 1001}}}},
        "/composition/layers/1": {"body": {"video": {"opacity": {"id": 2002}}, "bypassed": {"id": 2003}}},
        "/composition/layers/1/clips/2": {"body": {"connected": {"id": 3001}, "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}}}},
    })
    fake.websocket_watch = AsyncMock(return_value={"update_count": 0})
    mock_client_factory.return_value = fake

    payload = json.loads(
        await subscribe_playback_state(
            layer_indices_json="[1]",
            clip_pairs_json='[{"layer_index":1,"clip_index":2}]',
            duration_s=1.0,
        )
    )
    assert len(payload["targets"]) == 6
    assert fake.request.await_count == 3
    fake.websocket_watch.assert_awaited_once_with(
        [f"/parameter/by-id/{i}" for i in (1001, 2002, 2003, 3001, 3004, 3003)],
        duration_s=1.0,
    )


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_unsubscribe_playback_state(mock_client_factory):
    from resolume_mcp.server import unsubscribe_playback_state

    payload = json.loads(await unsubscribe_playback_state())
    assert payload["response"] is None
    assert "nothing to unsubscribe" in payload["note"]
    mock_client_factory.assert_not_called()


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_deck_snapshot(mock_client_factory):
    from resolume_mcp.server import get_deck_snapshot

    fake = MagicMock()
    deck_body = {"selected": {"id": 4001}, "scrollx": {"id": 4002}, "closed": False}
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition/decks/2", "body": deck_body},
        {"body": deck_body},
        {"body": deck_body},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"value": True}},
        {"response": {"value": 0.5}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await get_deck_snapshot(2))
    assert payload["deck"]["path"] == "/api/v1/composition/decks/2"
    assert payload["selected"]["request"]["parameter"] == "/parameter/by-id/4001"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_monitor_decks(mock_client_factory):
    from resolume_mcp.server import monitor_decks

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": {"selected": {"id": 4001}, "scrollx": {"id": 4002}}},
        {"body": {"selected": {"id": 4001}, "scrollx": {"id": 4002}}},
        {"body": {"selected": {"id": 4001}, "scrollx": {"id": 4002}}},
        {"body": {"selected": {"id": 5001}, "scrollx": {"id": 5002}}},
        {"body": {"selected": {"id": 5001}, "scrollx": {"id": 5002}}},
        {"body": {"selected": {"id": 5001}, "scrollx": {"id": 5002}}},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"value": True}},
        {"response": {"value": 0.1}},
        {"response": {"value": False}},
        {"response": {"value": 0.2}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await monitor_decks("[1,2]"))
    assert len(payload["decks"]) == 2
    assert payload["decks"][1]["deck_index"] == 2


@pytest.mark.asyncio
@patch("resolume_mcp.server.get_deck_snapshot")
async def test_audit_deck(mock_snapshot):
    from resolume_mcp.server import audit_deck

    mock_snapshot.return_value = json.dumps(
        {
            "selected": {"response": {"response": {"value": False}}},
            "closed": True,
        }
    )

    payload = json.loads(await audit_deck(1))
    assert "Deck is closed." in payload["findings"]
    assert "Deck is not selected." in payload["findings"]


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_prepare_deck(mock_client_factory):
    from resolume_mcp.server import prepare_deck

    payload = json.loads(await prepare_deck(1, playing=True, speed=1.0))
    assert len(payload["results"]) == 2
    assert payload["results"][1]["skipped"] is True


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_subscribe_decks(mock_client_factory):
    from resolume_mcp.server import subscribe_decks

    fake = MagicMock()
    fake.request = _rest_by_path({
        "/composition/decks/1": {"body": {"selected": {"id": 4001}, "scrollx": {"id": 4002}}},
        "/composition/decks/2": {"body": {"selected": {"id": 5001}, "scrollx": {"id": 5002}}},
    })
    fake.websocket_watch = AsyncMock(return_value={"update_count": 0})
    mock_client_factory.return_value = fake

    payload = json.loads(await subscribe_decks("[1,2]"))
    assert len(payload["targets"]) == 4
    assert payload["targets"][2] == {"deck_index": 2, "rest_path": "/composition/decks/2", "parameter_suffix": "selected", "parameter": "/parameter/by-id/5001"}
    fake.websocket_watch.assert_awaited_once_with(
        [f"/parameter/by-id/{i}" for i in (4001, 4002, 5001, 5002)],
        duration_s=2.0,
    )


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_unsubscribe_decks(mock_client_factory):
    from resolume_mcp.server import unsubscribe_decks

    payload = json.loads(await unsubscribe_decks("[1]"))
    assert payload["response"] is None
    mock_client_factory.assert_not_called()


@pytest.mark.asyncio
async def test_subscribe_rejects_out_of_range_duration():
    from resolume_mcp.server import subscribe_decks

    with pytest.raises(ValueError, match="duration_s must be greater than 0"):
        await subscribe_decks("[1]", duration_s=0)
    with pytest.raises(ValueError, match="at most 30 seconds"):
        await subscribe_decks("[1]", duration_s=31)


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_prepare_multiple_decks(mock_client_factory):
    from resolume_mcp.server import prepare_multiple_decks

    fake = MagicMock()
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/composition/decks/1/transport/playing", "value": True}},
        {"request": {"parameter": "/composition/decks/1/transport/speed", "value": 1.0}},
        {"request": {"parameter": "/composition/decks/2/transport/playing", "value": True}},
        {"request": {"parameter": "/composition/decks/2/transport/speed", "value": 1.0}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await prepare_multiple_decks("[1,2]", playing=True, speed=1.0))
    assert payload["deck_count"] == 2


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_composition_playing(mock_client_factory):
    from resolume_mcp.server import set_composition_playing

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"body": {}})
    mock_client_factory.return_value = fake

    payload = json.loads(await set_composition_playing(True))
    assert payload["skipped"] is True


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_list_output_screens(mock_client_factory):
    from resolume_mcp.server import list_output_screens

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/advancedoutput/screens"})
    mock_client_factory.return_value = fake

    payload = json.loads(await list_output_screens())
    assert payload["path"] == "/api/v1/advancedoutput/screens"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_output_overview(mock_client_factory):
    from resolume_mcp.server import get_output_overview

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": [{"name": "Screen A"}, {"name": "Screen B"}]},
        {"path": "/api/v1/advancedoutput/screens/0"},
        {"path": "/api/v1/advancedoutput/screens/0/slices"},
        {"path": "/api/v1/advancedoutput/screens/1"},
        {"path": "/api/v1/advancedoutput/screens/1/slices"},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await get_output_overview())
    assert len(payload["screen_snapshots"]) == 2
    assert payload["screen_snapshots"][1]["screen"]["path"] == "/api/v1/advancedoutput/screens/1"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_audit_output_screen(mock_client_factory):
    from resolume_mcp.server import audit_output_screen

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/advancedoutput/screens/0"},
        {"body": [{"input": ""}, {"input": "/composition/layers/1"}]},
    ])
    fake.websocket_action = AsyncMock(return_value={"response": {"value": False}})
    mock_client_factory.return_value = fake

    payload = json.loads(await audit_output_screen(0))
    assert "Screen is disabled." in payload["findings"]
    assert "Slice 0 has no input assignment in REST payload." in payload["findings"]


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_audit_all_output_screens(mock_client_factory):
    from resolume_mcp.server import audit_all_output_screens

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": [{"name": "A"}, {"name": "B"}]},
        {"path": "/api/v1/advancedoutput/screens/0"},
        {"body": []},
        {"path": "/api/v1/advancedoutput/screens/1"},
        {"body": []},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"value": True}},
        {"response": {"value": True}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await audit_all_output_screens())
    assert payload["summary"]["screen_count"] == 2
    assert len(payload["audits"]) == 2


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_output_screen_snapshot(mock_client_factory):
    from resolume_mcp.server import get_output_screen_snapshot

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/advancedoutput/screens/3"},
        {"path": "/api/v1/advancedoutput/screens/3/slices"},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await get_output_screen_snapshot(3))
    assert payload["screen"]["path"] == "/api/v1/advancedoutput/screens/3"
    assert payload["slices"]["path"] == "/api/v1/advancedoutput/screens/3/slices"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_output_slice_snapshot(mock_client_factory):
    from resolume_mcp.server import get_output_slice_snapshot

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"path": "/api/v1/advancedoutput/screens/1/slices/2"})
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/advancedoutput/screens/1/slices/2/input"}},
        {"request": {"parameter": "/advancedoutput/screens/1/slices/2/opacity"}},
        {"request": {"parameter": "/advancedoutput/screens/1/slices/2/bypassed"}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await get_output_slice_snapshot(1, 2))
    assert payload["slice"]["path"] == "/api/v1/advancedoutput/screens/1/slices/2"
    assert payload["input"]["request"]["parameter"] == "/advancedoutput/screens/1/slices/2/input"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_prepare_output_screen(mock_client_factory):
    from resolume_mcp.server import prepare_output_screen

    fake = MagicMock()
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/advancedoutput/screens/2/enabled", "value": True}},
        {"request": {"parameter": "/advancedoutput/screens/2/slices/0/bypassed", "value": False}},
        {"request": {"parameter": "/advancedoutput/screens/2/slices/0/opacity", "value": 1.0}},
        {"request": {"parameter": "/advancedoutput/screens/2/slices/1/bypassed", "value": False}},
        {"request": {"parameter": "/advancedoutput/screens/2/slices/1/opacity", "value": 1.0}},
    ])
    fake.request = AsyncMock(return_value={"body": [{"slice": 0}, {"slice": 1}]})
    mock_client_factory.return_value = fake

    payload = json.loads(await prepare_output_screen(2, enabled=True, slice_opacity=1.0, unbypass_slices=True))
    assert payload["prepared_slice_count"] == 2
    assert payload["results"][0]["action"] == "set_screen_enabled"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_prepare_multiple_output_screens(mock_client_factory):
    from resolume_mcp.server import prepare_multiple_output_screens

    fake = MagicMock()
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/advancedoutput/screens/1/enabled", "value": True}},
        {"request": {"parameter": "/advancedoutput/screens/1/slices/0/bypassed", "value": False}},
        {"request": {"parameter": "/advancedoutput/screens/2/enabled", "value": True}},
        {"request": {"parameter": "/advancedoutput/screens/2/slices/0/bypassed", "value": False}},
    ])
    fake.request = AsyncMock(side_effect=[
        {"body": [{"slice": 0}]},
        {"body": [{"slice": 0}]},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await prepare_multiple_output_screens("[1,2]", enabled=True, unbypass_slices=True))
    assert payload["screen_count"] == 2
    assert payload["screens"][1]["screen_index"] == 2


@pytest.mark.asyncio
@patch("resolume_mcp.server.audit_composition")
@patch("resolume_mcp.server.audit_all_output_screens")
async def test_audit_show_readiness(mock_output_audit, mock_composition_audit):
    from resolume_mcp.server import audit_show_readiness

    mock_composition_audit.return_value = json.dumps({"summary": {"finding_count": 2}})
    mock_output_audit.return_value = json.dumps({"summary": {"total_findings": 3}})

    payload = json.loads(await audit_show_readiness())
    assert payload["summary"]["total_findings"] == 5


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_output_parameter(mock_client_factory):
    from resolume_mcp.server import set_output_parameter

    fake = MagicMock()
    fake.websocket_action = AsyncMock(return_value={"request": {"parameter": "/advancedoutput/screens/1/enabled", "value": True}})
    mock_client_factory.return_value = fake

    payload = json.loads(await set_output_parameter("/screens/1/enabled", "true"))
    assert payload["request"]["parameter"] == "/advancedoutput/screens/1/enabled"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_subscribe_output_screen_parameter(mock_client_factory):
    from resolume_mcp.server import subscribe_output_screen_parameter

    fake = MagicMock()
    fake.websocket_watch = AsyncMock(return_value={"parameters": ["/advancedoutput/screens/2/transform/rotation"]})
    mock_client_factory.return_value = fake

    payload = json.loads(await subscribe_output_screen_parameter(2, "transform/rotation"))
    assert payload["parameters"] == ["/advancedoutput/screens/2/transform/rotation"]
    fake.websocket_watch.assert_awaited_once_with(["/advancedoutput/screens/2/transform/rotation"], duration_s=2.0)


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_output_slice_input(mock_client_factory):
    from resolume_mcp.server import set_output_slice_input

    fake = MagicMock()
    fake.websocket_action = AsyncMock(return_value={"request": {"parameter": "/advancedoutput/screens/1/slices/2/input"}})
    mock_client_factory.return_value = fake

    payload = json.loads(await set_output_slice_input(1, 2, "/composition/layers/3"))
    assert payload["request"]["parameter"] == "/advancedoutput/screens/1/slices/2/input"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_subscribe_output_slice_parameter(mock_client_factory):
    from resolume_mcp.server import subscribe_output_slice_parameter

    fake = MagicMock()
    fake.websocket_watch = AsyncMock(return_value={"parameters": ["/advancedoutput/screens/1/slices/2/feather"]})
    mock_client_factory.return_value = fake

    payload = json.loads(await subscribe_output_slice_parameter(1, 2, "feather", duration_s=5))
    assert payload["parameters"] == ["/advancedoutput/screens/1/slices/2/feather"]
    fake.websocket_watch.assert_awaited_once_with(["/advancedoutput/screens/1/slices/2/feather"], duration_s=5)


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_output_screen_enabled(mock_client_factory):
    from resolume_mcp.server import set_output_screen_enabled

    fake = MagicMock()
    fake.websocket_action = AsyncMock(return_value={"request": {"parameter": "/advancedoutput/screens/4/enabled", "value": False}})
    mock_client_factory.return_value = fake

    payload = json.loads(await set_output_screen_enabled(4, False))
    assert payload["request"]["value"] is False


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_list_decks(mock_client_factory):
    from resolume_mcp.server import list_decks

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition", "body": {"decks": [{"id": 1}]}})
    mock_client_factory.return_value = fake

    payload = json.loads(await list_decks())
    assert payload["body"] == [{"id": 1}]


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_trigger_column(mock_client_factory):
    from resolume_mcp.server import trigger_column

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/columns/2/connect"})
    mock_client_factory.return_value = fake

    payload = json.loads(await trigger_column(2))
    assert payload["path"] == "/api/v1/composition/columns/2/connect"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_select_group(mock_client_factory):
    from resolume_mcp.server import select_group

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"path": "/api/v1/composition/layergroups/3/select"})
    mock_client_factory.return_value = fake

    payload = json.loads(await select_group(3))
    assert payload["path"] == "/api/v1/composition/layergroups/3/select"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_bypass_clip(mock_client_factory):
    from resolume_mcp.server import bypass_clip

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"body": {"bypassed": {"id": 3005}}})
    fake.websocket_action = AsyncMock(return_value={"response": {"value": True}})
    mock_client_factory.return_value = fake

    payload = json.loads(await bypass_clip(1, 5, True))
    assert payload["request"]["parameter"] == "/parameter/by-id/3005"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_deck_parameter(mock_client_factory):
    from resolume_mcp.server import set_deck_parameter

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"body": {"selected": {"id": 4001}}})
    fake.websocket_action = AsyncMock(return_value={"response": {"value": True}})
    mock_client_factory.return_value = fake

    payload = json.loads(await set_deck_parameter(2, "selected", "true"))
    assert payload["request"]["parameter"] == "/parameter/by-id/4001"
    assert payload["request"]["value"] is True


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_output_screen_parameter(mock_client_factory):
    from resolume_mcp.server import set_output_screen_parameter

    fake = MagicMock()
    fake.websocket_action = AsyncMock(return_value={"request": {"parameter": "/advancedoutput/screens/3/transform/rotation", "value": 45}})
    mock_client_factory.return_value = fake

    payload = json.loads(await set_output_screen_parameter(3, "transform/rotation", "45"))
    assert payload["request"]["parameter"] == "/advancedoutput/screens/3/transform/rotation"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_output_slice_parameter(mock_client_factory):
    from resolume_mcp.server import set_output_slice_parameter

    fake = MagicMock()
    fake.websocket_action = AsyncMock(return_value={"request": {"parameter": "/advancedoutput/screens/2/slices/4/feather", "value": 0.25}})
    mock_client_factory.return_value = fake

    payload = json.loads(await set_output_slice_parameter(2, 4, "feather", "0.25"))
    assert payload["request"]["parameter"] == "/advancedoutput/screens/2/slices/4/feather"
    assert payload["request"]["value"] == 0.25


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_output_slice_transform(mock_client_factory):
    from resolume_mcp.server import set_output_slice_transform

    fake = MagicMock()
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/advancedoutput/screens/1/slices/2/transform/position/x", "value": 0.1}},
        {"request": {"parameter": "/advancedoutput/screens/1/slices/2/transform/position/y", "value": 0.2}},
        {"request": {"parameter": "/advancedoutput/screens/1/slices/2/transform/rotation", "value": 15.0}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await set_output_slice_transform(1, 2, x=0.1, y=0.2, rotation=15.0))
    assert len(payload["updates"]) == 3
    assert payload["updates"][0]["parameter"] == "/advancedoutput/screens/1/slices/2/transform/position/x"
    assert payload["updates"][2]["parameter"] == "/advancedoutput/screens/1/slices/2/transform/rotation"


@pytest.mark.asyncio
async def test_set_output_slice_transform_requires_value():
    from resolume_mcp.server import set_output_slice_transform

    with pytest.raises(ValueError, match="At least one transform value is required."):
        await set_output_slice_transform(1, 2)


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_output_slice_corners(mock_client_factory):
    from resolume_mcp.server import set_output_slice_corners

    fake = MagicMock()
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/advancedoutput/screens/1/slices/2/corners/top_left/x", "value": 0.0}},
        {"request": {"parameter": "/advancedoutput/screens/1/slices/2/corners/top_left/y", "value": 0.1}},
        {"request": {"parameter": "/advancedoutput/screens/1/slices/2/corners/bottom_right/x", "value": 0.9}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(
        await set_output_slice_corners(
            1,
            2,
            top_left_x=0.0,
            top_left_y=0.1,
            bottom_right_x=0.9,
        )
    )
    assert len(payload["updates"]) == 3
    assert payload["updates"][0]["parameter"] == "/advancedoutput/screens/1/slices/2/corners/top_left/x"


@pytest.mark.asyncio
async def test_set_output_slice_corners_requires_value():
    from resolume_mcp.server import set_output_slice_corners

    with pytest.raises(ValueError, match="At least one corner value is required."):
        await set_output_slice_corners(1, 2)


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_output_screen_transform(mock_client_factory):
    from resolume_mcp.server import set_output_screen_transform

    fake = MagicMock()
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/advancedoutput/screens/3/transform/position/x", "value": 0.2}},
        {"request": {"parameter": "/advancedoutput/screens/3/transform/rotation", "value": 30.0}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await set_output_screen_transform(3, x=0.2, rotation=30.0))
    assert len(payload["updates"]) == 2
    assert payload["updates"][1]["parameter"] == "/advancedoutput/screens/3/transform/rotation"


@pytest.mark.asyncio
async def test_set_output_screen_transform_requires_value():
    from resolume_mcp.server import set_output_screen_transform

    with pytest.raises(ValueError, match="At least one transform value is required."):
        await set_output_screen_transform(1)


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_batch_set_output_screen_parameter(mock_client_factory):
    from resolume_mcp.server import batch_set_output_screen_parameter

    fake = MagicMock()
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/advancedoutput/screens/1/enabled", "value": True}},
        {"request": {"parameter": "/advancedoutput/screens/2/enabled", "value": True}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await batch_set_output_screen_parameter("[1,2]", "enabled", "true"))
    assert len(payload["updates"]) == 2
    assert payload["updates"][0]["parameter"] == "/advancedoutput/screens/1/enabled"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_batch_set_output_slice_opacity(mock_client_factory):
    from resolume_mcp.server import batch_set_output_slice_opacity

    fake = MagicMock()
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/advancedoutput/screens/2/slices/1/opacity", "value": 0.75}},
        {"request": {"parameter": "/advancedoutput/screens/2/slices/3/opacity", "value": 0.75}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await batch_set_output_slice_opacity(2, "[1,3]", 0.75))
    assert len(payload["updates"]) == 2
    assert payload["updates"][1]["parameter"] == "/advancedoutput/screens/2/slices/3/opacity"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_batch_set_output_slice_bypassed(mock_client_factory):
    from resolume_mcp.server import batch_set_output_slice_bypassed

    fake = MagicMock()
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/advancedoutput/screens/4/slices/2/bypassed", "value": False}},
        {"request": {"parameter": "/advancedoutput/screens/4/slices/5/bypassed", "value": False}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await batch_set_output_slice_bypassed(4, "[2,5]", False))
    assert len(payload["updates"]) == 2
    assert payload["updates"][0]["value"] is False


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_route_output_slices(mock_client_factory):
    from resolume_mcp.server import route_output_slices

    fake = MagicMock()
    fake.websocket_action = AsyncMock(side_effect=[
        {"request": {"parameter": "/advancedoutput/screens/1/slices/1/input", "value": "/composition/layers/1"}},
        {"request": {"parameter": "/advancedoutput/screens/1/slices/2/input", "value": "/composition/layers/2"}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(
        await route_output_slices(
            1,
            '[{"slice_index":1,"input_path":"/composition/layers/1"},{"slice_index":2,"input_path":"/composition/layers/2"}]',
        )
    )
    assert len(payload["updates"]) == 2
    assert payload["updates"][1]["parameter"] == "/advancedoutput/screens/1/slices/2/input"


@pytest.mark.asyncio
async def test_route_output_slices_requires_fields():
    from resolume_mcp.server import route_output_slices

    with pytest.raises(ValueError, match="Each route must include slice_index and input_path."):
        await route_output_slices(1, '[{"slice_index":1}]')


def test_get_server_config_includes_xml_paths():
    payload = json.loads(get_server_config())
    assert "advanced_output_xml_path" in payload
    assert "slices_xml_path" in payload


def test_get_advanced_output_preferences_summary(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import get_advanced_output_preferences_summary

    advanced_output = tmp_path / "AdvancedOutput.xml"
    slices_xml = tmp_path / "slices.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(advanced_output),
            slices_xml_path=str(slices_xml),
        ),
    ):
        payload = json.loads(get_advanced_output_preferences_summary())
    assert payload["screen_count"] == 1
    assert payload["screens"][0]["slice_count"] == 1


def test_get_advanced_output_slice_xml(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import get_advanced_output_slice_xml

    advanced_output = tmp_path / "AdvancedOutput.xml"
    slices_xml = tmp_path / "slices.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(advanced_output),
            slices_xml_path=str(slices_xml),
        ),
    ):
        payload = json.loads(get_advanced_output_slice_xml(0, 0))
    assert payload["name"] == "Slice A"
    assert payload["slice_index"] == 0


def test_get_slices_inspector_summary(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import get_slices_inspector_summary

    advanced_output = tmp_path / "AdvancedOutput.xml"
    slices_xml = tmp_path / "slices.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(advanced_output),
            slices_xml_path=str(slices_xml),
        ),
    ):
        payload = json.loads(get_slices_inspector_summary())
    assert payload["item_count"] == 0


def test_backup_advanced_output_preferences(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import backup_advanced_output_preferences

    advanced_output = tmp_path / "AdvancedOutput.xml"
    slices_xml = tmp_path / "slices.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(advanced_output),
            slices_xml_path=str(slices_xml),
        ),
    ):
        payload = json.loads(backup_advanced_output_preferences(str(tmp_path / "backups")))
    assert Path(payload["advanced_output_xml"]["backup"]).exists()
    assert Path(payload["slices_xml"]["backup"]).exists()


def test_diff_advanced_output_preferences(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import diff_advanced_output_preferences

    current = tmp_path / "AdvancedOutput.xml"
    other = tmp_path / "OtherAdvancedOutput.xml"
    slices_xml = tmp_path / "slices.xml"
    current.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    other.write_text(ADVANCED_OUTPUT_XML.replace("Slice A", "Slice B"), encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(current),
            slices_xml_path=str(slices_xml),
        ),
    ):
        payload = json.loads(diff_advanced_output_preferences(str(other)))
    assert payload["diff_line_count"] > 0
    assert any("Slice B" in line for line in payload["diff"])


def test_export_advanced_output_preferences(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import export_advanced_output_preferences

    advanced_output = tmp_path / "AdvancedOutput.xml"
    slices_xml = tmp_path / "slices.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(advanced_output),
            slices_xml_path=str(slices_xml),
        ),
    ):
        payload = json.loads(export_advanced_output_preferences(str(tmp_path / "exports"), "bundle-a"))
    assert Path(payload["advanced_output_xml"]["export"]).exists()
    assert "notes" in payload


def test_preview_restore_advanced_output_preferences(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import preview_restore_advanced_output_preferences

    current_advanced_output = tmp_path / "AdvancedOutput.xml"
    current_slices = tmp_path / "slices.xml"
    source_dir = tmp_path / "bundle"
    source_dir.mkdir()
    source_advanced_output = source_dir / "AdvancedOutput.xml"
    source_slices = source_dir / "slices.xml"
    current_advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    current_slices.write_text(SLICES_XML, encoding="utf-8")
    source_advanced_output.write_text(ADVANCED_OUTPUT_XML.replace("Slice A", "Slice C"), encoding="utf-8")
    source_slices.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(current_advanced_output),
            slices_xml_path=str(current_slices),
        ),
    ):
        payload = json.loads(preview_restore_advanced_output_preferences(str(source_advanced_output)))
    assert payload["diffs"]["advanced_output_xml"]["diff_line_count"] > 0


def test_restore_advanced_output_preferences(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import restore_advanced_output_preferences

    current_advanced_output = tmp_path / "AdvancedOutput.xml"
    current_slices = tmp_path / "slices.xml"
    source_dir = tmp_path / "bundle"
    source_dir.mkdir()
    source_advanced_output = source_dir / "AdvancedOutput.xml"
    source_slices = source_dir / "slices.xml"
    current_advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    current_slices.write_text(SLICES_XML, encoding="utf-8")
    source_advanced_output.write_text(ADVANCED_OUTPUT_XML.replace("Slice A", "Slice Restored"), encoding="utf-8")
    source_slices.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(current_advanced_output),
            slices_xml_path=str(current_slices),
        ),
    ):
        payload = json.loads(
            restore_advanced_output_preferences(
                str(source_advanced_output),
                backup_dir=str(tmp_path / "backups"),
                confirm_destructive=True,
            )
        )
    assert Path(payload["backups"]["advanced_output_xml"]["backup"]).exists()
    assert "Slice Restored" in current_advanced_output.read_text(encoding="utf-8")


def test_get_windows_advanced_output_path_candidates():
    from resolume_mcp.server import get_windows_advanced_output_path_candidates

    payload = json.loads(get_windows_advanced_output_path_candidates("MediaUser", "D:"))
    assert payload["documents_root"] == "D:\\Users\\MediaUser\\Documents\\Resolume Arena"


def test_probe_advanced_output_paths(tmp_path: Path):
    from resolume_mcp.server import probe_advanced_output_paths

    documents = tmp_path / "Resolume Arena"
    preferences = documents / "Preferences"
    preferences.mkdir(parents=True)
    advanced_output = preferences / "AdvancedOutput.xml"
    slices_xml = preferences / "slices.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    payload = json.loads(
        probe_advanced_output_paths(
            str(documents),
            str(advanced_output),
            str(slices_xml),
        )
    )
    assert payload["documents_root"]["exists"] is True
    assert payload["advanced_output_xml_path"]["is_file"] is True


def test_rename_advanced_output_screen(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import rename_advanced_output_screen

    advanced_output = tmp_path / "AdvancedOutput.xml"
    slices_xml = tmp_path / "slices.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(advanced_output),
            slices_xml_path=str(slices_xml),
        ),
    ):
        payload = json.loads(rename_advanced_output_screen(0, "Main Wall"))
    assert "Main Wall" in advanced_output.read_text(encoding="utf-8")
    assert Path(payload["backup"]["backup"]).exists()


def test_rename_advanced_output_slice(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import rename_advanced_output_slice

    advanced_output = tmp_path / "AdvancedOutput.xml"
    slices_xml = tmp_path / "slices.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(advanced_output),
            slices_xml_path=str(slices_xml),
        ),
    ):
        payload = json.loads(rename_advanced_output_slice(0, 0, "Hero Slice"))
    assert "Hero Slice" in advanced_output.read_text(encoding="utf-8")
    assert Path(payload["backup"]["backup"]).exists()


def test_set_advanced_output_soft_edge_power_xml(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import set_advanced_output_soft_edge_power_xml

    advanced_output = tmp_path / "AdvancedOutput.xml"
    slices_xml = tmp_path / "slices.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(advanced_output),
            slices_xml_path=str(slices_xml),
        ),
    ):
        payload = json.loads(set_advanced_output_soft_edge_power_xml(4.25))
    assert 'value="4.25"' in advanced_output.read_text(encoding="utf-8")
    assert Path(payload["backup"]["backup"]).exists()


def test_set_advanced_output_screen_output_device_xml(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import set_advanced_output_screen_output_device_xml

    advanced_output = tmp_path / "AdvancedOutput.xml"
    slices_xml = tmp_path / "slices.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(advanced_output),
            slices_xml_path=str(slices_xml),
        ),
    ):
        payload = json.loads(
            set_advanced_output_screen_output_device_xml(
                0,
                "LED Wall",
                "\\\\.\\DISPLAY3",
                3840,
                1080,
            )
        )
    assert 'name="LED Wall"' in advanced_output.read_text(encoding="utf-8")
    assert Path(payload["backup"]["backup"]).exists()


def test_set_advanced_output_slice_input_rect_xml(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import set_advanced_output_slice_input_rect_xml

    advanced_output = tmp_path / "AdvancedOutput.xml"
    slices_xml = tmp_path / "slices.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(advanced_output),
            slices_xml_path=str(slices_xml),
        ),
    ):
        payload = json.loads(
            set_advanced_output_slice_input_rect_xml(
                0,
                0,
                '[{"x":1,"y":2}]',
            )
        )
    assert 'x="1" y="2"' in advanced_output.read_text(encoding="utf-8")
    assert Path(payload["backup"]["backup"]).exists()


def test_set_advanced_output_slice_homography_dst_xml_rejects_wrong_count(tmp_path: Path):
    from resolume_mcp.config import ResolumeConfig
    from resolume_mcp.server import set_advanced_output_slice_homography_dst_xml

    advanced_output = tmp_path / "AdvancedOutput.xml"
    slices_xml = tmp_path / "slices.xml"
    advanced_output.write_text(ADVANCED_OUTPUT_XML, encoding="utf-8")
    slices_xml.write_text(SLICES_XML, encoding="utf-8")

    with patch(
        "resolume_mcp.server.load_config",
        return_value=ResolumeConfig(
            documents_root=str(tmp_path),
            advanced_output_xml_path=str(advanced_output),
            slices_xml_path=str(slices_xml),
        ),
        ):
            with pytest.raises(ValueError, match="Vertex count mismatch"):
                set_advanced_output_slice_homography_dst_xml(
                    0,
                    0,
                    '[{"x":1,"y":2},{"x":3,"y":4}]',
                )


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_open_clip_file(mock_client_factory):
    from resolume_mcp.server import open_clip_file

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layers/2/clips/5/openfile"})
    mock_client_factory.return_value = fake

    payload = json.loads(await open_clip_file(2, 5, '{"path":"C:/media/loop.mov"}'))
    assert payload["ok"] is True
    fake.request.assert_awaited_once_with(
        "POST",
        "/composition/layers/2/clips/5/openfile",
        body="file:///C:/media/loop.mov",
    )


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_open_selected_clip_file(mock_client_factory):
    from resolume_mcp.server import open_selected_clip_file

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/clips/selected/openfile"})
    mock_client_factory.return_value = fake

    payload = json.loads(await open_selected_clip_file('{"path":"D:/content/test.png"}'))
    assert payload["path"] == "/api/v1/composition/clips/selected/openfile"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_insert_clip_normalizes_to_array(mock_client_factory):
    from resolume_mcp.server import insert_clip

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layers/1/clips/2/insert"})
    mock_client_factory.return_value = fake

    payload = json.loads(await insert_clip(1, 2, '"file:///Users/test/video.mp4"'))
    assert payload["path"] == "/api/v1/composition/layers/1/clips/2/insert"
    fake.request.assert_awaited_once_with(
        "POST",
        "/composition/layers/1/clips/2/insert",
        body=["file:///Users/test/video.mp4"],
    )


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_add_effect_for_selected_layer(mock_client_factory):
    from resolume_mcp.server import add_effect

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layers/selected/effects/video/add/4"})
    mock_client_factory.return_value = fake

    payload = json.loads(await add_effect("selected-layer", "video", "effect:///video/Blow", effect_index=4))
    assert payload["path"] == "/api/v1/composition/layers/selected/effects/video/add/4"
    fake.request.assert_awaited_once_with(
        "POST",
        "/composition/layers/selected/effects/video/add/4",
        body="effect:///video/Blow",
    )


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_list_available_effects(mock_client_factory):
    from resolume_mcp.server import list_available_effects

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/effects"})
    mock_client_factory.return_value = fake

    payload = json.loads(await list_available_effects())
    assert payload["path"] == "/api/v1/effects"
    fake.request.assert_awaited_once_with("GET", "/effects")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_list_available_sources(mock_client_factory):
    from resolume_mcp.server import list_available_sources

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/sources"})
    mock_client_factory.return_value = fake

    payload = json.loads(await list_available_sources())
    assert payload["path"] == "/api/v1/sources"
    fake.request.assert_awaited_once_with("GET", "/sources")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_product_info(mock_client_factory):
    from resolume_mcp.server import get_product_info

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/product"})
    mock_client_factory.return_value = fake

    payload = json.loads(await get_product_info())
    assert payload["path"] == "/api/v1/product"
    fake.request.assert_awaited_once_with("GET", "/product")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_file_info_normalizes_urls(mock_client_factory):
    from resolume_mcp.server import get_file_info

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/files"})
    mock_client_factory.return_value = fake

    payload = json.loads(await get_file_info('["C:/media/loop.mov", "file:///Users/test/video.mp4"]'))
    assert payload["path"] == "/api/v1/files"
    fake.request.assert_awaited_once_with(
        "POST",
        "/files",
        body=["file:///C:/media/loop.mov", "file:///Users/test/video.mp4"],
    )


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_clip_effect(mock_client_factory):
    from resolume_mcp.server import get_effect

    fake = MagicMock()
    fake.request = AsyncMock(return_value={
        "ok": True,
        "path": "/api/v1/composition/layers/1/clips/3",
        "body": {
            "audio": {
                "effects": [
                    {"name": "EQ"},
                    {"name": "Reverb", "display_name": "Big Verb"},
                ]
            }
        },
    })
    mock_client_factory.return_value = fake

    payload = json.loads(await get_effect("clip", "audio", 2, layer_index=1, clip_index=3))
    assert payload["path"] == "/api/v1/composition/layers/1/clips/3/effects/audio/2"
    assert payload["fallback_used"] is True
    assert payload["body"]["display_name"] == "Big Verb"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_remove_effect_from_composition(mock_client_factory):
    from resolume_mcp.server import remove_effect

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/effects/video/1"})
    mock_client_factory.return_value = fake

    payload = json.loads(await remove_effect("composition", "video", 1, confirm_destructive=True))
    assert payload["path"] == "/api/v1/composition/effects/video/1"
    fake.request.assert_awaited_once_with("DELETE", "/composition/effects/video/1")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_remove_effect_from_clip_uses_clip_id(mock_client_factory):
    from resolume_mcp.server import remove_effect

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layers/1/clips/2/effects/video/1"})
    mock_client_factory.return_value = fake

    payload = json.loads(await remove_effect("clip", "video", 1, layer_index=1, clip_index=2, confirm_destructive=True))
    assert payload["path"] == "/api/v1/composition/layers/1/clips/2/effects/video/1"
    fake.request.assert_awaited_once_with("DELETE", "/composition/layers/1/clips/2/effects/video/1")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_move_group_video_effect(mock_client_factory):
    from resolume_mcp.server import move_video_effect

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layergroups/2/effects/video/move"})
    mock_client_factory.return_value = fake

    payload = json.loads(await move_video_effect("group", '{"from":1,"to":0}', group_index=2))
    assert payload["path"] == "/api/v1/composition/layergroups/2/effects/video/move"
    fake.request.assert_awaited_once_with(
        "POST",
        "/composition/layergroups/2/effects/video/move",
        body={"from": 1, "to": 0},
    )


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_rename_composition_effect(mock_client_factory):
    from resolume_mcp.server import rename_effect

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/effects/video/1/set-display-name"})
    mock_client_factory.return_value = fake

    payload = json.loads(await rename_effect("composition", "video", 1, "Glow FX"))
    assert payload["path"] == "/api/v1/composition/effects/video/1/set-display-name"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_duplicate_layer(mock_client_factory):
    from resolume_mcp.server import duplicate_layer

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layers/3/duplicate"})
    mock_client_factory.return_value = fake

    payload = json.loads(await duplicate_layer(3))
    assert payload["path"] == "/api/v1/composition/layers/3/duplicate"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_add_group(mock_client_factory):
    from resolume_mcp.server import add_group

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layergroups/add"})
    mock_client_factory.return_value = fake

    payload = json.loads(await add_group('{"name":"Notch Group"}'))
    assert payload["path"] == "/api/v1/composition/layergroups/add"
    fake.request.assert_awaited_once_with(
        "POST",
        "/composition/layergroups/add",
        body={"name": "Notch Group"},
    )


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_clear_selected_group(mock_client_factory):
    from resolume_mcp.server import clear_selected_group

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layergroups/selected/clear"})
    mock_client_factory.return_value = fake

    payload = json.loads(await clear_selected_group(confirm_destructive=True))
    assert payload["path"] == "/api/v1/composition/layergroups/selected/clear"
    fake.request.assert_awaited_once_with("POST", "/composition/layergroups/selected/clear")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_move_layer_to_group(mock_client_factory):
    from resolume_mcp.server import move_layer_to_group

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layergroups/1/move-layer"})
    mock_client_factory.return_value = fake

    payload = json.loads(await move_layer_to_group(1, '{"layerIndex":4}'))
    assert payload["path"] == "/api/v1/composition/layergroups/1/move-layer"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_clear_layer_clips(mock_client_factory):
    from resolume_mcp.server import clear_layer_clips

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": {"clips": [{"id": 1}]}},
        {"body": {"name": {"value": "Loaded"}, "connected": {"value": "Disconnected"}, "video": {}, "audio": {}}},
        {"ok": True, "path": "/api/v1/composition/layers/6/clearclips"},
        {"body": {"name": {"value": ""}, "connected": {"value": "Empty"}, "video": {}, "audio": {}}},
        {"body": {"name": {"value": ""}, "connected": {"value": "Empty"}}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await clear_layer_clips(6, confirm_destructive=True))
    assert payload["response"]["path"] == "/api/v1/composition/layers/6/clearclips"
    assert payload["cleared"] is True


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_clear_selected_layer_clips(mock_client_factory):
    from resolume_mcp.server import clear_selected_layer_clips

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": {"clips": [{"name": {"value": "Loaded"}, "connected": {"value": "Disconnected"}, "video": {}, "audio": {}}]}},
        {"ok": True, "path": "/api/v1/composition/layers/selected/clearclips"},
        {"body": {"clips": [{"name": {"value": ""}, "connected": {"value": "Empty"}, "video": {}, "audio": {}}]}},
        {"body": {"clips": [{"name": {"value": ""}, "connected": {"value": "Empty"}}]}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await clear_selected_layer_clips(confirm_destructive=True))
    assert payload["response"]["path"] == "/api/v1/composition/layers/selected/clearclips"
    assert payload["cleared"] is True


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_group_column(mock_client_factory):
    from resolume_mcp.server import get_group_column

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layergroups/1/columns/2"})
    mock_client_factory.return_value = fake

    payload = json.loads(await get_group_column(1, 2))
    assert payload["path"] == "/api/v1/composition/layergroups/1/columns/2"
    fake.request.assert_awaited_once_with("GET", "/composition/layergroups/1/columns/2")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_trigger_group_column(mock_client_factory):
    from resolume_mcp.server import trigger_group_column

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layergroups/1/columns/2/connect"})
    mock_client_factory.return_value = fake

    payload = json.loads(await trigger_group_column(1, 2))
    assert payload["path"] == "/api/v1/composition/layergroups/1/columns/2/connect"
    fake.request.assert_awaited_once_with("POST", "/composition/layergroups/1/columns/2/connect")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_select_group_column(mock_client_factory):
    from resolume_mcp.server import select_group_column

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layergroups/1/columns/2/select"})
    mock_client_factory.return_value = fake

    payload = json.loads(await select_group_column(1, 2))
    assert payload["path"] == "/api/v1/composition/layergroups/1/columns/2/select"
    fake.request.assert_awaited_once_with("POST", "/composition/layergroups/1/columns/2/select")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_disconnect_all(mock_client_factory):
    from resolume_mcp.server import disconnect_all

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/disconnect-all"})
    mock_client_factory.return_value = fake

    payload = json.loads(await disconnect_all(confirm_destructive=True))
    assert payload["path"] == "/api/v1/composition/disconnect-all"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_select_deck(mock_client_factory):
    from resolume_mcp.server import select_deck

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/decks/2/select"})
    mock_client_factory.return_value = fake

    payload = json.loads(await select_deck(2))
    assert payload["path"] == "/api/v1/composition/decks/2/select"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_revert_clip_thumbnail(mock_client_factory):
    from resolume_mcp.server import revert_clip_thumbnail

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layers/1/clips/2/thumbnail"})
    mock_client_factory.return_value = fake

    payload = json.loads(await revert_clip_thumbnail(1, 2))
    assert payload["path"] == "/api/v1/composition/layers/1/clips/2/thumbnail"
    fake.request.assert_awaited_once_with("DELETE", "/composition/layers/1/clips/2/thumbnail")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_revert_selected_clip_thumbnail(mock_client_factory):
    from resolume_mcp.server import revert_selected_clip_thumbnail

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/clips/selected/thumbnail"})
    mock_client_factory.return_value = fake

    payload = json.loads(await revert_selected_clip_thumbnail())
    assert payload["path"] == "/api/v1/composition/clips/selected/thumbnail"
    fake.request.assert_awaited_once_with("DELETE", "/composition/clips/selected/thumbnail")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_trigger_selected_clip(mock_client_factory):
    from resolume_mcp.server import trigger_selected_clip

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/clips/selected/connect"})
    mock_client_factory.return_value = fake

    payload = json.loads(await trigger_selected_clip())
    assert payload["path"] == "/api/v1/composition/clips/selected/connect"
    fake.request.assert_awaited_once_with("POST", "/composition/clips/selected/connect")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_disconnect_selected_clip_reports_verified_state(mock_client_factory):
    from resolume_mcp.server import disconnect_selected_clip

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": {"connected": {"value": "Connected"}}},
        {"ok": True, "path": "/api/v1/composition/clips/selected/connect"},
        {"body": {"connected": {"value": "Connected"}}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await disconnect_selected_clip(confirm_destructive=True))
    assert payload["before_state"] == "Connected"
    assert payload["after_state"] == "Connected"
    assert payload["disconnected"] is False


@pytest.mark.asyncio
async def test_add_effect_rejects_bad_kind():
    from resolume_mcp.server import add_effect

    with pytest.raises(ValueError, match="effect_kind must be 'audio' or 'video'"):
        await add_effect("composition", "shader", "effect:///video/Blow")


@pytest.mark.asyncio
async def test_add_effect_requires_spec():
    from resolume_mcp.server import add_effect

    with pytest.raises(ValueError, match="effect_spec is required"):
        await add_effect("composition", "video", "   ")


@pytest.mark.asyncio
async def test_disconnect_all_requires_confirmation():
    """Destructive tools must require confirm_destructive=True."""
    from resolume_mcp.server import disconnect_all
    result = await disconnect_all()
    parsed = json.loads(result)
    assert parsed["requires_confirmation"] is True
    assert "disconnect" in parsed["message"].lower()


@pytest.mark.asyncio
async def test_clear_composition_requires_confirmation():
    """clear_composition must require confirmation before proceeding."""
    from resolume_mcp.server import clear_composition
    result = await clear_composition()
    parsed = json.loads(result)
    assert parsed["requires_confirmation"] is True
    assert "composition" in parsed["message"].lower()


@pytest.mark.asyncio
async def test_clear_clip_requires_confirmation():
    """clear_clip must require confirmation before proceeding."""
    from resolume_mcp.server import clear_clip
    result = await clear_clip(layer_index=1, clip_index=1)
    parsed = json.loads(result)
    assert parsed["requires_confirmation"] is True


@pytest.mark.asyncio
async def test_remove_effect_requires_confirmation():
    """remove_effect must require confirmation before proceeding."""
    from resolume_mcp.server import remove_effect
    result = await remove_effect(scope="composition", effect_kind="video", effect_index=1)
    parsed = json.loads(result)
    assert parsed["requires_confirmation"] is True


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_reports_unverified_when_read_back_differs(mock_client_factory):
    from resolume_mcp.server import set_layer_opacity

    fake = MagicMock()
    fake.request = _rest_by_path({"/composition/layers/1": {"body": {"video": {"opacity": {"id": 2002, "value": 1.0}}}}})
    fake.websocket_action = AsyncMock(return_value={"response": None})
    mock_client_factory.return_value = fake

    payload = json.loads(await set_layer_opacity(1, 0.25))
    assert payload["value_before"] == 1.0
    assert payload["value_after"] == 1.0
    assert payload["verified"] is False
    assert payload["retried"] is True
    assert fake.websocket_action.await_count == 2
    # one resolve read + four verification polls, twice
    assert fake.request.await_count == 9


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_retry_succeeds_when_first_set_is_dropped(mock_client_factory):
    from resolume_mcp.server import set_clip_parameter

    reads = [
        {"body": {"transporttype": {"id": 7001, "value": "Timeline", "options": ["Timeline", "BPM Sync", "SMPTE 1"]}}},
    ] * 5 + [
        {"body": {"transporttype": {"id": 7001, "value": "SMPTE 1", "options": ["Timeline", "BPM Sync", "SMPTE 1"]}}},
    ]
    fake = MagicMock()
    fake.request = AsyncMock(side_effect=reads)
    fake.websocket_action = AsyncMock(return_value={"response": None})
    mock_client_factory.return_value = fake

    payload = json.loads(await set_clip_parameter(1, 3, "transporttype", '"SMPTE 1"'))
    assert payload["verified"] is True
    assert payload["retried"] is True


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_position_is_not_retried(mock_client_factory):
    from resolume_mcp.server import set_clip_transport_position

    fake = MagicMock()
    fake.request = _rest_by_path({"/composition/layers/1/clips/1": {"body": {"transport": {"position": {"id": 5, "value": 0.9}}}}})
    fake.websocket_action = AsyncMock(return_value={"response": None})
    mock_client_factory.return_value = fake

    payload = json.loads(await set_clip_transport_position(1, 1, 0.1))
    assert payload["verified"] is False
    assert "retried" not in payload
    assert fake.websocket_action.await_count == 1


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_set_rejects_value_outside_choice_options(mock_client_factory):
    from resolume_mcp.server import set_clip_parameter

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"body": {"ignorecolumntrigger": {"id": 8, "value": "Layer Determined", "options": ["Layer Determined", "On", "Off"]}}})
    fake.websocket_action = AsyncMock()
    mock_client_factory.return_value = fake

    with pytest.raises(ValueError, match="'Layer Determined', 'On', 'Off'"):
        await set_clip_parameter(1, 1, "ignorecolumntrigger", "true")
    fake.websocket_action.assert_not_awaited()


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("source:///video/DeckLink 8K Pro (1) - SDI 1", "source:///video/DeckLink%208K%20Pro%20%281%29%20-%20SDI%201"),
        ("source:///video/DeckLink%208K%20Pro%20%281%29", "source:///video/DeckLink%208K%20Pro%20%281%29"),
        ("effect:///video/AR IMAG", "effect:///video/AR%20IMAG"),
        ("source:///video/Solid Color", "source:///video/Solid%20Color"),
        ("file:///C:/Videos/a.mov", "file:///C:/Videos/a.mov"),
    ],
)
def test_resolume_uris_are_percent_encoded(raw, expected):
    from resolume_mcp.server import _normalize_media_uri

    assert _normalize_media_uri(raw) == expected


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_add_effect_encodes_effect_name(mock_client_factory):
    from resolume_mcp.server import add_effect

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True})
    mock_client_factory.return_value = fake

    await add_effect("layer", "video", "effect:///video/AR IMAG", layer_index=2)
    fake.request.assert_awaited_once_with("POST", "/composition/layers/2/effects/video/add", body="effect:///video/AR%20IMAG")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_websocket_subscribe_watches_and_unsubscribe_is_a_noop(mock_client_factory):
    from resolume_mcp.server import websocket_subscribe, websocket_unsubscribe

    fake = MagicMock()
    fake.websocket_watch = AsyncMock(return_value={"update_count": 2})
    mock_client_factory.return_value = fake

    payload = json.loads(await websocket_subscribe("/parameter/by-id/5", duration_s=3))
    assert payload["update_count"] == 2
    fake.websocket_watch.assert_awaited_once_with(["/parameter/by-id/5"], duration_s=3)

    mock_client_factory.reset_mock()
    payload = json.loads(await websocket_unsubscribe("/parameter/by-id/5"))
    assert payload["response"] is None
    mock_client_factory.assert_not_called()


@pytest.mark.asyncio
async def test_every_tool_is_described_and_annotated():
    import inspect

    from resolume_mcp import server

    tools = await mcp.list_tools()
    assert tools
    for tool in tools:
        assert tool.description, f"{tool.name} has no description"
        assert tool.annotations is not None, f"{tool.name} has no annotations"
        gated = "confirm_destructive" in inspect.signature(getattr(server, tool.name)).parameters
        if gated:
            assert tool.annotations.destructiveHint is True, f"{tool.name} is gated but not marked destructive"
        if tool.annotations.readOnlyHint:
            assert not gated, f"{tool.name} is read-only but gated"


def _show_composition():
    """Composition shaped like Arena's REST payload, with bulky per-clip parameter trees."""
    bulky = {"video": {"effects": [{"params": {f"p{i}": {"id": i, "value": 0.5} for i in range(200)}}]}}

    def clip(name, connected, transport="Timeline"):
        if connected == "Empty":
            return {"connected": {"value": "Empty"}, **bulky}
        return {"name": {"value": name}, "connected": {"value": connected}, "transporttype": {"value": transport}, **bulky}

    return {
        "path": "/api/v1/composition",
        "body": {
            "name": {"value": "AvoidRafa"},
            "tempocontroller": {"tempo": {"id": 1, "value": 124.0}},
            "layers": [
                {"name": {"value": "Timecode"}, "bypassed": {"value": False}, "video": {"opacity": {"value": 1.0}},
                 "clips": [clip("01_intro", "Connected", "SMPTE 1"), clip("02_drop", "Disconnected", "SMPTE 1"), clip(None, "Empty")]},
                {"name": {"value": "IMAG"}, "bypassed": {"value": True}, "video": {"opacity": {"value": 0.0}},
                 "clips": [clip(None, "Empty"), clip("DeckLink feed", "Disconnected")]},
            ],
            "columns": [{"name": {"value": "Column 1"}}, {"name": {"value": "Column 2"}}],
            "decks": [{"name": {"value": "Show"}, "selected": {"value": True}}],
            "layergroups": [],
        },
    }


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_composition_summary_is_compact(mock_client_factory):
    from resolume_mcp.server import get_composition_summary

    composition = _show_composition()
    fake = MagicMock()
    fake.request = AsyncMock(return_value=composition)
    mock_client_factory.return_value = fake

    raw = await get_composition_summary()
    payload = json.loads(raw)
    assert payload["name"] == "AvoidRafa"
    assert payload["bpm"] == 124.0
    assert payload["layer_count"] == 2
    timecode, imag = payload["layers"]
    assert timecode == {
        "layer_index": 1, "name": "Timecode", "bypassed": False, "opacity": 1.0, "clip_slots": 3,
        "loaded_clip_count": 2,
        "playing": [{"clip_index": 1, "name": "01_intro", "connected": "Connected", "transport_type": "SMPTE 1"}],
    }
    assert imag["bypassed"] is True and imag["playing"] == []
    assert payload["decks"] == [{"deck_index": 1, "name": "Show", "selected": True}]
    assert len(raw) * 20 < len(json.dumps(composition))
    fake.request.assert_awaited_once_with("GET", "/composition")


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_layer_summary_lists_loaded_slots(mock_client_factory):
    from resolume_mcp.server import get_layer_summary

    layer = _show_composition()["body"]["layers"][0]
    fake = MagicMock()
    fake.request = AsyncMock(return_value={"path": "/api/v1/composition/layers/1", "body": layer})
    mock_client_factory.return_value = fake

    payload = json.loads(await get_layer_summary(1))
    assert payload["name"] == "Timecode"
    assert [clip["clip_index"] for clip in payload["clips"]] == [1, 2]
    assert payload["clips"][1] == {"clip_index": 2, "name": "02_drop", "connected": "Disconnected", "transport_type": "SMPTE 1"}


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_wait_for_resolume_retries_until_ready(mock_client_factory):
    from resolume_mcp.client import ResolumeConnectionError
    from resolume_mcp.server import wait_for_resolume

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        ResolumeConnectionError("not up yet"),
        {"ok": False, "status_code": 503},
        {"ok": True, "body": {"name": "Arena", "major": 7}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await wait_for_resolume(timeout_s=5, interval_s=0.01))
    assert payload["ready"] is True
    assert payload["attempts"] == 3
    assert payload["product"]["name"] == "Arena"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_wait_for_resolume_gives_up_after_timeout(mock_client_factory):
    from resolume_mcp.client import ResolumeConnectionError
    from resolume_mcp.server import wait_for_resolume

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=ResolumeConnectionError("refused"))
    mock_client_factory.return_value = fake

    payload = json.loads(await wait_for_resolume(timeout_s=0.05, interval_s=0.01))
    assert payload["ready"] is False
    assert payload["last_error"] == "refused"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_save_composition_explains_missing_endpoint(mock_client_factory):
    from resolume_mcp.server import save_composition

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"path": "/api/v1/composition/save", "status_code": 404, "ok": False})
    mock_client_factory.return_value = fake

    payload = json.loads(await save_composition())
    assert "Ctrl+S" in payload["note"]
