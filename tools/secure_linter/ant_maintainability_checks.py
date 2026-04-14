from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Set, Tuple
from urllib.parse import urlencode
from urllib.request import urlopen

from .ant_parser import local_name


STALE_THRESHOLD = timedelta(days=365 * 2)
COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)
VERSION_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]*$")
JAR_WITH_VERSION_RE = re.compile(
    r"(?P<artifact>[A-Za-z0-9_.-]+)-(?P<version>[A-Za-z0-9_.+-]+)\.jar$"
)
MAVEN_API_URL = "https://search.maven.org/solrsearch/select"


def _normalize_xml_fragment(text: str) -> str:
    text = re.sub(r">\s+<", "><", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _target_body_signature(target_elem: ET.Element) -> str:
    parts = [ET.tostring(child, encoding="unicode") for child in list(target_elem)]
    return _normalize_xml_fragment("".join(parts))


def _safe_bool_attr(value: Optional[str]) -> Optional[bool]:
    if value is None:
        return None
    lowered = value.strip().lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    return None


def _looks_like_version(value: str) -> bool:
    value = (value or "").strip()
    return bool(value and VERSION_RE.match(value))


def _extract_versioned_jars(raw_content: str) -> List[Tuple[str, str]]:
    jars: List[Tuple[str, str]] = []
    for match in re.finditer(r'["\']([^"\']+\.jar)["\']', raw_content):
        jar_name = match.group(1).split("/")[-1].split("\\")[-1]
        jar_match = JAR_WITH_VERSION_RE.match(jar_name)
        if jar_match:
            jars.append((jar_match.group("artifact"), jar_match.group("version")))
    return jars


def _target_dependency_graph(ant_data) -> Dict[str, List[str]]:
    graph: Dict[str, List[str]] = {}
    for target in ant_data["targets"]:
        name = (target.get("name") or "").strip()
        if not name:
            continue
        deps = [
            dep.strip()
            for dep in target["element"].attrib.get("depends", "").split(",")
            if dep.strip()
        ]
        graph[name] = deps
    return graph


def _max_dependency_chain(graph: Dict[str, List[str]]) -> int:
    visiting: Set[str] = set()
    memo: Dict[str, int] = {}

    def dfs(node: str) -> int:
        if node in memo:
            return memo[node]
        if node in visiting:
            return 0
        visiting.add(node)
        best = 1
        for nxt in graph.get(node, []):
            best = max(best, 1 + dfs(nxt))
        visiting.remove(node)
        memo[node] = best
        return best

    return max((dfs(node) for node in graph), default=0)


def _normalize_version_tuple(value: str) -> Tuple[int, ...]:
    return tuple(int(part) for part in re.findall(r"\d+", value or ""))


def _fetch_package_metadata_by_artifact(artifact: str) -> Optional[Dict]:
    artifact = (artifact or "").strip()
    if not artifact:
        return None
    try:
        query = urlencode({
            "q": f'a:"{artifact}"',
            "rows": 1,
            "wt": "json",
            "core": "gav",
            "sort": "version desc",
        })
        with urlopen(f"{MAVEN_API_URL}?{query}", timeout=5) as resp:
            payload = resp.read().decode("utf-8", errors="ignore")
        docs = json.loads(payload).get("response", {}).get("docs", [])
        return docs[0] if docs else None
    except Exception:
        return None


def _dependencies_with_metadata(ant_data) -> List[Dict]:
    enriched: List[Dict] = []
    for dep in ant_data.get("dependencies", []):
        item = dict(dep)
        if item.get("artifact") and (
            not item.get("latest_version") or not item.get("last_release_timestamp")
        ):
            meta = _fetch_package_metadata_by_artifact(item["artifact"])
            if meta:
                item.setdefault("latest_version", meta.get("v") or meta.get("latestVersion", ""))
                item.setdefault("last_release_timestamp", meta.get("timestamp"))
                item.setdefault("group", meta.get("g", item.get("group", "")))
                item.setdefault("artifact", meta.get("a", item.get("artifact", "")))
        enriched.append(item)
    return enriched


def check_complexity(ant_data) -> List[Dict[str, str]]:
    """
    Heuristic Ant build complexity check.
    Not a formal cyclomatic complexity metric.
    """
    issues: List[Dict[str, str]] = []
    root = ant_data["root"]
    raw = ant_data["raw_content"]

    condition_tags = {
        "condition", "available", "uptodate", "isset", "equals",
        "contains", "matches", "and", "or", "not",
    }
    score = 0
    large_targets: list[tuple[str, int]] = []

    for elem in root.iter():
        tag = local_name(elem.tag).lower()

        if tag in condition_tags:
            score += 1
        if "if" in elem.attrib:
            score += 1
        if "unless" in elem.attrib:
            score += 1

        if tag == "target":
            children = list(elem)
            if len(children) > 12:
                large_targets.append((elem.attrib.get("name", "<unnamed>"), len(children)))
            depends = [dep.strip() for dep in elem.attrib.get("depends", "").split(",") if dep.strip()]
            score += len(depends)

    graph = _target_dependency_graph(ant_data)
    max_chain = _max_dependency_chain(graph)
    score += max(0, max_chain - 3)

    if score > 10:
        issues.append({
            "issue": f"Complex Ant build logic heuristic is high (score={score}).",
            "severity": "Low",
        })

    if len(ant_data["targets"]) > 12:
        issues.append({
            "issue": f"Large Ant build file with {len(ant_data['targets'])} targets.",
            "severity": "Low",
        })

    if len(raw.splitlines()) > 300:
        issues.append({
            "issue": f"Ant build file is long ({len(raw.splitlines())} lines).",
            "severity": "Low",
        })

    for name, size in large_targets:
        issues.append({
            "issue": f"Large target '{name}' contains {size} nested tasks; consider decomposing it.",
            "severity": "Low",
        })

    if max_chain > 5:
        issues.append({
            "issue": f"Deep target dependency chain detected (depth={max_chain}).",
            "severity": "Medium",
        })

    return issues


def check_duplicates(ant_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    seen_names: Set[str] = set()
    seen_bodies: Dict[str, str] = {}

    for target in ant_data["targets"]:
        name = (target.get("name") or "").strip()
        elem = target["element"]

        if name:
            if name in seen_names:
                issues.append({
                    "issue": f"Duplicate Ant target name found: '{name}'.",
                    "severity": "Medium",
                })
            seen_names.add(name)

        signature = _target_body_signature(elem)
        if len(signature) < 50:
            continue

        if signature in seen_bodies:
            issues.append({
                "issue": f"Duplicate target logic found in '{name or '<unnamed>'}' and '{seen_bodies[signature]}'.",
                "severity": "Low",
            })
        else:
            seen_bodies[signature] = name or "<unnamed>"

    return issues


def check_empty_incomplete_tags(ant_data) -> List[Dict[str, str]]:
    """
    Structural/configuration issues mapped into the Empty / Incomplete Tags bucket.
    """
    issues: List[Dict[str, str]] = []

    for elem in ant_data["root"].iter():
        tag = local_name(elem.tag).lower()
        text = (elem.text or "").strip()
        children = list(elem)

        if tag == "target" and not elem.attrib.get("name", "").strip():
            issues.append({
                "issue": "<target> is missing required attribute 'name'.",
                "severity": "Medium",
            })
        elif tag == "target" and not children and not text and not elem.attrib.get("depends", "").strip():
            issues.append({
                "issue": f"Target '{elem.attrib.get('name', '<unnamed>')}' is empty.",
                "severity": "Low",
            })

        elif tag == "property":
            name = elem.attrib.get("name", "").strip()
            has_value = any(elem.attrib.get(attr, "").strip() for attr in (
                "value", "location", "file", "resource", "environment", "refid", "url"
            ))
            if name and not has_value:
                issues.append({
                    "issue": f"Property '{name}' has no assigned value source.",
                    "severity": "Low",
                })

        elif tag == "exec" and not elem.attrib.get("executable", "").strip():
            issues.append({
                "issue": "<exec> is missing required attribute 'executable'.",
                "severity": "Medium",
            })

        elif tag == "javac":
            srcdir = elem.attrib.get("srcdir", "").strip()
            if not srcdir:
                issues.append({
                    "issue": "<javac> is missing 'srcdir'.",
                    "severity": "Low",
                })

        elif tag == "copy" and not any(elem.attrib.get(attr, "").strip() for attr in ("file", "todir", "tofile")) and not list(elem):
            issues.append({
                "issue": "<copy> looks incomplete; expected file/todir/tofile or nested resource collection.",
                "severity": "Low",
            })

    return issues


def check_inconsistent_dependency_management(ant_data) -> List[Dict[str, str]]:
    """
    Heuristic only:
    - inconsistent versions for the same logical package across properties
    - mixture of property-managed versions and inline versioned JAR names
    """
    issues: List[Dict[str, str]] = []
    seen_versions: Dict[str, str] = {}

    for prop in ant_data.get("version_properties", []):
        pkg = (prop.get("package") or "").strip()
        version = (prop.get("version") or "").strip()
        if not pkg or not version:
            continue
        if pkg in seen_versions and seen_versions[pkg] != version:
            issues.append({
                "issue": f"Inconsistent versions for package '{pkg}': {seen_versions[pkg]} vs {version}.",
                "severity": "Medium",
            })
        seen_versions[pkg] = version

    uses_property_versions = bool(ant_data.get("version_properties"))
    uses_literal_versioned_jars = bool(_extract_versioned_jars(ant_data["raw_content"]))
    if uses_property_versions and uses_literal_versioned_jars:
        issues.append({
            "issue": "Mixed dependency version styles detected: version properties and inline versioned JAR filenames.",
            "severity": "Low",
        })

    return issues


def check_lack_of_error_handling(ant_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    risky_tags = {"exec", "java", "ant", "subant"}

    for elem in ant_data["root"].iter():
        tag = local_name(elem.tag).lower()
        if tag not in risky_tags:
            continue

        failonerror = _safe_bool_attr(elem.attrib.get("failonerror"))
        if failonerror is False:
            issues.append({
                "issue": f"<{tag}> sets failonerror='false'.",
                "severity": "Medium",
            })
        elif failonerror is None and tag in {"exec", "java"}:
            issues.append({
                "issue": f"<{tag}> does not explicitly declare failonerror.",
                "severity": "Low",
            })

    return issues


def check_missing_dependency_version(ant_data) -> List[Dict[str, str]]:
    """
    Checks only the quality of parsed version properties.
    Does not claim the Ant build is generally missing versions.
    """
    issues: List[Dict[str, str]] = []

    for prop in ant_data.get("version_properties", []):
        prop_name = prop.get("property", "<unknown>")
        version = (prop.get("version") or "").strip()
        if not version:
            issues.append({
                "issue": f"Version property '{prop_name}' is empty.",
                "severity": "Medium",
            })
        elif not _looks_like_version(version):
            issues.append({
                "issue": f"Version property '{prop_name}' has an unusual format: {version!r}",
                "severity": "Low",
            })

    return issues


def check_suspicious_comments(ant_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for idx, match in enumerate(COMMENT_RE.finditer(ant_data["raw_content"]), start=1):
        text = re.sub(r"\s+", " ", match.group(1)).strip()
        if (
            re.search(r"\b(TODO|FIXME|HACK|XXX)\b", text, re.IGNORECASE)
            or re.search(r"<\s*(target|exec|javac|copy|delete|mkdir|jar|move|get)\b", text, re.IGNORECASE)
        ):
            issues.append({
                "issue": f"Suspicious comment #{idx}: {text[:120]}",
                "severity": "Low",
            })
    return issues


def check_deprecated_dependencies(ant_data) -> List[Dict[str, str]]:
    """
    Conservative check:
    runs only for explicit versioned dependencies that can be matched to
    Maven metadata with a last release timestamp.
    """
    issues: List[Dict[str, str]] = []
    cutoff = datetime.utcnow() - STALE_THRESHOLD

    for dep in _dependencies_with_metadata(ant_data):
        ts = dep.get("last_release_timestamp")
        if not ts:
            continue
        last = datetime.utcfromtimestamp(ts / 1000.0)
        if last < cutoff:
            months = (datetime.utcnow() - last).days // 30
            issues.append({
                "issue": (
                    f"Dependency {dep.get('group', '?')}:{dep.get('artifact', '?')} "
                    f"appears stale; last release was {months} months ago ({last.date()})."
                ),
                "severity": "Medium",
            })

    return issues


def check_outdated_dependencies(ant_data) -> List[Dict[str, str]]:
    """
    Conservative check:
    runs only for explicit versioned dependencies that can be matched to
    Maven metadata with a latest version.
    """
    issues: List[Dict[str, str]] = []

    for dep in _dependencies_with_metadata(ant_data):
        current = (dep.get("version") or "").strip()
        latest = (dep.get("latest_version") or "").strip()
        cur_tuple = _normalize_version_tuple(current)
        latest_tuple = _normalize_version_tuple(latest)
        if not current or not latest or not cur_tuple or not latest_tuple:
            continue
        if cur_tuple < latest_tuple:
            issues.append({
                "issue": (
                    f"Outdated dependency {dep.get('group', '?')}:{dep.get('artifact', '?')} "
                    f"(current={current}, latest={latest})."
                ),
                "severity": "Medium",
            })

    return issues
