from __future__ import annotations

import asyncio
import json
import math
import posixpath
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse, urlsplit

from mcp.server.fastmcp import FastMCP
from mcp.types import ToolAnnotations

from .advanced_output_xml import (
    AdvancedOutputPreferences,
    SliceInspectorPreferences,
    backup_xml_file,
    diff_xml_text,
    export_advanced_output_bundle,
    preview_restore_advanced_output_bundle,
    rename_screen_in_advanced_output,
    rename_slice_in_advanced_output,
    restore_advanced_output_bundle,
    set_advanced_output_soft_edge_power,
    set_advanced_output_screen_output_device,
    set_advanced_output_slice_vertices,
    windows_advanced_output_path_candidates,
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


def _confirmation_required(action: str, message: str) -> str:
    return _json_response({"action": action, "requires_confirmation": True, "message": message})


_DESTRUCTIVE_ENDPOINTS = frozenset({"clear", "clearclips", "disconnect-all", "disconnectall"})
_READ_VERBS = frozenset({"get", "subscribe", "unsubscribe"})


def _destructive_reason(verb: str, path: str, value: Any = None) -> str | None:
    """Best-effort classification of a generic REST/WebSocket/OSC call as destructive."""
    verb = (verb or "").strip().lower()
    if verb in _READ_VERBS:
        return None
    if verb in {"delete", "remove"}:
        return f"{verb.upper()} removes Resolume content."
    # httpx drops ?query/#fragment and resolves dot segments before sending, so classify the same path.
    normalized = posixpath.normpath("/" + urlsplit((path or "").strip().lower()).path)
    segments = [segment for segment in normalized.split("/") if segment]
    if len(segments) >= 2 and segments[0] == "api":
        segments = segments[2:]
    if not segments:
        return None
    last = segments[-1]
    if last in _DESTRUCTIVE_ENDPOINTS:
        return f"'{last}' clears or disconnects live content."
    if segments in (["composition", "new"], ["composition", "open"]):
        return "This replaces the entire composition."
    if last == "close" and segments[:2] == ["composition", "decks"]:
        return "This closes a deck."
    if last == "connect" and value is False:
        return "connect with false disconnects live content."
    return None


def _generic_gate(tool: str, verb: str, path: str, value: Any, confirm_destructive: bool) -> str | None:
    if confirm_destructive:
        return None
    reason = _destructive_reason(verb, path, value)
    if reason is None:
        return None
    return _confirmation_required(tool, f"{reason} Re-call with confirm_destructive=True to proceed.")


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


def _optional_json_object(value: str, *, field_name: str) -> Any:
    parsed = _parse_json(value)
    if parsed is None:
        return None
    if not isinstance(parsed, dict):
        raise ValueError(f"{field_name} must decode to a JSON object.")
    return parsed


def _normalize_media_uri(value: str) -> str:
    candidate = (value or "").strip()
    if not candidate:
        raise ValueError("media path/value is required.")
    if len(candidate) >= 3 and candidate[1] == ":" and candidate[0].isalpha() and candidate[2] in {"\\", "/"}:
        drive = candidate[0].upper()
        remainder = candidate[2:].replace("\\", "/")
        return f"file:///{drive}:{quote(remainder)}"
    parsed = urlparse(candidate)
    if parsed.scheme:
        return _encode_resolume_uri(candidate)
    return Path(candidate).expanduser().resolve().as_uri()


_RESOLUME_URI_PREFIXES = ("source:///", "effect:///")


def _encode_resolume_uri(uri: str) -> str:
    """Percent-encode the path segments of a source:/// or effect:/// URI.

    Arena only accepts the encoded display name (e.g. 'DeckLink%208K%20Pro%20%281%29'); raw spaces
    or parentheses fail with 400. Already-encoded segments are left as they are.
    """
    for prefix in _RESOLUME_URI_PREFIXES:
        if uri.lower().startswith(prefix):
            segments = uri[len(prefix):].split("/")
            return prefix + "/".join(quote(unquote(segment), safe="") for segment in segments)
    return uri


def _normalize_media_scalar_or_field(value: Any) -> str:
    if isinstance(value, str):
        return _normalize_media_uri(value)
    if isinstance(value, dict):
        for key in ("path", "file", "filename", "location", "url"):
            field = value.get(key)
            if isinstance(field, str) and field.strip():
                return _normalize_media_uri(field)
    raise ValueError("Expected a media path string or an object containing one of: path, file, filename, location, url.")


def _normalize_media_insert_body(value: Any) -> list[str]:
    if isinstance(value, list):
        if not value:
            raise ValueError("Media insert body array cannot be empty.")
        return [_normalize_media_scalar_or_field(item) for item in value]
    return [_normalize_media_scalar_or_field(value)]


def _parameter_path_from_id(parameter_id: int) -> str:
    return f"/parameter/by-id/{parameter_id}"


def _effect_kind_path(effect_kind: str) -> str:
    normalized = (effect_kind or "").strip().lower()
    if normalized not in {"audio", "video"}:
        raise ValueError("effect_kind must be 'audio' or 'video'.")
    return normalized


def _effect_scope_path(scope: str, index: int | None = None, *, layer_index: int | None = None, clip_index: int | None = None) -> str:
    normalized = (scope or "").strip().lower()
    if normalized == "composition":
        return "/composition"
    if normalized == "layer":
        if layer_index is None:
            raise ValueError("layer_index is required for layer effect scope.")
        return f"/composition/layers/{layer_index}"
    if normalized == "group":
        if index is None:
            raise ValueError("group_index is required for group effect scope.")
        return f"/composition/layergroups/{index}"
    if normalized == "selected-layer":
        return "/composition/layers/selected"
    if normalized == "selected-group":
        return "/composition/layergroups/selected"
    if normalized == "clip":
        if layer_index is None or clip_index is None:
            raise ValueError("layer_index and clip_index are required for clip effect scope.")
        return f"/composition/layers/{layer_index}/clips/{clip_index}"
    if normalized == "selected-clip":
        return "/composition/clips/selected"
    raise ValueError("scope must be one of: composition, layer, selected-layer, group, selected-group, clip, selected-clip.")


def _extract_effect_from_scope_payload(payload: Any, effect_kind: str, effect_index: int) -> dict[str, Any]:
    body = _extract_body(payload)
    if not isinstance(body, dict):
        raise ValueError("REST payload body must be a JSON object to resolve an effect.")

    kind_node = body.get(effect_kind)
    if not isinstance(kind_node, dict):
        raise ValueError(f"Scope payload does not expose a '{effect_kind}' node.")

    effects = kind_node.get("effects")
    if not isinstance(effects, list):
        raise ValueError(f"Scope payload does not expose an '{effect_kind}.effects' list.")

    if effect_index < 1 or effect_index > len(effects):
        raise IndexError(f"effect_index {effect_index} is out of range for the current {effect_kind} effects list.")

    effect = effects[effect_index - 1]
    if not isinstance(effect, dict):
        raise ValueError("Resolved effect entry was not a JSON object.")
    return effect


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
    rest_payload: Any = None,
) -> dict[str, Any]:
    if rest_payload is None:
        rest_payload = await client.request("GET", rest_path)
    resolved = _lookup_parameter_node(rest_payload, parameter_suffix, aliases=aliases)
    node = resolved["node"]
    return {
        "rest_path": rest_path,
        "resolved_suffix": resolved["suffix"],
        "parameter_id": node["id"],
        "parameter_path": _parameter_path_from_id(node["id"]),
        "node": node,
    }


_SET_VERIFY_ATTEMPTS = 4
_SET_VERIFY_DELAY_S = 0.1
_MAX_WATCH_DURATION_S = 30.0
_UNSUBSCRIBE_NOTE = (
    "Subscriptions only live for the duration of a subscribe/watch call and end automatically, "
    "so there is nothing to unsubscribe."
)


def _values_match(actual: Any, expected: Any) -> bool:
    if isinstance(actual, bool) or isinstance(expected, bool):
        return actual == expected
    if isinstance(actual, (int, float)) and isinstance(expected, (int, float)):
        return math.isclose(actual, expected, rel_tol=1e-4, abs_tol=1e-6)
    return actual == expected


async def _verify_parameter_value(client: ResolumeClient, rest_path: str, suffix: str, expected: Any) -> dict[str, Any]:
    """Read a parameter back over REST after a WebSocket set, polling briefly for Resolume to apply it."""
    value_after: Any = None
    for attempt in range(_SET_VERIFY_ATTEMPTS):
        if attempt:
            await asyncio.sleep(_SET_VERIFY_DELAY_S)
        try:
            node = _lookup_parameter_node(await client.request("GET", rest_path), suffix)["node"]
        except Exception as exc:
            return {"value_after": value_after, "verified": False, "verify_error": str(exc)}
        value_after = node.get("value")
        if _values_match(value_after, expected):
            return {"value_after": value_after, "verified": True}
    return {"value_after": value_after, "verified": False}


async def _parameter_action(
    client: ResolumeClient,
    *,
    action: str,
    rest_path: str,
    parameter_suffix: str,
    value: Any = None,
    aliases: tuple[str, ...] = (),
    rest_payload: Any = None,
    duration_s: float = 2.0,
) -> dict[str, Any]:
    if action == "unsubscribe":
        return {
            "request": {"action": action, "rest_path": rest_path, "parameter_suffix": parameter_suffix},
            "response": None,
            "note": _UNSUBSCRIBE_NOTE,
        }
    reference = await _resolve_parameter_reference(client, rest_path, parameter_suffix, aliases=aliases, rest_payload=rest_payload)
    node = reference["node"]
    request = {
        "action": action,
        "parameter": reference["parameter_path"],
        "rest_path": rest_path,
        "resolved_suffix": reference["resolved_suffix"],
        **({"value": value} if action == "set" else {}),
    }
    if action == "get":
        # The REST payload already carries the live value, so no WebSocket round trip is needed.
        return {"request": request, "response": {"source": "rest", "response": node}, "parameter": node, "value": node.get("value")}
    if action == "subscribe":
        response = await client.websocket_watch([reference["parameter_path"]], duration_s=_watch_duration(duration_s))
        return {"request": request, "response": response, "parameter": node}
    if action == "set":
        _validate_choice_value(node, value, reference["resolved_suffix"])
    response = await client.websocket_action(action, reference["parameter_path"], value=value)
    result: dict[str, Any] = {"request": request, "response": response, "parameter": node}
    if action == "set" and node.get("valuetype") == "ParamEvent":
        result.update({"value_before": node.get("value"), "verified": None, "note": "Event parameter: fired once, nothing to read back."})
    elif action == "set":
        result["value_before"] = node.get("value")
        verification = await _verify_parameter_value(client, rest_path, reference["resolved_suffix"], value)
        # Arena can drop a set that lands right after a clip load; one resend fixes that. A playhead
        # position keeps moving while playing, so a mismatch there is expected and not retried.
        if not verification["verified"] and "verify_error" not in verification and not reference["resolved_suffix"].endswith("position"):
            await client.websocket_action(action, reference["parameter_path"], value=value)
            verification = {**await _verify_parameter_value(client, rest_path, reference["resolved_suffix"], value), "retried": True}
        result.update(verification)
    return result


def _validate_choice_value(node: dict[str, Any], value: Any, suffix: str) -> None:
    options = node.get("options")
    if isinstance(options, list) and options and value not in options:
        raise ValueError(f"'{suffix}' is a choice parameter; value must be one of: {', '.join(repr(option) for option in options)}.")


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
    rest_payload: Any = None,
) -> dict[str, Any]:
    try:
        return await _parameter_action(
            client,
            action="get",
            rest_path=rest_path,
            parameter_suffix=parameter_suffix,
            aliases=aliases,
            rest_payload=rest_payload,
        )
    except Exception as exc:
        return {
            "error": str(exc),
            "rest_path": rest_path,
            "parameter_suffix": parameter_suffix,
            "aliases": list(aliases),
        }


def _watch_duration(duration_s: float) -> float:
    if not 0 < duration_s <= _MAX_WATCH_DURATION_S:
        raise ValueError(f"duration_s must be greater than 0 and at most {_MAX_WATCH_DURATION_S:g} seconds.")
    return duration_s


async def _watch_resolved_parameters(
    client: ResolumeClient,
    targets: list[dict[str, Any]],
    duration_s: float,
) -> dict[str, Any]:
    """Resolve each target's parameter id over REST (one GET per scope) and watch them on a single connection."""
    payloads: dict[str, Any] = {}
    resolved: list[dict[str, Any]] = []
    for target in targets:
        rest_path = target["rest_path"]
        if rest_path not in payloads:
            payloads[rest_path] = await client.request("GET", rest_path)
        reference = await _resolve_parameter_reference(
            client, rest_path, target["parameter_suffix"], aliases=target.get("aliases", ()), rest_payload=payloads[rest_path]
        )
        resolved.append({**{k: v for k, v in target.items() if k != "aliases"}, "parameter": reference["parameter_path"]})
    response = await client.websocket_watch([target["parameter"] for target in resolved], duration_s=duration_s)
    return {"action": "subscribe", "targets": resolved, "response": response}


async def _clip_connection_state(client: ResolumeClient, layer_index: int, clip_index: int) -> str | None:
    rest_path = f"/composition/layers/{layer_index}/clips/{clip_index}"
    payload = await _resolved_get_or_error(client, rest_path=rest_path, parameter_suffix="connected")
    response = payload.get("response", {}).get("response")
    if isinstance(response, dict):
        value = response.get("value")
        if isinstance(value, str):
            return value
    return None


def _is_connected(state: Any) -> bool:
    return isinstance(state, str) and state.startswith("Connected")


