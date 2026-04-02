from __future__ import annotations

import difflib
import os
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


def _find_param(element: ET.Element, name: str) -> ET.Element | None:
    for param in element.findall("./Params/*"):
        if param.get("name") == name:
            return param
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


def _set_vertices(parent: ET.Element, path: str, vertices: list[dict[str, float]]) -> None:
    node = parent.find(path)
    if node is None:
        raise ValueError(f"Could not find XML node at path {path!r}.")
    existing_vertices = node.findall("./v")
    if existing_vertices and len(existing_vertices) != len(vertices):
        raise ValueError(
            f"Vertex count mismatch for {path!r}: expected {len(existing_vertices)}, got {len(vertices)}."
        )
    for vertex in list(existing_vertices):
        node.remove(vertex)
    for point in vertices:
        x = point.get("x")
        y = point.get("y")
        if not isinstance(x, (int, float)) or not isinstance(y, (int, float)):
            raise ValueError("Each vertex must include numeric x and y values.")
        ET.SubElement(node, "v", x=str(x), y=str(y))


def _screen_elements(root: ET.Element) -> list[ET.Element]:
    screens_parent = root.find("./screens")
    return screens_parent.findall("./Screen") if screens_parent is not None else []


def _slice_elements(screen: ET.Element) -> list[ET.Element]:
    slices_parent = screen.find("./layers")
    return slices_parent.findall("./Slice") if slices_parent is not None else []


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

    def save(self, path: str | Path | None = None) -> dict[str, Any]:
        destination = Path(path).expanduser() if path is not None else self.path
        xml_text = ET.tostring(self.root, encoding="unicode")
        destination.write_text('<?xml version="1.0" encoding="utf-8"?>\n' + xml_text, encoding="utf-8")
        return {"path": str(destination)}


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


def export_xml_file(source_path: str | Path, export_dir: str | Path, *, export_name: str | None = None) -> dict[str, Any]:
    source = Path(source_path).expanduser()
    target_dir = Path(export_dir).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    destination_name = export_name or source.name
    destination = target_dir / destination_name
    shutil.copy2(source, destination)
    return {
        "source": str(source),
        "export": str(destination),
    }


def export_advanced_output_bundle(
    *,
    advanced_output_xml_path: str | Path,
    slices_xml_path: str | Path,
    export_dir: str | Path,
) -> dict[str, Any]:
    target_dir = Path(export_dir).expanduser()
    target_dir.mkdir(parents=True, exist_ok=True)
    return {
        "bundle_dir": str(target_dir),
        "advanced_output_xml": export_xml_file(
            advanced_output_xml_path,
            target_dir,
            export_name="AdvancedOutput.xml",
        ),
        "slices_xml": export_xml_file(
            slices_xml_path,
            target_dir,
            export_name="slices.xml",
        ),
    }


