from __future__ import annotations

import os
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
SECURE_LINTER_DIR = os.path.join(REPO_ROOT, "tools", "secure_linter")

for path in (BASE_DIR, REPO_ROOT, SECURE_LINTER_DIR):
    if path not in sys.path:
        sys.path.insert(0, path)

GRADLE_CONFIGS = (
    "api",
    "implementation",
    "compileOnly",
    "runtimeOnly",
    "compile",
    "testImplementation",
    "testCompile",
    "androidTestImplementation",
    "androidTestCompile",
)

GRADLE_CATALOG_DEP_RE = re.compile(
    r"^\s*(?:"
    + "|".join(re.escape(item) for item in GRADLE_CONFIGS)
    + r")\s*\(?\s*libs\.[A-Za-z0-9_.-]+",
    re.MULTILINE,
)

GRADLE_PLATFORM_DEP_RE = re.compile(
    r"^\s*(?:"
    + "|".join(re.escape(item) for item in GRADLE_CONFIGS)
    + r")\s*\(\s*(?:platform|enforcedPlatform)\(\s*['\"]([^:'\"]+):([^:'\"]+):([^'\"]+)['\"]\s*\)\s*\)",
    re.MULTILINE,
)

GRADLE_PROPERTY_PATTERNS = [
    re.compile(r"^\s*(?:ext\.)?([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE),
    re.compile(r"^\s*def\s+([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE),
    re.compile(r"^\s*val\s+([A-Za-z_][A-Za-z0-9_.-]*)\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE),
    re.compile(r"^\s*extra\[\s*['\"]([^'\"]+)['\"]\s*\]\s*=\s*['\"]([^'\"]+)['\"]", re.MULTILINE),
]

GRADLE_STRING_DEP_RE = re.compile(
    r"^\s*(api|implementation|compileOnly|runtimeOnly|compile|testImplementation|testCompile|androidTestImplementation|androidTestCompile)"
    r"\s*(?:\(\s*)?['\"]([^:'\"]+):([^:'\"]+)(?::([^'\"]+))?['\"][ \t]*\)?",
    re.MULTILINE,
)

GRADLE_MAP_DEP_RE = re.compile(
    r"^\s*(api|implementation|compile|compileOnly|runtimeOnly|testImplementation|testCompile|androidTestImplementation|androidTestCompile)"
    r"\s+group\s*:\s*['\"](.+?)['\"],\s*name\s*:\s*['\"](.+?)['\"],\s*version\s*:\s*['\"](.+?)['\"]",
    re.MULTILINE,
)

PROPERTY_REF_RE = re.compile(r"^\$\{([^}]+)\}$")
INLINE_PROPERTY_REF_RE = re.compile(r"\$\{([^}]+)\}")


def empty_dependency_stability_result() -> dict[str, Any]:
    return {
        "dependency_count": 0,
        "fixed_dependency_count": 0,
        "dynamic_dependency_count": 0,
        "snapshot_dependency_count": 0,
        "unknown_dependency_count": 0,
        "dss": 0.0,
    }


def detect_build_type(file_path: str) -> str:
    name = Path(file_path).name.lower()
    if name.endswith(".gradle") or name.endswith(".gradle.kts") or name.endswith(".groovy"):
        return "gradle"
    if name == "pom.xml":
        return "maven"
    if name == "build.xml":
        return "ant"
    return "unknown"


def classify_version(version: str) -> str:
    value = (version or "").strip()
    lowered = value.lower()

    if not value:
        return "unknown"
    if lowered.startswith("libs.") or lowered.startswith("project("):
        return "unknown"
    if value.startswith("$") or PROPERTY_REF_RE.match(value) or INLINE_PROPERTY_REF_RE.search(value):
        return "unknown"
    if "snapshot" in lowered:
        return "snapshot"
    if lowered in {"latest.release", "latest.integration", "latest", "release", "integration"}:
        return "dynamic"
    if any(char in value for char in "*[](),+"):
        return "dynamic"
    return "fixed"


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    return tag


def summarize_dependency_versions(versions: list[str]) -> dict[str, Any]:
    counts = {
        "fixed": 0,
        "dynamic": 0,
        "snapshot": 0,
        "unknown": 0,
    }

    for version in versions:
        counts[classify_version(version)] += 1

    total = len(versions)
    dss = round(counts["fixed"] / total, 4) if total > 0 else 0.0

    return {
        "dependency_count": total,
        "fixed_dependency_count": counts["fixed"],
        "dynamic_dependency_count": counts["dynamic"],
        "snapshot_dependency_count": counts["snapshot"],
        "unknown_dependency_count": counts["unknown"],
        "dss": dss,
    }


def _resolve_value(value: str, properties: dict[str, str], passes: int = 4) -> str:
    resolved = (value or "").strip()
    if not resolved:
        return ""

    for _ in range(passes):
        previous = resolved
        match = PROPERTY_REF_RE.match(resolved)
        if match:
            resolved = properties.get(match.group(1), resolved)
        elif resolved.startswith("$") and len(resolved) > 1 and "{" not in resolved:
            resolved = properties.get(resolved[1:], resolved)
        else:
            resolved = INLINE_PROPERTY_REF_RE.sub(lambda item: properties.get(item.group(1), item.group(0)), resolved)

        if resolved == previous:
            break

    return resolved.strip()


def _extract_gradle_properties(raw_content: str) -> dict[str, str]:
    properties: dict[str, str] = {}
    for pattern in GRADLE_PROPERTY_PATTERNS:
        for match in pattern.finditer(raw_content):
            key, value = match.groups()
            properties[key.strip()] = value.strip()
    return properties


def compute_gradle_dependency_stability(file_path: str) -> dict[str, Any]:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
        raw_content = handle.read()
    properties = _extract_gradle_properties(raw_content)

    versions: list[str] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for match in GRADLE_STRING_DEP_RE.finditer(raw_content):
        config, group, artifact, version = match.groups()
        key = (group.strip(), artifact.strip(), config.strip())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        versions.append(_resolve_value(version or "", properties))

    for match in GRADLE_MAP_DEP_RE.finditer(raw_content):
        config, group, artifact, version = match.groups()
        key = (group.strip(), artifact.strip(), config.strip())
        if key in seen_keys:
            continue
        seen_keys.add(key)
        versions.append(_resolve_value(version, properties))

    for match in GRADLE_PLATFORM_DEP_RE.finditer(raw_content):
        key = (match.group(1).strip(), match.group(2).strip(), "platform")
        if key in seen_keys:
            continue
        seen_keys.add(key)
        versions.append(_resolve_value(match.group(3), properties))

    for match in GRADLE_CATALOG_DEP_RE.finditer(raw_content):
        key = ("catalog", match.group(0).strip(), "catalog")
        if key in seen_keys:
            continue
        seen_keys.add(key)
        versions.append("libs.catalog")

    return summarize_dependency_versions(versions)


def _parse_maven_root(file_path: str) -> Any | None:
    try:
        raw_bytes = open(file_path, "rb").read()
        text = raw_bytes.decode("utf-8", errors="ignore")
        text = re.sub(r"<\?xml[^>]*\?>", "", text)
        cleaned = "\n".join(re.sub(r"^\s*\d+:\s*", "", line) for line in text.splitlines())
        return ET.fromstring(cleaned.encode("utf-8"))
    except Exception:
        return None


def _maven_properties(root: Any) -> dict[str, str]:
    properties: dict[str, str] = {}
    for child in root:
        if local_name(child.tag) == "properties":
            for prop in child:
                properties[local_name(prop.tag)] = (prop.text or "").strip()

    project_coords: dict[str, str] = {}
    for child in root:
        tag = local_name(child.tag)
        if tag in {"groupId", "artifactId", "version"}:
            project_coords[tag] = (child.text or "").strip()

    parent = next((child for child in root if local_name(child.tag) == "parent"), None)
    for tag in ("groupId", "version"):
        if not project_coords.get(tag) and parent is not None:
            child = next((node for node in parent if local_name(node.tag) == tag), None)
            if child is not None and (child.text or "").strip():
                project_coords[tag] = (child.text or "").strip()

    for tag, value in project_coords.items():
        if value:
            properties[f"project.{tag}"] = value
            properties[f"pom.{tag}"] = value

    return properties


def _maven_dependency_management_versions(root: Any, properties: dict[str, str]) -> dict[tuple[str, str], str]:
    mapping: dict[tuple[str, str], str] = {}
    for child in root.iter():
        if local_name(child.tag) != "dependencyManagement":
            continue
        for deps in child:
            if local_name(deps.tag) != "dependencies":
                continue
            for dep in deps:
                if local_name(dep.tag) != "dependency":
                    continue
                group = _resolve_value(
                    next((node.text or "" for node in dep if local_name(node.tag) == "groupId"), ""),
                    properties,
                )
                artifact = _resolve_value(
                    next((node.text or "" for node in dep if local_name(node.tag) == "artifactId"), ""),
                    properties,
                )
                version = _resolve_value(
                    next((node.text or "" for node in dep if local_name(node.tag) == "version"), ""),
                    properties,
                )
                if group and artifact:
                    mapping[(group, artifact)] = version
    return mapping


def _maven_child_text(elem: Any, child_name: str) -> str:
    return next((node.text or "" for node in elem if local_name(node.tag) == child_name), "")


def _collect_maven_dependencies(elem: Any, inside_dependency_management: bool = False) -> list[Any]:
    collected: list[Any] = []
    current_inside = inside_dependency_management or local_name(elem.tag) == "dependencyManagement"

    if local_name(elem.tag) == "dependency" and not current_inside:
        collected.append(elem)

    for child in list(elem):
        collected.extend(_collect_maven_dependencies(child, current_inside))

    return collected


def compute_maven_dependency_stability(file_path: str) -> dict[str, Any]:
    root = _parse_maven_root(file_path)
    if root is None:
        return empty_dependency_stability_result()

    properties = _maven_properties(root)
    dependency_management = _maven_dependency_management_versions(root, properties)

    versions: list[str] = []
    for dep in _collect_maven_dependencies(root):
        group = _resolve_value(_maven_child_text(dep, "groupId"), properties)
        artifact = _resolve_value(_maven_child_text(dep, "artifactId"), properties)
        version = _resolve_value(_maven_child_text(dep, "version"), properties)
        if not version and group and artifact:
            version = dependency_management.get((group, artifact), "")
        versions.append(version)

    return summarize_dependency_versions(versions)


def compute_ant_dependency_stability(file_path: str) -> dict[str, Any]:
    from ant_parser import JAR_WITH_VERSION_RE, parse_ant

    ant_data = parse_ant(file_path)
    if ant_data is None:
        return empty_dependency_stability_result()

    property_values = ant_data.get("property_values", {})
    versions: list[str] = []
    seen_jars: set[str] = set()

    for elem in ant_data["root"].iter():
        for attr_value in elem.attrib.values():
            resolved = _resolve_value(attr_value, property_values)
            candidates = re.findall(r"[A-Za-z0-9_.+-]+\.jar", resolved)
            for jar_name in candidates:
                if jar_name in seen_jars:
                    continue
                seen_jars.add(jar_name)

                match = JAR_WITH_VERSION_RE.match(jar_name)
                if match:
                    versions.append(match.group("version"))
                else:
                    versions.append("")

    return summarize_dependency_versions(versions)


def compute_dependency_stability(file_path: str) -> dict[str, Any]:
    if not file_path or not os.path.exists(file_path):
        return empty_dependency_stability_result()

    build_type = detect_build_type(file_path)
    if build_type == "gradle":
        return compute_gradle_dependency_stability(file_path)
    if build_type == "maven":
        return compute_maven_dependency_stability(file_path)
    if build_type == "ant":
        return compute_ant_dependency_stability(file_path)

    return empty_dependency_stability_result()