async def _disconnect_clip(client: ResolumeClient, layer_index: int, clip_index: int) -> dict[str, Any]:
    before_state = await _clip_connection_state(client, layer_index, clip_index)
    if isinstance(before_state, str) and not _is_connected(before_state):
        # Arena may treat connect=false as a trigger, and the fallback would stop whatever else is playing.
        return {
            "layer_index": layer_index,
            "clip_index": clip_index,
            "response": None,
            "fallback_response": None,
            "method": "none",
            "before_state": before_state,
            "after_state": before_state,
            "disconnected": True,
            "note": "Clip was not playing; nothing was sent.",
        }
    response = await client.request("POST", f"/composition/layers/{layer_index}/clips/{clip_index}/connect", body=False)
    after_state = await _clip_connection_state(client, layer_index, clip_index)
    method = "connect=false"
    fallback_response = None
    if _is_connected(before_state) and _is_connected(after_state):
        # Arena 7 answers 204 to connect=false but keeps the clip playing. A layer only plays one clip,
        # so clearing the layer stops exactly this clip; the media stays in its slot.
        fallback_response = await client.request("POST", f"/composition/layers/{layer_index}/clear")
        after_state = await _clip_connection_state(client, layer_index, clip_index)
        method = "layer clear"
    disconnected = isinstance(after_state, str) and not _is_connected(after_state)
    return {
        "layer_index": layer_index,
        "clip_index": clip_index,
        "response": response,
        "fallback_response": fallback_response,
        "method": method,
        "before_state": before_state,
        "after_state": after_state,
        "disconnected": disconnected,
        "note": None if disconnected else "Clip is still connected (or its state could not be read) after the disconnect request.",
    }


async def _clip_material_state(client: ResolumeClient, layer_index: int, clip_index: int) -> dict[str, Any]:
    payload = await client.request("GET", f"/composition/layers/{layer_index}/clips/{clip_index}")
    return _clip_material_state_from_payload(payload)


def _clip_material_state_from_payload(payload: Any) -> dict[str, Any]:
    body = _extract_body(payload)
    if not isinstance(body, dict):
        return {"connected": None, "name": None, "has_video": None, "has_audio": None, "payload": payload}
    connected = body.get("connected", {}).get("value") if isinstance(body.get("connected"), dict) else None
    name = body.get("name", {}).get("value") if isinstance(body.get("name"), dict) else body.get("name")
    has_video = isinstance(body.get("video"), dict)
    has_audio = isinstance(body.get("audio"), dict)
    return {
        "connected": connected,
        "name": name,
        "has_video": has_video,
        "has_audio": has_audio,
        "payload": payload,
    }


def _clip_material_state_from_clip_body(clip_body: Any, *, payload: Any) -> dict[str, Any]:
    if not isinstance(clip_body, dict):
        return {"connected": None, "name": None, "has_video": None, "has_audio": None, "payload": payload}
    connected = clip_body.get("connected", {}).get("value") if isinstance(clip_body.get("connected"), dict) else None
    name = clip_body.get("name", {}).get("value") if isinstance(clip_body.get("name"), dict) else clip_body.get("name")
    has_video = isinstance(clip_body.get("video"), dict)
    has_audio = isinstance(clip_body.get("audio"), dict)
    return {
        "connected": connected,
        "name": name,
        "has_video": has_video,
        "has_audio": has_audio,
        "payload": payload,
    }


def _clip_material_state_cleared(state: dict[str, Any]) -> bool:
    return state["connected"] == "Empty" and not state["name"] and not state["has_video"] and not state["has_audio"]


async def _poll_clip_material_state(
    client: ResolumeClient,
    *,
    layer_index: int,
    clip_index: int,
    attempts: int = 4,
    delay_s: float = 0.2,
) -> dict[str, Any]:
    latest = await _clip_material_state(client, layer_index, clip_index)
    for _ in range(attempts - 1):
        if _clip_material_state_cleared(latest):
            break
        await asyncio.sleep(delay_s)
        try:
            latest = await _clip_material_state(client, layer_index, clip_index)
        except Exception:
            break
    return latest


async def _poll_selected_clip_material_state_by_id(
    client: ResolumeClient,
    *,
    clip_id: int,
    attempts: int = 4,
    delay_s: float = 0.2,
) -> dict[str, Any]:
    latest = _clip_material_state_from_payload(await client.request("GET", f"/composition/clips/by-id/{clip_id}"))
    for _ in range(attempts - 1):
        if _clip_material_state_cleared(latest):
            break
        await asyncio.sleep(delay_s)
        try:
            latest = _clip_material_state_from_payload(await client.request("GET", f"/composition/clips/by-id/{clip_id}"))
        except Exception:
            break
    return latest


async def _selected_layer_first_clip_material_state(client: ResolumeClient) -> dict[str, Any]:
    payload = await client.request("GET", "/composition/layers/selected")
    body = _extract_body(payload)
    clips = body.get("clips") if isinstance(body, dict) else None
    first_clip = clips[0] if isinstance(clips, list) and clips else None
    return _clip_material_state_from_clip_body(first_clip, payload=payload)


async def _poll_selected_layer_first_clip_material_state(
    client: ResolumeClient,
    *,
    attempts: int = 4,
    delay_s: float = 0.2,
) -> dict[str, Any]:
    latest = await _selected_layer_first_clip_material_state(client)
    for _ in range(attempts - 1):
        if _clip_material_state_cleared(latest):
            break
        await asyncio.sleep(delay_s)
        try:
            latest = await _selected_layer_first_clip_material_state(client)
        except Exception:
            break
    return latest


async def _get_embedded_collection(
    client: ResolumeClient,
    *,
    direct_path: str,
    fallback_path: str,
    collection_key: str,
) -> dict[str, Any]:
    direct = await client.request("GET", direct_path)
    if direct.get("ok") and isinstance(direct.get("body"), list):
        return direct

    fallback = await client.request("GET", fallback_path)
    return {
        "method": "GET",
        "path": direct.get("path", direct_path),
        "url": direct.get("url"),
        "status_code": direct.get("status_code"),
        "content_type": direct.get("content_type", fallback.get("content_type", "")),
        **_embedded_collection(fallback, collection_key),
    }


def _embedded_collection(payload: Any, collection_key: str) -> dict[str, Any]:
    """Pull a collection (layers, clips, ...) out of an already-fetched parent payload."""
    body = _extract_body(payload)
    collection = body.get(collection_key) if isinstance(body, dict) else None
    return {
        "ok": isinstance(collection, list),
        "body": collection if isinstance(collection, list) else [],
        "fallback_used": True,
        "fallback_path": payload.get("path") if isinstance(payload, dict) else None,
    }


def _without_collections(payload: Any, keys: tuple[str, ...]) -> Any:
    """Copy of a REST response with collections removed that the caller reports separately."""
    body = _extract_body(payload)
    if not isinstance(payload, dict) or not isinstance(body, dict):
        return payload
    return {**payload, "body": {key: value for key, value in body.items() if key not in keys}}


_COMPOSITION_COLLECTIONS = ("layers", "columns", "layergroups", "decks")


def _param_value(node: Any, *path: str) -> Any:
    """Value of a nested REST parameter node ({"value": ...}), or the raw entry if it is not a node."""
    for key in path:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node.get("value") if isinstance(node, dict) else node


def _clip_summary(clip_index: int, clip: dict[str, Any]) -> dict[str, Any]:
    return {
        "clip_index": clip_index,
        "name": _param_value(clip, "name"),
        "connected": _param_value(clip, "connected"),
        "transport_type": _param_value(clip, "transporttype"),
    }


def _loaded_clips(layer: dict[str, Any]) -> list[dict[str, Any]]:
    clips = layer.get("clips") if isinstance(layer.get("clips"), list) else []
    return [
        _clip_summary(index, clip)
        for index, clip in enumerate(clips, start=1)
        if isinstance(clip, dict) and _param_value(clip, "connected") not in (None, "Empty")
    ]


def _layer_summary(layer_index: int, layer: dict[str, Any]) -> dict[str, Any]:
    clips = layer.get("clips") if isinstance(layer.get("clips"), list) else []
    return {
        "layer_index": layer_index,
        "name": _param_value(layer, "name"),
        "bypassed": _param_value(layer, "bypassed"),
        "opacity": _param_value(layer, "video", "opacity"),
        "clip_slots": len(clips),
    }


def _with_missing_endpoint_note(result: dict[str, Any], hint: str) -> dict[str, Any]:
    if result.get("status_code") == 404:
        result["note"] = f"This Arena build has no {result.get('path')} endpoint. {hint}"
    return result


def _advanced_output_preferences() -> AdvancedOutputPreferences:
    return AdvancedOutputPreferences.load(load_config().advanced_output_xml_path)


def _slice_inspector_preferences() -> SliceInspectorPreferences:
    return SliceInspectorPreferences.load(load_config().slices_xml_path)


async def _parameter_tool_impl(
    scope_path: str,
    action: str,
    parameter_suffix: str,
    value: Any = None,
    aliases: tuple[str, ...] = (),
    duration_s: float = 2.0,
) -> str:
    client = _client()
    kwargs: dict[str, Any] = {
        "action": action,
        "rest_path": scope_path,
        "parameter_suffix": parameter_suffix,
        "aliases": aliases,
        "duration_s": duration_s,
    }
    if value is not None:
        kwargs["value"] = value
    result = await _parameter_action(client, **kwargs)
    return _json_response(result)


async def _output_watch_tool_impl(path: str, duration_s: float) -> str:
    result = await _client().websocket_watch([path], duration_s=_watch_duration(duration_s))
    return _json_response(result)


def _output_unsubscribe_note(path: str) -> str:
    return _json_response({"action": "unsubscribe", "parameter": path, "response": None, "note": _UNSUBSCRIBE_NOTE})


async def _output_websocket_tool_impl(action: str, path: str, value: Any = None) -> str:
    kwargs: dict[str, Any] = {}
    if value is not None:
        kwargs["value"] = value
    result = await _client().websocket_action(action, path, **kwargs)
    return _json_response(result)


def _parse_playback_targets(layer_indices_json: str, clip_pairs_json: str) -> tuple[list[Any], list[dict[str, Any]]]:
    layer_indices = _parse_json_list(layer_indices_json, field_name="layer_indices_json") if layer_indices_json.strip() else []
    clip_pairs: list[dict[str, Any]] = []
    if clip_pairs_json.strip():
        clip_pairs = _parse_json_list(clip_pairs_json, field_name="clip_pairs_json")
        for pair in clip_pairs:
            if not isinstance(pair, dict) or "layer_index" not in pair or "clip_index" not in pair:
                raise ValueError("Each clip pair must include layer_index and clip_index.")
    return layer_indices, clip_pairs


