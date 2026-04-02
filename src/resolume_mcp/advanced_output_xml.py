from __future__ import annotations

import difflib
import shutil
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from xml.etree import ElementTree as ET


def _attr_int(element: ET.Element, name: str) -> int | None:
    value = element.get(name)
    if value is None:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _attr_float(element: ET.Element, name: str) -> float | None:
    value = element.get(name)
    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def _param_value(element: ET.Element, name: str) -> str | float | int | None:
    for param in element.findall("./Params/*"):
        if param.get("name") != name:
            continue
        value = param.get("value")
        if value is None:
            return None
        for caster in (int, float):
            try:
                return caster(value)
            except ValueError:
                continue
        return value
    return None


def _vertices(parent: ET.Element, path: str) -> list[dict[str, float]]:
    node = parent.find(path)
    if node is None:
        return []
    output: list[dict[str, float]] = []
    for vertex in node.findall("./v"):
        x = _attr_float(vertex, "x")
        y = _attr_float(vertex, "y")
        if x is None or y is None:
            continue
        output.append({"x": x, "y": y})
    return output


def _slice_summary(slice_element: ET.Element, *, index: int) -> dict[str, Any]:
    return {
        "slice_index": index,
        "unique_id": slice_element.get("uniqueId"),
        "name": _param_value(slice_element, "Name"),
        "input_rect": _vertices(slice_element, "./InputRect"),
        "output_rect": _vertices(slice_element, "./OutputRect"),
        "bezier_vertices": _vertices(slice_element, "./Warper/BezierWarper/vertices"),
        "homography_src": _vertices(slice_element, "./Warper/Homography/src"),
        "homography_dst": _vertices(slice_element, "./Warper/Homography/dst"),
    }


def _screen_summary(screen_element: ET.Element, *, index: int) -> dict[str, Any]:
    slices_parent = screen_element.find("./layers")
    slice_elements = slices_parent.findall("./Slice") if slices_parent is not None else []
    output_device = screen_element.find("./OutputDevice/*")
    return {
        "screen_index": index,
        "unique_id": screen_element.get("uniqueId"),
        "name": _param_value(screen_element, "Name") or screen_element.get("name"),
        "guide_count": len(screen_element.findall("./guides/*")),
        "slice_count": len(slice_elements),
        "output_device": {
            "type": output_device.tag if output_device is not None else None,
            "name": output_device.get("name") if output_device is not None else None,
            "device_id": output_device.get("deviceId") if output_device is not None else None,
            "width": _attr_int(output_device, "width") if output_device is not None else None,
            "height": _attr_int(output_device, "height") if output_device is not None else None,
        },
        "slices": [_slice_summary(slice_element, index=slice_index) for slice_index, slice_element in enumerate(slice_elements)],
    }


@dataclass(frozen=True)
class AdvancedOutputPreferences:
    path: Path
    raw_xml: str
    root: ET.Element

    @classmethod
    def load(cls, path: str | Path) -> "AdvancedOutputPreferences":
        resolved = Path(path).expanduser()
        raw_xml = resolved.read_text(encoding="utf-8")
        root = ET.fromstring(raw_xml)
        return cls(path=resolved, raw_xml=raw_xml, root=root)

    def summary(self) -> dict[str, Any]:
        screens_parent = self.root.find("./screens")
        screen_elements = screens_parent.findall("./Screen") if screens_parent is not None else []
        texture_size = self.root.find("./CurrentCompositionTextureSize")
        soft_edge = self.root.find("./SoftEdging/Params/ParamRange[@name='Power']")
        return {
            "path": str(self.path),
            "root_tag": self.root.tag,
            "version": self.root.find("./versionInfo").attrib if self.root.find("./versionInfo") is not None else {},
            "current_composition_texture_size": {
                "width": _attr_int(texture_size, "width") if texture_size is not None else None,
                "height": _attr_int(texture_size, "height") if texture_size is not None else None,
            },
            "screen_count": len(screen_elements),
            "soft_edge_power": _attr_float(soft_edge, "value") if soft_edge is not None else None,
            "screens": [_screen_summary(screen_element, index=index) for index, screen_element in enumerate(screen_elements)],
        }


@dataclass(frozen=True)
class SliceInspectorPreferences:
    path: Path
    raw_xml: str
    root: ET.Element

    @classmethod
    def load(cls, path: str | Path) -> "SliceInspectorPreferences":
        resolved = Path(path).expanduser()
        raw_xml = resolved.read_text(encoding="utf-8")
        root = ET.fromstring(raw_xml)
        return cls(path=resolved, raw_xml=raw_xml, root=root)

    def summary(self) -> dict[str, Any]:
        items = self.root.findall("./List/Items/*")
        return {
            "path": str(self.path),
            "root_tag": self.root.tag,
            "version": self.root.find("./versionInfo").attrib if self.root.find("./versionInfo") is not None else {},
            "item_count": len(items),
        }


def backup_xml_file(source_path: str | Path, backup_dir: str | Path) -> dict[str, Any]:
    source = Path(source_path).expanduser()
    target_dir = Path(backup_dir).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    destination = target_dir / f"{source.stem}-{timestamp}{source.suffix}"
    shutil.copy2(source, destination)
    return {
        "source": str(source),
        "backup": str(destination),
        "timestamp_utc": timestamp,
    }


def diff_xml_text(current_text: str, other_text: str, *, current_name: str, other_name: str) -> list[str]:
    return list(
        difflib.unified_diff(
            current_text.splitlines(),
            other_text.splitlines(),
            fromfile=current_name,
            tofile=other_name,
            lineterm="",
        )
    )
