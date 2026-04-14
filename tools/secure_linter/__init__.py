from __future__ import annotations

import inspect
import os
from importlib import import_module, reload
from types import ModuleType
from typing import Callable, List, Dict, Any
import re
from pathlib import Path

_SMELL_OVERRIDES: dict[str, str | None] = {

    "COMPLEX_HEURISTICS":  None,
    "CMAKE_COMPLEXITY":    "Complexity",
    "COMPLEXITY":          "Complexity",


    "HARD_CODED_CREDENTIALS":  "Hardcoded Credentials",
    "HARDCODED_CREDENTIALS":   "Hardcoded Credentials",
    "HARDCODED_SIGNING_CREDENTIALS":   "Hardcoded Credentials",
    "SENSITIVE_INFORMATION":   "Hardcoded Credentials",


    "OUTDATED_DEPENDENCIES": "Outdated Dependencies",
    "DEPRECATED_DEPENDENCIES":      "Deprecated Dependencies",
    "FIND_PACKAGE_OUTDATED":        "Outdated Dependencies",
    "FIND_PACKAGE_STALE":           "Deprecated Dependencies",   #  ⟵ NEW
    "STALE_VERSION_VARIABLES":      "Deprecated Dependencies",   #  ⟵ NEW
    "OUTDATED_VERSION_VARIABLES":   "Outdated Dependencies",   #  ⟵ NEW


    "MISSING_DEPENDENCY_VERSIONS":  "Missing  Dependency Version",
    "MISSING_VERSION_INFORMATION":  "Missing  Dependency Version",
    "INCONSISTENT_DEPENDENCY_VERSIONS": "Inconsistent Dependency Management",
    "INCONSISTENT_PLUGIN_MANAGEMENT":   "Inconsistent Dependency Management",
    "INCONSISTENT_VERSION_MANAGEMENT":  "Inconsistent Dependency Management",
    "FIND_PACKAGE_MISSING_VERSION":     "Missing  Dependency Version",


    "DUPLICATE_FIND_PACKAGE":        "Duplicate (Code/Dependency)",
    "DUPLICATE_FIND_PACKAGE_CALLS":  "Duplicate (Code/Dependency)",
    "DUPLICATE_DEPENDENCIES":        "Duplicate (Code/Dependency)",
    "DUPLICATE_PLUGINS":             "Duplicate (Code/Dependency)",
    "DUPLICATES": "Duplicate (Code/Dependency)",
    "DUPLICATE_CODE": "Duplicate (Code/Dependency)",


    "WILDCARD_USAGE":            "WildCard Usage",
    "WILDCARD_VERSION_RANGES":   "WildCard Usage",
    "SUSPICIOUS_COMMENTS":       "Suspicious Comments",
    "SUSPICIOUS_COMMENT":        "Suspicious Comments",
    "COMMENTED_CODE":            "Suspicious Comments",


    "LACK_OF_ERROR_HANDLING":    "Lack Error Handling",
    "ERROR_HANDLING":            "Lack Error Handling",
    "MISSING_OR_IMPROPER_ERROR_HANDLING": "Lack Error Handling",
    "HARDCODED_PATHS_AND_URLS":  "Hardcoded Paths/URLs",
    "HARDCODED PATH/URL":        "Hardcoded Paths/URLs",
    "INSECURE_URLS":             "Insecure URLs",
    "HARD_CODED_PATH/URL":       "Hardcoded Paths & URLs",



    "UNUSED_FIND_PACKAGE":       None,
}


_SNAKE_RE = re.compile(r"(?<!^)_")  # split on underscores not at start
def _smell_id(func_name: str) -> str | None:
    if func_name.startswith("check_"):
        func_name = func_name[6:]           # strip the prefix
    parts = _SNAKE_RE.split(func_name)
    raw = "_".join(p.upper() for p in parts)
    # apply any override (None ⇒ drop this smell)
    if raw in _SMELL_OVERRIDES:
        return _SMELL_OVERRIDES[raw]
    return raw

def _collect_checks(module: ModuleType) -> List[Callable[[Any], List[Dict[str, str]]]]:
    checks: List[Callable[[Any], List[Dict[str, str]]]] = []
    for name, func in inspect.getmembers(module, inspect.isfunction):
        if name.startswith("check_"):
            sig = inspect.signature(func)
            if len(sig.parameters) == 1:
                checks.append(func)
    return checks

from .maven_parser import parse_pom
from .gradle_parser import parse_gradle
from .makefile_analyzer import parse_makefile_database, MakefileAnalysis, looks_like_makefile  # noqa: F401
from .cmake_parser import parse_cmake
from .maintainability_smells import (
    MaintainabilitySmellExtractor,
    extract_maintainability_smells,
)
from .security_smells import (
    SecuritySmellExtractor,
    extract_security_smells,
)


maven_sec  = reload(import_module("secure_linter.maven_security_checks"))
gradle_sec = reload(import_module("secure_linter.gradle_security_checks"))
make_sec   = reload(import_module("secure_linter.makefile_security_checks"))
cmake_sec  = reload(import_module("secure_linter.cmake_security_checks"))

MAVEN_CHECKS = _collect_checks(maven_sec)
GRADLE_CHECKS = _collect_checks(gradle_sec)
MAKE_CHECKS   = _collect_checks(make_sec)
CMAKE_CHECKS  = _collect_checks(cmake_sec)

