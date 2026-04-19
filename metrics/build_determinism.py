from __future__ import annotations

import os
import re
from typing import Any


TIME_PATTERNS = [
    re.compile(r"\bSystem\.currentTimeMillis\s*\("),
    re.compile(r"\bSystem\.nanoTime\s*\("),
    re.compile(r"\bnew\s+Date\s*\("),
    re.compile(r"\bInstant\.now\s*\("),
    re.compile(r"\bLocalDateTime\.now\s*\("),
    re.compile(r"\bLocalDate\.now\s*\("),
    re.compile(r"\bLocalTime\.now\s*\("),
    re.compile(r"\bZonedDateTime\.now\s*\("),
    re.compile(r"\bOffsetDateTime\.now\s*\("),
    re.compile(r"\bCalendar\.getInstance\s*\("),
    re.compile(r"\$\{maven\.build\.timestamp\}"),
]

RANDOMNESS_PATTERNS = [
    re.compile(r"\bMath\.random\s*\("),
    re.compile(r"\bnew\s+Random\s*\("),
    re.compile(r"\bnew\s+SecureRandom\s*\("),
    re.compile(r"\bThreadLocalRandom\.current\s*\("),
    re.compile(r"\bUUID\.randomUUID\s*\("),
    re.compile(r"\$RANDOM\b"),
]

NON_REPRODUCIBLE_STEP_PATTERNS = [
    re.compile(r"\bcurl\b", re.IGNORECASE),
    re.compile(r"\bwget\b", re.IGNORECASE),
    re.compile(r"\bInvoke-WebRequest\b", re.IGNORECASE),
    re.compile(r"\bgit\s+clone\b", re.IGNORECASE),
    re.compile(r"\bsvn\s+checkout\b", re.IGNORECASE),
    re.compile(r"<get\b", re.IGNORECASE),
]

PATTERN_GROUPS = {
    "TIME": TIME_PATTERNS,
    "RANDOMNESS": RANDOMNESS_PATTERNS,
    "NON_REPRODUCIBLE_STEP": NON_REPRODUCIBLE_STEP_PATTERNS,
}


def empty_build_determinism_result() -> dict[str, Any]:
    return {
        "non_deterministic_construct_count": 0,
        "non_deterministic_summary": "",
        "bds": 0.0,
    }


def compute_build_determinism(file_path: str, bloc: int) -> dict[str, Any]:
    if not file_path or not os.path.exists(file_path):
        return empty_build_determinism_result()

    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
        lines = handle.readlines()

    findings: list[tuple[int, str, str]] = []
    seen: set[tuple[int, str]] = set()

    for line_number, line in enumerate(lines, start=1):
        for label, patterns in PATTERN_GROUPS.items():
            for pattern in patterns:
                if not pattern.search(line):
                    continue
                key = (line_number, label)
                if key in seen:
                    continue
                seen.add(key)
                findings.append((line_number, label, line.strip()))

    count = len(findings)
    summary = ";".join(sorted({label for _, label, _ in findings}))
    bds = round(max(0.0, 1 - (count / max(bloc, 1))), 4) if bloc > 0 else 0.0

    return {
        "non_deterministic_construct_count": count,
        "non_deterministic_summary": summary,
        "bds": bds,
    }
