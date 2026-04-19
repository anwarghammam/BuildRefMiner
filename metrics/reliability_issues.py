RELIABILITY_MAINTAINABILITY_SMELLS = [
    "DEPRECATED_DEPENDENCIES",
    "OUTDATED_DEPENDENCIES",
]

RELIABILITY_SECURITY_SMELLS = [
    "HARDCODED_CREDENTIALS",
    "INSECURE_URLS",
    "WILDCARD_USAGE",
    "HARDCODED_PATHS_AND_URLS",
]


def count_smells(smell_result: dict, tracked_smells: list[str]) -> int:
    tracked = set(tracked_smells)
    return sum(1 for smell in smell_result.get("smells", []) if smell.get("smell_id") in tracked)


def compute_reliability_issue_count(maintainability_result: dict, security_result: dict) -> int:
    return count_smells(maintainability_result, RELIABILITY_MAINTAINABILITY_SMELLS) + count_smells(
        security_result,
        RELIABILITY_SECURITY_SMELLS,
    )


def compute_reliability_score(issue_count: int, bloc: int) -> float:
    if bloc <= 0:
        return 0.0
    return round(max(0.0, 1 - (issue_count / bloc)), 4)
