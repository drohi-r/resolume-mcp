from __future__ import annotations

import json
import socket
import struct
import asyncio
from dataclasses import dataclass
from typing import Any

import httpx
import websockets

from .config import ResolumeConfig


def normalize_api_path(path: str) -> str:
    path = (path or "").strip()
    if not path:
        raise ValueError("path is required")
    if not path.startswith("/"):
        path = f"/{path}"
    if not path.startswith("/api/"):
        path = f"/api/v1{path}"
    return path


def join_url(base: str, path: str) -> str:
    return f"{base.rstrip('/')}{path}"


@dataclass
class ResolumeClient:
    config: ResolumeConfig

    async def _drain_websocket_bootstrap(self, websocket: Any) -> list[Any]:
        messages: list[Any] = []
        for _ in range(3):
            try:
                raw = await asyncio.wait_for(websocket.recv(), timeout=0.5)
            except TimeoutError:
                break
            try:
                messages.append(json.loads(raw))
            except json.JSONDecodeError:
                messages.append(raw)
        return messages

    async def request(
        self,
        method: str,
        path: str,
        *,
        body: Any = None,
        params: dict[str, Any] | None = None,
        timeout_s: float = 10.0,
    ) -> dict[str, Any]:
        normalized = normalize_api_path(path)
        url = join_url(self.config.http_base_url, normalized)
        request_kwargs: dict[str, Any] = {"params": params}
        if isinstance(body, str):
            request_kwargs["content"] = body
            request_kwargs["headers"] = {"content-type": "text/plain"}
        else:
            request_kwargs["json"] = body

        async with httpx.AsyncClient(timeout=timeout_s) as client:
            response = await client.request(method.upper(), url, **request_kwargs)

        parsed: Any
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            parsed = response.json()
        else:
            parsed = response.text

        return {
            "method": method.upper(),
            "path": normalized,
            "url": url,
            "status_code": response.status_code,
            "ok": response.is_success,
            "content_type": content_type,
            "body": parsed,
        }

    async def websocket_action(
        self,
        action: str,
        parameter: str,
        value: Any = None,
        timeout_s: float = 10.0,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"action": action, "parameter": parameter}
        if value is not None:
            payload["value"] = value

        async with websockets.connect(self.config.websocket_url, open_timeout=timeout_s) as websocket:
            bootstrap = await self._drain_websocket_bootstrap(websocket)
            await websocket.send(json.dumps(payload))
            response: Any = None
            if action not in {"trigger", "reset", "post", "remove"}:
                response = await websocket.recv()

        parsed = None
        if response is not None:
            try:
                parsed = json.loads(response)
            except json.JSONDecodeError:
                parsed = response

        return {
            "url": self.config.websocket_url,
            "bootstrap": bootstrap,
            "request": payload,
            "response": parsed,
        }

    def send_osc(
        self,
        address: str,
        values: list[Any],
        *,
        host: str | None = None,
        port: int | None = None,
    ) -> dict[str, Any]:
        target_host = host or self.config.host
        target_port = port or self.config.osc_port
        packet = build_osc_message(address, values)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.sendto(packet, (target_host, target_port))
        finally:
            sock.close()
        return {
            "address": address,
            "values": values,
            "host": target_host,
            "port": target_port,
            "bytes_sent": len(packet),
        }


def _pad_osc_string(value: str) -> bytes:
    data = value.encode("utf-8") + b"\x00"
    while len(data) % 4 != 0:
        data += b"\x00"
    return data


def build_osc_message(address: str, values: list[Any]) -> bytes:
    if not address.startswith("/"):
        raise ValueError("OSC address must start with '/'.")

    type_tags = ","
    encoded_values = b""

    for value in values:
        if isinstance(value, bool):
            type_tags += "T" if value else "F"
        elif isinstance(value, int):
            type_tags += "i"
            encoded_values += struct.pack(">i", value)
        elif isinstance(value, float):
            type_tags += "f"
            encoded_values += struct.pack(">f", value)
        else:
            type_tags += "s"
            encoded_values += _pad_osc_string(str(value))

    return _pad_osc_string(address) + _pad_osc_string(type_tags) + encoded_values
