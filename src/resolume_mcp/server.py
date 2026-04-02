from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .advanced_output_xml import (
    AdvancedOutputPreferences,
    SliceInspectorPreferences,
    backup_xml_file,
    diff_xml_text,
)
from .client import ResolumeClient
from .config import load_config


def _client() -> ResolumeClient:
    return ResolumeClient(load_config())


def _parse_json(value: str | None) -> Any:
    if value is None or not value.strip():
        return None
    return json.loads(value)


def _json_response(payload: Any) -> str:
    return json.dumps(payload, indent=2)


def _extract_body(payload: Any) -> Any:
    if isinstance(payload, dict) and "body" in payload:
        return payload["body"]
    return payload


def _normalize_output_path(path: str) -> str:
    path = (path or "").strip()
    if not path:
        return "/advancedoutput"
    if not path.startswith("/"):
        path = f"/{path}"
    if not path.startswith("/advancedoutput"):
        path = f"/advancedoutput{path}"
    return path


def _join_parameter_path(base: str, suffix: str) -> str:
    suffix = (suffix or "").strip()
    if not suffix:
        return base
    if suffix.startswith("/"):
        suffix = suffix[1:]
    return f"{base}/{suffix}"


def _parse_json_list(value: str, *, field_name: str) -> list[Any]:
    parsed = _parse_json(value)
    if not isinstance(parsed, list):
        raise ValueError(f"{field_name} must decode to a JSON array.")
    return parsed


def _parameter_path_from_id(parameter_id: int) -> str:
    return f"/parameter/by-id/{parameter_id}"


def _lookup_parameter_node(payload: Any, parameter_suffix: str, aliases: tuple[str, ...] = ()) -> dict[str, Any]:
    body = _extract_body(payload)
    if not isinstance(body, dict):
        raise ValueError("REST payload body must be a JSON object to resolve a parameter.")

    candidates = [parameter_suffix.strip(), *[alias.strip() for alias in aliases if alias.strip()]]
    for candidate in candidates:
        if not candidate:
            continue
        node: Any = body
        found = True
        for part in candidate.split("/"):
            if not isinstance(node, dict) or part not in node:
                found = False
                break
            node = node[part]
        if found and isinstance(node, dict) and isinstance(node.get("id"), int):
            return {"suffix": candidate, "node": node}

    joined = ", ".join(repr(value) for value in candidates if value)
    raise ValueError(f"Could not resolve parameter in REST payload for suffix {joined}.")


async def _resolve_parameter_reference(
    client: ResolumeClient,
    rest_path: str,
    parameter_suffix: str,
    aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    rest_payload = await client.request("GET", rest_path)
    resolved = _lookup_parameter_node(rest_payload, parameter_suffix, aliases=aliases)
    node = resolved["node"]
    return {
        "rest_path": rest_path,
        "resolved_suffix": resolved["suffix"],
        "parameter_id": node["id"],
        "parameter_path": _parameter_path_from_id(node["id"]),
        "rest_payload": rest_payload,
        "node": node,
    }


async def _parameter_action(
    client: ResolumeClient,
    *,
    action: str,
    rest_path: str,
    parameter_suffix: str,
    value: Any = None,
    aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    reference = await _resolve_parameter_reference(client, rest_path, parameter_suffix, aliases=aliases)
    response = await client.websocket_action(action, reference["parameter_path"], value=value)
    return {
        "request": {
            "action": action,
            "parameter": reference["parameter_path"],
            "rest_path": rest_path,
            "resolved_suffix": reference["resolved_suffix"],
            **({"value": value} if action == "set" else {}),
        },
        "response": response,
        "parameter": reference["node"],
    }


async def _websocket_get_or_error(client: ResolumeClient, parameter: str) -> dict[str, Any]:
    try:
        return await client.websocket_action("get", parameter)
    except Exception as exc:
        return {"error": str(exc), "parameter": parameter}


async def _resolved_get_or_error(
    client: ResolumeClient,
    *,
    rest_path: str,
    parameter_suffix: str,
    aliases: tuple[str, ...] = (),
) -> dict[str, Any]:
    try:
        return await _parameter_action(
            client,
            action="get",
            rest_path=rest_path,
            parameter_suffix=parameter_suffix,
            aliases=aliases,
        )
    except Exception as exc:
        return {
            "error": str(exc),
            "rest_path": rest_path,
            "parameter_suffix": parameter_suffix,
            "aliases": list(aliases),
        }


def _advanced_output_preferences() -> AdvancedOutputPreferences:
    return AdvancedOutputPreferences.load(load_config().advanced_output_xml_path)


def _slice_inspector_preferences() -> SliceInspectorPreferences:
    return SliceInspectorPreferences.load(load_config().slices_xml_path)


mcp = FastMCP(
    name="Resolume MCP",
    instructions=(
        "Private MCP server for Resolume Arena/Avenue control via REST, "
        "WebSocket, and OSC. Use the generic API tools for full surface access "
        "and the convenience tools for common composition, layer, and clip operations."
    ),
)


@mcp.tool()
def get_server_config() -> str:
    config = load_config()
    return _json_response(
        {
            "host": config.host,
            "http_port": config.http_port,
            "osc_port": config.osc_port,
            "use_https": config.use_https,
            "http_base_url": config.http_base_url,
            "websocket_url": config.websocket_url,
            "documents_root": config.documents_root,
            "advanced_output_xml_path": config.advanced_output_xml_path,
            "slices_xml_path": config.slices_xml_path,
        }
    )


@mcp.tool()
async def rest_request(
    method: str,
    path: str,
    body_json: str = "",
    query_json: str = "",
) -> str:
    body = _parse_json(body_json)
    params = _parse_json(query_json)
    result = await _client().request(method, path, body=body, params=params)
    return _json_response(result)


@mcp.tool()
async def rest_get(path: str, query_json: str = "") -> str:
    params = _parse_json(query_json)
    result = await _client().request("GET", path, params=params)
    return _json_response(result)


@mcp.tool()
async def rest_post(path: str, body_json: str = "") -> str:
    body = _parse_json(body_json)
    result = await _client().request("POST", path, body=body)
    return _json_response(result)


@mcp.tool()
async def rest_put(path: str, body_json: str = "") -> str:
    body = _parse_json(body_json)
    result = await _client().request("PUT", path, body=body)
    return _json_response(result)


@mcp.tool()
async def rest_delete(path: str, body_json: str = "") -> str:
    body = _parse_json(body_json)
    result = await _client().request("DELETE", path, body=body)
    return _json_response(result)


@mcp.tool()
async def websocket_action(
    action: str,
    parameter: str,
    value_json: str = "",
) -> str:
    value = _parse_json(value_json)
    result = await _client().websocket_action(action, parameter, value=value)
    return _json_response(result)


@mcp.tool()
async def websocket_get(parameter: str) -> str:
    result = await _client().websocket_action("get", parameter)
    return _json_response(result)


@mcp.tool()
async def websocket_set(parameter: str, value_json: str) -> str:
    value = _parse_json(value_json)
    result = await _client().websocket_action("set", parameter, value=value)
    return _json_response(result)


@mcp.tool()
async def websocket_trigger(parameter: str) -> str:
    result = await _client().websocket_action("trigger", parameter)
    return _json_response(result)


@mcp.tool()
async def websocket_reset(parameter: str) -> str:
    result = await _client().websocket_action("reset", parameter)
    return _json_response(result)


@mcp.tool()
async def websocket_subscribe(parameter: str) -> str:
    result = await _client().websocket_action("subscribe", parameter)
    return _json_response(result)


@mcp.tool()
async def websocket_unsubscribe(parameter: str) -> str:
    result = await _client().websocket_action("unsubscribe", parameter)
    return _json_response(result)


@mcp.tool()
async def websocket_post(parameter: str, value_json: str = "") -> str:
    value = _parse_json(value_json)
    result = await _client().websocket_action("post", parameter, value=value)
    return _json_response(result)


@mcp.tool()
async def websocket_remove(parameter: str, value_json: str = "") -> str:
    value = _parse_json(value_json)
    result = await _client().websocket_action("remove", parameter, value=value)
    return _json_response(result)


@mcp.tool()
def osc_send(
    address: str,
    values_json: str = "[]",
    host: str = "",
    port: int = 0,
) -> str:
    values = _parse_json(values_json)
    if values is None:
        values = []
    if not isinstance(values, list):
        raise ValueError("values_json must decode to a JSON array.")
    result = _client().send_osc(address, values, host=host or None, port=port or None)
    return _json_response(result)


@mcp.tool()
async def get_composition() -> str:
    result = await _client().request("GET", "/composition")
    return _json_response(result)


@mcp.tool()
async def get_composition_parameter(parameter_suffix: str) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="get",
        rest_path="/composition",
        parameter_suffix=parameter_suffix,
    )
    return _json_response(result)


@mcp.tool()
async def set_composition_parameter(parameter_suffix: str, value_json: str) -> str:
    value = _parse_json(value_json)
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path="/composition",
        parameter_suffix=parameter_suffix,
        value=value,
    )
    return _json_response(result)