def _playback_state_targets(layer_indices: list[Any], clip_pairs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    targets: list[dict[str, Any]] = [{"rest_path": "/composition", "parameter_suffix": "tempocontroller/tempo"}]
    for li in layer_indices:
        base = f"/composition/layers/{li}"
        targets.append({"layer_index": li, "rest_path": base, "parameter_suffix": "video/opacity"})
        targets.append({"layer_index": li, "rest_path": base, "parameter_suffix": "bypassed"})
    for pair in clip_pairs:
        base = f"/composition/layers/{pair['layer_index']}/clips/{pair['clip_index']}"
        for suffix in ("connected", "transport/speed", "transport/position"):
            aliases = ("transport/controls/speed",) if suffix == "transport/speed" else ()
            targets.append({"layer_index": pair["layer_index"], "clip_index": pair["clip_index"], "rest_path": base, "parameter_suffix": suffix, "aliases": aliases})
    return targets


async def _fetch_parameters(
    client: ResolumeClient,
    rest_path: str,
    suffixes: list[str],
    aliases_map: dict[str, tuple[str, ...]] | None = None,
    rest_payload: Any = None,
) -> dict[str, Any]:
    """Resolve several parameters from a single REST read of their scope."""
    aliases_map = aliases_map or {}
    if rest_payload is None:
        try:
            rest_payload = await client.request("GET", rest_path)
        except Exception as exc:
            return {suffix: {"error": str(exc), "rest_path": rest_path, "parameter_suffix": suffix} for suffix in suffixes}
    results: dict[str, Any] = {}
    for suffix in suffixes:
        results[suffix] = await _resolved_get_or_error(
            client, rest_path=rest_path, parameter_suffix=suffix, aliases=aliases_map.get(suffix, ()), rest_payload=rest_payload
        )
    return results


_READ_ONLY = ToolAnnotations(readOnlyHint=True, openWorldHint=False)
_WRITE = ToolAnnotations(readOnlyHint=False, destructiveHint=False, openWorldHint=False)
_DESTRUCTIVE = ToolAnnotations(readOnlyHint=False, destructiveHint=True, openWorldHint=False)

mcp = FastMCP(
    name="Resolume MCP",
    instructions=(
        "Control Resolume Arena/Avenue over REST, WebSocket and OSC. "
        "Conventions: composition layer, clip, column, group and deck indices are 1-based; "
        "Advanced Output screen and slice indices are 0-based. "
        "Arguments ending in _json take JSON text (e.g. layer_indices_json='[1,2]', value_json='0.5'). "
        "parameter_suffix is a path inside the scope's REST payload, e.g. 'video/opacity', 'bypassed', "
        "'transport/position', 'tempocontroller/tempo'. "
        "Destructive tools only return a confirmation request until called again with confirm_destructive=True; "
        "confirm with the operator first during a live show. "
        "Start with get_composition_summary (compact) or wait_for_resolume after launching Arena; prefer named tools over the generic "
        "rest_*/websocket_*/osc_send tools. Advanced Output REST/WebSocket tools are experimental; "
        "the *_xml tools work on the local AdvancedOutput.xml."
    ),
)


@mcp.tool(annotations=_READ_ONLY)
def get_server_config() -> str:
    """Show the Resolume host, ports, URLs and Advanced Output XML paths this server is configured for."""
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


@mcp.tool(annotations=_DESTRUCTIVE)
async def rest_request(
    method: str,
    path: str,
    body_json: str = "",
    query_json: str = "",
    confirm_destructive: bool = False,
) -> str:
    """Send any REST request (method + path under /api/v1) with optional JSON body and query. Calls matching a destructive pattern (clear, disconnect-all, DELETE, ...) need confirm_destructive=True."""
    body = _parse_json(body_json)
    params = _parse_json(query_json)
    if gate := _generic_gate("rest_request", method, path, body, confirm_destructive):
        return gate
    result = await _client().request(method, path, body=body, params=params)
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def rest_get(path: str, query_json: str = "") -> str:
    """GET any REST path under /api/v1, e.g. '/composition/layers/1'. Arena does not serve sub-parameter paths like '.../clips/1/connected' (404); use get_*_parameter or '/parameter/by-id/{id}'."""
    params = _parse_json(query_json)
    result = await _client().request("GET", path, params=params)
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def rest_post(path: str, body_json: str = "", confirm_destructive: bool = False) -> str:
    """POST to any REST path; body_json is JSON, or a JSON string sent as text/plain. Calls matching a destructive pattern (clear, disconnect-all, DELETE, ...) need confirm_destructive=True."""
    body = _parse_json(body_json)
    if gate := _generic_gate("rest_post", "POST", path, body, confirm_destructive):
        return gate
    result = await _client().request("POST", path, body=body)
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def rest_put(path: str, body_json: str = "", confirm_destructive: bool = False) -> str:
    """PUT to any REST path with a JSON body. Calls matching a destructive pattern (clear, disconnect-all, DELETE, ...) need confirm_destructive=True."""
    body = _parse_json(body_json)
    if gate := _generic_gate("rest_put", "PUT", path, body, confirm_destructive):
        return gate
    result = await _client().request("PUT", path, body=body)
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def rest_delete(path: str, body_json: str = "", confirm_destructive: bool = False) -> str:
    """DELETE any REST path. Always destructive: requires confirm_destructive=True."""
    body = _parse_json(body_json)
    if gate := _generic_gate("rest_delete", "DELETE", path, body, confirm_destructive):
        return gate
    result = await _client().request("DELETE", path, body=body)
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def websocket_action(
    action: str,
    parameter: str,
    value_json: str = "",
    confirm_destructive: bool = False,
) -> str:
    """Send a raw WebSocket action (get, set, trigger, reset, subscribe, post, remove) for a parameter path. get/subscribe wait up to 2 s for the matching reply; other actions are fire-and-forget. Calls matching a destructive pattern (clear, disconnect-all, DELETE, ...) need confirm_destructive=True."""
    value = _parse_json(value_json)
    if gate := _generic_gate("websocket_action", action, parameter, value, confirm_destructive):
        return gate
    result = await _client().websocket_action(action, parameter, value=value)
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def websocket_get(parameter: str) -> str:
    """Read a parameter over WebSocket, e.g. '/parameter/by-id/123'. Waits up to 2 s for the matching reply (reply_timed_out tells you if none came)."""
    result = await _client().websocket_action("get", parameter)
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def websocket_set(parameter: str, value_json: str, confirm_destructive: bool = False) -> str:
    """Set a parameter over WebSocket (fire-and-forget), e.g. '/parameter/by-id/123' with value_json '0.5'. Prefer the named set_* tools, which verify. Calls matching a destructive pattern (clear, disconnect-all, DELETE, ...) need confirm_destructive=True."""
    value = _parse_json(value_json)
    if gate := _generic_gate("websocket_set", "set", parameter, value, confirm_destructive):
        return gate
    result = await _client().websocket_action("set", parameter, value=value)
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def websocket_trigger(parameter: str, confirm_destructive: bool = False) -> str:
    """Fire a WebSocket trigger on a parameter or action path. Calls matching a destructive pattern (clear, disconnect-all, DELETE, ...) need confirm_destructive=True."""
    if gate := _generic_gate("websocket_trigger", "trigger", parameter, None, confirm_destructive):
        return gate
    result = await _client().websocket_action("trigger", parameter)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def websocket_reset(parameter: str) -> str:
    """Reset a parameter to its default over WebSocket."""
    result = await _client().websocket_action("reset", parameter)
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def websocket_subscribe(parameter: str, duration_s: float = 2.0) -> str:
    """Watch a raw parameter path. Subscribes for duration_s seconds (max 30) on one connection and returns the updates received."""
    result = await _client().websocket_watch([parameter], duration_s=_watch_duration(duration_s))
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def websocket_unsubscribe(parameter: str) -> str:
    """No-op kept for compatibility: subscriptions end automatically when the subscribe call returns."""
    return _json_response({"action": "unsubscribe", "parameter": parameter, "response": None, "note": _UNSUBSCRIBE_NOTE})


@mcp.tool(annotations=_DESTRUCTIVE)
async def websocket_post(parameter: str, value_json: str = "", confirm_destructive: bool = False) -> str:
    """Send a WebSocket 'post' action to a path. Calls matching a destructive pattern (clear, disconnect-all, DELETE, ...) need confirm_destructive=True."""
    value = _parse_json(value_json)
    if gate := _generic_gate("websocket_post", "post", parameter, value, confirm_destructive):
        return gate
    result = await _client().websocket_action("post", parameter, value=value)
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def websocket_remove(parameter: str, value_json: str = "", confirm_destructive: bool = False) -> str:
    """Send a WebSocket 'remove' action. Always destructive: requires confirm_destructive=True."""
    value = _parse_json(value_json)
    if gate := _generic_gate("websocket_remove", "remove", parameter, value, confirm_destructive):
        return gate
    result = await _client().websocket_action("remove", parameter, value=value)
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
def osc_send(
    address: str,
    values_json: str = "[]",
    host: str = "",
    port: int = 0,
    confirm_destructive: bool = False,
) -> str:
    """Send one OSC message (values_json is a JSON array). Resolume OSC triggers such as /clear fire on a 0->1 change, so send 0 then 1 to fire again. host override must be in RESOLUME_ALLOWED_HOSTS. Calls matching a destructive pattern (clear, disconnect-all, DELETE, ...) need confirm_destructive=True."""
    values = _parse_json(values_json)
    if values is None:
        values = []
    if not isinstance(values, list):
        raise ValueError("values_json must decode to a JSON array.")
    if gate := _generic_gate("osc_send", "osc", address, None, confirm_destructive):
        return gate
    result = _client().send_osc(address, values, host=host or None, port=port or None)
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_composition() -> str:
    """Full raw composition JSON. Very large on real shows (hundreds of KB); prefer get_composition_summary."""
    result = await _client().request("GET", "/composition")
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def new_composition(body_json: str = "", confirm_destructive: bool = False) -> str:
    """Replace the current composition with a new empty one. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("new_composition", "This will replace the ENTIRE current composition with a new empty one. Re-call with confirm_destructive=True to proceed.")
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", "/composition/new", body=body)
    return _json_response(_with_missing_endpoint_note(result, "Use File > New in Arena."))


@mcp.tool(annotations=_DESTRUCTIVE)
async def open_composition(body_json: str = "", confirm_destructive: bool = False) -> str:
    """Open a composition, replacing the current one; body_json is passed to /composition/open. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("open_composition", "This will replace the ENTIRE current composition with the opened one. Re-call with confirm_destructive=True to proceed.")
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", "/composition/open", body=body)
    return _json_response(_with_missing_endpoint_note(result, "Open the composition from Arena (File > Open)."))


@mcp.tool(annotations=_WRITE)
async def save_composition(body_json: str = "") -> str:
    """Save the current composition via /composition/save. Arena 7.23 has no such endpoint (404); the result then says to save in Arena with Ctrl+S."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", "/composition/save", body=body)
    return _json_response(_with_missing_endpoint_note(result, "Save from Arena itself (Ctrl+S or File > Save)."))


@mcp.tool(annotations=_WRITE)
async def grow_composition_to(body_json: str) -> str:
    """Grow the composition; body_json is passed to /composition/grow-to."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", "/composition/grow-to", body=body)
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_composition_parameter(parameter_suffix: str) -> str:
    """Read a composition parameter, e.g. 'tempocontroller/tempo'. parameter_suffix is the path inside the scope's REST payload, e.g. 'video/opacity' or 'bypassed'."""
    return await _parameter_tool_impl("/composition", "get", parameter_suffix)


@mcp.tool(annotations=_WRITE)
async def set_composition_parameter(parameter_suffix: str, value_json: str) -> str:
    """Set a composition parameter; value_json is a JSON value like 128 or true. Verifies by reading the value back over REST (value_before, value_after, verified)."""
    return await _parameter_tool_impl("/composition", "set", parameter_suffix, value=_parse_json(value_json))


@mcp.tool(annotations=_READ_ONLY)
async def subscribe_composition_parameter(parameter_suffix: str, duration_s: float = 2.0) -> str:
    """Watch a composition parameter. Subscribes for duration_s seconds (max 30) on one connection and returns the updates received."""
    return await _parameter_tool_impl("/composition", "subscribe", parameter_suffix, duration_s=duration_s)


@mcp.tool(annotations=_READ_ONLY)
async def unsubscribe_composition_parameter(parameter_suffix: str) -> str:
    """No-op kept for compatibility: subscriptions end automatically when the subscribe call returns."""
    return await _parameter_tool_impl("/composition", "unsubscribe", parameter_suffix)


@mcp.tool(annotations=_READ_ONLY)
async def get_node(path: str, query_json: str = "") -> str:
    """GET any REST path (alias of rest_get). Sub-parameter paths like '.../connected' 404; use get_*_parameter instead."""
    params = _parse_json(query_json)
    result = await _client().request("GET", path, params=params)
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def disconnect_all(confirm_destructive: bool = False) -> str:
    """Disconnect every clip in the composition (output goes dark). Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("disconnect_all", "This will disconnect ALL clips in the entire composition. Re-call with confirm_destructive=True to proceed.")
    result = await _client().request("POST", "/composition/disconnect-all")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_advanced_output_tree(path: str = "/advancedoutput") -> str:
    """GET a path under /advancedoutput. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    result = await _client().request("GET", _normalize_output_path(path))
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
def get_advanced_output_preferences_summary() -> str:
    """Summarize screens, slices and soft-edge settings from the local AdvancedOutput.xml."""
    prefs = _advanced_output_preferences()
    return _json_response(prefs.summary())


@mcp.tool(annotations=_READ_ONLY)
def get_advanced_output_screen_xml(screen_index: int) -> str:
    """One screen from AdvancedOutput.xml (0-based screen_index)."""
    summary = _advanced_output_preferences().summary()
    screens = summary.get("screens", [])
    if not isinstance(screens, list) or screen_index < 0 or screen_index >= len(screens):
        raise IndexError("screen_index is out of range for the current AdvancedOutput.xml.")
    return _json_response(screens[screen_index])


@mcp.tool(annotations=_READ_ONLY)
def get_advanced_output_slice_xml(screen_index: int, slice_index: int) -> str:
    """One slice from AdvancedOutput.xml (0-based screen_index and slice_index)."""
    summary = _advanced_output_preferences().summary()
    screens = summary.get("screens", [])
    if not isinstance(screens, list) or screen_index < 0 or screen_index >= len(screens):
        raise IndexError("screen_index is out of range for the current AdvancedOutput.xml.")
    slices = screens[screen_index].get("slices", [])
    if not isinstance(slices, list) or slice_index < 0 or slice_index >= len(slices):
        raise IndexError("slice_index is out of range for the selected screen in AdvancedOutput.xml.")
    return _json_response(slices[slice_index])


@mcp.tool(annotations=_READ_ONLY)
def get_slices_inspector_summary() -> str:
    """Summarize the local slices.xml (slice inspector state)."""
    prefs = _slice_inspector_preferences()
    return _json_response(prefs.summary())


@mcp.tool(annotations=_WRITE)
def backup_advanced_output_preferences(backup_dir: str = "") -> str:
    """Copy AdvancedOutput.xml and slices.xml into a timestamped backup (default: <documents_root>/Backups/AdvancedOutput)."""
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


@mcp.tool(annotations=_WRITE)
def export_advanced_output_preferences(export_dir: str = "", bundle_name: str = "") -> str:
    """Export AdvancedOutput.xml and slices.xml as a bundle without touching the live files."""
    config = load_config()
    target_dir = Path(export_dir.strip() or Path(config.documents_root) / "Exports" / "AdvancedOutput").expanduser()
    if bundle_name.strip():
        target_dir = target_dir / bundle_name.strip()
    payload = export_advanced_output_bundle(
        advanced_output_xml_path=config.advanced_output_xml_path,
        slices_xml_path=config.slices_xml_path,
        export_dir=target_dir,
    )
    payload["notes"] = [
        "This exports the current Advanced Output XML bundle without changing the live files."
    ]
    return _json_response(payload)


@mcp.tool(annotations=_READ_ONLY)
def get_windows_advanced_output_path_candidates(username: str = "", drive: str = "C:") -> str:
    """Likely Windows locations of the Advanced Output XML files for a user and drive."""
    return _json_response(windows_advanced_output_path_candidates(username=username, drive=drive))


@mcp.tool(annotations=_READ_ONLY)
def probe_advanced_output_paths(
    documents_root: str = "",
    advanced_output_xml_path: str = "",
    slices_xml_path: str = "",
) -> str:
    """Check which configured (or given) Advanced Output paths exist on this machine."""
    config = load_config()
    documents = Path(documents_root.strip() or config.documents_root).expanduser()
    advanced_output = Path(advanced_output_xml_path.strip() or config.advanced_output_xml_path).expanduser()
    slices = Path(slices_xml_path.strip() or config.slices_xml_path).expanduser()
    return _json_response(
        {
            "documents_root": {"path": str(documents), "exists": documents.exists(), "is_dir": documents.is_dir()},
            "advanced_output_xml_path": {
                "path": str(advanced_output),
                "exists": advanced_output.exists(),
                "is_file": advanced_output.is_file(),
            },
            "slices_xml_path": {
                "path": str(slices),
                "exists": slices.exists(),
                "is_file": slices.is_file(),
            },
            "notes": [
                "This only probes the local filesystem of the machine running the MCP server.",
                "Use explicit env vars on Windows media servers so these paths resolve correctly on that host.",
            ],
        }
    )


@mcp.tool(annotations=_READ_ONLY)
def preview_restore_advanced_output_preferences(
    source_advanced_output_xml_path: str,
    source_slices_xml_path: str = "",
) -> str:
    """Dry run of restore_advanced_output_preferences: diff of what a restore would change."""
    config = load_config()
    candidate_slices_path = source_slices_xml_path.strip() or str(Path(source_advanced_output_xml_path).expanduser().with_name("slices.xml"))
    payload = preview_restore_advanced_output_bundle(
        current_advanced_output_xml_path=config.advanced_output_xml_path,
        current_slices_xml_path=config.slices_xml_path,
        candidate_advanced_output_xml_path=source_advanced_output_xml_path,
        candidate_slices_xml_path=candidate_slices_path,
    )
    return _json_response(payload)


