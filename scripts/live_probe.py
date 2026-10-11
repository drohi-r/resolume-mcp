"""Live validation probe for a running Resolume instance.

    uv run python scripts/live_probe.py                 # read-only checks
    uv run python scripts/live_probe.py --write-checks  # also reversible writes (opacity, selection)

Run --write-checks only against a test composition, never a live show: it briefly changes
layer 1 opacity (then restores it) and moves the layer/clip selection, leaving layer 1 / clip 1 selected.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from typing import Any

from resolume_mcp.client import ResolumeClient
from resolume_mcp.config import load_config
from resolume_mcp.server import _lookup_parameter_node, _verify_parameter_value


def show(title: str, payload: Any) -> None:
    print(f"\n== {title}")
    print(json.dumps(payload, indent=2, default=str)[:1500])


def summarize_message(message: Any) -> Any:
    if isinstance(message, dict):
        return {key: message[key] for key in list(message)[:8]}
    return message


async def read_checks(client: ResolumeClient) -> None:
    for name, path in [
        ("product", "/product"),
        ("composition", "/composition"),
        ("layer_1", "/composition/layers/1"),
        ("column_1", "/composition/columns/1"),
        ("deck_1", "/composition/decks/1"),
        ("selected_layer", "/composition/layers/selected"),
        ("selected_clip", "/composition/clips/selected"),
    ]:
        payload = await client.request("GET", path)
        show(f"rest {name}", {"status_code": payload["status_code"], "ok": payload["ok"], "body_type": type(payload["body"]).__name__})

    layer = await client.request("GET", "/composition/layers/1")
    opacity_id = _lookup_parameter_node(layer, "video/opacity")["node"]["id"]
    parameter = f"/parameter/by-id/{opacity_id}"

    reply = await client.websocket_action("get", parameter)
    show("websocket get layer 1 opacity (is the reply matched?)", {
        "reply_timed_out": reply["reply_timed_out"],
        "skipped_message_count": reply["skipped_message_count"],
        "bootstrap_message_count": reply["bootstrap_message_count"],
        "reply": summarize_message(reply["response"]),
    })

    watch = await client.websocket_watch([parameter], duration_s=1.5)
    show("websocket watch layer 1 opacity for 1.5 s (message format)", {
        "update_count": watch["update_count"],
        "unmatched_message_count": watch["unmatched_message_count"],
        "first_update": summarize_message(next(iter(watch["updates"][parameter]), None)),
    })


async def selected_id(client: ResolumeClient, path: str) -> Any:
    body = (await client.request("GET", path))["body"]
    return body.get("id") if isinstance(body, dict) else None


SELECT_METHODS = {
    "websocket set <path>/selected": lambda client, path, kind, obj_id: client.websocket_action("set", f"{path}/selected", value=True),
    "rest POST <path>/select": lambda client, path, kind, obj_id: client.request("POST", f"{path}/select"),
    "websocket trigger by-id/select": lambda client, path, kind, obj_id: client.websocket_action("trigger", f"/composition/{kind}/by-id/{obj_id}/select"),
}


async def object_id(client: ResolumeClient, path: str) -> Any:
    body = (await client.request("GET", path))["body"]
    return body.get("id") if isinstance(body, dict) else None


async def select_with_every_method(client: ResolumeClient, path: str, kind: str, obj_id: Any) -> None:
    for method in SELECT_METHODS.values():
        try:
            await method(client, path, kind, obj_id)
        except Exception:
            pass
    await asyncio.sleep(0.3)


async def try_select_methods(client: ResolumeClient, kind: str, home_path: str, target_path: str, selected_path: str) -> None:
    """Report which selection method actually moves the selection from home_path to target_path."""
    home_id = await object_id(client, home_path)
    target_id = await object_id(client, target_path)
    results: dict[str, Any] = {}
    for name, method in SELECT_METHODS.items():
        await select_with_every_method(client, home_path, kind, home_id)
        if await selected_id(client, selected_path) != home_id:
            results[name] = "inconclusive: could not reset selection to the home object"
            continue
        try:
            await method(client, target_path, kind, target_id)
            await asyncio.sleep(0.3)
            results[name] = (await selected_id(client, selected_path)) == target_id
        except Exception as exc:
            results[name] = f"error: {exc}"
    await select_with_every_method(client, home_path, kind, home_id)
    show(f"select {target_path} (True = selection moved; ends selected on {home_path})", {"home_id": home_id, "target_id": target_id, "results": results})


async def write_checks(client: ResolumeClient) -> None:
    layer = await client.request("GET", "/composition/layers/1")
    node = _lookup_parameter_node(layer, "video/opacity")["node"]
    parameter = f"/parameter/by-id/{node['id']}"
    current = node.get("value")
    probe_value = 0.5 if current != 0.5 else 0.6
    # Send exactly once (no server-side retry) so a set dropped by the immediate close shows up as unverified.
    await client.websocket_action("set", parameter, value=probe_value)
    changed = await _verify_parameter_value(client, "/composition/layers/1", "video/opacity", probe_value)
    await client.websocket_action("set", parameter, value=current)
    restored = await _verify_parameter_value(client, "/composition/layers/1", "video/opacity", current)
    show("websocket set delivery: single send, then restore", {
        "original": current,
        "set_to": probe_value,
        "verified_after_single_set": changed["verified"],
        "value_after_set": changed["value_after"],
        "verified_after_restore": restored["verified"],
    })

    # Needs at least 2 layers and 2 clip slots on layer 1. Columns have no 'selected' endpoint to read
    # back, so they are assumed to follow whichever method works for layers.
    await try_select_methods(client, "layers", "/composition/layers/1", "/composition/layers/2", "/composition/layers/selected")
    await try_select_methods(client, "clips", "/composition/layers/1/clips/1", "/composition/layers/1/clips/2", "/composition/clips/selected")


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--write-checks", action="store_true", help="run reversible write checks (test compositions only)")
    args = parser.parse_args()

    client = ResolumeClient(load_config())
    show("config", {"http_base_url": client.config.http_base_url, "websocket_url": client.config.websocket_url})
    await read_checks(client)
    if args.write_checks:
        await write_checks(client)


if __name__ == "__main__":
    asyncio.run(main())