@mcp.tool()
async def subscribe_composition_parameter(parameter_suffix: str) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="subscribe",
        rest_path="/composition",
        parameter_suffix=parameter_suffix,
    )
    return _json_response(result)


@mcp.tool()
async def unsubscribe_composition_parameter(parameter_suffix: str) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="unsubscribe",
        rest_path="/composition",
        parameter_suffix=parameter_suffix,
    )
    return _json_response(result)


@mcp.tool()
async def get_node(path: str, query_json: str = "") -> str:
    params = _parse_json(query_json)
    result = await _client().request("GET", path, params=params)
    return _json_response(result)


@mcp.tool()
async def get_advanced_output_tree(path: str = "/advancedoutput") -> str:
    result = await _client().request("GET", _normalize_output_path(path))
    return _json_response(result)


@mcp.tool()
def get_advanced_output_preferences_summary() -> str:
    prefs = _advanced_output_preferences()
    return _json_response(prefs.summary())


@mcp.tool()
def get_advanced_output_screen_xml(screen_index: int) -> str:
    summary = _advanced_output_preferences().summary()
    screens = summary.get("screens", [])
    if not isinstance(screens, list) or screen_index < 0 or screen_index >= len(screens):
        raise IndexError("screen_index is out of range for the current AdvancedOutput.xml.")
    return _json_response(screens[screen_index])


@mcp.tool()
def get_advanced_output_slice_xml(screen_index: int, slice_index: int) -> str:
    summary = _advanced_output_preferences().summary()
    screens = summary.get("screens", [])
    if not isinstance(screens, list) or screen_index < 0 or screen_index >= len(screens):
        raise IndexError("screen_index is out of range for the current AdvancedOutput.xml.")
    slices = screens[screen_index].get("slices", [])
    if not isinstance(slices, list) or slice_index < 0 or slice_index >= len(slices):
        raise IndexError("slice_index is out of range for the selected screen in AdvancedOutput.xml.")
    return _json_response(slices[slice_index])


@mcp.tool()
def get_slices_inspector_summary() -> str:
    prefs = _slice_inspector_preferences()
    return _json_response(prefs.summary())


@mcp.tool()
def backup_advanced_output_preferences(backup_dir: str = "") -> str:
    config = load_config()
    target_dir = backup_dir.strip() or str(Path(config.documents_root) / "Backups" / "AdvancedOutput")
    advanced_output_backup = backup_xml_file(config.advanced_output_xml_path, target_dir)
    slices_backup = backup_xml_file(config.slices_xml_path, target_dir)
    return _json_response(
        {
            "backup_dir": target_dir,
            "advanced_output_xml": advanced_output_backup,
            "slices_xml": slices_backup,
        }
    )


@mcp.tool()
def diff_advanced_output_preferences(other_xml_path: str) -> str:
    current = _advanced_output_preferences()
    other_path = Path(other_xml_path).expanduser()
    other = AdvancedOutputPreferences.load(other_path)
    diff = diff_xml_text(
        current.raw_xml,
        other.raw_xml,
        current_name=str(current.path),
        other_name=str(other_path),
    )
    return _json_response(
        {
            "current_path": str(current.path),
            "other_path": str(other_path),
            "diff_line_count": len(diff),
            "diff": diff,
        }
    )


@mcp.tool()
async def list_layers() -> str:
    result = await _client().request("GET", "/composition/layers")
    return _json_response(result)


@mcp.tool()
async def list_columns() -> str:
    result = await _client().request("GET", "/composition/columns")
    return _json_response(result)


@mcp.tool()
async def list_groups() -> str:
    result = await _client().request("GET", "/composition")
    if isinstance(result.get("body"), dict):
        result["body"] = result["body"].get("layergroups", [])
    return _json_response(result)


@mcp.tool()
async def list_decks() -> str:
    result = await _client().request("GET", "/composition")
    if isinstance(result.get("body"), dict):
        result["body"] = result["body"].get("decks", [])
    return _json_response(result)


@mcp.tool()
async def list_output_screens() -> str:
    result = await _client().request("GET", "/advancedoutput/screens")
    return _json_response(result)


@mcp.tool()
async def get_output_overview() -> str:
    client = _client()
    screens = await client.request("GET", "/advancedoutput/screens")
    screen_entries = screens.get("body")
    if not isinstance(screen_entries, list):
        return _json_response(
            {
                "screens": screens,
                "screen_snapshots": [],
                "note": "Screen list was not a JSON array; returning raw response only.",
            }
        )

    snapshots: list[dict[str, Any]] = []
    for index, screen_body in enumerate(screen_entries):
        screen = await client.request("GET", f"/advancedoutput/screens/{index}")
        slices = await client.request("GET", f"/advancedoutput/screens/{index}/slices")
        snapshots.append(
            {
                "screen_index": index,
                "screen": screen,
                "slices": slices,
                "source_list_item": screen_body,
            }
        )

    return _json_response({"screens": screens, "screen_snapshots": snapshots})


@mcp.tool()
async def get_output_screen(screen_index: int) -> str:
    result = await _client().request("GET", f"/advancedoutput/screens/{screen_index}")
    return _json_response(result)


@mcp.tool()
async def get_output_screen_snapshot(screen_index: int) -> str:
    client = _client()
    screen = await client.request("GET", f"/advancedoutput/screens/{screen_index}")
    slices = await client.request("GET", f"/advancedoutput/screens/{screen_index}/slices")
    return _json_response(
        {
            "screen_index": screen_index,
            "screen": screen,
            "slices": slices,
        }
    )


@mcp.tool()
async def list_output_slices(screen_index: int) -> str:
    result = await _client().request("GET", f"/advancedoutput/screens/{screen_index}/slices")
    return _json_response(result)


@mcp.tool()
async def get_output_slice(screen_index: int, slice_index: int) -> str:
    result = await _client().request("GET", f"/advancedoutput/screens/{screen_index}/slices/{slice_index}")
    return _json_response(result)


@mcp.tool()
async def get_output_slice_snapshot(screen_index: int, slice_index: int) -> str:
    client = _client()
    slice_payload = await client.request("GET", f"/advancedoutput/screens/{screen_index}/slices/{slice_index}")
    input_payload = await client.websocket_action(
        "get",
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}/input",
    )
    opacity_payload = await client.websocket_action(
        "get",
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}/opacity",
    )
    bypass_payload = await client.websocket_action(
        "get",
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}/bypassed",
    )
    return _json_response(
        {
            "screen_index": screen_index,
            "slice_index": slice_index,
            "slice": slice_payload,
            "input": input_payload,
            "opacity": opacity_payload,
            "bypassed": bypass_payload,
        }
    )