@mcp.tool(annotations=_WRITE)
def rename_advanced_output_screen(screen_index: int, new_name: str, backup_dir: str = "") -> str:
    """Rename a screen in AdvancedOutput.xml. Edits the local AdvancedOutput.xml after taking a backup; Resolume may need a restart to pick it up."""
    config = load_config()
    target_backup_dir = backup_dir.strip() or str(Path(config.documents_root) / "Backups" / "AdvancedOutput")
    payload = rename_screen_in_advanced_output(
        advanced_output_xml_path=config.advanced_output_xml_path,
        screen_index=screen_index,
        new_name=new_name,
        backup_dir=target_backup_dir,
    )
    return _json_response(payload)


@mcp.tool(annotations=_WRITE)
def rename_advanced_output_slice(screen_index: int, slice_index: int, new_name: str, backup_dir: str = "") -> str:
    """Rename a slice in AdvancedOutput.xml. Edits the local AdvancedOutput.xml after taking a backup; Resolume may need a restart to pick it up."""
    config = load_config()
    target_backup_dir = backup_dir.strip() or str(Path(config.documents_root) / "Backups" / "AdvancedOutput")
    payload = rename_slice_in_advanced_output(
        advanced_output_xml_path=config.advanced_output_xml_path,
        screen_index=screen_index,
        slice_index=slice_index,
        new_name=new_name,
        backup_dir=target_backup_dir,
    )
    return _json_response(payload)


@mcp.tool(annotations=_WRITE)
def set_advanced_output_soft_edge_power_xml(value: float, backup_dir: str = "") -> str:
    """Set the soft-edge power value. Edits the local AdvancedOutput.xml after taking a backup; Resolume may need a restart to pick it up."""
    config = load_config()
    target_backup_dir = backup_dir.strip() or str(Path(config.documents_root) / "Backups" / "AdvancedOutput")
    payload = set_advanced_output_soft_edge_power(
        advanced_output_xml_path=config.advanced_output_xml_path,
        value=value,
        backup_dir=target_backup_dir,
    )
    return _json_response(payload)


@mcp.tool(annotations=_WRITE)
def set_advanced_output_screen_output_device_xml(
    screen_index: int,
    name: str,
    device_id: str,
    width: int,
    height: int,
    backup_dir: str = "",
) -> str:
    """Point a screen at an output device (name, device_id, width, height). Edits the local AdvancedOutput.xml after taking a backup; Resolume may need a restart to pick it up."""
    config = load_config()
    target_backup_dir = backup_dir.strip() or str(Path(config.documents_root) / "Backups" / "AdvancedOutput")
    payload = set_advanced_output_screen_output_device(
        advanced_output_xml_path=config.advanced_output_xml_path,
        screen_index=screen_index,
        name=name,
        device_id=device_id,
        width=width,
        height=height,
        backup_dir=target_backup_dir,
    )
    return _json_response(payload)


@mcp.tool(annotations=_WRITE)
def set_advanced_output_slice_input_rect_xml(
    screen_index: int,
    slice_index: int,
    vertices_json: str,
    backup_dir: str = "",
) -> str:
    """Replace a slice's input rect vertices; vertices_json is a JSON array of {"x":..,"y":..}. Edits the local AdvancedOutput.xml after taking a backup; Resolume may need a restart to pick it up."""
    vertices = _parse_json_list(vertices_json, field_name="vertices_json")
    config = load_config()
    target_backup_dir = backup_dir.strip() or str(Path(config.documents_root) / "Backups" / "AdvancedOutput")
    payload = set_advanced_output_slice_vertices(
        advanced_output_xml_path=config.advanced_output_xml_path,
        screen_index=screen_index,
        slice_index=slice_index,
        path="./InputRect",
        vertices=vertices,
        backup_dir=target_backup_dir,
    )
    return _json_response(payload)


@mcp.tool(annotations=_WRITE)
def set_advanced_output_slice_output_rect_xml(
    screen_index: int,
    slice_index: int,
    vertices_json: str,
    backup_dir: str = "",
) -> str:
    """Replace a slice's output rect vertices; vertices_json is a JSON array of {"x":..,"y":..}. Edits the local AdvancedOutput.xml after taking a backup; Resolume may need a restart to pick it up."""
    vertices = _parse_json_list(vertices_json, field_name="vertices_json")
    config = load_config()
    target_backup_dir = backup_dir.strip() or str(Path(config.documents_root) / "Backups" / "AdvancedOutput")
    payload = set_advanced_output_slice_vertices(
        advanced_output_xml_path=config.advanced_output_xml_path,
        screen_index=screen_index,
        slice_index=slice_index,
        path="./OutputRect",
        vertices=vertices,
        backup_dir=target_backup_dir,
    )
    return _json_response(payload)


@mcp.tool(annotations=_WRITE)
def set_advanced_output_slice_homography_dst_xml(
    screen_index: int,
    slice_index: int,
    vertices_json: str,
    backup_dir: str = "",
) -> str:
    """Replace a slice's warp (homography) destination vertices; vertices_json is a JSON array of {"x":..,"y":..}. Edits the local AdvancedOutput.xml after taking a backup; Resolume may need a restart to pick it up."""
    vertices = _parse_json_list(vertices_json, field_name="vertices_json")
    config = load_config()
    target_backup_dir = backup_dir.strip() or str(Path(config.documents_root) / "Backups" / "AdvancedOutput")
    payload = set_advanced_output_slice_vertices(
        advanced_output_xml_path=config.advanced_output_xml_path,
        screen_index=screen_index,
        slice_index=slice_index,
        path="./Warper/Homography/dst",
        vertices=vertices,
        backup_dir=target_backup_dir,
    )
    return _json_response(payload)


@mcp.tool(annotations=_DESTRUCTIVE)
def restore_advanced_output_preferences(
    source_advanced_output_xml_path: str,
    source_slices_xml_path: str = "",
    backup_dir: str = "",
    confirm_destructive: bool = False,
) -> str:
    """Overwrite the live AdvancedOutput.xml and slices.xml from a source bundle, backing up first. Preview with preview_restore_advanced_output_preferences. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("restore_advanced_output_preferences", "This will overwrite the live AdvancedOutput.xml and slices.xml (a backup is taken first). Run preview_restore_advanced_output_preferences to see the diff, then re-call with confirm_destructive=True to proceed.")
    config = load_config()
    candidate_slices_path = source_slices_xml_path.strip() or str(Path(source_advanced_output_xml_path).expanduser().with_name("slices.xml"))
    target_backup_dir = backup_dir.strip() or str(Path(config.documents_root) / "Backups" / "AdvancedOutput")
    payload = restore_advanced_output_bundle(
        current_advanced_output_xml_path=config.advanced_output_xml_path,
        current_slices_xml_path=config.slices_xml_path,
        source_advanced_output_xml_path=source_advanced_output_xml_path,
        source_slices_xml_path=candidate_slices_path,
        backup_dir=target_backup_dir,
    )
    return _json_response(payload)


@mcp.tool(annotations=_READ_ONLY)
def diff_advanced_output_preferences(other_xml_path: str) -> str:
    """Unified diff between the live AdvancedOutput.xml and another XML file."""
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


@mcp.tool(annotations=_READ_ONLY)
async def list_layers() -> str:
    """Full raw layer list, clips included (large on real shows; prefer get_composition_summary). Falls back to the embedded composition list when the direct endpoint 404s."""
    client = _client()
    result = await _get_embedded_collection(
        client,
        direct_path="/composition/layers",
        fallback_path="/composition",
        collection_key="layers",
    )
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def list_columns() -> str:
    """List columns, falling back to the embedded composition list when the direct endpoint 404s."""
    client = _client()
    result = await _get_embedded_collection(
        client,
        direct_path="/composition/columns",
        fallback_path="/composition",
        collection_key="columns",
    )
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def list_groups() -> str:
    """List layer groups (REST 'layergroups'), falling back to the embedded composition list."""
    client = _client()
    result = await _get_embedded_collection(
        client,
        direct_path="/composition/layergroups",
        fallback_path="/composition",
        collection_key="layergroups",
    )
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def list_decks() -> str:
    """List decks from the composition payload."""
    result = await _client().request("GET", "/composition")
    if isinstance(result.get("body"), dict):
        result["body"] = result["body"].get("decks", [])
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_selected_layer() -> str:
    """Raw REST payload for the selected layer."""
    result = await _client().request("GET", "/composition/layers/selected")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_selected_group() -> str:
    """Raw REST payload for the selected layer group. Returned 404 on the validated build."""
    result = await _client().request("GET", "/composition/layergroups/selected")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_selected_clip() -> str:
    """Raw REST payload for the selected clip."""
    result = await _client().request("GET", "/composition/clips/selected")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_selected_active_clip() -> str:
    """The connected clip on the selected layer. May 404 on some builds."""
    result = await _client().request("GET", "/composition/layers/selected/clips/active")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def list_output_screens() -> str:
    """List output screens (0-based). Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    result = await _client().request("GET", "/advancedoutput/screens")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_output_overview() -> str:
    """All screens with their slices. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
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


@mcp.tool(annotations=_READ_ONLY)
async def get_output_screen(screen_index: int) -> str:
    """One output screen (0-based screen_index). Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    result = await _client().request("GET", f"/advancedoutput/screens/{screen_index}")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_output_screen_snapshot(screen_index: int) -> str:
    """One screen plus its slices. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
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


@mcp.tool(annotations=_READ_ONLY)
async def list_output_slices(screen_index: int) -> str:
    """Slices of a screen (0-based). Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    result = await _client().request("GET", f"/advancedoutput/screens/{screen_index}/slices")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_output_slice(screen_index: int, slice_index: int) -> str:
    """One slice. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    result = await _client().request("GET", f"/advancedoutput/screens/{screen_index}/slices/{slice_index}")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_output_slice_snapshot(screen_index: int, slice_index: int) -> str:
    """One slice plus its input, opacity and bypassed values. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
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


@mcp.tool(annotations=_READ_ONLY)
async def audit_output_screen(screen_index: int) -> str:
    """Audit a screen: flags no slices, unassigned slice inputs, or disabled screen. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
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


@mcp.tool(annotations=_READ_ONLY)
async def audit_all_output_screens() -> str:
    """audit_output_screen for every screen. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
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


