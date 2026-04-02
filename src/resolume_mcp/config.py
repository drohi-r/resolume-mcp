from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class ResolumeConfig:
    host: str = "127.0.0.1"
    http_port: int = 8080
    osc_port: int = 7000
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


def load_config() -> ResolumeConfig:
    return ResolumeConfig(
        host=os.getenv("RESOLUME_HOST", "127.0.0.1"),
        http_port=int(os.getenv("RESOLUME_HTTP_PORT", "8080")),
        osc_port=int(os.getenv("RESOLUME_OSC_PORT", "7000")),
        use_https=os.getenv("RESOLUME_USE_HTTPS", "0") == "1",
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