@mcp.tool()
async def audit_output_screen(screen_index: int) -> str:
    client = _client()
    screen = await client.request("GET", f"/advancedoutput/screens/{screen_index}")
    slices = await client.request("GET", f"/advancedoutput/screens/{screen_index}/slices")
    enabled = await _websocket_get_or_error(client, f"/advancedoutput/screens/{screen_index}/enabled")

    findings: list[str] = []
    slice_count: int | None = None
    slice_entries = slices.get("body")
    if isinstance(slice_entries, list):
        slice_count = len(slice_entries)
        if not slice_entries:
            findings.append("Screen has no slices configured.")
        for idx, entry in enumerate(slice_entries):
            if isinstance(entry, dict) and not entry.get("input"):
                findings.append(f"Slice {idx} has no input assignment in REST payload.")
    else:
        findings.append("Could not derive slice count from screen slice payload.")

    enabled_response = enabled.get("response")
    if isinstance(enabled_response, dict) and enabled_response.get("value") is False:
        findings.append("Screen is disabled.")

    return _json_response(
        {
            "screen_index": screen_index,
            "screen": screen,
            "enabled": enabled,
            "slices": slices,
            "summary": {
                "slice_count": slice_count,
                "finding_count": len(findings),
            },
            "findings": findings,
        }
    )


@mcp.tool()
async def audit_all_output_screens() -> str:
    client = _client()
    screens = await client.request("GET", "/advancedoutput/screens")
    screen_entries = screens.get("body")
    audits: list[dict[str, Any]] = []
    if isinstance(screen_entries, list):
        for index, _ in enumerate(screen_entries):
            audit = json.loads(await audit_output_screen(index))
            audits.append(audit)
    return _json_response(
        {
            "screens": screens,
            "audits": audits,
            "summary": {
                "screen_count": len(audits),
                "total_findings": sum(audit["summary"]["finding_count"] for audit in audits),
            },
        }
    )


@mcp.tool()
async def get_layer(layer_index: int) -> str:
    result = await _client().request("GET", f"/composition/layers/{layer_index}")
    return _json_response(result)


@mcp.tool()
async def get_composition_overview() -> str:
    client = _client()
    composition = await client.request("GET", "/composition")
    layers = await client.request("GET", "/composition/layers")
    columns = await client.request("GET", "/composition/columns")
    groups = await client.request("GET", "/composition/layergroups")
    decks = await client.request("GET", "/composition")
    if isinstance(decks.get("body"), dict):
        decks["body"] = decks["body"].get("decks", [])
    return _json_response(
        {
            "composition": composition,
            "layers": layers,
            "columns": columns,
            "groups": groups,
            "decks": decks,
        }
    )


@mcp.tool()
async def get_layer_snapshot(layer_index: int) -> str:
    client = _client()
    layer = await client.request("GET", f"/composition/layers/{layer_index}")
    clips = await client.request("GET", f"/composition/layers/{layer_index}/clips")
    opacity = await _resolved_get_or_error(
        client,
        rest_path=f"/composition/layers/{layer_index}",
        parameter_suffix="video/opacity",
    )
    bypassed = await _resolved_get_or_error(
        client,
        rest_path=f"/composition/layers/{layer_index}",
        parameter_suffix="bypassed",
    )
    return _json_response(
        {
            "layer_index": layer_index,
            "layer": layer,
            "clips": clips,
            "opacity": opacity,
            "bypassed": bypassed,
        }
    )


@mcp.tool()
async def audit_layer(layer_index: int) -> str:
    client = _client()
    layer = await client.request("GET", f"/composition/layers/{layer_index}")
    clips = await client.request("GET", f"/composition/layers/{layer_index}/clips")
    opacity = await _resolved_get_or_error(
        client,
        rest_path=f"/composition/layers/{layer_index}",
        parameter_suffix="video/opacity",
    )
    bypassed = await _resolved_get_or_error(
        client,
        rest_path=f"/composition/layers/{layer_index}",
        parameter_suffix="bypassed",
    )

    findings: list[str] = []
    clip_count: int | None = None
    clip_entries = clips.get("body")
    if isinstance(clip_entries, list):
        clip_count = len(clip_entries)
        if not clip_entries:
            findings.append("Layer contains no clips.")
    else:
        findings.append("Could not derive clip count from layer clip payload.")

    opacity_response = opacity.get("response", {}).get("response")
    if isinstance(opacity_response, dict):
        value = opacity_response.get("value")
        if value == 0:
            findings.append("Layer opacity is zero.")

    bypass_response = bypassed.get("response", {}).get("response")
    if isinstance(bypass_response, dict) and bypass_response.get("value") is True:
        findings.append("Layer is bypassed.")

    return _json_response(
        {
            "layer_index": layer_index,
            "layer": layer,
            "clips": clips,
            "opacity": opacity,
            "bypassed": bypassed,
            "summary": {
                "clip_count": clip_count,
                "finding_count": len(findings),
            },
            "findings": findings,
        }
    )


@mcp.tool()
async def audit_composition() -> str:
    client = _client()
    composition = await client.request("GET", "/composition")
    layers = await client.request("GET", "/composition/layers")
    columns = await client.request("GET", "/composition/columns")
    groups = await client.request("GET", "/composition/layergroups")
    decks = await client.request("GET", "/composition")
    if isinstance(decks.get("body"), dict):
        decks["body"] = decks["body"].get("decks", [])
    bpm = await _resolved_get_or_error(
        client,
        rest_path="/composition",
        parameter_suffix="tempocontroller/tempo",
    )

    findings: list[str] = []
    layer_entries = layers.get("body")
    column_entries = columns.get("body")
    group_entries = groups.get("body")
    deck_entries = decks.get("body")

    if isinstance(layer_entries, list) and not layer_entries:
        findings.append("Composition has no layers.")
    if isinstance(column_entries, list) and not column_entries:
        findings.append("Composition has no columns.")
    if isinstance(group_entries, list) and not group_entries:
        findings.append("Composition has no groups.")
    if isinstance(deck_entries, list) and not deck_entries:
        findings.append("No decks returned by API.")

    bpm_response = bpm.get("response", {}).get("response")
    if isinstance(bpm_response, dict):
        bpm_value = bpm_response.get("value")
        if bpm_value in (None, 0):
            findings.append("Composition tempo is unset or zero.")
    else:
        bpm_value = None

    return _json_response(
        {
            "composition": composition,
            "layers": layers,
            "columns": columns,
            "groups": groups,
            "decks": decks,
            "bpm": bpm,
            "summary": {
                "layer_count": len(layer_entries) if isinstance(layer_entries, list) else None,
                "column_count": len(column_entries) if isinstance(column_entries, list) else None,
                "group_count": len(group_entries) if isinstance(group_entries, list) else None,
                "deck_count": len(deck_entries) if isinstance(deck_entries, list) else None,
                "bpm": bpm_value,
                "finding_count": len(findings),
            },
            "findings": findings,
            "notes": [
                "Composition transport/playing is not currently exposed in the validated REST payload, so composition audit uses tempo and structure as the live-verified readiness baseline."
            ],
        }
    )


@mcp.tool()
async def get_layer_parameter(layer_index: int, parameter_suffix: str) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="get",
        rest_path=f"/composition/layers/{layer_index}",
        parameter_suffix=parameter_suffix,
    )
    return _json_response(result)


@mcp.tool()
async def set_layer_parameter(layer_index: int, parameter_suffix: str, value_json: str) -> str:
    value = _parse_json(value_json)
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path=f"/composition/layers/{layer_index}",
        parameter_suffix=parameter_suffix,
        value=value,
    )
    return _json_response(result)


@mcp.tool()
async def subscribe_layer_parameter(layer_index: int, parameter_suffix: str) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="subscribe",
        rest_path=f"/composition/layers/{layer_index}",
        parameter_suffix=parameter_suffix,
    )
    return _json_response(result)


@mcp.tool()
async def unsubscribe_layer_parameter(layer_index: int, parameter_suffix: str) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="unsubscribe",
        rest_path=f"/composition/layers/{layer_index}",
        parameter_suffix=parameter_suffix,
    )
    return _json_response(result)


@mcp.tool()
async def get_column(column_index: int) -> str:
    result = await _client().request("GET", f"/composition/columns/{column_index}")
    return _json_response(result)


@mcp.tool()
async def get_group(group_index: int) -> str:
    result = await _client().request("GET", f"/composition/layergroups/{group_index}")
    return _json_response(result)


@mcp.tool()
async def get_deck(deck_index: int) -> str:
    result = await _client().request("GET", f"/composition/decks/{deck_index}")
    return _json_response(result)