def _run_checks(data: Any,
                checks: List[Callable[[Any], List[Dict[str, str]]]]
               ) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for chk in checks:
        sid = _smell_id(chk.__name__)
        # skip disabled smells
        if sid is None:
            continue
        try:
            for it in chk(data):
                it.setdefault("smell_id", sid)
                issues.append(it)
        except Exception as exc:
            issues.append({
                "smell_id": sid,
                "issue": f"{chk.__name__} raised: {exc}",
                "severity": "Low",
            })
    return issues
def lint_pom(file_path: str) -> List[Dict[str, str]]:
    import os, io, re
    from lxml import etree
    from secure_linter.maven_security_checks import (
        check_hardcoded_credentials,
        check_hardcoded_paths_and_urls,
        check_suspicious_comments,
    )

    pom_root = parse_pom(file_path)
    if pom_root is None:
        # fallback generic XML parse
        raw_bytes = open(file_path, "rb").read()
        text = raw_bytes.decode("utf-8", errors="ignore")
        text = re.sub(r"<\?xml[^>]*\?>", "", text)
        cleaned = "\n".join(
            re.sub(r"^\s*\d+[:\s]*", "", line)
            for line in text.splitlines()
        )

        parser = etree.XMLParser(recover=True)
        try:
            tree = etree.parse(io.BytesIO(cleaned.encode("utf-8")), parser)
            pom_root = tree.getroot()
        except Exception:
            os.remove(file_path)
            return [{"issue": "Failed to parse XML", "severity": "High"}]

        if pom_root is None:
            os.remove(file_path)
            return [{"issue": "Failed to recover XML root", "severity": "High"}]

        issues: List[Dict[str, str]] = []
        for chk in (
            check_hardcoded_credentials,
            check_hardcoded_paths_and_urls,
            check_suspicious_comments,
        ):
            sid = _smell_id(chk.__name__)
            if sid is None:
                continue
            try:
                for it in chk(pom_root):
                    it.setdefault("smell_id", sid)
                    issues.append(it)
            except Exception as exc:
                issues.append({
                    "smell_id": sid,
                    "issue": f"{chk.__name__} raised: {exc}",
                    "severity": "Low",
                })

        os.remove(file_path)
        return issues

    issues = _run_checks(pom_root, MAVEN_CHECKS)
    os.remove(file_path)
    return issues

def lint_gradle(file_path: str) -> List[Dict[str, str]]:
    gradle_data = parse_gradle(file_path)
    issues = _run_checks(gradle_data, GRADLE_CHECKS)
    os.remove(file_path)
    return issues

def lint_make(file_path: str) -> List[Dict[str, str]]:
    analysis = parse_makefile_database(file_path)
    issues = []
    if not analysis.targets and not analysis.variables:
        issues.append({
            "smell_id": "MAKEFILE_PARSE_FAILURE",
            "issue": "Could not obtain targets/vars – falling back to text scan.",
            "severity": "Medium",
        })

    with open(file_path, encoding="utf‑8", errors="ignore") as fh:
        analysis.raw_text = fh.read()

    issues.extend(_run_checks(analysis, MAKE_CHECKS))
    os.remove(file_path)
    return issues
def lint_cmake(file_path: str) -> List[Dict[str, str]]:
    cmake_data = parse_cmake(file_path)
    if cmake_data is None:
        return [{"issue": "File does not appear to be a valid CMake file.", "severity": "High"}]
    issues = _run_checks(cmake_data, CMAKE_CHECKS)
    os.remove(file_path)
    return issues

def check_if_cmake(file_path: str) -> bool:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as fh:
        snippet = fh.read(1024).lower()
    return any(
        token in snippet for token in (
            "cmake_minimum_required",
            "project(",
            "add_executable",
            "add_library",
        )
    )

def lint_file_to_record(file_path: str,
                        explicit_build_system: str | None = None
                       ) -> dict[str, object]:
    path = Path(file_path).resolve()
    name = os.path.basename(file_path).lower()
    build_system = explicit_build_system

    if build_system is None:
        if name.endswith(".xml"):
            root = parse_pom(str(path))
            if root is not None:
                tag = root.tag
                local = tag.split("}", 1)[-1] if tag.startswith("{") else tag
                if local.lower() == "project":
                    build_system = "maven"

        if build_system is None and (name.endswith(".gradle") or name.endswith(".gradle.kts")):
            build_system = "gradle"

        if build_system is None and ("cmakelists.txt" in name or check_if_cmake(str(path))):
            build_system = "cmake"

        if build_system is None and ("makefile" in name.lower()
                                     or name.lower().endswith(".mk")
                                     or looks_like_makefile(str(path))):
            build_system = "make"

        if build_system is None:
            raise ValueError(f"Cannot determine build system for {path}")

    if build_system == "maven":
        issues = lint_pom(str(path))
    elif build_system == "gradle":
        issues = lint_gradle(str(path))
    elif build_system == "cmake":
        issues = lint_cmake(str(path))
    elif build_system == "make":
        issues = lint_make(str(path))
    else:
        raise ValueError(f"Unknown build system: {build_system!r}")

    smells = sorted({it["smell_id"] for it in issues})
    if smells == ["MAKEFILE_PARSE_FAILURE"] or smells == {"MAKEFILE_PARSE_FAILURE"}:
        smells = []
    return {
        "build_system": build_system,
        "file_path": str(path),
        "smells": smells,
    }

__all__ = [
    "lint_pom",
    "lint_gradle",
    "lint_make",
    "lint_cmake",
    "check_if_cmake",
    "MaintainabilitySmellExtractor",
    "extract_maintainability_smells",
    "SecuritySmellExtractor",
    "extract_security_smells",
]