@mcp.tool(annotations=_READ_ONLY)
async def get_layer(layer_index: int) -> str:
    """Raw REST payload for one layer, all clips included (can be hundreds of KB); prefer get_layer_summary."""
    result = await _client().request("GET", f"/composition/layers/{layer_index}")
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def duplicate_layer(layer_index: int, body_json: str = "") -> str:
    """Duplicate a layer (1-based layer_index)."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", f"/composition/layers/{layer_index}/duplicate", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def add_layer(body_json: str = "") -> str:
    """Add a layer; optional body_json is passed through."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", "/composition/layers/add", body=body)
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_composition_overview() -> str:
    """Raw composition settings plus the full layers, columns, groups and decks lists in one read. Large on real shows; prefer get_composition_summary."""
    composition = await _client().request("GET", "/composition")
    return _json_response(
        {
            "composition": _without_collections(composition, _COMPOSITION_COLLECTIONS),
            "layers": _embedded_collection(composition, "layers"),
            "columns": _embedded_collection(composition, "columns"),
            "groups": _embedded_collection(composition, "layergroups"),
            "decks": _embedded_collection(composition, "decks"),
        }
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_composition_summary() -> str:
    """Compact show state from one read: composition name and BPM, every layer (name, bypassed, opacity, loaded clip count, playing clips), columns, decks and groups. Start here; it stays small on large shows."""
    composition = await _client().request("GET", "/composition")
    body = _extract_body(composition)
    if not isinstance(body, dict):
        return _json_response({"ok": False, "status_code": composition.get("status_code"), "body": body})

    def entries(key: str) -> list[dict[str, Any]]:
        value = body.get(key)
        return [entry for entry in value if isinstance(entry, dict)] if isinstance(value, list) else []

    layers = []
    for index, layer in enumerate(entries("layers"), start=1):
        loaded = _loaded_clips(layer)
        layers.append(
            {
                **_layer_summary(index, layer),
                "loaded_clip_count": len(loaded),
                "playing": [clip for clip in loaded if _is_connected(clip["connected"])],
            }
        )
    return _json_response(
        {
            "ok": True,
            "name": _param_value(body, "name"),
            "bpm": _param_value(body, "tempocontroller", "tempo"),
            "layer_count": len(layers),
            "layers": layers,
            "columns": [{"column_index": i, "name": _param_value(c, "name")} for i, c in enumerate(entries("columns"), start=1)],
            "decks": [{"deck_index": i, "name": _param_value(d, "name"), "selected": _param_value(d, "selected")} for i, d in enumerate(entries("decks"), start=1)],
            "groups": [{"group_index": i, "name": _param_value(g, "name")} for i, g in enumerate(entries("layergroups"), start=1)],
        }
    )


@mcp.tool(annotations=_READ_ONLY)
async def get_layer_summary(layer_index: int) -> str:
    """Compact view of one layer: name, bypassed, opacity and every loaded clip slot (index, name, connected state, transport type). Much smaller than get_layer."""
    layer = await _client().request("GET", f"/composition/layers/{layer_index}")
    body = _extract_body(layer)
    if not isinstance(body, dict):
        return _json_response({"ok": False, "status_code": layer.get("status_code"), "body": body})
    return _json_response({"ok": True, **_layer_summary(layer_index, body), "clips": _loaded_clips(body)})


@mcp.tool(annotations=_READ_ONLY)
async def wait_for_resolume(timeout_s: float = 60.0, interval_s: float = 1.0) -> str:
    """Poll Resolume's REST API until it answers (e.g. right after launching Arena). Returns ready, how long it took and product info. timeout_s is capped at 300, interval_s at 10."""
    if not 0 < timeout_s <= 300 or not 0 < interval_s <= 10:
        raise ValueError("timeout_s must be in (0, 300] and interval_s in (0, 10].")
    client = _client()
    loop = asyncio.get_running_loop()
    started = loop.time()
    attempts = 0
    last_error: str | None = None
    while True:
        attempts += 1
        try:
            product = await client.request("GET", "/product", timeout_s=max(interval_s, 1.0))
            if product.get("ok"):
                return _json_response({"ready": True, "waited_s": round(loop.time() - started, 2), "attempts": attempts, "product": product.get("body")})
            last_error = f"HTTP {product.get('status_code')}"
        except Exception as exc:
            last_error = str(exc)
        if loop.time() - started + interval_s > timeout_s:
            return _json_response({"ready": False, "waited_s": round(loop.time() - started, 2), "attempts": attempts, "last_error": last_error})
        await asyncio.sleep(interval_s)


@mcp.tool(annotations=_READ_ONLY)
async def get_layer_snapshot(layer_index: int) -> str:
    """One-read layer snapshot: layer settings, its clips, opacity and bypassed values."""
    client = _client()
    rest_path = f"/composition/layers/{layer_index}"
    layer = await client.request("GET", rest_path)
    params = await _fetch_parameters(client, rest_path, ["video/opacity", "bypassed"], rest_payload=layer)
    return _json_response(
        {
            "layer_index": layer_index,
            "layer": _without_collections(layer, ("clips",)),
            "clips": _embedded_collection(layer, "clips"),
            "opacity": params["video/opacity"],
            "bypassed": params["bypassed"],
        }
    )


@mcp.tool(annotations=_READ_ONLY)
async def audit_layer(layer_index: int) -> str:
    """Audit a layer: flags no clips, zero opacity or bypassed."""
    client = _client()
    rest_path = f"/composition/layers/{layer_index}"
    layer = await client.request("GET", rest_path)
    clips = _embedded_collection(layer, "clips")
    params = await _fetch_parameters(client, rest_path, ["video/opacity", "bypassed"], rest_payload=layer)
    opacity = params["video/opacity"]
    bypassed = params["bypassed"]

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
            "layer": _without_collections(layer, ("clips",)),
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


@mcp.tool(annotations=_READ_ONLY)
async def audit_composition() -> str:
    """Readiness audit of the composition: counts layers/columns/groups/decks, checks tempo, returns findings."""
    client = _client()
    composition = await client.request("GET", "/composition")
    layers = _embedded_collection(composition, "layers")
    columns = _embedded_collection(composition, "columns")
    groups = _embedded_collection(composition, "layergroups")
    decks = _embedded_collection(composition, "decks")
    bpm = await _resolved_get_or_error(
        client,
        rest_path="/composition",
        parameter_suffix="tempocontroller/tempo",
        rest_payload=composition,
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
            "composition": _without_collections(composition, _COMPOSITION_COLLECTIONS),
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


@mcp.tool(annotations=_READ_ONLY)
async def get_layer_parameter(layer_index: int, parameter_suffix: str) -> str:
    """Read a layer parameter. parameter_suffix is the path inside the scope's REST payload, e.g. 'video/opacity' or 'bypassed'."""
    return await _parameter_tool_impl(f"/composition/layers/{layer_index}", "get", parameter_suffix)


@mcp.tool(annotations=_WRITE)
async def set_layer_parameter(layer_index: int, parameter_suffix: str, value_json: str) -> str:
    """Set a layer parameter; value_json is a JSON value. Verifies by reading the value back over REST (value_before, value_after, verified)."""
    return await _parameter_tool_impl(f"/composition/layers/{layer_index}", "set", parameter_suffix, value=_parse_json(value_json))


@mcp.tool(annotations=_READ_ONLY)
async def subscribe_layer_parameter(layer_index: int, parameter_suffix: str, duration_s: float = 2.0) -> str:
    """Watch a layer parameter. Subscribes for duration_s seconds (max 30) on one connection and returns the updates received."""
    return await _parameter_tool_impl(f"/composition/layers/{layer_index}", "subscribe", parameter_suffix, duration_s=duration_s)


@mcp.tool(annotations=_READ_ONLY)
async def unsubscribe_layer_parameter(layer_index: int, parameter_suffix: str) -> str:
    """No-op kept for compatibility: subscriptions end automatically when the subscribe call returns."""
    return await _parameter_tool_impl(f"/composition/layers/{layer_index}", "unsubscribe", parameter_suffix)


@mcp.tool(annotations=_READ_ONLY)
async def get_column(column_index: int) -> str:
    """Raw REST payload for one column (1-based column_index)."""
    result = await _client().request("GET", f"/composition/columns/{column_index}")
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def duplicate_column(column_index: int, body_json: str = "") -> str:
    """Duplicate a column (1-based column_index)."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", f"/composition/columns/{column_index}/duplicate", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def add_column(body_json: str = "") -> str:
    """Add a column; optional body_json is passed through."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", "/composition/columns/add", body=body)
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_group(group_index: int) -> str:
    """Raw REST payload for one layer group (1-based group_index)."""
    result = await _client().request("GET", f"/composition/layergroups/{group_index}")
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def duplicate_group(group_index: int, body_json: str = "") -> str:
    """Duplicate a layer group."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", f"/composition/layergroups/{group_index}/duplicate", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def add_group(body_json: str = "") -> str:
    """Add a layer group; optional body_json is passed through."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", "/composition/layergroups/add", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def add_layer_to_group(group_index: int, body_json: str = "") -> str:
    """Add a new layer to a group; optional body_json is passed through."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", f"/composition/layergroups/{group_index}/add-layer", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def move_layer_to_group(group_index: int, body_json: str) -> str:
    """Move a layer into a group; body_json (JSON object) is passed to /move-layer."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", f"/composition/layergroups/{group_index}/move-layer", body=body)
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def clear_group(group_index: int, confirm_destructive: bool = False) -> str:
    """Clear a layer group, removing its content. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("clear_group", f"This will clear group {group_index}, removing all its content. Re-call with confirm_destructive=True to proceed.")
    result = await _client().request("POST", f"/composition/layergroups/{group_index}/clear")
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def clear_selected_group(confirm_destructive: bool = False) -> str:
    """Clear the selected layer group. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("clear_selected_group", "This will clear the selected group, removing all its content. Re-call with confirm_destructive=True to proceed.")
    result = await _client().request("POST", "/composition/layergroups/selected/clear")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_deck(deck_index: int) -> str:
    """Raw REST payload for one deck (1-based deck_index)."""
    result = await _client().request("GET", f"/composition/decks/{deck_index}")
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def duplicate_deck(deck_index: int, body_json: str = "") -> str:
    """Duplicate a deck."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", f"/composition/decks/{deck_index}/duplicate", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def add_deck(body_json: str = "") -> str:
    """Add a deck; optional body_json is passed through."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", "/composition/decks/add", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def open_deck(deck_index: int, body_json: str = "") -> str:
    """POST /composition/decks/{deck_index}/open."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", f"/composition/decks/{deck_index}/open", body=body)
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def close_deck(deck_index: int, body_json: str = "", confirm_destructive: bool = False) -> str:
    """Close a deck, removing it from the composition. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("close_deck", f"This will close deck {deck_index}, removing it from the composition. Re-call with confirm_destructive=True to proceed.")
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", f"/composition/decks/{deck_index}/close", body=body)
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def list_clips(layer_index: int) -> str:
    """List clips on a layer, falling back to the embedded layer payload when the direct endpoint 404s."""
    client = _client()
    result = await _get_embedded_collection(
        client,
        direct_path=f"/composition/layers/{layer_index}/clips",
        fallback_path=f"/composition/layers/{layer_index}",
        collection_key="clips",
    )
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_clip(layer_index: int, clip_index: int) -> str:
    """Raw REST payload for one clip (1-based layer_index and clip_index)."""
    result = await _client().request("GET", f"/composition/layers/{layer_index}/clips/{clip_index}")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_active_clip(layer_index: int) -> str:
    """The connected clip on a layer. Returned 404 on the validated build; use list_clips and check 'connected'."""
    result = await _client().request("GET", f"/composition/layers/{layer_index}/clips/active")
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def open_clip(layer_index: int, clip_index: int, body_json: str = "") -> str:
    """Load media or a source into a clip slot (replaces what is there). Sources use their display name, e.g. 'source:///video/DeckLink 8K Pro (1) - SDI 1' (encoded automatically), not the idstring. body_json: a media path or URI as a JSON string (Windows/POSIX paths become file:// URIs), or an object with a 'path' field."""
    parsed = _parse_json(body_json)
    body = _normalize_media_scalar_or_field(parsed) if parsed is not None else None
    result = await _client().request("POST", f"/composition/layers/{layer_index}/clips/{clip_index}/open", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def open_clip_file(layer_index: int, clip_index: int, body_json: str) -> str:
    """Load media via the deprecated /openfile endpoint; prefer open_clip. body_json: a media path or URI as a JSON string (Windows/POSIX paths become file:// URIs), or an object with a 'path' field."""
    body = _normalize_media_scalar_or_field(_parse_json(body_json))
    result = await _client().request("POST", f"/composition/layers/{layer_index}/clips/{clip_index}/openfile", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def insert_clip(layer_index: int, clip_index: int, body_json: str) -> str:
    """Insert media at a clip slot; body_json is a path/URI or a JSON array of them."""
    body = _normalize_media_insert_body(_parse_json(body_json))
    result = await _client().request("POST", f"/composition/layers/{layer_index}/clips/{clip_index}/insert", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def open_clip_in_selected_slot(body_json: str) -> str:
    """Load media into the selected clip slot. body_json: a media path or URI as a JSON string (Windows/POSIX paths become file:// URIs), or an object with a 'path' field."""
    parsed = _parse_json(body_json)
    body = _normalize_media_scalar_or_field(parsed) if parsed is not None else None
    result = await _client().request("POST", "/composition/clips/open", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def open_selected_clip(body_json: str = "") -> str:
    """Load media into the selected clip. body_json: a media path or URI as a JSON string (Windows/POSIX paths become file:// URIs), or an object with a 'path' field."""
    parsed = _parse_json(body_json)
    body = _normalize_media_scalar_or_field(parsed) if parsed is not None else None
    result = await _client().request("POST", "/composition/clips/selected/open", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def open_selected_clip_file(body_json: str) -> str:
    """Deprecated /openfile variant of open_selected_clip. body_json: a media path or URI as a JSON string (Windows/POSIX paths become file:// URIs), or an object with a 'path' field."""
    body = _normalize_media_scalar_or_field(_parse_json(body_json))
    result = await _client().request("POST", "/composition/clips/selected/openfile", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def insert_selected_clip(body_json: str) -> str:
    """Insert media at the selected clip; body_json is a path/URI or a JSON array of them."""
    body = _normalize_media_insert_body(_parse_json(body_json))
    result = await _client().request("POST", "/composition/clips/selected/insert", body=body)
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def list_available_effects() -> str:
    """List the effects Resolume offers (use the effect URIs with add_effect)."""
    result = await _client().request("GET", "/effects")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def list_available_sources() -> str:
    """List generator and capture sources. Load one with open_clip using 'source:///video/<display name>'."""
    result = await _client().request("GET", "/sources")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_product_info() -> str:
    """Resolume product name and version; a quick connectivity check."""
    result = await _client().request("GET", "/product")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_file_info(body_json: str) -> str:
    """Ask Resolume about media files; body_json is a JSON array of paths or URIs."""
    body = _parse_json_list(body_json, field_name="body_json")
    normalized = [_normalize_media_uri(item) for item in body]
    result = await _client().request("POST", "/files", body=normalized)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def update_clip_thumbnail(layer_index: int, clip_index: int, body_json: str = "") -> str:
    """Regenerate a clip's thumbnail."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", f"/composition/layers/{layer_index}/clips/{clip_index}/thumbnail/update", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def revert_clip_thumbnail(layer_index: int, clip_index: int) -> str:
    """Revert a clip's thumbnail to the default."""
    result = await _client().request("DELETE", f"/composition/layers/{layer_index}/clips/{clip_index}/thumbnail")
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def update_selected_clip_thumbnail(body_json: str = "") -> str:
    """Regenerate the selected clip's thumbnail."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", "/composition/clips/selected/thumbnail/update", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def revert_selected_clip_thumbnail() -> str:
    """Revert the selected clip's thumbnail to the default."""
    result = await _client().request("DELETE", "/composition/clips/selected/thumbnail")
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_clip_snapshot(layer_index: int, clip_index: int) -> str:
    """One-read clip snapshot: connected, selected, speed and position."""
    client = _client()
    rest_path = f"/composition/layers/{layer_index}/clips/{clip_index}"
    clip = await client.request("GET", rest_path)
    params = await _fetch_parameters(
        client, rest_path,
        ["connected", "transport/speed", "selected", "transport/position"],
        aliases_map={"transport/speed": ("transport/controls/speed",)},
        rest_payload=clip,
    )
    return _json_response(
        {
            "layer_index": layer_index,
            "clip_index": clip_index,
            "clip": clip,
            "connected": params["connected"],
            "selected": params["selected"],
            "speed": params["transport/speed"],
            "position": params["transport/position"],
        }
    )


@mcp.tool(annotations=_READ_ONLY)
async def audit_clip(layer_index: int, clip_index: int) -> str:
    """Audit a clip: flags disconnected, not selected, zero speed or bypassed."""
    client = _client()
    rest_path = f"/composition/layers/{layer_index}/clips/{clip_index}"
    clip = await client.request("GET", rest_path)
    params = await _fetch_parameters(
        client, rest_path,
        ["connected", "selected", "transport/speed", "transport/position", "bypassed"],
        aliases_map={"transport/speed": ("transport/controls/speed",)},
        rest_payload=clip,
    )
    connected = params["connected"]
    selected = params["selected"]
    speed = params["transport/speed"]
    position = params["transport/position"]
    bypassed = params["bypassed"]

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


@mcp.tool(annotations=_WRITE)
async def trigger_clips(layer_index: int, clip_indices_json: str) -> str:
    """Trigger several clips on one layer; clip_indices_json is a JSON array."""
    clip_indices = _parse_json_list(clip_indices_json, field_name="clip_indices_json")
    results: list[dict[str, Any]] = []
    client = _client()
    for clip_index in clip_indices:
        response = await client.request("POST", f"/composition/layers/{layer_index}/clips/{clip_index}/connect")
        results.append({"layer_index": layer_index, "clip_index": clip_index, "response": response})
    return _json_response({"results": results})


@mcp.tool(annotations=_DESTRUCTIVE)
async def disconnect_clips(layer_index: int, clip_indices_json: str, confirm_destructive: bool = False) -> str:
    """Stop several clips on one layer (same fallback as disconnect_clip); clip_indices_json is a JSON array. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("disconnect_clips", f"This will disconnect the specified clips on layer {layer_index}. Re-call with confirm_destructive=True to proceed.")
    clip_indices = _parse_json_list(clip_indices_json, field_name="clip_indices_json")
    client = _client()
    results = [await _disconnect_clip(client, layer_index, clip_index) for clip_index in clip_indices]
    return _json_response({"results": results})


@mcp.tool(annotations=_DESTRUCTIVE)
async def clear_layers(layer_indices_json: str, confirm_destructive: bool = False) -> str:
    """Clear several layers: stops what is playing on the layer (disconnects its active clip); the clips stay in their slots. layer_indices_json is a JSON array. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("clear_layers", "This will stop playback on the specified layers (their playing clips are disconnected; clips stay in their slots). Re-call with confirm_destructive=True to proceed.")
    layer_indices = _parse_json_list(layer_indices_json, field_name="layer_indices_json")
    results: list[dict[str, Any]] = []
    client = _client()
    for layer_index in layer_indices:
        response = await client.request("POST", f"/composition/layers/{layer_index}/clear")
        results.append({"layer_index": layer_index, "response": response})
    return _json_response({"results": results})


@mcp.tool(annotations=_WRITE)
async def prepare_layer(
    layer_index: int,
    *,
    opacity: float | None = None,
    unbypass: bool = True,
) -> str:
    """Get a layer show-ready: un-bypass it and optionally set opacity. Each set is verified."""
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


@mcp.tool(annotations=_WRITE)
async def prepare_multiple_layers(
    layer_indices_json: str,
    *,
    opacity: float | None = None,
    unbypass: bool = True,
) -> str:
    """prepare_layer for several layers; layer_indices_json is a JSON array like [1,2]."""
    layer_indices = _parse_json_list(layer_indices_json, field_name="layer_indices_json")
    results: list[dict[str, Any]] = []
    for layer_index in layer_indices:
        payload = json.loads(await prepare_layer(layer_index, opacity=opacity, unbypass=unbypass))
        results.append(payload)
    return _json_response({"layer_count": len(results), "layers": results})


@mcp.tool(annotations=_WRITE)
async def prepare_playback(
    *,
    playing: bool = True,
    bpm: float | None = None,
    layer_indices_json: str = "",
    layer_opacity: float | None = None,
    unbypass_layers: bool = True,
) -> str:
    """Show prep in one call: optional BPM, composition playing (skipped where unsupported), and layer un-bypass/opacity for layer_indices_json."""
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


@mcp.tool(annotations=_WRITE)
async def select_clips(layer_index: int, clip_indices_json: str) -> str:
    """Select several clips on one layer; clip_indices_json is a JSON array. Not live-verified."""
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


@mcp.tool(annotations=_WRITE)
async def select_layers(layer_indices_json: str) -> str:
    """Select several layers; layer_indices_json is a JSON array. Not live-verified."""
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


@mcp.tool(annotations=_WRITE)
async def select_columns(column_indices_json: str) -> str:
    """Select several columns; column_indices_json is a JSON array. Not live-verified."""
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


@mcp.tool(annotations=_READ_ONLY)
async def monitor_playback_state(layer_indices_json: str = "", clip_pairs_json: str = "") -> str:
    """Read tempo plus opacity/bypassed for layers (layer_indices_json) and connected/speed/position for clips (clip_pairs_json: [{"layer_index":1,"clip_index":2}])."""
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
    tempo = (await _fetch_parameters(client, "/composition", ["tempocontroller/tempo"]))["tempocontroller/tempo"]

    layers: list[dict[str, Any]] = []
    for layer_index in layer_indices:
        params = await _fetch_parameters(client, f"/composition/layers/{layer_index}", ["video/opacity", "bypassed"])
        layers.append({"layer_index": layer_index, "opacity": params["video/opacity"], "bypassed": params["bypassed"]})

    clips: list[dict[str, Any]] = []
    for pair in clip_pairs:
        layer_index = pair["layer_index"]
        clip_index = pair["clip_index"]
        params = await _fetch_parameters(
            client,
            f"/composition/layers/{layer_index}/clips/{clip_index}",
            ["connected", "transport/speed", "transport/position"],
            aliases_map={"transport/speed": ("transport/controls/speed",)},
        )
        clips.append(
            {
                "layer_index": layer_index,
                "clip_index": clip_index,
                "connected": params["connected"],
                "speed": params["transport/speed"],
                "position": params["transport/position"],
            }
        )

    return _json_response(
        {
            "tempo": tempo,
            "layers": layers,
            "clips": clips,
            "notes": [
                "Composition transport/playing is not included in the live-validated REST payload on this build, so playback monitoring uses tempo plus layer and clip state."
            ],
        }
    )


@mcp.tool(annotations=_READ_ONLY)
async def subscribe_playback_state(layer_indices_json: str = "", clip_pairs_json: str = "", duration_s: float = 2.0) -> str:
    """Watch tempo and the given layers/clips (same arguments as monitor_playback_state). Subscribes for duration_s seconds (max 30) on one connection and returns the updates received."""
    layer_indices, clip_pairs = _parse_playback_targets(layer_indices_json, clip_pairs_json)
    targets = _playback_state_targets(layer_indices, clip_pairs)
    return _json_response(await _watch_resolved_parameters(_client(), targets, _watch_duration(duration_s)))


@mcp.tool(annotations=_READ_ONLY)
async def unsubscribe_playback_state(layer_indices_json: str = "", clip_pairs_json: str = "") -> str:
    """No-op kept for compatibility: subscriptions end automatically when the subscribe call returns."""
    _parse_playback_targets(layer_indices_json, clip_pairs_json)
    return _json_response({"action": "unsubscribe", "response": None, "note": _UNSUBSCRIBE_NOTE})


@mcp.tool(annotations=_READ_ONLY)
async def get_deck_snapshot(deck_index: int) -> str:
    """One-read deck snapshot: selected, scrollx and closed."""
    client = _client()
    rest_path = f"/composition/decks/{deck_index}"
    deck = await client.request("GET", rest_path)
    params = await _fetch_parameters(client, rest_path, ["selected", "scrollx"], rest_payload=deck)
    deck_body = _extract_body(deck)
    return _json_response(
        {
            "deck_index": deck_index,
            "deck": deck,
            "selected": params["selected"],
            "scrollx": params["scrollx"],
            "closed": deck_body.get("closed") if isinstance(deck_body, dict) else None,
            "notes": [
                "The validated deck REST schema exposes selected and scrollx, but not deck transport fields."
            ],
        }
    )


@mcp.tool(annotations=_READ_ONLY)
async def audit_deck(deck_index: int) -> str:
    """Audit a deck: flags closed or not selected."""
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


@mcp.tool(annotations=_READ_ONLY)
async def monitor_decks(deck_indices_json: str) -> str:
    """Snapshot several decks; deck_indices_json is a JSON array."""
    deck_indices = _parse_json_list(deck_indices_json, field_name="deck_indices_json")
    decks: list[dict[str, Any]] = []
    client = _client()
    for deck_index in deck_indices:
        rest_path = f"/composition/decks/{deck_index}"
        deck = await client.request("GET", rest_path)
        params = await _fetch_parameters(client, rest_path, ["selected", "scrollx"], rest_payload=deck)
        decks.append(
            {
                "deck_index": deck_index,
                "deck": deck,
                "selected": params["selected"],
                "scrollx": params["scrollx"],
            }
        )
    return _json_response({"decks": decks})


@mcp.tool(annotations=_READ_ONLY)
async def subscribe_decks(deck_indices_json: str, duration_s: float = 2.0) -> str:
    """Watch selected/scrollx on several decks. Subscribes for duration_s seconds (max 30) on one connection and returns the updates received."""
    deck_indices = _parse_json_list(deck_indices_json, field_name="deck_indices_json")
    targets = [
        {"deck_index": deck_index, "rest_path": f"/composition/decks/{deck_index}", "parameter_suffix": suffix}
        for deck_index in deck_indices
        for suffix in ("selected", "scrollx")
    ]
    return _json_response(await _watch_resolved_parameters(_client(), targets, _watch_duration(duration_s)))


@mcp.tool(annotations=_READ_ONLY)
async def unsubscribe_decks(deck_indices_json: str) -> str:
    """No-op kept for compatibility: subscriptions end automatically when the subscribe call returns."""
    _parse_json_list(deck_indices_json, field_name="deck_indices_json")
    return _json_response({"action": "unsubscribe", "response": None, "note": _UNSUBSCRIBE_NOTE})


@mcp.tool(annotations=_READ_ONLY)
async def prepare_deck(deck_index: int, *, playing: bool = True, speed: float | None = None) -> str:
    """Placeholder: deck transport is not in the validated REST schema, so this reports skipped actions and changes nothing."""
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


@mcp.tool(annotations=_READ_ONLY)
async def prepare_multiple_decks(
    deck_indices_json: str,
    *,
    playing: bool = True,
    speed: float | None = None,
) -> str:
    """Placeholder like prepare_deck for several decks; changes nothing."""
    deck_indices = _parse_json_list(deck_indices_json, field_name="deck_indices_json")
    results: list[dict[str, Any]] = []
    for deck_index in deck_indices:
        payload = json.loads(await prepare_deck(deck_index, playing=playing, speed=speed))
        results.append(payload)
    return _json_response({"deck_count": len(results), "decks": results})


@mcp.tool(annotations=_WRITE)
async def prepare_output_screen(
    screen_index: int,
    *,
    enabled: bool = True,
    slice_opacity: float | None = None,
    unbypass_slices: bool = True,
) -> str:
    """Enable a screen and un-bypass / set opacity on all its slices. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
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


@mcp.tool(annotations=_WRITE)
async def prepare_multiple_output_screens(
    screen_indices_json: str,
    *,
    enabled: bool = True,
    slice_opacity: float | None = None,
    unbypass_slices: bool = True,
) -> str:
    """prepare_output_screen for several screens; screen_indices_json is a JSON array. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
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


@mcp.tool(annotations=_READ_ONLY)
async def audit_show_readiness() -> str:
    """Composition audit plus Advanced Output screen audits in one call, with a total finding count."""
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


@mcp.tool(annotations=_READ_ONLY)
async def get_clip_parameter(layer_index: int, clip_index: int, parameter_suffix: str) -> str:
    """Read a clip parameter, e.g. 'transport/position'. parameter_suffix is the path inside the scope's REST payload, e.g. 'video/opacity' or 'bypassed'."""
    aliases = ("transport/controls/speed",) if parameter_suffix.strip() == "transport/speed" else ()
    return await _parameter_tool_impl(f"/composition/layers/{layer_index}/clips/{clip_index}", "get", parameter_suffix, aliases=aliases)


@mcp.tool(annotations=_WRITE)
async def set_clip_parameter(layer_index: int, clip_index: int, parameter_suffix: str, value_json: str) -> str:
    """Set a clip parameter; value_json is a JSON value. Verifies by reading the value back over REST (value_before, value_after, verified)."""
    aliases = ("transport/controls/speed",) if parameter_suffix.strip() == "transport/speed" else ()
    return await _parameter_tool_impl(f"/composition/layers/{layer_index}/clips/{clip_index}", "set", parameter_suffix, value=_parse_json(value_json), aliases=aliases)


@mcp.tool(annotations=_READ_ONLY)
async def subscribe_clip_parameter(layer_index: int, clip_index: int, parameter_suffix: str, duration_s: float = 2.0) -> str:
    """Watch a clip parameter, e.g. transport/position while playing. Subscribes for duration_s seconds (max 30) on one connection and returns the updates received."""
    aliases = ("transport/controls/speed",) if parameter_suffix.strip() == "transport/speed" else ()
    return await _parameter_tool_impl(f"/composition/layers/{layer_index}/clips/{clip_index}", "subscribe", parameter_suffix, aliases=aliases, duration_s=duration_s)


@mcp.tool(annotations=_READ_ONLY)
async def unsubscribe_clip_parameter(layer_index: int, clip_index: int, parameter_suffix: str) -> str:
    """No-op kept for compatibility: subscriptions end automatically when the subscribe call returns."""
    aliases = ("transport/controls/speed",) if parameter_suffix.strip() == "transport/speed" else ()
    return await _parameter_tool_impl(f"/composition/layers/{layer_index}/clips/{clip_index}", "unsubscribe", parameter_suffix, aliases=aliases)


@mcp.tool(annotations=_WRITE)
async def trigger_clip(layer_index: int, clip_index: int) -> str:
    """Trigger (connect) a clip so it plays on its layer."""
    result = await _client().request("POST", f"/composition/layers/{layer_index}/clips/{clip_index}/connect")
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def trigger_selected_clip() -> str:
    """Trigger the selected clip."""
    result = await _client().request("POST", "/composition/clips/selected/connect")
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def disconnect_clip(layer_index: int, clip_index: int, confirm_destructive: bool = False) -> str:
    """Stop a clip and report before/after state. Arena 7 ignores connect=false, so if the clip is still connected this clears its layer instead (only that clip stops; media stays in the slot). Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("disconnect_clip", f"This will disconnect clip {clip_index} on layer {layer_index}. Re-call with confirm_destructive=True to proceed.")
    return _json_response(await _disconnect_clip(_client(), layer_index, clip_index))


@mcp.tool(annotations=_DESTRUCTIVE)
async def disconnect_selected_clip(confirm_destructive: bool = False) -> str:
    """Disconnect the selected clip and report before/after state. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("disconnect_selected_clip", "This will disconnect the currently selected clip. Re-call with confirm_destructive=True to proceed.")
    client = _client()
    before_payload = await client.request("GET", "/composition/clips/selected")
    before_state = _extract_body(before_payload).get("connected", {}).get("value") if isinstance(_extract_body(before_payload), dict) else None
    if isinstance(before_state, str) and not _is_connected(before_state):
        return _json_response({"response": None, "before_state": before_state, "after_state": before_state, "disconnected": True, "note": "Selected clip was not playing; nothing was sent."})
    response = await client.request("POST", "/composition/clips/selected/connect", body=False)
    after_payload = await client.request("GET", "/composition/clips/selected")
    after_state = _extract_body(after_payload).get("connected", {}).get("value") if isinstance(_extract_body(after_payload), dict) else None
    disconnected = after_state in {"Disconnected", "Empty"}
    return _json_response(
        {
            "response": response,
            "before_state": before_state,
            "after_state": after_state,
            "disconnected": disconnected,
            "note": None if disconnected else "Selected clip remained connected after disconnect request on this Resolume build.",
        }
    )


@mcp.tool(annotations=_DESTRUCTIVE)
async def clear_clip(layer_index: int, clip_index: int, confirm_destructive: bool = False) -> str:
    """Remove a clip's media and verify the slot empties. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("clear_clip", f"This will clear clip {clip_index} on layer {layer_index}, removing its media. Re-call with confirm_destructive=True to proceed.")
    client = _client()
    before = await _clip_material_state(client, layer_index, clip_index)
    response = await client.request("POST", f"/composition/layers/{layer_index}/clips/{clip_index}/clear")
    after = await _poll_clip_material_state(client, layer_index=layer_index, clip_index=clip_index)
    cleared = _clip_material_state_cleared(after)
    return _json_response(
        {
            "layer_index": layer_index,
            "clip_index": clip_index,
            "response": response,
            "before_state": {
                "connected": before["connected"],
                "name": before["name"],
                "has_video": before["has_video"],
                "has_audio": before["has_audio"],
            },
            "after_state": {
                "connected": after["connected"],
                "name": after["name"],
                "has_video": after["has_video"],
                "has_audio": after["has_audio"],
            },
            "cleared": cleared,
            "note": None if cleared else "Clip retained media state after clear request on this Resolume build.",
        }
    )


@mcp.tool(annotations=_DESTRUCTIVE)
async def clear_selected_clip(confirm_destructive: bool = False) -> str:
    """Remove the selected clip's media and verify. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("clear_selected_clip", "This will clear the currently selected clip, removing its media. Re-call with confirm_destructive=True to proceed.")
    client = _client()
    selected_payload = await client.request("GET", "/composition/clips/selected")
    selected_body = _extract_body(selected_payload)
    clip_id = selected_body.get("id") if isinstance(selected_body, dict) else None
    before_state = None
    if isinstance(selected_body, dict):
        before_state = {
            "connected": selected_body.get("connected", {}).get("value") if isinstance(selected_body.get("connected"), dict) else None,
            "name": selected_body.get("name", {}).get("value") if isinstance(selected_body.get("name"), dict) else selected_body.get("name"),
            "has_video": isinstance(selected_body.get("video"), dict),
            "has_audio": isinstance(selected_body.get("audio"), dict),
        }
    response = await client.request("POST", "/composition/clips/selected/clear")
    after_state = None
    cleared = None
    note = None
    if isinstance(clip_id, int):
        after = await _poll_selected_clip_material_state_by_id(client, clip_id=clip_id)
        after_state = {
            "connected": after["connected"],
            "name": after["name"],
            "has_video": after["has_video"],
            "has_audio": after["has_audio"],
        }
        cleared = _clip_material_state_cleared(after)
        note = None if cleared else "Selected clip retained media state after clear request on this Resolume build."
    return _json_response(
        {
            "clip_id": clip_id,
            "response": response,
            "before_state": before_state,
            "after_state": after_state,
            "cleared": cleared,
            "note": note,
        }
    )


@mcp.tool(annotations=_WRITE)
async def trigger_column(column_index: int) -> str:
    """Trigger (connect) a column, launching its clip on every layer."""
    result = await _client().request("POST", f"/composition/columns/{column_index}/connect")
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def disconnect_column(column_index: int, confirm_destructive: bool = False) -> str:
    """Disconnect a column via connect=false, which Arena 7 ignores for clips; check the result with get_composition_summary. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("disconnect_column", f"This will disconnect column {column_index}. Re-call with confirm_destructive=True to proceed.")
    result = await _client().request("POST", f"/composition/columns/{column_index}/connect", body=False)
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_group_column(group_index: int, column_index: int) -> str:
    """Read a group column. Returned 404 on the validated build."""
    result = await _client().request("GET", f"/composition/layergroups/{group_index}/columns/{column_index}")
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def trigger_group_column(group_index: int, column_index: int) -> str:
    """Trigger a column within one group. Returned 404 on the validated build."""
    result = await _client().request("POST", f"/composition/layergroups/{group_index}/columns/{column_index}/connect")
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def select_group_column(group_index: int, column_index: int) -> str:
    """Select a column within one group. Returned 404 on the validated build."""
    result = await _client().request("POST", f"/composition/layergroups/{group_index}/columns/{column_index}/select")
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def select_clip(layer_index: int, clip_index: int) -> str:
    """Select a clip via WebSocket set on its 'selected' path. Not live-verified."""
    result = await _client().websocket_action(
        "set",
        f"/composition/layers/{layer_index}/clips/{clip_index}/selected",
        value=True,
    )
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def clear_layer(layer_index: int, confirm_destructive: bool = False) -> str:
    """Clear a layer: stops what is playing on the layer (disconnects its active clip); the clips stay in their slots. Use clear_layer_clips to remove the clips themselves. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("clear_layer", f"This will stop playback on layer {layer_index} (its playing clip is disconnected; clips stay in their slots). Re-call with confirm_destructive=True to proceed.")
    result = await _client().request("POST", f"/composition/layers/{layer_index}/clear")
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def clear_selected_layer(confirm_destructive: bool = False) -> str:
    """Clear the selected layer: stops what is playing on the layer (disconnects its active clip); the clips stay in their slots. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("clear_selected_layer", "This will stop playback on the selected layer (its playing clip is disconnected; clips stay in their slots). Re-call with confirm_destructive=True to proceed.")
    result = await _client().request("POST", "/composition/layers/selected/clear")
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def clear_layer_clips(layer_index: int, confirm_destructive: bool = False) -> str:
    """Remove all clips from a layer and verify the first slot empties. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("clear_layer_clips", f"This will clear all clips on layer {layer_index}. Re-call with confirm_destructive=True to proceed.")
    client = _client()
    # Determine if the layer has clips before verifying state
    layer_payload = await client.request("GET", f"/composition/layers/{layer_index}")
    layer_body = _extract_body(layer_payload)
    has_clips = isinstance(layer_body, dict) and isinstance(layer_body.get("clips"), list) and len(layer_body["clips"]) > 0
    empty_state = {"connected": None, "name": None, "has_video": None, "has_audio": None}
    if has_clips:
        before = await _clip_material_state(client, layer_index, 1)
    else:
        before = empty_state
    response = await client.request("POST", f"/composition/layers/{layer_index}/clearclips")
    if has_clips:
        after = await _poll_clip_material_state(client, layer_index=layer_index, clip_index=1)
        cleared = _clip_material_state_cleared(after)
    else:
        after = empty_state
        cleared = True
    return _json_response(
        {
            "layer_index": layer_index,
            "response": response,
            "before_state": {
                "connected": before.get("connected"),
                "name": before.get("name"),
                "has_video": before.get("has_video"),
                "has_audio": before.get("has_audio"),
            },
            "after_state": {
                "connected": after.get("connected"),
                "name": after.get("name"),
                "has_video": after.get("has_video"),
                "has_audio": after.get("has_audio"),
            },
            "cleared": cleared,
            "note": None if cleared else "Layer retained clip media state after clearclips request on this Resolume build.",
        }
    )


@mcp.tool(annotations=_DESTRUCTIVE)
async def clear_selected_layer_clips(confirm_destructive: bool = False) -> str:
    """Remove all clips from the selected layer. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("clear_selected_layer_clips", "This will clear all clips on the selected layer. Re-call with confirm_destructive=True to proceed.")
    client = _client()
    before = await _selected_layer_first_clip_material_state(client)
    response = await client.request("POST", "/composition/layers/selected/clearclips")
    after = await _poll_selected_layer_first_clip_material_state(client)
    cleared = _clip_material_state_cleared(after)
    return _json_response(
        {
            "response": response,
            "before_state": {
                "connected": before["connected"],
                "name": before["name"],
                "has_video": before["has_video"],
                "has_audio": before["has_audio"],
            },
            "after_state": {
                "connected": after["connected"],
                "name": after["name"],
                "has_video": after["has_video"],
                "has_audio": after["has_audio"],
            },
            "cleared": cleared,
            "note": None if cleared else "Selected layer retained clip media state after clearclips request on this Resolume build.",
        }
    )


@mcp.tool(annotations=_DESTRUCTIVE)
async def clear_composition(confirm_destructive: bool = False) -> str:
    """Clear all media from the entire composition. Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("clear_composition", "This will clear the ENTIRE composition, removing all media from all layers. Re-call with confirm_destructive=True to proceed.")
    result = await _client().request("POST", "/composition/clear")
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def select_layer(layer_index: int) -> str:
    """Select a layer via WebSocket set on its 'selected' path. Not live-verified."""
    result = await _client().websocket_action(
        "set",
        f"/composition/layers/{layer_index}/selected",
        value=True,
    )
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def select_column(column_index: int) -> str:
    """Select a column via WebSocket set on its 'selected' path. Not live-verified."""
    result = await _client().websocket_action(
        "set",
        f"/composition/columns/{column_index}/selected",
        value=True,
    )
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def select_group(group_index: int) -> str:
    """Select a layer group."""
    result = await _client().request("POST", f"/composition/layergroups/{group_index}/select")
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def duplicate_selected_layer(body_json: str = "") -> str:
    """Duplicate the currently selected layer."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", "/composition/layers/selected/duplicate", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def duplicate_selected_group(body_json: str = "") -> str:
    """Duplicate the selected layer group. Selected-group endpoints returned 404 on the validated build."""
    body = _optional_json_object(body_json, field_name="body_json")
    result = await _client().request("POST", "/composition/layergroups/selected/duplicate", body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def select_deck(deck_index: int) -> str:
    """Select (switch to) a deck."""
    result = await _client().request("POST", f"/composition/decks/{deck_index}/select")
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def set_output_parameter(path: str, value_json: str) -> str:
    """Set a parameter under /advancedoutput (fire-and-forget). Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    return await _output_websocket_tool_impl("set", _normalize_output_path(path), value=_parse_json(value_json))


@mcp.tool(annotations=_READ_ONLY)
async def get_output_parameter(path: str) -> str:
    """Read a parameter under /advancedoutput over WebSocket. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    return await _output_websocket_tool_impl("get", _normalize_output_path(path))


@mcp.tool(annotations=_WRITE)
async def trigger_output_action(path: str) -> str:
    """Trigger an action under /advancedoutput. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    return await _output_websocket_tool_impl("trigger", _normalize_output_path(path))


@mcp.tool(annotations=_WRITE)
async def reset_output_parameter(path: str) -> str:
    """Reset a parameter under /advancedoutput. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    return await _output_websocket_tool_impl("reset", _normalize_output_path(path))


@mcp.tool(annotations=_READ_ONLY)
async def subscribe_output_parameter(path: str, duration_s: float = 2.0) -> str:
    """Watch a parameter under /advancedoutput. Subscribes for duration_s seconds (max 30) on one connection and returns the updates received. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    return await _output_watch_tool_impl(_normalize_output_path(path), duration_s)


@mcp.tool(annotations=_READ_ONLY)
async def unsubscribe_output_parameter(path: str) -> str:
    """No-op kept for compatibility: subscriptions end automatically when the subscribe call returns."""
    return _output_unsubscribe_note(_normalize_output_path(path))


@mcp.tool(annotations=_READ_ONLY)
async def subscribe_output_screen_parameter(screen_index: int, parameter_suffix: str, duration_s: float = 2.0) -> str:
    """Watch a screen parameter. Subscribes for duration_s seconds (max 30) on one connection and returns the updates received. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    return await _output_watch_tool_impl(_join_parameter_path(f"/advancedoutput/screens/{screen_index}", parameter_suffix), duration_s)


@mcp.tool(annotations=_READ_ONLY)
async def unsubscribe_output_screen_parameter(screen_index: int, parameter_suffix: str) -> str:
    """No-op kept for compatibility: subscriptions end automatically when the subscribe call returns."""
    return _output_unsubscribe_note(_join_parameter_path(f"/advancedoutput/screens/{screen_index}", parameter_suffix))


@mcp.tool(annotations=_READ_ONLY)
async def subscribe_output_slice_parameter(screen_index: int, slice_index: int, parameter_suffix: str, duration_s: float = 2.0) -> str:
    """Watch a slice parameter. Subscribes for duration_s seconds (max 30) on one connection and returns the updates received. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    return await _output_watch_tool_impl(_join_parameter_path(f"/advancedoutput/screens/{screen_index}/slices/{slice_index}", parameter_suffix), duration_s)


@mcp.tool(annotations=_READ_ONLY)
async def unsubscribe_output_slice_parameter(screen_index: int, slice_index: int, parameter_suffix: str) -> str:
    """No-op kept for compatibility: subscriptions end automatically when the subscribe call returns."""
    return _output_unsubscribe_note(_join_parameter_path(f"/advancedoutput/screens/{screen_index}/slices/{slice_index}", parameter_suffix))


@mcp.tool(annotations=_WRITE)
async def set_layer_opacity(layer_index: int, opacity: float) -> str:
    """Set layer opacity (0.0-1.0). Verifies by reading the value back over REST (value_before, value_after, verified)."""
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path=f"/composition/layers/{layer_index}",
        parameter_suffix="video/opacity",
        value=opacity,
    )
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def set_param(parameter: str, value_json: str, confirm_destructive: bool = False) -> str:
    """Set any parameter path over WebSocket (fire-and-forget). Prefer named set_* tools, which verify. Calls matching a destructive pattern (clear, disconnect-all, DELETE, ...) need confirm_destructive=True."""
    value = _parse_json(value_json)
    if gate := _generic_gate("set_param", "set", parameter, value, confirm_destructive):
        return gate
    result = await _client().websocket_action("set", parameter, value=value)
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def trigger_param(parameter: str, confirm_destructive: bool = False) -> str:
    """Trigger any parameter or action path over WebSocket. Calls matching a destructive pattern (clear, disconnect-all, DELETE, ...) need confirm_destructive=True."""
    if gate := _generic_gate("trigger_param", "trigger", parameter, None, confirm_destructive):
        return gate
    result = await _client().websocket_action("trigger", parameter)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def reset_param(parameter: str) -> str:
    """Reset any parameter path to its default over WebSocket."""
    result = await _client().websocket_action("reset", parameter)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def bypass_layer(layer_index: int, bypassed: bool = True) -> str:
    """Bypass (hide) or un-bypass a layer. Verifies by reading the value back over REST (value_before, value_after, verified)."""
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path=f"/composition/layers/{layer_index}",
        parameter_suffix="bypassed",
        value=bypassed,
    )
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def set_clip_transport_position(layer_index: int, clip_index: int, position: float) -> str:
    """Set clip playhead position. Read-back verification can report false while the clip is playing, because the position keeps moving."""
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path=f"/composition/layers/{layer_index}/clips/{clip_index}",
        parameter_suffix="transport/position",
        value=position,
    )
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def set_clip_speed(layer_index: int, clip_index: int, speed: float) -> str:
    """Set clip playback speed (1.0 = normal). Verifies by reading the value back over REST (value_before, value_after, verified)."""
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


@mcp.tool(annotations=_WRITE)
async def set_output_screen_enabled(screen_index: int, enabled: bool = True) -> str:
    """Enable or disable an output screen. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    result = await _client().websocket_action(
        "set",
        f"/advancedoutput/screens/{screen_index}/enabled",
        value=enabled,
    )
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def set_output_slice_bypassed(screen_index: int, slice_index: int, bypassed: bool = True) -> str:
    """Bypass or un-bypass a slice. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    result = await _client().websocket_action(
        "set",
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}/bypassed",
        value=bypassed,
    )
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def set_output_slice_input(screen_index: int, slice_index: int, input_path: str) -> str:
    """Route a slice to an input path, e.g. '/composition/layers/3'. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    result = await _client().websocket_action(
        "set",
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}/input",
        value=input_path,
    )
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def set_output_slice_opacity(screen_index: int, slice_index: int, opacity: float) -> str:
    """Set slice opacity (0.0-1.0). Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    result = await _client().websocket_action(
        "set",
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}/opacity",
        value=opacity,
    )
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def set_composition_bpm(bpm: float) -> str:
    """Set the composition tempo in BPM. Verifies by reading the value back over REST (value_before, value_after, verified)."""
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path="/composition",
        parameter_suffix="tempocontroller/tempo",
        value=bpm,
    )
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def set_composition_playing(playing: bool = True) -> str:
    """Set composition transport playing. The validated build does not expose transport/playing, so this usually returns skipped."""
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