@mcp.tool()
async def list_clips(layer_index: int) -> str:
    result = await _client().request("GET", f"/composition/layers/{layer_index}/clips")
    return _json_response(result)


@mcp.tool()
async def get_clip(layer_index: int, clip_index: int) -> str:
    result = await _client().request("GET", f"/composition/layers/{layer_index}/clips/{clip_index}")
    return _json_response(result)


@mcp.tool()
async def get_clip_snapshot(layer_index: int, clip_index: int) -> str:
    client = _client()
    rest_path = f"/composition/layers/{layer_index}/clips/{clip_index}"
    clip = await client.request("GET", rest_path)
    connected = await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="connected")
    selected = await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="selected")
    speed = await _resolved_get_or_error(
        client,
        rest_path=rest_path,
        parameter_suffix="transport/speed",
        aliases=("transport/controls/speed",),
    )
    position = await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="transport/position")
    return _json_response(
        {
            "layer_index": layer_index,
            "clip_index": clip_index,
            "clip": clip,
            "connected": connected,
            "selected": selected,
            "speed": speed,
            "position": position,
        }
    )


@mcp.tool()
async def audit_clip(layer_index: int, clip_index: int) -> str:
    client = _client()
    rest_path = f"/composition/layers/{layer_index}/clips/{clip_index}"
    clip = await client.request("GET", rest_path)
    connected = await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="connected")
    selected = await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="selected")
    speed = await _resolved_get_or_error(
        client,
        rest_path=rest_path,
        parameter_suffix="transport/speed",
        aliases=("transport/controls/speed",),
    )
    position = await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="transport/position")
    bypassed = await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="bypassed")

    findings: list[str] = []
    connected_response = connected.get("response", {}).get("response")
    if isinstance(connected_response, dict) and connected_response.get("value") in (False, "Disconnected", "Empty"):
        findings.append("Clip is disconnected.")

    selected_response = selected.get("response", {}).get("response")
    if isinstance(selected_response, dict) and selected_response.get("value") is False:
        findings.append("Clip is not selected.")

    speed_response = speed.get("response", {}).get("response")
    if isinstance(speed_response, dict):
        speed_value = speed_response.get("value")
        if speed_value == 0:
            findings.append("Clip speed is zero.")

    bypassed_response = bypassed.get("response", {}).get("response")
    if isinstance(bypassed_response, dict) and bypassed_response.get("value") is True:
        findings.append("Clip is bypassed.")

    return _json_response(
        {
            "layer_index": layer_index,
            "clip_index": clip_index,
            "clip": clip,
            "connected": connected,
            "selected": selected,
            "speed": speed,
            "position": position,
            "bypassed": bypassed,
            "summary": {"finding_count": len(findings)},
            "findings": findings,
        }
    )


@mcp.tool()
async def trigger_clips(layer_index: int, clip_indices_json: str) -> str:
    clip_indices = _parse_json_list(clip_indices_json, field_name="clip_indices_json")
    results: list[dict[str, Any]] = []
    client = _client()
    for clip_index in clip_indices:
        response = await client.request("POST", f"/composition/layers/{layer_index}/clips/{clip_index}/connect")
        results.append({"layer_index": layer_index, "clip_index": clip_index, "response": response})
    return _json_response({"results": results})


@mcp.tool()
async def disconnect_clips(layer_index: int, clip_indices_json: str) -> str:
    clip_indices = _parse_json_list(clip_indices_json, field_name="clip_indices_json")
    results: list[dict[str, Any]] = []
    client = _client()
    for clip_index in clip_indices:
        response = await client.request("POST", f"/composition/layers/{layer_index}/clips/{clip_index}/connect", body=False)
        results.append({"layer_index": layer_index, "clip_index": clip_index, "response": response})
    return _json_response({"results": results})


@mcp.tool()
async def clear_layers(layer_indices_json: str) -> str:
    layer_indices = _parse_json_list(layer_indices_json, field_name="layer_indices_json")
    results: list[dict[str, Any]] = []
    client = _client()
    for layer_index in layer_indices:
        response = await client.request("POST", f"/composition/layers/{layer_index}/clear")
        results.append({"layer_index": layer_index, "response": response})
    return _json_response({"results": results})


@mcp.tool()
async def prepare_layer(
    layer_index: int,
    *,
    opacity: float | None = None,
    unbypass: bool = True,
) -> str:
    client = _client()
    results: list[dict[str, Any]] = []
    if unbypass:
        bypass_response = await _parameter_action(
            client,
            action="set",
            rest_path=f"/composition/layers/{layer_index}",
            parameter_suffix="bypassed",
            value=False,
        )
        results.append({"action": "set_layer_bypassed", "layer_index": layer_index, "response": bypass_response})
    if opacity is not None:
        opacity_response = await _parameter_action(
            client,
            action="set",
            rest_path=f"/composition/layers/{layer_index}",
            parameter_suffix="video/opacity",
            value=opacity,
        )
        results.append({"action": "set_layer_opacity", "layer_index": layer_index, "response": opacity_response})
    return _json_response({"layer_index": layer_index, "results": results})


@mcp.tool()
async def prepare_multiple_layers(
    layer_indices_json: str,
    *,
    opacity: float | None = None,
    unbypass: bool = True,
) -> str:
    layer_indices = _parse_json_list(layer_indices_json, field_name="layer_indices_json")
    results: list[dict[str, Any]] = []
    for layer_index in layer_indices:
        payload = json.loads(await prepare_layer(layer_index, opacity=opacity, unbypass=unbypass))
        results.append(payload)
    return _json_response({"layer_count": len(results), "layers": results})


@mcp.tool()
async def prepare_playback(
    *,
    playing: bool = True,
    bpm: float | None = None,
    layer_indices_json: str = "",
    layer_opacity: float | None = None,
    unbypass_layers: bool = True,
) -> str:
    client = _client()
    results: list[dict[str, Any]] = []

    try:
        playing_response = await _parameter_action(
            client,
            action="set",
            rest_path="/composition",
            parameter_suffix="transport/playing",
            value=playing,
        )
        results.append({"action": "set_composition_playing", "response": playing_response})
    except ValueError as exc:
        results.append(
            {
                "action": "set_composition_playing",
                "skipped": True,
                "reason": str(exc),
                "note": "Composition transport/playing is not live-verified on this Resolume build.",
            }
        )

    if bpm is not None:
        bpm_response = await _parameter_action(
            client,
            action="set",
            rest_path="/composition",
            parameter_suffix="tempocontroller/tempo",
            value=bpm,
        )
        results.append({"action": "set_composition_bpm", "response": bpm_response})

    if layer_indices_json.strip():
        layer_indices = _parse_json_list(layer_indices_json, field_name="layer_indices_json")
        layer_payload = json.loads(
            await prepare_multiple_layers(
                json.dumps(layer_indices),
                opacity=layer_opacity,
                unbypass=unbypass_layers,
            )
        )
        results.append({"action": "prepare_multiple_layers", "response": layer_payload})

    return _json_response({"results": results})


@mcp.tool()
async def select_clips(layer_index: int, clip_indices_json: str) -> str:
    clip_indices = _parse_json_list(clip_indices_json, field_name="clip_indices_json")
    results: list[dict[str, Any]] = []
    client = _client()
    for clip_index in clip_indices:
        response = await client.websocket_action(
            "set",
            f"/composition/layers/{layer_index}/clips/{clip_index}/selected",
            value=True,
        )
        results.append({"layer_index": layer_index, "clip_index": clip_index, "response": response})
    return _json_response({"results": results})


@mcp.tool()
async def select_layers(layer_indices_json: str) -> str:
    layer_indices = _parse_json_list(layer_indices_json, field_name="layer_indices_json")
    results: list[dict[str, Any]] = []
    client = _client()
    for layer_index in layer_indices:
        response = await client.websocket_action(
            "set",
            f"/composition/layers/{layer_index}/selected",
            value=True,
        )
        results.append({"layer_index": layer_index, "response": response})
    return _json_response({"results": results})


