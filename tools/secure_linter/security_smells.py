from __future__ import annotations

import argparse
import importlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable

IssueList = list[dict[str, str]]
CheckFn = Callable[[Any], IssueList]


SMELL_LABELS: dict[str, str] = {
    "HARDCODED_CREDENTIALS": "Hardcoded Credentials",
    "INSECURE_URLS": "Insecure URLs",
    "WILDCARD_USAGE": "Wildcard Usage",
    "HARDCODED_PATHS_AND_URLS": "Hardcoded Paths/URLs",
    "DEPRECATED_DEPENDENCIES": "Deprecated Dependencies",
    "OUTDATED_DEPENDENCIES": "Outdated Dependencies",
}

SCRIPT_DIR = Path(__file__).resolve().parent
TOOLS_DIR = SCRIPT_DIR.parent
REPO_ROOT = TOOLS_DIR.parent

for path in (SCRIPT_DIR, TOOLS_DIR, REPO_ROOT):
    path_str = str(path)
    if path_str not in sys.path:
        sys.path.insert(0, path_str)


def _import_secure_linter_module(module_name: str):
    if __package__:
        return importlib.import_module(f"{__package__}.{module_name}")
    return importlib.import_module(module_name)


def _checks_for_build_type(build_type: str) -> list[tuple[str, CheckFn]]:
    if build_type == "ant":
        ant_checks = _import_secure_linter_module("ant_security_checks")
        ant_maintainability_checks = _import_secure_linter_module("ant_maintainability_checks")

        return [
            ("HARDCODED_CREDENTIALS", ant_checks.check_hardcoded_credentials),
            ("INSECURE_URLS", ant_checks.check_insecure_urls),
            ("WILDCARD_USAGE", ant_checks.check_wildcard_usage),
            ("HARDCODED_PATHS_AND_URLS", ant_checks.check_hardcoded_paths_and_urls),
            ("DEPRECATED_DEPENDENCIES", ant_maintainability_checks.check_deprecated_dependencies),
            ("OUTDATED_DEPENDENCIES", ant_maintainability_checks.check_outdated_dependencies),
        ]

    if build_type == "gradle":
        gradle_checks = _import_secure_linter_module("gradle_security_checks")

        return [
            ("HARDCODED_CREDENTIALS", gradle_checks.check_hardcoded_credentials),
            ("HARDCODED_CREDENTIALS", gradle_checks.check_hardcoded_signing_credentials),
            ("INSECURE_URLS", gradle_checks.check_insecure_urls),
            ("WILDCARD_USAGE", gradle_checks.check_wildcard_usage),
            ("WILDCARD_USAGE", gradle_checks.check_wildcard_version_ranges),
            ("HARDCODED_PATHS_AND_URLS", gradle_checks.check_hardcoded_paths_and_urls),
            ("DEPRECATED_DEPENDENCIES", gradle_checks.check_deprecated_dependencies),
            ("OUTDATED_DEPENDENCIES", gradle_checks.check_outdated_dependencies),
        ]

    if build_type == "maven":
        maven_checks = _import_secure_linter_module("maven_security_checks")

        return [
            ("HARDCODED_CREDENTIALS", maven_checks.check_hardcoded_credentials),
            ("INSECURE_URLS", maven_checks.check_insecure_urls),
            ("WILDCARD_USAGE", maven_checks.check_wildcard_version_ranges),
            ("HARDCODED_PATHS_AND_URLS", maven_checks.check_hardcoded_paths_and_urls),
            ("DEPRECATED_DEPENDENCIES", maven_checks.check_deprecated_dependencies),
            ("OUTDATED_DEPENDENCIES", maven_checks.check_outdated_dependencies),
        ]

    raise ValueError(f"Unsupported build type: {build_type!r}")


def detect_build_type(file_path: str) -> str:
    path = Path(file_path)
    name = path.name.lower()

    if name.endswith(".gradle") or name.endswith(".gradle.kts") or name.endswith(".groovy"):
        return "gradle"
    if name == "build.xml":
        return "ant"
    if name == "pom.xml":
        return "maven"

    if name.endswith(".xml"):
        parse_pom = _import_secure_linter_module("maven_parser").parse_pom

        root = parse_pom(str(path))
        if root is not None and "maven.apache.org/POM" in str(root.tag):
            return "maven"

    raise ValueError(f"Unsupported or unknown build system for {file_path!r}")


