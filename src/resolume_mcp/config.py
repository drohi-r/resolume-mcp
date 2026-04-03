from __future__ import annotations

import os
from dataclasses import dataclass

_DEFAULT_ALLOWED_HOSTS = "127.0.0.1,localhost,::1"


def _parse_port(env_name: str, default: str) -> int:
    raw = os.getenv(env_name, default)
    try:
        port = int(raw)
    except ValueError:
        raise ValueError(f"{env_name}={raw!r} is not a valid integer") from None
    if not (1 <= port <= 65535):
        raise ValueError(f"{env_name}={port} is outside valid port range 1-65535")
    return port


def _parse_bool(env_name: str, default: str) -> bool:
    raw = os.getenv(env_name, default).strip().lower()
    return raw in ("1", "true", "yes")


def _parse_allowed_hosts(raw: str) -> frozenset[str]:
    hosts = frozenset(h.strip() for h in raw.split(",") if h.strip())
    if not hosts:
        raise ValueError("RESOLUME_ALLOWED_HOSTS must contain at least one host")
    return hosts


@dataclass(frozen=True)
class ResolumeConfig:
    host: str = "127.0.0.1"
    http_port: int = 8080
    osc_port: int = 7000
    allowed_hosts: frozenset[str] = frozenset({"127.0.0.1", "localhost", "::1"})
    use_https: bool = False
    documents_root: str = os.path.expanduser("~/Documents/Resolume Arena")
    advanced_output_xml_path: str = os.path.expanduser("~/Documents/Resolume Arena/Preferences/AdvancedOutput.xml")
    slices_xml_path: str = os.path.expanduser("~/Documents/Resolume Arena/Preferences/slices.xml")

    @property
    def http_base_url(self) -> str:
        scheme = "https" if self.use_https else "http"
        return f"{scheme}://{self.host}:{self.http_port}"

    @property
    def websocket_url(self) -> str:
        scheme = "wss" if self.use_https else "ws"
        return f"{scheme}://{self.host}:{self.http_port}/api/v1"

    def check_host_allowed(self) -> None:
        if "*" in self.allowed_hosts:
            return
        if self.host not in self.allowed_hosts:
            raise ValueError(
                f"Host {self.host!r} is not in RESOLUME_ALLOWED_HOSTS. "
                f"Allowed: {', '.join(sorted(self.allowed_hosts))}. "
                f"Set RESOLUME_ALLOWED_HOSTS=* to allow any host."
            )


def load_config() -> ResolumeConfig:
    config = ResolumeConfig(
        host=os.getenv("RESOLUME_HOST", "127.0.0.1"),
        http_port=_parse_port("RESOLUME_HTTP_PORT", "8080"),
        osc_port=_parse_port("RESOLUME_OSC_PORT", "7000"),
        allowed_hosts=_parse_allowed_hosts(os.getenv("RESOLUME_ALLOWED_HOSTS", _DEFAULT_ALLOWED_HOSTS)),
        use_https=_parse_bool("RESOLUME_USE_HTTPS", "0"),
        documents_root=os.getenv("RESOLUME_DOCUMENTS_ROOT", os.path.expanduser("~/Documents/Resolume Arena")),
        advanced_output_xml_path=os.getenv(
            "RESOLUME_ADVANCED_OUTPUT_XML",
            os.path.expanduser("~/Documents/Resolume Arena/Preferences/AdvancedOutput.xml"),
        ),
        slices_xml_path=os.getenv(
            "RESOLUME_SLICES_XML",
            os.path.expanduser("~/Documents/Resolume Arena/Preferences/slices.xml"),
        ),
    )
    config.check_host_allowed()
    return config