@mcp.tool()
async def select_columns(column_indices_json: str) -> str:
    column_indices = _parse_json_list(column_indices_json, field_name="column_indices_json")
    results: list[dict[str, Any]] = []
    client = _client()
    for column_index in column_indices:
        response = await client.websocket_action(
            "set",
            f"/composition/columns/{column_index}/selected",
            value=True,
        )
        results.append({"column_index": column_index, "response": response})
    return _json_response({"results": results})


@mcp.tool()
async def monitor_playback_state(layer_indices_json: str = "", clip_pairs_json: str = "") -> str:
    client = _client()
    composition = await client.request("GET", "/composition")
    tempo = await _resolved_get_or_error(
        client,
        rest_path="/composition",
        parameter_suffix="tempocontroller/tempo",
    )

    layers: list[dict[str, Any]] = []
    if layer_indices_json.strip():
        layer_indices = _parse_json_list(layer_indices_json, field_name="layer_indices_json")
        for layer_index in layer_indices:
            rest_path = f"/composition/layers/{layer_index}"
            layers.append(
                {
                    "layer_index": layer_index,
                    "opacity": await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="video/opacity"),
                    "bypassed": await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="bypassed"),
                }
            )

    clips: list[dict[str, Any]] = []
    if clip_pairs_json.strip():
        clip_pairs = _parse_json_list(clip_pairs_json, field_name="clip_pairs_json")
        for pair in clip_pairs:
            if not isinstance(pair, dict) or "layer_index" not in pair or "clip_index" not in pair:
                raise ValueError("Each clip pair must include layer_index and clip_index.")
            layer_index = pair["layer_index"]
            clip_index = pair["clip_index"]
            rest_path = f"/composition/layers/{layer_index}/clips/{clip_index}"
            clips.append(
                {
                    "layer_index": layer_index,
                    "clip_index": clip_index,
                    "connected": await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="connected"),
                    "speed": await _resolved_get_or_error(
                        client,
                        rest_path=rest_path,
                        parameter_suffix="transport/speed",
                        aliases=("transport/controls/speed",),
                    ),
                    "position": await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="transport/position"),
                }
            )

    return _json_response(
        {
            "composition": composition,
            "tempo": tempo,
            "layers": layers,
            "clips": clips,
            "notes": [
                "Composition transport/playing is not included in the live-validated REST payload on this build, so playback monitoring uses tempo plus layer and clip state."
            ],
        }
    )


@mcp.tool()
async def subscribe_playback_state(layer_indices_json: str = "", clip_pairs_json: str = "") -> str:
    layer_indices: list[Any] = []
    if layer_indices_json.strip():
        layer_indices = _parse_json_list(layer_indices_json, field_name="layer_indices_json")

    clip_pairs: list[Any] = []
    if clip_pairs_json.strip():
        clip_pairs = _parse_json_list(clip_pairs_json, field_name="clip_pairs_json")
        for pair in clip_pairs:
            if not isinstance(pair, dict) or "layer_index" not in pair or "clip_index" not in pair:
                raise ValueError("Each clip pair must include layer_index and clip_index.")

    client = _client()
    results: list[dict[str, Any]] = []

    results.append(
        await _parameter_action(
            client,
            action="subscribe",
            rest_path="/composition",
            parameter_suffix="tempocontroller/tempo",
        )
    )

    if layer_indices:
        for layer_index in layer_indices:
            rest_path = f"/composition/layers/{layer_index}"
            for suffix in ["video/opacity", "bypassed"]:
                results.append(
                    await _parameter_action(
                        client,
                        action="subscribe",
                        rest_path=rest_path,
                        parameter_suffix=suffix,
                    )
                )

    if clip_pairs:
        for pair in clip_pairs:
            layer_index = pair["layer_index"]
            clip_index = pair["clip_index"]
            rest_path = f"/composition/layers/{layer_index}/clips/{clip_index}"
            parameter_specs = [
                ("connected", ()),
                ("transport/speed", ("transport/controls/speed",)),
                ("transport/position", ()),
            ]
            for suffix, aliases in parameter_specs:
                results.append(
                    await _parameter_action(
                        client,
                        action="subscribe",
                        rest_path=rest_path,
                        parameter_suffix=suffix,
                        aliases=aliases,
                    )
                )

    return _json_response({"results": results})


@mcp.tool()
async def unsubscribe_playback_state(layer_indices_json: str = "", clip_pairs_json: str = "") -> str:
    layer_indices: list[Any] = []
    if layer_indices_json.strip():
        layer_indices = _parse_json_list(layer_indices_json, field_name="layer_indices_json")

    clip_pairs: list[Any] = []
    if clip_pairs_json.strip():
        clip_pairs = _parse_json_list(clip_pairs_json, field_name="clip_pairs_json")
        for pair in clip_pairs:
            if not isinstance(pair, dict) or "layer_index" not in pair or "clip_index" not in pair:
                raise ValueError("Each clip pair must include layer_index and clip_index.")

    client = _client()
    results: list[dict[str, Any]] = []

    results.append(
        await _parameter_action(
            client,
            action="unsubscribe",
            rest_path="/composition",
            parameter_suffix="tempocontroller/tempo",
        )
    )

    if layer_indices:
        for layer_index in layer_indices:
            rest_path = f"/composition/layers/{layer_index}"
            for suffix in ["video/opacity", "bypassed"]:
                results.append(
                    await _parameter_action(
                        client,
                        action="unsubscribe",
                        rest_path=rest_path,
                        parameter_suffix=suffix,
                    )
                )

    if clip_pairs:
        for pair in clip_pairs:
            layer_index = pair["layer_index"]
            clip_index = pair["clip_index"]
            rest_path = f"/composition/layers/{layer_index}/clips/{clip_index}"
            parameter_specs = [
                ("connected", ()),
                ("transport/speed", ("transport/controls/speed",)),
                ("transport/position", ()),
            ]
            for suffix, aliases in parameter_specs:
                results.append(
                    await _parameter_action(
                        client,
                        action="unsubscribe",
                        rest_path=rest_path,
                        parameter_suffix=suffix,
                        aliases=aliases,
                    )
                )

    return _json_response({"results": results})


@mcp.tool()
async def get_deck_snapshot(deck_index: int) -> str:
    client = _client()
    rest_path = f"/composition/decks/{deck_index}"
    deck = await client.request("GET", rest_path)
    selected = await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="selected")
    scrollx = await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="scrollx")
    deck_body = _extract_body(deck)
    return _json_response(
        {
            "deck_index": deck_index,
            "deck": deck,
            "selected": selected,
            "scrollx": scrollx,
            "closed": deck_body.get("closed") if isinstance(deck_body, dict) else None,
            "notes": [
                "The validated deck REST schema exposes selected and scrollx, but not deck transport fields."
            ],
        }
    )


@mcp.tool()
async def audit_deck(deck_index: int) -> str:
    payload = json.loads(await get_deck_snapshot(deck_index))
    findings: list[str] = []
    if payload.get("closed") is True:
        findings.append("Deck is closed.")

    selected_response = payload["selected"].get("response", {}).get("response")
    if isinstance(selected_response, dict) and selected_response.get("value") is False:
        findings.append("Deck is not selected.")

    payload["summary"] = {"finding_count": len(findings)}
    payload["findings"] = findings
    return _json_response(payload)


@mcp.tool()
async def monitor_decks(deck_indices_json: str) -> str:
    deck_indices = _parse_json_list(deck_indices_json, field_name="deck_indices_json")
    decks: list[dict[str, Any]] = []
    client = _client()
    for deck_index in deck_indices:
        rest_path = f"/composition/decks/{deck_index}"
        deck = await client.request("GET", rest_path)
        decks.append(
            {
                "deck_index": deck_index,
                "deck": deck,
                "selected": await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="selected"),
                "scrollx": await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="scrollx"),
            }
        )
    return _json_response({"decks": decks})


@mcp.tool()
async def subscribe_decks(deck_indices_json: str) -> str:
    deck_indices = _parse_json_list(deck_indices_json, field_name="deck_indices_json")
    results: list[dict[str, Any]] = []
    client = _client()
    for deck_index in deck_indices:
        rest_path = f"/composition/decks/{deck_index}"
        for suffix in ["selected", "scrollx"]:
            results.append(
                await _parameter_action(
                    client,
                    action="subscribe",
                    rest_path=rest_path,
                    parameter_suffix=suffix,
                )
            )
    return _json_response({"results": results})


