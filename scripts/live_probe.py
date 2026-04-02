from __future__ import annotations

import asyncio
import json

from resolume_mcp.client import ResolumeClient
from resolume_mcp.config import load_config


async def main() -> None:
    client = ResolumeClient(load_config())

    print("config")
    print(json.dumps(
        {
            "http_base_url": client.config.http_base_url,
            "websocket_url": client.config.websocket_url,
            "osc_port": client.config.osc_port,
        },
        indent=2,
    ))

    for name, path in [
        ("composition", "/composition"),
        ("layer_1", "/composition/layers/1"),
        ("column_1", "/composition/columns/1"),
        ("deck_1", "/composition/decks/1"),
    ]:
        payload = await client.request("GET", path)
        print(f"\nrest:{name}")
        print(json.dumps(
            {
                "path": payload["path"],
                "status_code": payload["status_code"],
                "ok": payload["ok"],
                "body_type": type(payload["body"]).__name__,
            },
            indent=2,
        ))

    ws_payload = await client.websocket_action("get", "/parameter/by-id/1775109982479")
    print("\nwebsocket:get_parameter_by_id")
    print(json.dumps(
        {
            "bootstrap_count": len(ws_payload["bootstrap"]),
            "response": ws_payload["response"],
        },
        indent=2,
    ))


if __name__ == "__main__":
    asyncio.run(main())