def windows_advanced_output_path_candidates(
    *,
    username: str = "",
    drive: str = "C:",
) -> dict[str, Any]:
    resolved_username = username.strip() or os.getenv("USERNAME", "").strip() or "<USERNAME>"
    base = f"{drive}\\Users\\{resolved_username}\\Documents\\Resolume Arena"
    return {
        "documents_root": base,
        "advanced_output_xml_path": f"{base}\\Preferences\\AdvancedOutput.xml",
        "slices_xml_path": f"{base}\\Preferences\\slices.xml",
        "notes": [
            "These are Windows candidate paths only.",
            "They should be validated on the actual media server and then set through RESOLUME_DOCUMENTS_ROOT, RESOLUME_ADVANCED_OUTPUT_XML, and RESOLUME_SLICES_XML.",
        ],
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


def preview_restore_advanced_output_bundle(
    *,
    current_advanced_output_xml_path: str | Path,
    current_slices_xml_path: str | Path,
    candidate_advanced_output_xml_path: str | Path,
    candidate_slices_xml_path: str | Path,
) -> dict[str, Any]:
    current_advanced_output = AdvancedOutputPreferences.load(current_advanced_output_xml_path)
    candidate_advanced_output = AdvancedOutputPreferences.load(candidate_advanced_output_xml_path)
    current_slices = SliceInspectorPreferences.load(current_slices_xml_path)
    candidate_slices = SliceInspectorPreferences.load(candidate_slices_xml_path)

    advanced_output_diff = diff_xml_text(
        current_advanced_output.raw_xml,
        candidate_advanced_output.raw_xml,
        current_name=str(current_advanced_output.path),
        other_name=str(Path(candidate_advanced_output_xml_path).expanduser()),
    )
    slices_diff = diff_xml_text(
        current_slices.raw_xml,
        candidate_slices.raw_xml,
        current_name=str(current_slices.path),
        other_name=str(Path(candidate_slices_xml_path).expanduser()),
    )

    return {
        "current": {
            "advanced_output_xml": current_advanced_output.summary(),
            "slices_xml": current_slices.summary(),
        },
        "candidate": {
            "advanced_output_xml": candidate_advanced_output.summary(),
            "slices_xml": candidate_slices.summary(),
        },
        "diffs": {
            "advanced_output_xml": {
                "diff_line_count": len(advanced_output_diff),
                "diff": advanced_output_diff,
            },
            "slices_xml": {
                "diff_line_count": len(slices_diff),
                "diff": slices_diff,
            },
        },
        "notes": [
            "This is a file-level preview only.",
            "Resolume reload behavior after XML replacement is not yet verified on this machine.",
        ],
    }


def restore_advanced_output_bundle(
    *,
    current_advanced_output_xml_path: str | Path,
    current_slices_xml_path: str | Path,
    source_advanced_output_xml_path: str | Path,
    source_slices_xml_path: str | Path,
    backup_dir: str | Path,
) -> dict[str, Any]:
    backups = {
        "advanced_output_xml": backup_xml_file(current_advanced_output_xml_path, backup_dir),
        "slices_xml": backup_xml_file(current_slices_xml_path, backup_dir),
    }
    restores = {
        "advanced_output_xml": export_xml_file(
            source_advanced_output_xml_path,
            Path(current_advanced_output_xml_path).expanduser().parent,
            export_name=Path(current_advanced_output_xml_path).expanduser().name,
        ),
        "slices_xml": export_xml_file(
            source_slices_xml_path,
            Path(current_slices_xml_path).expanduser().parent,
            export_name=Path(current_slices_xml_path).expanduser().name,
        ),
    }
    return {
        "backups": backups,
        "restores": restores,
        "notes": [
            "Current files were backed up before restore.",
            "Resolume reload behavior after XML replacement is not yet verified on this machine. Manual reopen, preset import, or app restart may be required.",
        ],
    }


def rename_screen_in_advanced_output(
    *,
    advanced_output_xml_path: str | Path,
    screen_index: int,
    new_name: str,
    backup_dir: str | Path,
) -> dict[str, Any]:
    prefs = AdvancedOutputPreferences.load(advanced_output_xml_path)
    screen_elements = _screen_elements(prefs.root)
    if screen_index < 0 or screen_index >= len(screen_elements):
        raise IndexError("screen_index is out of range for AdvancedOutput.xml.")
    screen = screen_elements[screen_index]
    param = _find_param(screen, "Name")
    if param is None:
        raise ValueError("Could not find the screen Name parameter in AdvancedOutput.xml.")
    backup = backup_xml_file(advanced_output_xml_path, backup_dir)
    old_name = param.get("value")
    param.set("value", new_name)
    prefs.save()
    return {
        "backup": backup,
        "path": str(prefs.path),
        "screen_index": screen_index,
        "old_name": old_name,
        "new_name": new_name,
        "notes": [
            "Only the screen Name parameter was changed.",
            "Resolume reload behavior after XML replacement is not yet verified on this machine.",
        ],
    }


def rename_slice_in_advanced_output(
    *,
    advanced_output_xml_path: str | Path,
    screen_index: int,
    slice_index: int,
    new_name: str,
    backup_dir: str | Path,
) -> dict[str, Any]:
    prefs = AdvancedOutputPreferences.load(advanced_output_xml_path)
    screen_elements = _screen_elements(prefs.root)
    if screen_index < 0 or screen_index >= len(screen_elements):
        raise IndexError("screen_index is out of range for AdvancedOutput.xml.")
    slice_elements = _slice_elements(screen_elements[screen_index])
    if slice_index < 0 or slice_index >= len(slice_elements):
        raise IndexError("slice_index is out of range for the selected screen in AdvancedOutput.xml.")
    slice_element = slice_elements[slice_index]
    param = _find_param(slice_element, "Name")
    if param is None:
        raise ValueError("Could not find the slice Name parameter in AdvancedOutput.xml.")
    backup = backup_xml_file(advanced_output_xml_path, backup_dir)
    old_name = param.get("value")
    param.set("value", new_name)
    prefs.save()
    return {
        "backup": backup,
        "path": str(prefs.path),
        "screen_index": screen_index,
        "slice_index": slice_index,
        "old_name": old_name,
        "new_name": new_name,
        "notes": [
            "Only the slice Name parameter was changed.",
            "Resolume reload behavior after XML replacement is not yet verified on this machine.",
        ],
    }


def set_advanced_output_soft_edge_power(
    *,
    advanced_output_xml_path: str | Path,
    value: float,
    backup_dir: str | Path,
) -> dict[str, Any]:
    prefs = AdvancedOutputPreferences.load(advanced_output_xml_path)
    param = prefs.root.find("./SoftEdging/Params/ParamRange[@name='Power']")
    if param is None:
        raise ValueError("Could not find SoftEdging/Power in AdvancedOutput.xml.")
    backup = backup_xml_file(advanced_output_xml_path, backup_dir)
    old_value = param.get("value")
    param.set("value", repr(value))
    prefs.save()
    return {
        "backup": backup,
        "path": str(prefs.path),
        "old_value": old_value,
        "new_value": value,
        "notes": [
            "Only the Soft Edge Power parameter was changed.",
            "Resolume reload behavior after XML replacement is not yet verified on this machine.",
        ],
    }


def set_advanced_output_screen_output_device(
    *,
    advanced_output_xml_path: str | Path,
    screen_index: int,
    name: str,
    device_id: str,
    width: int,
    height: int,
    backup_dir: str | Path,
) -> dict[str, Any]:
    prefs = AdvancedOutputPreferences.load(advanced_output_xml_path)
    screen_elements = _screen_elements(prefs.root)
    if screen_index < 0 or screen_index >= len(screen_elements):
        raise IndexError("screen_index is out of range for AdvancedOutput.xml.")
    screen = screen_elements[screen_index]
    output_device = screen.find("./OutputDevice/*")
    if output_device is None:
        raise ValueError("Could not find OutputDevice in AdvancedOutput.xml.")
    backup = backup_xml_file(advanced_output_xml_path, backup_dir)
    old = {
        "name": output_device.get("name"),
        "device_id": output_device.get("deviceId"),
        "width": _attr_int(output_device, "width"),
        "height": _attr_int(output_device, "height"),
    }
    output_device.set("name", name)
    output_device.set("deviceId", device_id)
    output_device.set("width", str(width))
    output_device.set("height", str(height))
    prefs.save()
    return {
        "backup": backup,
        "path": str(prefs.path),
        "screen_index": screen_index,
        "old_output_device": old,
        "new_output_device": {
            "name": name,
            "device_id": device_id,
            "width": width,
            "height": height,
        },
        "notes": [
            "Only the current screen output device attributes were changed.",
            "Resolume reload behavior after XML replacement is not yet verified on this machine.",
        ],
    }


def set_advanced_output_slice_vertices(
    *,
    advanced_output_xml_path: str | Path,
    screen_index: int,
    slice_index: int,
    path: str,
    vertices: list[dict[str, float]],
    backup_dir: str | Path,
) -> dict[str, Any]:
    prefs = AdvancedOutputPreferences.load(advanced_output_xml_path)
    screen_elements = _screen_elements(prefs.root)
    if screen_index < 0 or screen_index >= len(screen_elements):
        raise IndexError("screen_index is out of range for AdvancedOutput.xml.")
    slice_elements = _slice_elements(screen_elements[screen_index])
    if slice_index < 0 or slice_index >= len(slice_elements):
        raise IndexError("slice_index is out of range for the selected screen in AdvancedOutput.xml.")
    slice_element = slice_elements[slice_index]
    old_vertices = _vertices(slice_element, path)
    backup = backup_xml_file(advanced_output_xml_path, backup_dir)
    _set_vertices(slice_element, path, vertices)
    prefs.save()
    return {
        "backup": backup,
        "path": str(prefs.path),
        "screen_index": screen_index,
        "slice_index": slice_index,
        "target_path": path,
        "old_vertices": old_vertices,
        "new_vertices": vertices,
        "notes": [
            "Only the targeted vertex set was changed.",
            "Resolume reload behavior after XML replacement is not yet verified on this machine.",
        ],
    }