@mcp.tool()
async def unsubscribe_decks(deck_indices_json: str) -> str:
    deck_indices = _parse_json_list(deck_indices_json, field_name="deck_indices_json")
    results: list[dict[str, Any]] = []
    client = _client()
    for deck_index in deck_indices:
        rest_path = f"/composition/decks/{deck_index}"
        for suffix in ["selected", "scrollx"]:
            results.append(
                await _parameter_action(
                    client,
                    action="unsubscribe",
                    rest_path=rest_path,
                    parameter_suffix=suffix,
                )
            )
    return _json_response({"results": results})


@mcp.tool()
async def prepare_deck(deck_index: int, *, playing: bool = True, speed: float | None = None) -> str:
    results: list[dict[str, Any]] = [
        {
            "action": "set_deck_playing",
            "deck_index": deck_index,
            "skipped": True,
            "requested_value": playing,
            "reason": "Deck transport/playing is not present in the validated REST schema.",
        }
    ]
    if speed is not None:
        results.append(
            {
                "action": "set_deck_speed",
                "deck_index": deck_index,
                "skipped": True,
                "requested_value": speed,
                "reason": "Deck transport/speed is not present in the validated REST schema.",
            }
        )
    return _json_response({"deck_index": deck_index, "results": results})


@mcp.tool()
async def prepare_multiple_decks(
    deck_indices_json: str,
    *,
    playing: bool = True,
    speed: float | None = None,
) -> str:
    deck_indices = _parse_json_list(deck_indices_json, field_name="deck_indices_json")
    results: list[dict[str, Any]] = []
    for deck_index in deck_indices:
        payload = json.loads(await prepare_deck(deck_index, playing=playing, speed=speed))
        results.append(payload)
    return _json_response({"deck_count": len(results), "decks": results})


@mcp.tool()
async def prepare_output_screen(
    screen_index: int,
    *,
    enabled: bool = True,
    slice_opacity: float | None = None,
    unbypass_slices: bool = True,
) -> str:
    client = _client()
    results: list[dict[str, Any]] = []

    enabled_result = await client.websocket_action(
        "set",
        f"/advancedoutput/screens/{screen_index}/enabled",
        value=enabled,
    )
    results.append(
        {
            "action": "set_screen_enabled",
            "screen_index": screen_index,
            "response": enabled_result,
        }
    )

    slices = await client.request("GET", f"/advancedoutput/screens/{screen_index}/slices")
    results.append({"action": "get_slices", "screen_index": screen_index, "response": slices})

    slice_entries = slices.get("body")
    if isinstance(slice_entries, list):
        for slice_index, _ in enumerate(slice_entries):
            if unbypass_slices:
                response = await client.websocket_action(
                    "set",
                    f"/advancedoutput/screens/{screen_index}/slices/{slice_index}/bypassed",
                    value=False,
                )
                results.append(
                    {
                        "action": "set_slice_bypassed",
                        "screen_index": screen_index,
                        "slice_index": slice_index,
                        "response": response,
                    }
                )
            if slice_opacity is not None:
                response = await client.websocket_action(
                    "set",
                    f"/advancedoutput/screens/{screen_index}/slices/{slice_index}/opacity",
                    value=slice_opacity,
                )
                results.append(
                    {
                        "action": "set_slice_opacity",
                        "screen_index": screen_index,
                        "slice_index": slice_index,
                        "response": response,
                    }
                )

    return _json_response(
        {
            "screen_index": screen_index,
            "prepared_slice_count": len(slice_entries) if isinstance(slice_entries, list) else None,
            "results": results,
        }
    )


@mcp.tool()
async def prepare_multiple_output_screens(
    screen_indices_json: str,
    *,
    enabled: bool = True,
    slice_opacity: float | None = None,
    unbypass_slices: bool = True,
) -> str:
    screen_indices = _parse_json_list(screen_indices_json, field_name="screen_indices_json")
    results: list[dict[str, Any]] = []
    for screen_index in screen_indices:
        payload = json.loads(
            await prepare_output_screen(
                screen_index,
                enabled=enabled,
                slice_opacity=slice_opacity,
                unbypass_slices=unbypass_slices,
            )
        )
        results.append(payload)
    return _json_response(
        {
            "screen_count": len(results),
            "screens": results,
        }
    )


@mcp.tool()
async def audit_show_readiness() -> str:
    composition = json.loads(await audit_composition())
    output = json.loads(await audit_all_output_screens())
    return _json_response(
        {
            "composition": composition,
            "output": output,
            "summary": {
                "composition_findings": composition["summary"]["finding_count"],
                "output_findings": output["summary"]["total_findings"],
                "total_findings": composition["summary"]["finding_count"] + output["summary"]["total_findings"],
            },
        }
    )


@mcp.tool()
async def get_clip_parameter(layer_index: int, clip_index: int, parameter_suffix: str) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="get",
        rest_path=f"/composition/layers/{layer_index}/clips/{clip_index}",
        parameter_suffix=parameter_suffix,
        aliases=("transport/controls/speed",) if parameter_suffix.strip() == "transport/speed" else (),
    )
    return _json_response(result)


@mcp.tool()
async def set_clip_parameter(layer_index: int, clip_index: int, parameter_suffix: str, value_json: str) -> str:
    value = _parse_json(value_json)
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path=f"/composition/layers/{layer_index}/clips/{clip_index}",
        parameter_suffix=parameter_suffix,
        value=value,
        aliases=("transport/controls/speed",) if parameter_suffix.strip() == "transport/speed" else (),
    )
    return _json_response(result)


@mcp.tool()
async def subscribe_clip_parameter(layer_index: int, clip_index: int, parameter_suffix: str) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="subscribe",
        rest_path=f"/composition/layers/{layer_index}/clips/{clip_index}",
        parameter_suffix=parameter_suffix,
        aliases=("transport/controls/speed",) if parameter_suffix.strip() == "transport/speed" else (),
    )
    return _json_response(result)


@mcp.tool()
async def unsubscribe_clip_parameter(layer_index: int, clip_index: int, parameter_suffix: str) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="unsubscribe",
        rest_path=f"/composition/layers/{layer_index}/clips/{clip_index}",
        parameter_suffix=parameter_suffix,
        aliases=("transport/controls/speed",) if parameter_suffix.strip() == "transport/speed" else (),
    )
    return _json_response(result)


@mcp.tool()
async def trigger_clip(layer_index: int, clip_index: int) -> str:
    result = await _client().request("POST", f"/composition/layers/{layer_index}/clips/{clip_index}/connect")
    return _json_response(result)


@mcp.tool()
async def disconnect_clip(layer_index: int, clip_index: int) -> str:
    result = await _client().request("POST", f"/composition/layers/{layer_index}/clips/{clip_index}/connect", body=False)
    return _json_response(result)


@mcp.tool()
async def trigger_column(column_index: int) -> str:
    result = await _client().request("POST", f"/composition/columns/{column_index}/connect")
    return _json_response(result)


@mcp.tool()
async def disconnect_column(column_index: int) -> str:
    result = await _client().request("POST", f"/composition/columns/{column_index}/connect", body=False)
    return _json_response(result)


@mcp.tool()
async def select_clip(layer_index: int, clip_index: int) -> str:
    result = await _client().websocket_action(
        "set",
        f"/composition/layers/{layer_index}/clips/{clip_index}/selected",
        value=True,
    )
    return _json_response(result)


@mcp.tool()
async def clear_layer(layer_index: int) -> str:
    result = await _client().request("POST", f"/composition/layers/{layer_index}/clear")
    return _json_response(result)


@mcp.tool()
async def clear_composition() -> str:
    result = await _client().request("POST", "/composition/clear")
    return _json_response(result)


@mcp.tool()
async def select_layer(layer_index: int) -> str:
    result = await _client().websocket_action(
        "set",
        f"/composition/layers/{layer_index}/selected",
        value=True,
    )
    return _json_response(result)