@mcp.tool(annotations=_WRITE)
async def bypass_clip(layer_index: int, clip_index: int, bypassed: bool = True) -> str:
    """Bypass or un-bypass a clip. Verifies by reading the value back over REST (value_before, value_after, verified)."""
    client = _client()
    result = await _parameter_action(
        client,
        action="set",
        rest_path=f"/composition/layers/{layer_index}/clips/{clip_index}",
        parameter_suffix="bypassed",
        value=bypassed,
    )
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def set_deck_parameter(deck_index: int, parameter_suffix: str, value_json: str) -> str:
    """Set a deck parameter; value_json is a JSON value. Verifies by reading the value back over REST (value_before, value_after, verified)."""
    return await _parameter_tool_impl(f"/composition/decks/{deck_index}", "set", parameter_suffix, value=_parse_json(value_json))


@mcp.tool(annotations=_READ_ONLY)
async def get_deck_parameter(deck_index: int, parameter_suffix: str) -> str:
    """Read a deck parameter. parameter_suffix is the path inside the scope's REST payload, e.g. 'video/opacity' or 'bypassed'."""
    return await _parameter_tool_impl(f"/composition/decks/{deck_index}", "get", parameter_suffix)


@mcp.tool(annotations=_DESTRUCTIVE)
async def trigger_deck_action(deck_index: int, parameter_suffix: str, confirm_destructive: bool = False) -> str:
    """Trigger an action path under a deck, e.g. 'select'. Calls matching a destructive pattern (clear, disconnect-all, DELETE, ...) need confirm_destructive=True."""
    path = _join_parameter_path(f"/composition/decks/{deck_index}", parameter_suffix)
    if gate := _generic_gate("trigger_deck_action", "trigger", path, None, confirm_destructive):
        return gate
    result = await _client().websocket_action("trigger", path)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def reset_deck_parameter(deck_index: int, parameter_suffix: str) -> str:
    """Reset a deck parameter to its default."""
    path = _join_parameter_path(f"/composition/decks/{deck_index}", parameter_suffix)
    result = await _client().websocket_action("reset", path)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def add_effect(
    scope: str,
    effect_kind: str,
    effect_spec: str,
    *,
    effect_index: int | None = None,
    layer_index: int | None = None,
    group_index: int | None = None,
    clip_index: int | None = None,
) -> str:
    """Add an effect by URI using its display name, e.g. 'effect:///video/AR IMAG' (encoded automatically); effect_kind is audio or video. scope: composition, layer, selected-layer, group, selected-group, clip or selected-clip (pass layer_index/group_index/clip_index as the scope needs)."""
    base = _effect_scope_path(scope, index=group_index, layer_index=layer_index, clip_index=clip_index)
    kind = _effect_kind_path(effect_kind)
    path = f"{base}/effects/{kind}/add"
    if effect_index is not None:
        path = f"{path}/{effect_index}"
    effect_spec = effect_spec.strip()
    if not effect_spec:
        raise ValueError("effect_spec is required and must be a non-empty effect URI like effect:///video/Blow.")
    result = await _client().request("POST", path, body=_encode_resolume_uri(effect_spec))
    return _json_response(result)


