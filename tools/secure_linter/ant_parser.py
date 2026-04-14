from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from typing import Dict, List


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def _package_from_property_name(name: str) -> str:
    pkg = re.sub(r"(?i)(?:[._-]?version)$", "", name or "").strip()
    pkg = re.sub(r"[^A-Za-z0-9_.-]+", "-", pkg)
    return pkg


JAR_WITH_VERSION_RE = re.compile(
    r"(?P<artifact>[A-Za-z0-9_.-]+)-(?P<version>[A-Za-z0-9][A-Za-z0-9_.+-]*)\.jar$"
)
PROPERTY_REF_RE = re.compile(r"\$\{([^}]+)\}")


def _resolve_property_refs(value: str, properties: Dict[str, str], passes: int = 3) -> str:
    resolved = value
    for _ in range(passes):
        updated = PROPERTY_REF_RE.sub(lambda m: properties.get(m.group(1), m.group(0)), resolved)
        if updated == resolved:
            break
        resolved = updated
    return resolved


def _extract_dependency_from_value(value: str, properties: Dict[str, str]) -> List[Dict[str, str]]:
    candidates: List[Dict[str, str]] = []
    raw = (value or "").strip()
    if not raw:
        return candidates

    resolved = _resolve_property_refs(raw, properties)
    for variant in {raw, resolved}:
        jar_name = variant.split("/")[-1].split("\\")[-1]
        match = JAR_WITH_VERSION_RE.match(jar_name)
        if not match:
            continue
        candidates.append({
            "group": "",
            "artifact": match.group("artifact"),
            "version": match.group("version"),
            "source": raw,
        })
    return candidates


def parse_ant(file_path: str):
    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
        content = handle.read()

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
    except ET.ParseError:
        return None

    targets = []
    properties = []
    version_properties = []
    property_values: Dict[str, str] = {}
    dependencies: list[dict[str, str]] = []
    seen_dependencies: set[tuple[str, str]] = set()

    for elem in root.iter():
        tag = local_name(elem.tag).lower()

        if tag == "target":
            depends = elem.attrib.get("depends", "")
            targets.append({
                "name": elem.attrib.get("name", "").strip(),
                "depends": [dep.strip() for dep in depends.split(",") if dep.strip()],
                "element": elem,
            })

        if tag == "property":
            name = elem.attrib.get("name", "").strip()
            value = elem.attrib.get("value", "").strip()
            prop = {
                "name": name,
                "value": value,
                "element": elem,
            }
            properties.append(prop)
            if name:
                property_values[name] = value

            if re.search(r"(?i)(?:^|[._-])version$", name):
                version_properties.append({
                    "property": name,
                    "package": _package_from_property_name(name),
                    "version": value,
                    "element": elem,
                })

    for elem in root.iter():
        for attr_value in elem.attrib.values():
            for dep in _extract_dependency_from_value(attr_value, property_values):
                key = (dep["artifact"], dep["version"])
                if key in seen_dependencies:
                    continue
                seen_dependencies.add(key)
                dependencies.append(dep)

    return {
        "tree": tree,
        "root": root,
        "targets": targets,
        "properties": properties,
        "property_values": property_values,
        "version_properties": version_properties,
        "dependencies": dependencies,
        "raw_content": content,
    }
