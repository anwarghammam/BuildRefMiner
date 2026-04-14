from __future__ import annotations

import argparse
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
}


def _checks_for_build_type(build_type: str) -> list[tuple[str, CheckFn]]:
    if build_type == "ant":
        from . import ant_security_checks as ant_checks

        return [
            ("HARDCODED_CREDENTIALS", ant_checks.check_hardcoded_credentials),
            ("INSECURE_URLS", ant_checks.check_insecure_urls),
            ("WILDCARD_USAGE", ant_checks.check_wildcard_usage),
            ("HARDCODED_PATHS_AND_URLS", ant_checks.check_hardcoded_paths_and_urls),
        ]

    if build_type == "gradle":
        from . import gradle_security_checks as gradle_checks

        return [
            ("HARDCODED_CREDENTIALS", gradle_checks.check_hardcoded_credentials),
            ("HARDCODED_CREDENTIALS", gradle_checks.check_hardcoded_signing_credentials),
            ("INSECURE_URLS", gradle_checks.check_insecure_urls),
            ("WILDCARD_USAGE", gradle_checks.check_wildcard_usage),
            ("WILDCARD_USAGE", gradle_checks.check_wildcard_version_ranges),
            ("HARDCODED_PATHS_AND_URLS", gradle_checks.check_hardcoded_paths_and_urls),
        ]

    if build_type == "maven":
        from . import maven_security_checks as maven_checks

        return [
            ("HARDCODED_CREDENTIALS", maven_checks.check_hardcoded_credentials),
            ("INSECURE_URLS", maven_checks.check_insecure_urls),
            ("WILDCARD_USAGE", maven_checks.check_wildcard_version_ranges),
            ("HARDCODED_PATHS_AND_URLS", maven_checks.check_hardcoded_paths_and_urls),
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
        from .maven_parser import parse_pom

        root = parse_pom(str(path))
        if root is not None and "maven.apache.org/POM" in str(root.tag):
            return "maven"

    raise ValueError(f"Unsupported or unknown build system for {file_path!r}")


def _load_build_data(file_path: str, build_type: str) -> Any:
    if build_type == "ant":
        from .ant_parser import parse_ant

        data = parse_ant(file_path)
        if data is None:
            raise ValueError(f"Failed to parse Ant file: {file_path}")
        return data

    if build_type == "gradle":
        from .gradle_parser import parse_gradle

        return parse_gradle(file_path)

    if build_type == "maven":
        from .maven_parser import parse_pom

        data = parse_pom(file_path)
        if data is None:
            raise ValueError(f"Failed to parse Maven file: {file_path}")
        return data

    raise ValueError(f"Unsupported build type: {build_type!r}")


def _count_non_empty_lines(file_path: str) -> int:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
        return sum(1 for line in handle if line.strip())


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
    loc = _count_non_empty_lines(file_path)
    smell_count = len(smells)
    smell_summary = ";".join(sorted({smell["smell_id"] for smell in smells}))

    return {
        "file_path": str(Path(file_path).resolve()),
        "build_type": build_type,
        "smells": smells,
        "smell_count": smell_count,
        "smell_density": round((smell_count / max(loc, 1)) * 1000, 4),
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
