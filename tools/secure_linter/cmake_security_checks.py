from __future__ import annotations
import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Optional

from common.version_utils import fetch_latest_version, is_version_outdated

STALE_THRESHOLD = timedelta(days=365 * 2)
MAVEN_API_URL = "https://search.maven.org/solrsearch/select"

def _fetch_package_metadata(group: str, artifact: str) -> Optional[Dict]:
    try:
        resp = requests.get(
            MAVEN_API_URL,
            params={
                "q": f'g:"{group}" AND a:"{artifact}"',
                "rows": 1, "wt": "json", "core": "gav", "sort": "version desc"
            },
            timeout=5
        )
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])
        return docs[0] if docs else None
    except Exception:
        return None
def check_hardcoded_credentials(cmake_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    pat = re.compile(r"\b(password|apikey|secret|token)\b", re.IGNORECASE)
    for lineno, line in enumerate(cmake_data["raw_content"].splitlines(), 1):
        if pat.search(line):
            issues.append({
                "issue": f"Hardcoded sensitive info on line {lineno}: {line.strip()}",
                "severity": "High",
            })
    return issues

def check_hardcoded_paths_and_urls(cmake_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    # absolute Unix (/foo/bar) or Windows (C:\foo\bar)
    abs_pat = re.compile(r"""(['"])(/(?:[^/]+/)+[^/'"\s]+|[A-Za-z]:\\(?:[^\\]+\\)+[^\\"'\s]+)\1""")
    for m in abs_pat.finditer(cmake_data["raw_content"]):
        issues.append({
            "issue": f"Hardcoded absolute path: {m.group(1)}",
            "severity": "Medium",
        })
    return issues

def check_insecure_urls(cmake_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for lineno, line in enumerate(cmake_data["raw_content"].splitlines(), 1):
        if "http://" in line:
            for url in re.findall(r"(http://[^\s'\"()]+)", line):
                issues.append({
                    "issue": f"Insecure URL on line {lineno}: {url}",
                    "severity": "High",
                })
    return issues

def check_suspicious_comments(cmake_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    pat = re.compile(r"^\s*#.*\b(TODO|FIXME)\b", re.IGNORECASE)
    for lineno, line in enumerate(cmake_data["raw_content"].splitlines(), 1):
        if pat.search(line):
            issues.append({
                "issue": f"Suspicious comment on line {lineno}: {line.strip()}",
                "severity": "Low",
            })
    return issues

def check_find_package_missing_version(cmake_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for pkg in cmake_data["packages"]:
        # ver = pkg["version"] or ""
        # if pkg["required"] and (not ver or ver.strip() == "*" or ver.isspace()):
        ver = (pkg["version"] or "").strip()
        if (
                not ver  # truly empty
                or ver == "*"  # wildcard
                or ver.startswith("${")  # property / variable
                or ver.lower() == "latest"  # permissive token
        ):
            issues.append({
                "issue": f"Required package '{pkg['package']}' missing version.",
                "severity": "Medium",
            })
    return issues
def check_find_package_outdated(cmake_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for pkg in cmake_data["packages"]:
        if pkg["version"]:
            latest = fetch_latest_version(pkg["package"], pkg["package"])
            if latest and is_version_outdated(pkg["version"], latest):
                issues.append({
                    "issue": (
                        f"Package '{pkg['package']}' is outdated "
                        f"(current {pkg['version']}, latest {latest})."
                    ),
                    "severity": "Medium",
                })
    return issues

def check_find_package_stale(cmake_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    cutoff = datetime.utcnow() - STALE_THRESHOLD
    for pkg in cmake_data["packages"]:
        meta = _fetch_package_metadata(pkg["package"], pkg["package"])
        if meta and "timestamp" in meta:
            ts = datetime.utcfromtimestamp(meta["timestamp"] / 1000.0)
            if ts < cutoff:
                months = (datetime.utcnow() - ts).days // 30
                issues.append({
                    "issue": f"Package '{pkg['package']}' last released {months} months ago.",
                    "severity": "Medium",
                })
    return issues
def check_duplicate_find_package(cmake_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    seen: set[str] = set()
    for pkg in cmake_data["packages"]:
        name = pkg["package"]
        if name in seen:
            issues.append({
                "issue": f"Duplicate find_package() for '{name}'.",
                "severity": "Low",
            })
        seen.add(name)
    return issues

def check_commented_code(cmake_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    pat = re.compile(
        r"^\s*#.*\b(cmake_minimum_required|add_executable|add_library)\b",
        re.IGNORECASE
    )
    for lineno, line in enumerate(cmake_data["raw_content"].splitlines(), 1):
        if pat.search(line):
            issues.append({
                "issue": f"Commented-out CMake directive on line {lineno}.",
                "severity": "Low",
            })
    return issues

def check_unused_find_package(cmake_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for pkg in cmake_data["packages"]:
        occurrences = len(re.findall(
            r"\b" + re.escape(pkg["package"]) + r"\b",
            cmake_data["raw_content"]
        ))
        if occurrences <= 1:
            issues.append({
                "issue": f"find_package for '{pkg['package']}' might be unused.",
                "severity": "Low",
            })
    return issues

def check_wildcard_usage(cmake_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    for lineno, line in enumerate(cmake_data["raw_content"].splitlines(), 1):
        if re.search(r"\bfile\s*\(\s*GLOB(_RECURSE)?", line, re.IGNORECASE):
            issues.append({
                "issue": f"Wildcard file(GLOB…) on line {lineno}: {line.strip()}",
                "severity": "Medium",
            })
        for pat in re.findall(r"""(['"])([^'"]*\*[^'"]*)\1""", line):
            if not pat[1].lstrip().startswith("$<") or "*" in pat[1]:
                issues.append({
                    "issue": f"Wildcard path on line {lineno}: {pat[1]}",
                    "severity": "Medium",
                })

        for glob in re.findall(r"""['"]([^'"]*\*[^'"]*)['"]""", line):
            issues.append({
                "issue": f"Wildcard path on line {lineno}: {glob}",
                "severity": "Medium",
            })
    return issues

def check_error_handling(cmake_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for lineno, line in enumerate(cmake_data["raw_content"].splitlines(), 1):
        if "execute_process" in line and "RESULT_VARIABLE" not in line:
            issues.append({
                "issue": f"execute_process missing RESULT_VARIABLE on line {lineno}",
                "severity": "Medium",
            })
        if re.search(r"add_custom_command\s*\(", line, re.IGNORECASE) \
            and "&&" in line and "COMMAND" not in line:
            issues.append({
                "issue": f"add_custom_command may ignore failures on line {lineno}",
                "severity": "Medium",
            })
    return issues
def check_cmake_complexity(cmake_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    raw = cmake_data["raw_content"]
    score = sum(len(re.findall(p, raw)) for p in (
        r"\bif\s*\(", r"\bforeach\s*\(", r"\bfunction\s*\("
    ))
    if score > 12:
        issues.append({
            "issue": f"Complex CMake logic (conditionals/loops/functions = {score})",
            "severity": "Low",
        })

    length = len(raw.splitlines())
    if length > 500:
        issues.append({
            "issue": f"CMake file is very long ({length} lines); consider modularizing.",
            "severity": "Low",
        })

    return issues