@mcp.tool(annotations=_DESTRUCTIVE)
async def remove_effect(
    scope: str,
    effect_kind: str,
    effect_index: int,
    *,
    layer_index: int | None = None,
    group_index: int | None = None,
    clip_index: int | None = None,
    confirm_destructive: bool = False,
) -> str:
    """Remove the effect at effect_index (1-based). scope: composition, layer, selected-layer, group, selected-group, clip or selected-clip (pass layer_index/group_index/clip_index as the scope needs). Destructive: without confirm_destructive=True it only returns a confirmation request."""
    if not confirm_destructive:
        return _confirmation_required("remove_effect", f"This will remove effect at index {effect_index} from {scope}. Re-call with confirm_destructive=True to proceed.")
    base = _effect_scope_path(scope, index=group_index, layer_index=layer_index, clip_index=clip_index)
    kind = _effect_kind_path(effect_kind)
    path = f"{base}/effects/{kind}/{effect_index}"
    result = await _client().request("DELETE", path)
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_effect(
    scope: str,
    effect_kind: str,
    effect_index: int,
    *,
    layer_index: int | None = None,
    group_index: int | None = None,
    clip_index: int | None = None,
) -> str:
    """Read the effect at effect_index (1-based) from the scope's payload. scope: composition, layer, selected-layer, group, selected-group, clip or selected-clip (pass layer_index/group_index/clip_index as the scope needs)."""
    base = _effect_scope_path(scope, index=group_index, layer_index=layer_index, clip_index=clip_index)
    kind = _effect_kind_path(effect_kind)
    client = _client()
    scope_payload = await client.request("GET", base)
    try:
        effect = _extract_effect_from_scope_payload(scope_payload, kind, effect_index)
        payload: dict[str, Any] = {
            "ok": True,
            "path": f"/api/v1{base}/effects/{kind}/{effect_index}",
            "scope_path": scope_payload.get("path", base),
            "fallback_used": True,
            "effect_kind": kind,
            "effect_index": effect_index,
            "body": effect,
            "scope_payload": scope_payload,
        }
    except Exception as exc:
        payload = {
            "ok": False,
            "path": f"/api/v1{base}/effects/{kind}/{effect_index}",
            "scope_path": scope_payload.get("path", base),
            "fallback_used": True,
            "effect_kind": kind,
            "effect_index": effect_index,
            "error": str(exc),
            "scope_payload": scope_payload,
        }
    return _json_response(payload)


