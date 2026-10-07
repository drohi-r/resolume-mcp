from __future__ import annotations

import json
import socket
import struct
import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any

import httpx
import websockets

from .config import ResolumeConfig

_BY_ID_PREFIX = "/parameter/by-id/"
# Actions Resolume answers with a message about the parameter; every other action is fire-and-forget.
_REPLY_ACTIONS = frozenset({"get", "subscribe"})


class ResolumeConnectionError(RuntimeError):
    """Resolume could not be reached over HTTP or WebSocket."""


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


def message_matches_parameter(message: Any, parameter: str) -> bool:
    if not isinstance(message, dict):
        return False
    if message.get("path") == parameter:
        return True
    if parameter.startswith(_BY_ID_PREFIX):
        try:
            parameter_id = int(parameter[len(_BY_ID_PREFIX):])
        except ValueError:
            return False
        return message.get("id") == parameter_id
    return False


def _parse_websocket_message(raw: Any) -> Any:
    try:
        return json.loads(raw)
    except (TypeError, json.JSONDecodeError):
        return raw


def _unreachable_message(target: str, exc: BaseException) -> str:
    return (
        f"Could not reach Resolume at {target} ({type(exc).__name__}: {exc}). "
        "Check that Arena/Avenue is running with the web server enabled in Preferences, "
        "and that RESOLUME_HOST and RESOLUME_HTTP_PORT point at it."
    )


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
            messages.append(_parse_websocket_message(raw))
        return messages

    @asynccontextmanager
    async def _websocket(self, timeout_s: float) -> AsyncIterator[Any]:
        try:
            # max_size=None: the bootstrap message is the full composition, which can exceed the 1 MiB default.
            async with websockets.connect(self.config.websocket_url, open_timeout=timeout_s, max_size=None) as websocket:
                yield websocket
        except (OSError, TimeoutError, websockets.InvalidHandshake, websockets.ConnectionClosedError) as exc:
            raise ResolumeConnectionError(_unreachable_message(self.config.websocket_url, exc)) from exc

    async def _await_reply(self, websocket: Any, parameter: str, reply_timeout_s: float) -> tuple[Any, int]:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + reply_timeout_s
        skipped = 0
        while (remaining := deadline - loop.time()) > 0:
            try:
                raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
            except TimeoutError:
                break
            message = _parse_websocket_message(raw)
            if message_matches_parameter(message, parameter):
                return message, skipped
            skipped += 1
        return None, skipped

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

        try:
            async with httpx.AsyncClient(timeout=timeout_s) as client:
                response = await client.request(method.upper(), url, **request_kwargs)
        except httpx.TransportError as exc:
            raise ResolumeConnectionError(_unreachable_message(self.config.http_base_url, exc)) from exc

        parsed: Any
        content_type = response.headers.get("content-type", "")
        if "application/json" in content_type:
            try:
                parsed = response.json()
            except Exception:
                parsed = response.text
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
        reply_timeout_s: float = 2.0,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {"action": action, "parameter": parameter}
        if value is not None:
            payload["value"] = value

        expects_reply = action in _REPLY_ACTIONS
        response: Any = None
        skipped = 0
        async with self._websocket(timeout_s) as websocket:
            bootstrap = await self._drain_websocket_bootstrap(websocket)
            await websocket.send(json.dumps(payload))
            if expects_reply:
                response, skipped = await self._await_reply(websocket, parameter, reply_timeout_s)

        result: dict[str, Any] = {
            "url": self.config.websocket_url,
            "request": payload,
            "response": response,
            "bootstrap_message_count": len(bootstrap),
        }
        if expects_reply:
            result["reply_timed_out"] = response is None
            result["skipped_message_count"] = skipped
        return result

    async def websocket_watch(
        self,
        parameters: list[str],
        duration_s: float = 2.0,
        timeout_s: float = 10.0,
    ) -> dict[str, Any]:
        """Subscribe to parameters on one connection, collect updates for duration_s, then unsubscribe."""
        unique = list(dict.fromkeys(parameters))
        updates: dict[str, list[Any]] = {parameter: [] for parameter in unique}
        unmatched = 0
        async with self._websocket(timeout_s) as websocket:
            bootstrap = await self._drain_websocket_bootstrap(websocket)
            for parameter in unique:
                await websocket.send(json.dumps({"action": "subscribe", "parameter": parameter}))
            loop = asyncio.get_running_loop()
            deadline = loop.time() + duration_s
            while (remaining := deadline - loop.time()) > 0:
                try:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=remaining)
                except TimeoutError:
                    break
                message = _parse_websocket_message(raw)
                matched = next((parameter for parameter in unique if message_matches_parameter(message, parameter)), None)
                if matched is None:
                    unmatched += 1
                else:
                    updates[matched].append(message)
            for parameter in unique:
                await websocket.send(json.dumps({"action": "unsubscribe", "parameter": parameter}))

        return {
            "url": self.config.websocket_url,
            "parameters": unique,
            "duration_s": duration_s,
            "updates": updates,
            "update_count": sum(len(messages) for messages in updates.values()),
            "unmatched_message_count": unmatched,
            "bootstrap_message_count": len(bootstrap),
        }

    def send_osc(
        self,
        address: str,
        values: list[Any],
        *,
        host: str | None = None,
        port: int | None = None,
    ) -> dict[str, Any]:
        if host:
            self.config.check_host_allowed(host)
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