@mcp.tool()
async def select_column(column_index: int) -> str:
    result = await _client().websocket_action(
        "set",
        f"/composition/columns/{column_index}/selected",
        value=True,
    )
    return _json_response(result)


@mcp.tool()
async def select_group(group_index: int) -> str:
    result = await _client().request("POST", f"/composition/layergroups/{group_index}/select")
    return _json_response(result)


@mcp.tool()
async def set_output_parameter(path: str, value_json: str) -> str:
    value = _parse_json(value_json)
    result = await _client().websocket_action("set", _normalize_output_path(path), value=value)
    return _json_response(result)


@mcp.tool()
async def get_output_parameter(path: str) -> str:
    result = await _client().websocket_action("get", _normalize_output_path(path))
    return _json_response(result)


@mcp.tool()
async def trigger_output_action(path: str) -> str:
    result = await _client().websocket_action("trigger", _normalize_output_path(path))
    return _json_response(result)


@mcp.tool()
async def reset_output_parameter(path: str) -> str:
    result = await _client().websocket_action("reset", _normalize_output_path(path))
    return _json_response(result)


@mcp.tool()
async def subscribe_output_parameter(path: str) -> str:
    result = await _client().websocket_action("subscribe", _normalize_output_path(path))
    return _json_response(result)


@mcp.tool()
async def unsubscribe_output_parameter(path: str) -> str:
    result = await _client().websocket_action("unsubscribe", _normalize_output_path(path))
    return _json_response(result)


@mcp.tool()
async def subscribe_output_screen_parameter(screen_index: int, parameter_suffix: str) -> str:
    path = _join_parameter_path(f"/advancedoutput/screens/{screen_index}", parameter_suffix)
    result = await _client().websocket_action("subscribe", path)
    return _json_response(result)


@mcp.tool()
async def unsubscribe_output_screen_parameter(screen_index: int, parameter_suffix: str) -> str:
    path = _join_parameter_path(f"/advancedoutput/screens/{screen_index}", parameter_suffix)
    result = await _client().websocket_action("unsubscribe", path)
    return _json_response(result)


@mcp.tool()
async def subscribe_output_slice_parameter(screen_index: int, slice_index: int, parameter_suffix: str) -> str:
    path = _join_parameter_path(
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}",
        parameter_suffix,
    )
    result = await _client().websocket_action("subscribe", path)
    return _json_response(result)


@mcp.tool()
async def unsubscribe_output_slice_parameter(screen_index: int, slice_index: int, parameter_suffix: str) -> str:
    path = _join_parameter_path(
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}",
        parameter_suffix,
    )
    result = await _client().websocket_action("unsubscribe", path)
    return _json_response(result)


@mcp.tool()
async def set_layer_opacity(layer_index: int, opacity: float) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path=f"/composition/layers/{layer_index}",
        parameter_suffix="video/opacity",
        value=opacity,
    )
    return _json_response(result)


@mcp.tool()
async def set_param(parameter: str, value_json: str) -> str:
    value = _parse_json(value_json)
    result = await _client().websocket_action("set", parameter, value=value)
    return _json_response(result)


@mcp.tool()
async def trigger_param(parameter: str) -> str:
    result = await _client().websocket_action("trigger", parameter)
    return _json_response(result)


@mcp.tool()
async def reset_param(parameter: str) -> str:
    result = await _client().websocket_action("reset", parameter)
    return _json_response(result)


@mcp.tool()
async def bypass_layer(layer_index: int, bypassed: bool = True) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path=f"/composition/layers/{layer_index}",
        parameter_suffix="bypassed",
        value=bypassed,
    )
    return _json_response(result)


@mcp.tool()
async def set_clip_transport_position(layer_index: int, clip_index: int, position: float) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path=f"/composition/layers/{layer_index}/clips/{clip_index}",
        parameter_suffix="transport/position",
        value=position,
    )
    return _json_response(result)


@mcp.tool()
async def set_clip_speed(layer_index: int, clip_index: int, speed: float) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path=f"/composition/layers/{layer_index}/clips/{clip_index}",
        parameter_suffix="transport/speed",
        aliases=("transport/controls/speed",),
        value=speed,
    )
    return _json_response(result)


@mcp.tool()
async def set_output_screen_enabled(screen_index: int, enabled: bool = True) -> str:
    result = await _client().websocket_action(
        "set",
        f"/advancedoutput/screens/{screen_index}/enabled",
        value=enabled,
    )
    return _json_response(result)


@mcp.tool()
async def set_output_slice_bypassed(screen_index: int, slice_index: int, bypassed: bool = True) -> str:
    result = await _client().websocket_action(
        "set",
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}/bypassed",
        value=bypassed,
    )
    return _json_response(result)


@mcp.tool()
async def set_output_slice_input(screen_index: int, slice_index: int, input_path: str) -> str:
    result = await _client().websocket_action(
        "set",
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}/input",
        value=input_path,
    )
    return _json_response(result)


@mcp.tool()
async def set_output_slice_opacity(screen_index: int, slice_index: int, opacity: float) -> str:
    result = await _client().websocket_action(
        "set",
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}/opacity",
        value=opacity,
    )
    return _json_response(result)


@mcp.tool()
async def set_composition_bpm(bpm: float) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path="/composition",
        parameter_suffix="tempocontroller/tempo",
        value=bpm,
    )
    return _json_response(result)


@mcp.tool()
async def set_composition_playing(playing: bool = True) -> str:
    client = _client()
    try:
        result = await _parameter_action(
            client,
            action="set",
            rest_path="/composition",
            parameter_suffix="transport/playing",
            value=playing,
        )
    except ValueError as exc:
        result = {
            "action": "set_composition_playing",
            "skipped": True,
            "requested_value": playing,
            "reason": str(exc),
            "note": "Composition transport/playing is not live-verified on this Resolume build.",
        }
    return _json_response(result)


@mcp.tool()
async def bypass_clip(layer_index: int, clip_index: int, bypassed: bool = True) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path=f"/composition/layers/{layer_index}/clips/{clip_index}",
        parameter_suffix="bypassed",
        value=bypassed,
    )
    return _json_response(result)


@mcp.tool()
async def set_deck_parameter(deck_index: int, parameter_suffix: str, value_json: str) -> str:
    value = _parse_json(value_json)
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path=f"/composition/decks/{deck_index}",
        parameter_suffix=parameter_suffix,
        value=value,
    )
    return _json_response(result)


@mcp.tool()
async def get_deck_parameter(deck_index: int, parameter_suffix: str) -> str:
    client = _client()
    result = await _parameter_action(
        client,
        action="get",
        rest_path=f"/composition/decks/{deck_index}",
        parameter_suffix=parameter_suffix,
    )
    return _json_response(result)


@mcp.tool()
async def trigger_deck_action(deck_index: int, parameter_suffix: str) -> str:
    path = _join_parameter_path(f"/composition/decks/{deck_index}", parameter_suffix)
    result = await _client().websocket_action("trigger", path)
    return _json_response(result)


@mcp.tool()
async def reset_deck_parameter(deck_index: int, parameter_suffix: str) -> str:
    path = _join_parameter_path(f"/composition/decks/{deck_index}", parameter_suffix)
    result = await _client().websocket_action("reset", path)
    return _json_response(result)


@mcp.tool()
async def set_output_screen_parameter(screen_index: int, parameter_suffix: str, value_json: str) -> str:
    value = _parse_json(value_json)
    path = _join_parameter_path(f"/advancedoutput/screens/{screen_index}", parameter_suffix)
    result = await _client().websocket_action("set", path, value=value)
    return _json_response(result)


@mcp.tool()
async def get_output_screen_parameter(screen_index: int, parameter_suffix: str) -> str:
    path = _join_parameter_path(f"/advancedoutput/screens/{screen_index}", parameter_suffix)
    result = await _client().websocket_action("get", path)
    return _json_response(result)


@mcp.tool()
async def trigger_output_screen_action(screen_index: int, parameter_suffix: str) -> str:
    path = _join_parameter_path(f"/advancedoutput/screens/{screen_index}", parameter_suffix)
    result = await _client().websocket_action("trigger", path)
    return _json_response(result)


