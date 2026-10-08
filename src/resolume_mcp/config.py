from __future__ import annotations

import os
import sys
import uuid
from dataclasses import dataclass, field
from pathlib import Path

_DEFAULT_ALLOWED_HOSTS = "127.0.0.1,localhost,::1"
_FOLDERID_DOCUMENTS = uuid.UUID("FDD39AD0-238F-46AF-ADB4-6C85480369C7")


def _windows_documents_dir() -> Path | None:
    """The real Documents folder on Windows, which OneDrive often redirects away from ~/Documents."""
    try:
        import ctypes

        folder_id = (ctypes.c_char * 16).from_buffer_copy(_FOLDERID_DOCUMENTS.bytes_le)
        path_ptr = ctypes.c_wchar_p()
        if ctypes.windll.shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(path_ptr)) != 0:
            return None
        try:
            return Path(path_ptr.value) if path_ptr.value else None
        finally:
            ctypes.windll.ole32.CoTaskMemFree(path_ptr)
    except Exception:
        return None


def default_documents_root() -> str:
    documents = _windows_documents_dir() if sys.platform == "win32" else None
    return str((documents or Path.home() / "Documents") / "Resolume Arena")


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
    documents_root: str = field(default_factory=default_documents_root)
    # Empty means "derive from documents_root".
    advanced_output_xml_path: str = ""
    slices_xml_path: str = ""

    def __post_init__(self) -> None:
        preferences = Path(self.documents_root).expanduser() / "Preferences"
        if not self.advanced_output_xml_path:
            object.__setattr__(self, "advanced_output_xml_path", str(preferences / "AdvancedOutput.xml"))
        if not self.slices_xml_path:
            object.__setattr__(self, "slices_xml_path", str(preferences / "slices.xml"))

    @property
    def http_base_url(self) -> str:
        scheme = "https" if self.use_https else "http"
        return f"{scheme}://{self.host}:{self.http_port}"

    @property
    def websocket_url(self) -> str:
        scheme = "wss" if self.use_https else "ws"
        return f"{scheme}://{self.host}:{self.http_port}/api/v1"

    def check_host_allowed(self, host: str | None = None) -> None:
        target = self.host if host is None else host
        if "*" in self.allowed_hosts:
            return
        if target not in self.allowed_hosts:
            raise ValueError(
                f"Host {target!r} is not in RESOLUME_ALLOWED_HOSTS. "
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
        documents_root=os.path.expanduser(os.getenv("RESOLUME_DOCUMENTS_ROOT", "") or default_documents_root()),
        advanced_output_xml_path=os.path.expanduser(os.getenv("RESOLUME_ADVANCED_OUTPUT_XML", "")),
        slices_xml_path=os.path.expanduser(os.getenv("RESOLUME_SLICES_XML", "")),
    )
    config.check_host_allowed()
    return config
