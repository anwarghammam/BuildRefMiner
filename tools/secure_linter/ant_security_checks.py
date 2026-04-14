from __future__ import annotations

import re
from typing import Dict, Iterable, List, Tuple

from .ant_parser import local_name


ABS_PATH_RE = re.compile(
    r"""(?x)
    ^
    (?:
        /[^"']+ |
        [A-Za-z]:[\\/][^"']+
    )
    $
    """
)
URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
SECRET_NAME_RE = re.compile(
    r"(?i)(password|passwd|pwd|secret|token|apikey|api_key|accesskey|privatekey|passphrase)"
)
PROPERTY_REF_RE = re.compile(r"^\$\{[^}]+\}$")
WILDCARD_VALUE_RE = re.compile(r"[*?]|\$\{\*")


def _iter_candidate_values(ant_data) -> Iterable[Tuple[str, str, str]]:
    for elem in ant_data["root"].iter():
        tag = local_name(elem.tag).lower()
        for attr, value in elem.attrib.items():
            stripped = (value or "").strip()
            if stripped:
                yield tag, attr, stripped

        text = (elem.text or "").strip()
        if text:
            yield tag, "text", text


def check_hardcoded_credentials(ant_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    for elem in ant_data["root"].iter():
        tag = local_name(elem.tag).lower()

        for attr, value in elem.attrib.items():
            stripped = (value or "").strip()
            if not stripped or PROPERTY_REF_RE.match(stripped):
                continue

            if SECRET_NAME_RE.search(attr):
                issues.append({
                    "issue": f"Possible hardcoded credential in <{tag}> attribute '{attr}'.",
                    "severity": "High",
                })

        if tag == "property":
            name = (elem.attrib.get("name") or "").strip()
            value = (elem.attrib.get("value") or "").strip()
            if name and value and not PROPERTY_REF_RE.match(value) and SECRET_NAME_RE.search(name):
                issues.append({
                    "issue": f"Property '{name}' appears to contain a hardcoded credential.",
                    "severity": "High",
                })

    return issues


def check_hardcoded_paths_and_urls(ant_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    for tag, attr, value in _iter_candidate_values(ant_data):
        if ABS_PATH_RE.match(value):
            issues.append({
                "issue": f"Hardcoded absolute path in <{tag}> {attr}: {value}",
                "severity": "Medium",
            })

        for url in URL_RE.findall(value):
            issues.append({
                "issue": f"Hardcoded URL in <{tag}> {attr}: {url}",
                "severity": "High" if url.lower().startswith("http://") else "Low",
            })

    return issues


def check_insecure_urls(ant_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    for lineno, line in enumerate(ant_data["raw_content"].splitlines(), start=1):
        for url in URL_RE.findall(line):
            if url.lower().startswith("http://"):
                issues.append({
                    "issue": f"Insecure URL on line {lineno}: {url}",
                    "severity": "High",
                })

    return issues


def check_wildcard_usage(ant_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    wildcard_tags = {"fileset", "patternset", "include", "exclude", "filelist", "path", "pathelement"}
    wildcard_attrs = {"includes", "excludes", "name", "file", "location", "path"}

    for elem in ant_data["root"].iter():
        tag = local_name(elem.tag).lower()
        for attr, value in elem.attrib.items():
            stripped = (value or "").strip()
            if not stripped or attr.lower() not in wildcard_attrs:
                continue

            if WILDCARD_VALUE_RE.search(stripped) and (tag in wildcard_tags or "*" in stripped or "?" in stripped):
                issues.append({
                    "issue": f"Wildcard usage in <{tag}> attribute '{attr}': {stripped}",
                    "severity": "Medium",
                })

    return issues