@mcp.tool()
async def set_output_slice_parameter(
    screen_index: int,
    slice_index: int,
    parameter_suffix: str,
    value_json: str,
) -> str:
    value = _parse_json(value_json)
    path = _join_parameter_path(
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}",
        parameter_suffix,
    )
    result = await _client().websocket_action("set", path, value=value)
    return _json_response(result)


@mcp.tool()
async def get_output_slice_parameter(screen_index: int, slice_index: int, parameter_suffix: str) -> str:
    path = _join_parameter_path(
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}",
        parameter_suffix,
    )
    result = await _client().websocket_action("get", path)
    return _json_response(result)


@mcp.tool()
async def trigger_output_slice_action(screen_index: int, slice_index: int, parameter_suffix: str) -> str:
    path = _join_parameter_path(
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}",
        parameter_suffix,
    )
    result = await _client().websocket_action("trigger", path)
    return _json_response(result)


@mcp.tool()
async def reset_output_slice_parameter(screen_index: int, slice_index: int, parameter_suffix: str) -> str:
    path = _join_parameter_path(
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}",
        parameter_suffix,
    )
    result = await _client().websocket_action("reset", path)
    return _json_response(result)


@mcp.tool()
async def set_output_slice_corners(
    screen_index: int,
    slice_index: int,
    *,
    top_left_x: float | None = None,
    top_left_y: float | None = None,
    top_right_x: float | None = None,
    top_right_y: float | None = None,
    bottom_left_x: float | None = None,
    bottom_left_y: float | None = None,
    bottom_right_x: float | None = None,
    bottom_right_y: float | None = None,
) -> str:
    updates: list[dict[str, Any]] = []
    base = f"/advancedoutput/screens/{screen_index}/slices/{slice_index}"
    requested = {
        "corners/top_left/x": top_left_x,
        "corners/top_left/y": top_left_y,
        "corners/top_right/x": top_right_x,
        "corners/top_right/y": top_right_y,
        "corners/bottom_left/x": bottom_left_x,
        "corners/bottom_left/y": bottom_left_y,
        "corners/bottom_right/x": bottom_right_x,
        "corners/bottom_right/y": bottom_right_y,
    }
    for suffix, value in requested.items():
        if value is None:
            continue
        parameter = _join_parameter_path(base, suffix)
        response = await _client().websocket_action("set", parameter, value=value)
        updates.append({"parameter": parameter, "value": value, "response": response})
    if not updates:
        raise ValueError("At least one corner value is required.")
    return _json_response({"updates": updates})


@mcp.tool()
async def set_output_screen_transform(
    screen_index: int,
    *,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    rotation: float | None = None,
) -> str:
    updates: list[dict[str, Any]] = []
    base = f"/advancedoutput/screens/{screen_index}"
    requested = {
        "transform/position/x": x,
        "transform/position/y": y,
        "transform/size/width": width,
        "transform/size/height": height,
        "transform/rotation": rotation,
    }
    for suffix, value in requested.items():
        if value is None:
            continue
        parameter = _join_parameter_path(base, suffix)
        response = await _client().websocket_action("set", parameter, value=value)
        updates.append({"parameter": parameter, "value": value, "response": response})
    if not updates:
        raise ValueError("At least one transform value is required.")
    return _json_response({"updates": updates})


@mcp.tool()
async def set_output_slice_transform(
    screen_index: int,
    slice_index: int,
    *,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    rotation: float | None = None,
) -> str:
    updates: list[dict[str, Any]] = []
    base = f"/advancedoutput/screens/{screen_index}/slices/{slice_index}"
    requested = {
        "transform/position/x": x,
        "transform/position/y": y,
        "transform/size/width": width,
        "transform/size/height": height,
        "transform/rotation": rotation,
    }
    for suffix, value in requested.items():
        if value is None:
            continue
        parameter = _join_parameter_path(base, suffix)
        response = await _client().websocket_action("set", parameter, value=value)
        updates.append({"parameter": parameter, "value": value, "response": response})
    if not updates:
        raise ValueError("At least one transform value is required.")
    return _json_response({"updates": updates})


@mcp.tool()
async def batch_set_output_screen_parameter(
    screen_indices_json: str,
    parameter_suffix: str,
    value_json: str,
) -> str:
    screen_indices = _parse_json_list(screen_indices_json, field_name="screen_indices_json")
    value = _parse_json(value_json)
    updates: list[dict[str, Any]] = []
    for screen_index in screen_indices:
        path = _join_parameter_path(f"/advancedoutput/screens/{screen_index}", parameter_suffix)
        response = await _client().websocket_action("set", path, value=value)
        updates.append({"screen_index": screen_index, "parameter": path, "value": value, "response": response})
    return _json_response({"updates": updates})


@mcp.tool()
async def batch_set_output_slice_parameter(
    screen_index: int,
    slice_indices_json: str,
    parameter_suffix: str,
    value_json: str,
) -> str:
    slice_indices = _parse_json_list(slice_indices_json, field_name="slice_indices_json")
    value = _parse_json(value_json)
    updates: list[dict[str, Any]] = []
    for slice_index in slice_indices:
        path = _join_parameter_path(
            f"/advancedoutput/screens/{screen_index}/slices/{slice_index}",
            parameter_suffix,
        )
        response = await _client().websocket_action("set", path, value=value)
        updates.append({"slice_index": slice_index, "parameter": path, "value": value, "response": response})
    return _json_response({"updates": updates})


@mcp.tool()
async def batch_set_output_slice_opacity(
    screen_index: int,
    slice_indices_json: str,
    opacity: float,
) -> str:
    return await batch_set_output_slice_parameter(
        screen_index,
        slice_indices_json,
        "opacity",
        json.dumps(opacity),
    )


@mcp.tool()
async def batch_set_output_slice_bypassed(
    screen_index: int,
    slice_indices_json: str,
    bypassed: bool = True,
) -> str:
    return await batch_set_output_slice_parameter(
        screen_index,
        slice_indices_json,
        "bypassed",
        json.dumps(bypassed),
    )


@mcp.tool()
async def route_output_slices(screen_index: int, routes_json: str) -> str:
    routes = _parse_json_list(routes_json, field_name="routes_json")
    updates: list[dict[str, Any]] = []
    for route in routes:
        if not isinstance(route, dict):
            raise ValueError("Each route must be an object with slice_index and input_path.")
        if "slice_index" not in route or "input_path" not in route:
            raise ValueError("Each route must include slice_index and input_path.")
        slice_index = route["slice_index"]
        input_path = route["input_path"]
        path = f"/advancedoutput/screens/{screen_index}/slices/{slice_index}/input"
        response = await _client().websocket_action("set", path, value=input_path)
        updates.append(
            {
                "slice_index": slice_index,
                "parameter": path,
                "value": input_path,
                "response": response,
            }
        )
    return _json_response({"updates": updates})


@mcp.resource("resolume://docs/api-primitives")
def api_primitives() -> str:
    return _json_response(
        {
            "rest_tools": ["rest_request", "rest_get", "rest_post", "rest_put", "rest_delete", "get_node"],
            "websocket_tools": [
                "websocket_action",
                "websocket_get",
                "websocket_set",
                "websocket_trigger",
                "websocket_reset",
                "websocket_subscribe",
                "websocket_unsubscribe",
                "websocket_post",
                "websocket_remove",
            ],
            "osc_tools": ["osc_send"],
            "notes": [
                "Use REST for composition-tree inspection and many structural operations.",
                "Use WebSocket verbs for parameter get/set/trigger/reset/subscribe actions.",
                "Use OSC when you need direct address-based control compatible with Resolume's OSC listener.",
                "Use the output screen/slice parameter helpers when operating Advanced Output without hand-building long paths, but treat them as experimental until your target Resolume build exposes Advanced Output over HTTP.",
                "Use the Advanced Output XML tools for read-only inspection, backup, and diff on systems where Advanced Output is persisted to XML but not exposed over the live HTTP API.",
                "Use composition/layer/clip parameter helpers for live monitoring and operator-driven parameter workflows.",
            ],
        }
    )


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