@mcp.tool(annotations=_WRITE)
async def move_video_effect(
    scope: str,
    body_json: str,
    *,
    effect_index: int | None = None,
    layer_index: int | None = None,
    group_index: int | None = None,
    clip_index: int | None = None,
) -> str:
    """Move a video effect; body_json (JSON object) is passed to effects/video/move. scope: composition, layer, selected-layer, group, selected-group, clip or selected-clip (pass layer_index/group_index/clip_index as the scope needs)."""
    body = _optional_json_object(body_json, field_name="body_json")
    base = _effect_scope_path(scope, index=group_index, layer_index=layer_index, clip_index=clip_index)
    path = f"{base}/effects/video/move"
    if effect_index is not None:
        path = f"{path}/{effect_index}"
    result = await _client().request("POST", path, body=body)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def rename_effect(
    scope: str,
    effect_kind: str,
    effect_index: int,
    display_name: str,
    *,
    layer_index: int | None = None,
    group_index: int | None = None,
    clip_index: int | None = None,
) -> str:
    """Set an effect's display name. scope: composition, layer, selected-layer, group, selected-group, clip or selected-clip (pass layer_index/group_index/clip_index as the scope needs)."""
    base = _effect_scope_path(scope, index=group_index, layer_index=layer_index, clip_index=clip_index)
    kind = _effect_kind_path(effect_kind)
    result = await _client().request(
        "POST",
        f"{base}/effects/{kind}/{effect_index}/set-display-name",
        body={"displayName": display_name},
    )
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def set_output_screen_parameter(screen_index: int, parameter_suffix: str, value_json: str) -> str:
    """Set a screen parameter; value_json is a JSON value. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    value = _parse_json(value_json)
    path = _join_parameter_path(f"/advancedoutput/screens/{screen_index}", parameter_suffix)
    result = await _client().websocket_action("set", path, value=value)
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_output_screen_parameter(screen_index: int, parameter_suffix: str) -> str:
    """Read a screen parameter, e.g. 'enabled'. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    path = _join_parameter_path(f"/advancedoutput/screens/{screen_index}", parameter_suffix)
    result = await _client().websocket_action("get", path)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def trigger_output_screen_action(screen_index: int, parameter_suffix: str) -> str:
    """Trigger a screen action. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    path = _join_parameter_path(f"/advancedoutput/screens/{screen_index}", parameter_suffix)
    result = await _client().websocket_action("trigger", path)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def set_output_slice_parameter(
    screen_index: int,
    slice_index: int,
    parameter_suffix: str,
    value_json: str,
) -> str:
    """Set a slice parameter; value_json is a JSON value. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    value = _parse_json(value_json)
    path = _join_parameter_path(
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}",
        parameter_suffix,
    )
    result = await _client().websocket_action("set", path, value=value)
    return _json_response(result)


@mcp.tool(annotations=_READ_ONLY)
async def get_output_slice_parameter(screen_index: int, slice_index: int, parameter_suffix: str) -> str:
    """Read a slice parameter, e.g. 'opacity'. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    path = _join_parameter_path(
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}",
        parameter_suffix,
    )
    result = await _client().websocket_action("get", path)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def trigger_output_slice_action(screen_index: int, slice_index: int, parameter_suffix: str) -> str:
    """Trigger a slice action. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    path = _join_parameter_path(
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}",
        parameter_suffix,
    )
    result = await _client().websocket_action("trigger", path)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
async def reset_output_slice_parameter(screen_index: int, slice_index: int, parameter_suffix: str) -> str:
    """Reset a slice parameter. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    path = _join_parameter_path(
        f"/advancedoutput/screens/{screen_index}/slices/{slice_index}",
        parameter_suffix,
    )
    result = await _client().websocket_action("reset", path)
    return _json_response(result)


@mcp.tool(annotations=_WRITE)
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
    """Set any of a slice's corner x/y coordinates. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
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


@mcp.tool(annotations=_WRITE)
async def set_output_screen_transform(
    screen_index: int,
    *,
    x: float | None = None,
    y: float | None = None,
    width: float | None = None,
    height: float | None = None,
    rotation: float | None = None,
) -> str:
    """Set screen position, size or rotation (only the values given). Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
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


@mcp.tool(annotations=_WRITE)
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
    """Set slice position, size or rotation (only the values given). Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
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


@mcp.tool(annotations=_WRITE)
async def batch_set_output_screen_parameter(
    screen_indices_json: str,
    parameter_suffix: str,
    value_json: str,
) -> str:
    """Set one parameter on several screens; screen_indices_json is a JSON array. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    screen_indices = _parse_json_list(screen_indices_json, field_name="screen_indices_json")
    value = _parse_json(value_json)
    updates: list[dict[str, Any]] = []
    for screen_index in screen_indices:
        path = _join_parameter_path(f"/advancedoutput/screens/{screen_index}", parameter_suffix)
        response = await _client().websocket_action("set", path, value=value)
        updates.append({"screen_index": screen_index, "parameter": path, "value": value, "response": response})
    return _json_response({"updates": updates})


@mcp.tool(annotations=_WRITE)
async def batch_set_output_slice_parameter(
    screen_index: int,
    slice_indices_json: str,
    parameter_suffix: str,
    value_json: str,
) -> str:
    """Set one parameter on several slices of a screen; slice_indices_json is a JSON array. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
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


@mcp.tool(annotations=_WRITE)
async def batch_set_output_slice_opacity(
    screen_index: int,
    slice_indices_json: str,
    opacity: float,
) -> str:
    """Set opacity on several slices. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    return await batch_set_output_slice_parameter(
        screen_index,
        slice_indices_json,
        "opacity",
        json.dumps(opacity),
    )


@mcp.tool(annotations=_WRITE)
async def batch_set_output_slice_bypassed(
    screen_index: int,
    slice_indices_json: str,
    bypassed: bool = True,
) -> str:
    """Bypass or un-bypass several slices. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
    return await batch_set_output_slice_parameter(
        screen_index,
        slice_indices_json,
        "bypassed",
        json.dumps(bypassed),
    )


@mcp.tool(annotations=_WRITE)
async def route_output_slices(screen_index: int, routes_json: str) -> str:
    """Route several slices: routes_json is [{"slice_index":0,"input_path":"/composition/layers/1"}]. Experimental: the validated Resolume build does not expose Advanced Output over HTTP (404)."""
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
                "Use REST for composition-tree inspection and many structural operations; named parameter reads come straight from the REST payload.",
                "Use WebSocket verbs for parameter set/trigger/reset. Only get and subscribe wait for a reply (bounded by a timeout); subscriptions last for the duration_s of the call.",
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
