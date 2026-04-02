import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

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
        await clear_layers("{\"bad\":true}")


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
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition"},
        {"path": "/api/v1/composition/layers"},
        {"path": "/api/v1/composition/columns"},
        {"path": "/api/v1/composition/layergroups"},
        {"path": "/api/v1/composition", "body": {"decks": [{"id": 1}]}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await get_composition_overview())
    assert payload["composition"]["path"] == "/api/v1/composition"
    assert payload["decks"]["body"] == [{"id": 1}]


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_audit_composition(mock_client_factory):
    from resolume_mcp.server import audit_composition

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition", "body": {"tempocontroller": {"tempo": {"id": 1001, "value": 0}}}},
        {"body": []},
        {"body": []},
        {"body": []},
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
    fake.websocket_action = AsyncMock(return_value={"response": {"action": "subscribe"}})
    mock_client_factory.return_value = fake

    payload = json.loads(await subscribe_composition_parameter("tempocontroller/tempo"))
    assert payload["request"]["action"] == "subscribe"
    assert payload["request"]["parameter"] == "/parameter/by-id/1001"


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
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/columns"})
    mock_client_factory.return_value = fake

    payload = json.loads(await list_columns())
    assert payload["path"] == "/api/v1/composition/columns"


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
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition/layers/2", "body": {"video": {"opacity": {"id": 2002}}, "bypassed": {"id": 2003}}},
        {"path": "/api/v1/composition/layers/2/clips"},
        {"body": {"video": {"opacity": {"id": 2002}}, "bypassed": {"id": 2003}}},
        {"body": {"video": {"opacity": {"id": 2002}}, "bypassed": {"id": 2003}}},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"value": 1.0}},
        {"response": {"value": False}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await get_layer_snapshot(2))
    assert payload["layer"]["path"] == "/api/v1/composition/layers/2"
    assert payload["clips"]["path"] == "/api/v1/composition/layers/2/clips"
    assert payload["opacity"]["request"]["parameter"] == "/parameter/by-id/2002"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_audit_layer(mock_client_factory):
    from resolume_mcp.server import audit_layer

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition/layers/1", "body": {"video": {"opacity": {"id": 2002}}, "bypassed": {"id": 2003}}},
        {"body": []},
        {"body": {"video": {"opacity": {"id": 2002}}, "bypassed": {"id": 2003}}},
        {"body": {"video": {"opacity": {"id": 2002}}, "bypassed": {"id": 2003}}},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"value": 0}},
        {"response": {"value": True}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await audit_layer(1))
    assert "Layer contains no clips." in payload["findings"]
    assert "Layer opacity is zero." in payload["findings"]
    assert "Layer is bypassed." in payload["findings"]


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_disconnect_clip(mock_client_factory):
    from resolume_mcp.server import disconnect_clip

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"ok": True, "path": "/api/v1/composition/layers/1/clips/2/connect"})
    mock_client_factory.return_value = fake

    payload = json.loads(await disconnect_clip(1, 2))
    assert payload["ok"] is True
    fake.request.assert_awaited_once_with("POST", "/composition/layers/1/clips/2/connect", body=False)


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_subscribe_clip_parameter(mock_client_factory):
    from resolume_mcp.server import subscribe_clip_parameter

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"body": {"transport": {"position": {"id": 3003}}}})
    fake.websocket_action = AsyncMock(return_value={"response": {"action": "subscribe"}})
    mock_client_factory.return_value = fake

    payload = json.loads(await subscribe_clip_parameter(1, 2, "transport/position"))
    assert payload["request"]["parameter"] == "/parameter/by-id/3003"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_get_clip_snapshot(mock_client_factory):
    from resolume_mcp.server import get_clip_snapshot

    fake = MagicMock()
    clip_body = {
        "connected": {"id": 3001},
        "selected": {"id": 3002},
        "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}},
    }
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition/layers/1/clips/2", "body": clip_body},
        {"body": clip_body},
        {"body": clip_body},
        {"body": clip_body},
        {"body": clip_body},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"value": "Connected"}},
        {"response": {"value": True}},
        {"response": {"value": 1.0}},
        {"response": {"value": 0.5}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await get_clip_snapshot(1, 2))
    assert payload["clip"]["path"] == "/api/v1/composition/layers/1/clips/2"
    assert payload["speed"]["request"]["parameter"] == "/parameter/by-id/3004"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_audit_clip(mock_client_factory):
    from resolume_mcp.server import audit_clip

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition/layers/2/clips/4", "body": {"connected": {"id": 3001}, "selected": {"id": 3002}, "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}}}},
        {"body": {"connected": {"id": 3001}, "selected": {"id": 3002}, "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}}}},
        {"body": {"connected": {"id": 3001}, "selected": {"id": 3002}, "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}}}},
        {"body": {"connected": {"id": 3001}, "selected": {"id": 3002}, "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}}}},
        {"body": {"connected": {"id": 3001}, "selected": {"id": 3002}, "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}}}},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"value": "Disconnected"}},
        {"response": {"value": False}},
        {"response": {"value": 0}},
        {"response": {"value": 0.1}},
        {"error": "Could not resolve parameter"},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await audit_clip(2, 4))
    assert "Clip is disconnected." in payload["findings"]
    assert "Clip speed is zero." in payload["findings"]


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
        {"path": "/api/v1/composition/layers/1/clips/2/connect"},
        {"path": "/api/v1/composition/layers/1/clips/3/connect"},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await disconnect_clips(1, "[2,3]"))
    assert len(payload["results"]) == 2
    fake.request.assert_any_await("POST", "/composition/layers/1/clips/2/connect", body=False)


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

    payload = json.loads(await clear_layers("[1,4]"))
    assert len(payload["results"]) == 2
    assert payload["results"][0]["layer_index"] == 1


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_prepare_layer(mock_client_factory):
    from resolume_mcp.server import prepare_layer

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": {"bypassed": {"id": 2003}}},
        {"body": {"video": {"opacity": {"id": 2002}}}},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"value": False}},
        {"response": {"value": 0.9}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await prepare_layer(3, opacity=0.9, unbypass=True))
    assert len(payload["results"]) == 2
    assert payload["results"][1]["action"] == "set_layer_opacity"


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_prepare_multiple_layers(mock_client_factory):
    from resolume_mcp.server import prepare_multiple_layers

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": {"bypassed": {"id": 2001}}},
        {"body": {"bypassed": {"id": 2002}}},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"value": False}},
        {"response": {"value": False}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await prepare_multiple_layers("[1,2]", unbypass=True))
    assert payload["layer_count"] == 2


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_prepare_playback(mock_client_factory):
    from resolume_mcp.server import prepare_playback

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": {}},
        {"body": {"tempocontroller": {"tempo": {"id": 1001}}}},
        {"body": {"bypassed": {"id": 2001}}},
        {"body": {"video": {"opacity": {"id": 2002}}}},
        {"body": {"bypassed": {"id": 2003}}},
        {"body": {"video": {"opacity": {"id": 2004}}}},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"value": 128}},
        {"response": {"value": False}},
        {"response": {"value": 1.0}},
        {"response": {"value": False}},
        {"response": {"value": 1.0}},
    ])
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
    fake.request = AsyncMock(side_effect=[
        {"path": "/api/v1/composition", "body": {"tempocontroller": {"tempo": {"id": 1001}}}},
        {"body": {"tempocontroller": {"tempo": {"id": 1001}}}},
        {"body": {"video": {"opacity": {"id": 2002}}, "bypassed": {"id": 2003}}},
        {"body": {"video": {"opacity": {"id": 2002}}, "bypassed": {"id": 2003}}},
        {"body": {"connected": {"id": 3001}, "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}}}},
        {"body": {"connected": {"id": 3001}, "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}}}},
        {"body": {"connected": {"id": 3001}, "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}}}},
        {"body": {"connected": {"id": 3001}, "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}}}},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"value": 128}},
        {"response": {"value": 1.0}},
        {"response": {"value": False}},
        {"response": {"value": "Connected"}},
        {"response": {"value": 1.0}},
        {"response": {"value": 0.25}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(
        await monitor_playback_state(
            layer_indices_json="[1]",
            clip_pairs_json='[{"layer_index":1,"clip_index":2}]',
        )
    )
    assert payload["tempo"]["request"]["parameter"] == "/parameter/by-id/1001"
    assert payload["layers"][0]["layer_index"] == 1
    assert payload["clips"][0]["clip_index"] == 2


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_subscribe_playback_state(mock_client_factory):
    from resolume_mcp.server import subscribe_playback_state

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": {"tempocontroller": {"tempo": {"id": 1001}}}},
        {"body": {"video": {"opacity": {"id": 2002}}, "bypassed": {"id": 2003}}},
        {"body": {"video": {"opacity": {"id": 2002}}, "bypassed": {"id": 2003}}},
        {"body": {"connected": {"id": 3001}, "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}}}},
        {"body": {"connected": {"id": 3001}, "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}}}},
        {"body": {"connected": {"id": 3001}, "transport": {"position": {"id": 3003}, "controls": {"speed": {"id": 3004}}}}},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"action": "subscribe"}},
        {"response": {"action": "subscribe"}},
        {"response": {"action": "subscribe"}},
        {"response": {"action": "subscribe"}},
        {"response": {"action": "subscribe"}},
        {"response": {"action": "subscribe"}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(
        await subscribe_playback_state(
            layer_indices_json="[1]",
            clip_pairs_json='[{"layer_index":1,"clip_index":2}]',
        )
    )
    assert len(payload["results"]) == 6


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_unsubscribe_playback_state(mock_client_factory):
    from resolume_mcp.server import unsubscribe_playback_state

    fake = MagicMock()
    fake.request = AsyncMock(return_value={"body": {"tempocontroller": {"tempo": {"id": 1001}}}})
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"action": "unsubscribe"}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await unsubscribe_playback_state())
    assert len(payload["results"]) == 1


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
    fake.request = AsyncMock(side_effect=[
        {"body": {"selected": {"id": 4001}, "scrollx": {"id": 4002}}},
        {"body": {"selected": {"id": 4001}, "scrollx": {"id": 4002}}},
        {"body": {"selected": {"id": 5001}, "scrollx": {"id": 5002}}},
        {"body": {"selected": {"id": 5001}, "scrollx": {"id": 5002}}},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"action": "subscribe"}},
        {"response": {"action": "subscribe"}},
        {"response": {"action": "subscribe"}},
        {"response": {"action": "subscribe"}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await subscribe_decks("[1,2]"))
    assert len(payload["results"]) == 4


@pytest.mark.asyncio
@patch("resolume_mcp.server._client")
async def test_unsubscribe_decks(mock_client_factory):
    from resolume_mcp.server import unsubscribe_decks

    fake = MagicMock()
    fake.request = AsyncMock(side_effect=[
        {"body": {"selected": {"id": 4001}, "scrollx": {"id": 4002}}},
        {"body": {"selected": {"id": 4001}, "scrollx": {"id": 4002}}},
    ])
    fake.websocket_action = AsyncMock(side_effect=[
        {"response": {"action": "unsubscribe"}},
        {"response": {"action": "unsubscribe"}},
    ])
    mock_client_factory.return_value = fake

    payload = json.loads(await unsubscribe_decks("[1]"))
    assert len(payload["results"]) == 2


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
    fake.websocket_action = AsyncMock(return_value={"request": {"action": "subscribe", "parameter": "/advancedoutput/screens/2/transform/rotation"}})
    mock_client_factory.return_value = fake

    payload = json.loads(await subscribe_output_screen_parameter(2, "transform/rotation"))
    assert payload["request"]["parameter"] == "/advancedoutput/screens/2/transform/rotation"


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
    fake.websocket_action = AsyncMock(return_value={"request": {"action": "subscribe", "parameter": "/advancedoutput/screens/1/slices/2/feather"}})
    mock_client_factory.return_value = fake

    payload = json.loads(await subscribe_output_slice_parameter(1, 2, "feather"))
    assert payload["request"]["parameter"] == "/advancedoutput/screens/1/slices/2/feather"


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
        payload = json.loads(restore_advanced_output_preferences(str(source_advanced_output), backup_dir=str(tmp_path / "backups")))
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