def _load_build_data(file_path: str, build_type: str) -> Any:
    if build_type == "ant":
        parse_ant = _import_secure_linter_module("ant_parser").parse_ant

        data = parse_ant(file_path)
        if data is None:
            raise ValueError(f"Failed to parse Ant file: {file_path}")
        return data

    if build_type == "gradle":
        parse_gradle = _import_secure_linter_module("gradle_parser").parse_gradle

        return parse_gradle(file_path)

    if build_type == "maven":
        parse_pom = _import_secure_linter_module("maven_parser").parse_pom

        data = parse_pom(file_path)
        if data is None:
            raise ValueError(f"Failed to parse Maven file: {file_path}")
        return data

    raise ValueError(f"Unsupported build type: {build_type!r}")


def _count_non_empty_lines(file_path: str) -> int:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
        return sum(1 for line in handle if line.strip())


def _count_bloc(file_path: str) -> int:
    try:
        repo_root = Path(__file__).resolve().parents[2]
        if str(repo_root) not in sys.path:
            sys.path.insert(0, str(repo_root))

        from metrics.BLOC import compute_bloc

        return compute_bloc(file_path)
    except Exception:
        return _count_non_empty_lines(file_path)


def _normalize_issue(smell_id: str, issue: dict[str, str]) -> dict[str, str]:
    return {
        "smell_id": smell_id,
        "smell_label": SMELL_LABELS[smell_id],
        "issue": issue.get("issue", "").strip(),
        "severity": issue.get("severity", "Low"),
    }


def _run_checks(data: Any, checks: list[tuple[str, CheckFn]]) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    seen: set[tuple[str, str]] = set()

    for smell_id, check_fn in checks:
        try:
            issues = check_fn(data)
        except Exception as exc:
            issues = [{
                "issue": f"{check_fn.__name__} raised: {exc}",
                "severity": "Low",
            }]

        for raw_issue in issues:
            normalized = _normalize_issue(smell_id, raw_issue)
            dedupe_key = (normalized["smell_id"], normalized["issue"])
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            findings.append(normalized)

    return findings


def _format_result(file_path: str, build_type: str, smells: list[dict[str, str]]) -> dict[str, Any]:
    bloc = _count_bloc(file_path)
    smell_count = len(smells)
    smell_summary = ";".join(sorted({smell["smell_id"] for smell in smells}))

    return {
        "file_path": str(Path(file_path).resolve()),
        "build_type": build_type,
        "smells": smells,
        "smell_count": smell_count,
        "smell_density": round(smell_count / max(bloc, 1), 4),
        "smell_summary": smell_summary,
    }


class SecuritySmellExtractor:
    def detect_smells(self, file_path: str, build_type: str | None = None) -> dict[str, Any]:
        if not file_path or not os.path.exists(file_path):
            return self.empty_result()

        normalized_build_type = (build_type or detect_build_type(file_path)).strip().lower()
        supported = ("ant", "gradle", "maven")
        if normalized_build_type not in supported:
            raise ValueError(
                f"Unsupported build type {normalized_build_type!r}. "
                f"Supported types: {', '.join(sorted(supported))}"
            )

        data = _load_build_data(file_path, normalized_build_type)
        smells = _run_checks(data, _checks_for_build_type(normalized_build_type))
        return _format_result(file_path, normalized_build_type, smells)

    @staticmethod
    def empty_result() -> dict[str, Any]:
        return {
            "file_path": "",
            "build_type": "",
            "smells": [],
            "smell_count": 0,
            "smell_density": 0.0,
            "smell_summary": "",
        }


def extract_security_smells(file_path: str, build_type: str | None = None) -> dict[str, Any]:
    return SecuritySmellExtractor().detect_smells(file_path, build_type=build_type)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Extract security smells using the secure_linter parser/checker modules."
    )
    parser.add_argument("file_path", help="Path to the build file to analyze")
    parser.add_argument(
        "--build-type",
        choices=["ant", "gradle", "maven"],
        help="Optional explicit build type. Defaults to auto-detection.",
    )
    args = parser.parse_args(argv)

    try:
        result = extract_security_smells(args.file_path, build_type=args.build_type)
    except Exception as exc:
        print(str(exc), file=sys.stderr)
        return 1

    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
