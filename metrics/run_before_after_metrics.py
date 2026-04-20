import os
import sys
import csv
import io
import shutil
import argparse
import types
import importlib.util
from urllib.parse import urlparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

for path in (BASE_DIR, REPO_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from metrics.BLOC import compute_bloc, compute_comment_ratio, compute_line_stats_with_scc
from cyclomatic_complexity import (
    calculate_ant_build_logic_complexity,
    calculate_maven_build_logic_complexity,
    calculate_gradle_cc,
    calculate_gradle_kts_cc,
)
from halstead_volume import compute_halstead
from clone_density import compute_clone_density
from comment_readability import compute_comment_readability_stats
from build_cohesion import compute_build_cohesion_value
from coupling import compute_build_coupling
from dependency_stability import compute_dependency_stability
from external_dependency_risk import compute_external_dependency_risk
from build_determinism import compute_build_determinism
from modularity_metrics import write_modularity_summary
from reliability_issues import compute_reliability_issue_count, compute_reliability_score
from reliability_metrics import write_reliability_summary
from reliability_metric import compute_overall_reliability
from security_metrics import write_security_summary
from understandability_metrics import write_understandability_summary
from github_commits_util import (
    get_changed_build_files,
    materialize_before_after_files,
    materialize_project_snapshot,
)
from style_conformance import (
    calculate_gradle_kts_style_violations,
    calculate_gradle_style_violations,
    compute_style_score,
    count_ant_style_violations,
    count_maven_style_violations,
)

OUTPUT_FOLDER = os.path.join(BASE_DIR, "..", "results")
SUMMARY_CSV = os.path.join(BASE_DIR, "..", "results", "summary_metrics.csv")
MAINTAINABILITY_CSV = os.path.join(BASE_DIR, "..", "results", "maintainability_metrics.csv")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)


# --------------------------------------------------
# Generic build-tool detection for any repository
# --------------------------------------------------
BUILD_TOOL_RULES = {
    "Ant": ["build.xml"],
    "Maven": ["pom.xml"],
    "Gradle": [".gradle", ".gradle.kts"],
    "Gradle/Groovy": [".groovy"],
}

TRACKED_SMELLS = [
    "EMPTY_INCOMPLETE_TAGS",
    "INCONSISTENT_DEPENDENCY_MANAGEMENT",
    "LACK_OF_ERROR_HANDLING",
    "MISSING_DEPENDENCY_VERSION",
    "SUSPICIOUS_COMMENTS",
    "DEPRECATED_DEPENDENCIES",
    "OUTDATED_DEPENDENCIES",
]

TRACKED_SECURITY_SMELLS = [
    "HARDCODED_CREDENTIALS",
    "INSECURE_URLS",
    "WILDCARD_USAGE",
    "HARDCODED_PATHS_AND_URLS",
]

_SMELL_EXTRACTOR_IMPORT_FAILED = False
_EXTRACT_MAINTAINABILITY_SMELLS = None
_SECURITY_SMELL_EXTRACTOR_IMPORT_FAILED = False
_EXTRACT_SECURITY_SMELLS = None

try:
    from build_modularity import compute_project_modularity
except ImportError:
    def compute_project_modularity(project_dir: str) -> float:
        return 0.0


def detect_build_tool(file_path: str) -> str:
    """
    Detect the build tool dynamically from a file path or file name.
    This makes the framework reusable across any repository and
    supports mixed-build repositories as well.
    """
    name = os.path.basename(file_path).lower()

    for tool, patterns in BUILD_TOOL_RULES.items():
        for pattern in patterns:
            if name == pattern or name.endswith(pattern):
                return tool

    return "Unknown"


def normalize_build_type_for_smells(tool_name: str) -> str:
    tool_name = (tool_name or "").strip().lower()

    if tool_name == "ant":
        return "ant"
    elif tool_name == "maven":
        return "maven"
    elif tool_name == "gradle":
        return "gradle"
    elif tool_name == "gradle/groovy":
        return "gradle"
    elif tool_name == "cmake":
        return "cmake"
    elif tool_name == "make":
        return "make"

    return "unknown"


def empty_smell_result() -> dict:
    return {
        "file_path": "",
        "build_type": "",
        "smells": [],
        "smell_count": 0,
        "smell_density": 0.0,
        "smell_summary": "",
    }


def format_smell_result(file_path: str, build_type: str, smells: list[dict]) -> dict:
    loc = compute_bloc(file_path) if file_path and os.path.exists(file_path) else 0
    smell_count = len(smells)
    smell_summary = ";".join(sorted({s["smell_id"] for s in smells})) if smells else ""

    return {
        "file_path": file_path,
        "build_type": build_type,
        "smells": smells,
        "smell_count": smell_count,
        "smell_density": round(smell_count / max(loc, 1), 4),
        "smell_summary": smell_summary,
    }


def compute_smells_for_snapshot(snapshot_path: str, tool_name: str) -> dict:
    global _SMELL_EXTRACTOR_IMPORT_FAILED, _EXTRACT_MAINTAINABILITY_SMELLS

    if not snapshot_path or not os.path.exists(snapshot_path):
        return empty_smell_result()

    build_type = normalize_build_type_for_smells(tool_name)
    if build_type == "unknown":
        return empty_smell_result()

    if _EXTRACT_MAINTAINABILITY_SMELLS is None and not _SMELL_EXTRACTOR_IMPORT_FAILED:
        try:
            tools_dir = os.path.join(REPO_ROOT, "tools")
            package_dir = os.path.join(tools_dir, "secure_linter")
            module_path = os.path.join(package_dir, "maintainability_smells.py")

            if "tools" not in sys.modules:
                tools_pkg = types.ModuleType("tools")
                tools_pkg.__path__ = [tools_dir]
                sys.modules["tools"] = tools_pkg

            if "tools.secure_linter" not in sys.modules:
                secure_linter_pkg = types.ModuleType("tools.secure_linter")
                secure_linter_pkg.__path__ = [package_dir]
                sys.modules["tools.secure_linter"] = secure_linter_pkg

            spec = importlib.util.spec_from_file_location(
                "tools.secure_linter.maintainability_smells",
                module_path,
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load spec for {module_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            _EXTRACT_MAINTAINABILITY_SMELLS = module.extract_maintainability_smells
        except Exception as exc:
            if not _SMELL_EXTRACTOR_IMPORT_FAILED:
                print(f"[WARN] Maintainability smell extractor unavailable: {exc}")
                _SMELL_EXTRACTOR_IMPORT_FAILED = True
            return empty_smell_result()

    try:
        return _EXTRACT_MAINTAINABILITY_SMELLS(snapshot_path, build_type=build_type)
    except Exception as exc:
        print(f"[WARN] Smell extraction failed for {snapshot_path}: {exc}")
        return empty_smell_result()


def compute_security_smells_for_snapshot(snapshot_path: str, tool_name: str) -> dict:
    global _SECURITY_SMELL_EXTRACTOR_IMPORT_FAILED, _EXTRACT_SECURITY_SMELLS

    if not snapshot_path or not os.path.exists(snapshot_path):
        return empty_smell_result()

    build_type = normalize_build_type_for_smells(tool_name)
    if build_type not in {"ant", "gradle", "maven"}:
        return empty_smell_result()

    if _EXTRACT_SECURITY_SMELLS is None and not _SECURITY_SMELL_EXTRACTOR_IMPORT_FAILED:
        try:
            tools_dir = os.path.join(REPO_ROOT, "tools")
            package_dir = os.path.join(tools_dir, "secure_linter")
            module_path = os.path.join(package_dir, "security_smells.py")

            if "tools" not in sys.modules:
                tools_pkg = types.ModuleType("tools")
                tools_pkg.__path__ = [tools_dir]
                sys.modules["tools"] = tools_pkg

            if "tools.secure_linter" not in sys.modules:
                secure_linter_pkg = types.ModuleType("tools.secure_linter")
                secure_linter_pkg.__path__ = [package_dir]
                sys.modules["tools.secure_linter"] = secure_linter_pkg

            spec = importlib.util.spec_from_file_location(
                "tools.secure_linter.security_smells",
                module_path,
            )
            if spec is None or spec.loader is None:
                raise ImportError(f"Could not load spec for {module_path}")

            module = importlib.util.module_from_spec(spec)
            sys.modules[spec.name] = module
            spec.loader.exec_module(module)
            _EXTRACT_SECURITY_SMELLS = module.extract_security_smells
        except Exception as exc:
            if not _SECURITY_SMELL_EXTRACTOR_IMPORT_FAILED:
                print(f"[WARN] Security smell extractor unavailable: {exc}")
                _SECURITY_SMELL_EXTRACTOR_IMPORT_FAILED = True
            return empty_smell_result()

    try:
        return _EXTRACT_SECURITY_SMELLS(snapshot_path, build_type=build_type)
    except Exception as exc:
        print(f"[WARN] Security smell extraction failed for {snapshot_path}: {exc}")
        return empty_smell_result()


def compute_cc(snapshot_path: str, original_file_path: str) -> int:
    """
    Select the correct cyclomatic complexity calculator
    based on the detected build tool.
    """
    if not snapshot_path or not os.path.exists(snapshot_path):
        return 0

    tool = detect_build_tool(original_file_path)

    if tool == "Ant":
        return calculate_ant_build_logic_complexity(snapshot_path)
    elif tool == "Maven":
        return calculate_maven_build_logic_complexity(snapshot_path)
    elif original_file_path.lower().endswith(".gradle.kts"):
        return calculate_gradle_kts_cc(snapshot_path) or 0
    elif tool == "Gradle":
        return calculate_gradle_cc(snapshot_path) or 0

    return 0


def compute_halstead_for_snapshot(snapshot_path: str, original_filename: str) -> float:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return 0.0
    return compute_halstead(os.path.basename(original_filename), snapshot_path)


def normalize_metric_by_bloc(value: float | int, bloc: int) -> float:
    if bloc <= 0:
        return 0.0
    return round(float(value) / bloc, 4)


def compute_style_conformance_for_snapshot(snapshot_path: str, original_file_path: str) -> float:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return 0.0

    bloc = compute_bloc(snapshot_path)
    if bloc <= 0:
        return 0.0

    tool = detect_build_tool(original_file_path)

    if tool == "Ant":
        weighted_violations = count_ant_style_violations(snapshot_path)
    elif tool == "Maven":
        weighted_violations = count_maven_style_violations(snapshot_path)
    elif original_file_path.lower().endswith(".gradle.kts"):
        weighted_violations = calculate_gradle_kts_style_violations(snapshot_path)
    elif tool == "Gradle":
        weighted_violations = calculate_gradle_style_violations(snapshot_path)
    else:
        return 0.0

    score = compute_style_score(bloc, weighted_violations) if weighted_violations is not None else None
    return round(score, 2) if score is not None else 0.0


def compute_comment_ratio_for_snapshot(snapshot_path: str) -> float:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return 0.0
    return compute_comment_ratio(snapshot_path)


def compute_comment_readability_for_snapshot(snapshot_path: str) -> dict:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return {
            "sentence_count": 0,
            "word_count": 0,
            "syllable_count": 0,
            "flesch_reading_ease": 0.0,
        }
    return compute_comment_readability_stats(snapshot_path)


def compute_clone_density_for_snapshot(snapshot_path: str) -> float:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return 0.0
    return compute_clone_density(snapshot_path)


def compute_build_cohesion_for_snapshot(snapshot_path: str) -> float:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return 0.0
    return compute_build_cohesion_value(snapshot_path)


def compute_build_coupling_for_snapshot(snapshot_path: str, project_dir: str, bloc: int) -> dict:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return {
            "cp_internal": 0,
            "cp_external": 0,
            "cp_total": 0,
            "ncp_internal": 0.0,
            "ncp_external": 0.0,
            "coupling_ratio": 0.0,
        }
    try:
        return compute_build_coupling(snapshot_path, project_dir=project_dir, bloc=bloc)
    except Exception as exc:
        print(f"[WARN] Build coupling failed for {snapshot_path}: {exc}")
        return {
            "cp_internal": 0,
            "cp_external": 0,
            "cp_total": 0,
            "ncp_internal": 0.0,
            "ncp_external": 0.0,
            "coupling_ratio": 0.0,
        }


def compute_dependency_stability_for_snapshot(snapshot_path: str) -> dict:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return {
            "dependency_count": 0,
            "fixed_dependency_count": 0,
            "dynamic_dependency_count": 0,
            "snapshot_dependency_count": 0,
            "unknown_dependency_count": 0,
            "dss": 0.0,
        }
    try:
        return compute_dependency_stability(snapshot_path)
    except Exception as exc:
        print(f"[WARN] Dependency stability failed for {snapshot_path}: {exc}")
        return {
            "dependency_count": 0,
            "fixed_dependency_count": 0,
            "dynamic_dependency_count": 0,
            "snapshot_dependency_count": 0,
            "unknown_dependency_count": 0,
            "dss": 0.0,
        }


def compute_build_determinism_for_snapshot(snapshot_path: str, bloc: int) -> dict:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return {
            "non_deterministic_construct_count": 0,
            "non_deterministic_summary": "",
            "bds": 0.0,
        }
    try:
        return compute_build_determinism(snapshot_path, bloc)
    except Exception as exc:
        print(f"[WARN] Build determinism failed for {snapshot_path}: {exc}")
        return {
            "non_deterministic_construct_count": 0,
            "non_deterministic_summary": "",
            "bds": 0.0,
        }


def empty_change_activity_result() -> dict:
    return {
        "raw_churn": 0,
        "raw_change_frequency": 0,
        "avg_logical_loc": 0.0,
        "normalized_churn": 0.0,
        "normalized_change_frequency": 0.0,
        "window_days": 30,
    }


def compute_change_activity_metric(owner: str, repo: str, file_path: str, commit_sha: str, token: str) -> dict:
    if not commit_sha:
        return empty_change_activity_result()

    try:
        from change_activity import compute_change_activity_for_file_at_commit
    except Exception as exc:
        print(f"[WARN] Change activity metrics unavailable: {exc}")
        return empty_change_activity_result()

    try:
        return compute_change_activity_for_file_at_commit(owner, repo, file_path, commit_sha, token)
    except Exception as exc:
        print(f"[WARN] Change activity computation failed for {file_path} @ {commit_sha}: {exc}")
        return empty_change_activity_result()


def flatten_smell_result(prefix: str, smell_result: dict, tracked_smells: list[str], base_label: str = "Smell") -> dict:
    row = {
        f"{prefix}_{base_label}_Count": smell_result.get("smell_count", 0),
        f"{prefix}_{base_label}_Density": smell_result.get("smell_density", 0.0),
        f"{prefix}_{base_label}_Summary": smell_result.get("smell_summary", "")
    }

    smell_ids = {s["smell_id"] for s in smell_result.get("smells", [])}

    for smell in tracked_smells:
        row[f"{prefix}_{smell}"] = 1 if smell in smell_ids else 0

    return row


def write_summary(
    rows: list[dict],
    output_path: str | None = None,
    append: bool = True,
) -> None:
    header = [
        "Commit_SHA",
        "Parent_SHA",
        "File_Path",
        "File_Name",
        "Tool",
        "Status",
        "Additions",
        "Deletions",
        "Changes",
        "BLOC_Before",
        "BLOC_After",
        "Cyclomatic_Complexity_Before",
        "Cyclomatic_Complexity_After",
        "Normalized_CC_Before",
        "Normalized_CC_After",
        "Halstead_Volume_Before",
        "Halstead_Volume_After",
        "Normalized_HV_Before",
        "Normalized_HV_After",
        "Dependency_Count_Before",
        "Dependency_Count_After",
        "Fixed_Dependency_Count_Before",
        "Fixed_Dependency_Count_After",
        "Dynamic_Dependency_Count_Before",
        "Dynamic_Dependency_Count_After",
        "Snapshot_Dependency_Count_Before",
        "Snapshot_Dependency_Count_After",
        "Unknown_Dependency_Count_Before",
        "Unknown_Dependency_Count_After",
        "DSS_Before",
        "DSS_After",
        "DSS_Delta",
        "Non_Deterministic_Constructs_Before",
        "Non_Deterministic_Constructs_After",
        "Non_Deterministic_Summary_Before",
        "Non_Deterministic_Summary_After",
        "BDS_Before",
        "BDS_After",
        "BDS_Delta",
        "Comment_Ratio_Before",
        "Comment_Ratio_After",
        "Comment_Readability_Before",
        "Comment_Readability_After",
        "Style_Conformance_Score_Before",
        "Style_Conformance_Score_After",
        "Clone_Density_Before",
        "Clone_Density_After",
        "CP_Internal_Before",
        "CP_Internal_After",
        "CP_External_Before",
        "CP_External_After",
        "CP_Total_Before",
        "CP_Total_After",
        "NCP_Internal_Before",
        "NCP_Internal_After",
        "NCP_External_Before",
        "NCP_External_After",
        "Coupling_Ratio_Before",
        "Coupling_Ratio_After",
        "External_Risk_Factors_Before",
        "External_Risk_Factors_After",
        "EDR_Before",
        "EDR_After",
        "EDR_Delta",
        "Build_Cohesion_Before",
        "Build_Cohesion_After",
        "Build_Modularity_Before",
        "Build_Modularity_After",
        "Churn_Before",
        "Churn_After",
        "Change_Frequency_Before",
        "Change_Frequency_After",
        "Avg_Logical_LOC_Before",
        "Avg_Logical_LOC_After",
        "Normalized_Churn_Before",
        "Normalized_Churn_After",
        "Normalized_Change_Frequency_Before",
        "Normalized_Change_Frequency_After",
        "Observation_Window_Days",
        "Reliability_Issues_Before",
        "Reliability_Issues_After",
        "RE_Before",
        "RE_After",
        "RE_Delta",
        "RM_Before",
        "RM_After",
        "RM_Delta",
        "Before_Smell_Count",
        "After_Smell_Count",
        "Before_Smell_Density",
        "After_Smell_Density",
        "Before_Smell_Summary",
        "After_Smell_Summary",
        "Smell_Count_Delta",
        "Smell_Density_Delta",
        "Introduced_Smells",
        "Removed_Smells",
        "Before_Security_Smell_Count",
        "After_Security_Smell_Count",
        "Before_Security_Smell_Density",
        "After_Security_Smell_Density",
        "Before_Security_Smell_Summary",
        "After_Security_Smell_Summary",
        "Security_Smell_Count_Delta",
        "Security_Smell_Density_Delta",
        "Introduced_Security_Smells",
        "Removed_Security_Smells",

        "Before_EMPTY_INCOMPLETE_TAGS",
        "Before_INCONSISTENT_DEPENDENCY_MANAGEMENT",
        "Before_LACK_OF_ERROR_HANDLING",
        "Before_MISSING_DEPENDENCY_VERSION",
        "Before_SUSPICIOUS_COMMENTS",
        "Before_DEPRECATED_DEPENDENCIES",
        "Before_OUTDATED_DEPENDENCIES",

        "After_EMPTY_INCOMPLETE_TAGS",
        "After_INCONSISTENT_DEPENDENCY_MANAGEMENT",
        "After_LACK_OF_ERROR_HANDLING",
        "After_MISSING_DEPENDENCY_VERSION",
        "After_SUSPICIOUS_COMMENTS",
        "After_DEPRECATED_DEPENDENCIES",
        "After_OUTDATED_DEPENDENCIES",
        "Before_HARDCODED_CREDENTIALS",
        "Before_INSECURE_URLS",
        "Before_WILDCARD_USAGE",
        "Before_HARDCODED_PATHS_AND_URLS",
        "After_HARDCODED_CREDENTIALS",
        "After_INSECURE_URLS",
        "After_WILDCARD_USAGE",
        "After_HARDCODED_PATHS_AND_URLS",
    ]

    target_path = output_path or SUMMARY_CSV
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    file_exists = os.path.exists(target_path)
    write_header = True
    mode = "a" if append else "w"

    if append and file_exists and os.path.getsize(target_path) > 0:
        with open(target_path, "r", encoding="utf-8", newline="") as existing:
            first_line = existing.readline().strip()
        expected_header = ",".join(header)
        if first_line == expected_header:
            write_header = False
        else:
            print(f"[WARN] Rewriting {target_path} to match updated smell columns.")
            mode = "w"

    with open(target_path, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)

        if write_header:
            writer.writeheader()

        writer.writerows(rows)

    print(f"\nResults appended to: {target_path}")


def maintainability_row_from_summary(row: dict) -> dict:
    cc_before = row.get("Cyclomatic_Complexity_Before", 0) or 0
    cc_after = row.get("Cyclomatic_Complexity_After", 0) or 0

    return {
        "Commit_SHA": row.get("Commit_SHA", ""),
        "Parent_SHA": row.get("Parent_SHA", ""),
        "File_Path": row.get("File_Path", ""),
        "File_Name": row.get("File_Name", ""),
        "Tool": row.get("Tool", ""),
        "Status": row.get("Status", ""),
        "BLOC_Before": row.get("BLOC_Before", 0),
        "BLOC_After": row.get("BLOC_After", 0),
        "Cyclomatic_Complexity_Before": cc_before,
        "Cyclomatic_Complexity_After": cc_after,
        "Normalized_CC_Before": row.get("Normalized_CC_Before", 0.0),
        "Normalized_CC_After": row.get("Normalized_CC_After", 0.0),
        "Halstead_Volume_Before": row.get("Halstead_Volume_Before", 0.0),
        "Halstead_Volume_After": row.get("Halstead_Volume_After", 0.0),
        "Normalized_HV_Before": row.get("Normalized_HV_Before", 0.0),
        "Normalized_HV_After": row.get("Normalized_HV_After", 0.0),
        "Clone_Density_Before": row.get("Clone_Density_Before", ""),
        "Clone_Density_After": row.get("Clone_Density_After", ""),
        "Maintainability_Smell_Count_Before": row.get("Before_Smell_Count", 0),
        "Maintainability_Smell_Count_After": row.get("After_Smell_Count", 0),
        "Maintainability_Smell_Density_Before": row.get("Before_Smell_Density", 0.0),
        "Maintainability_Smell_Density_After": row.get("After_Smell_Density", 0.0),
        "Maintainability_Smell_Summary_Before": row.get("Before_Smell_Summary", ""),
        "Maintainability_Smell_Summary_After": row.get("After_Smell_Summary", ""),
    }


def write_maintainability_summary(
    rows: list[dict],
    output_path: str | None = None,
    append: bool = True,
) -> None:
    header = [
        "Commit_SHA",
        "Parent_SHA",
        "File_Path",
        "File_Name",
        "Tool",
        "Status",
        "BLOC_Before",
        "BLOC_After",
        "Cyclomatic_Complexity_Before",
        "Cyclomatic_Complexity_After",
        "Normalized_CC_Before",
        "Normalized_CC_After",
        "Halstead_Volume_Before",
        "Halstead_Volume_After",
        "Normalized_HV_Before",
        "Normalized_HV_After",
        "Clone_Density_Before",
        "Clone_Density_After",
        "Maintainability_Smell_Count_Before",
        "Maintainability_Smell_Count_After",
        "Maintainability_Smell_Density_Before",
        "Maintainability_Smell_Density_After",
        "Maintainability_Smell_Summary_Before",
        "Maintainability_Smell_Summary_After",
    ]

    maintainability_rows = [maintainability_row_from_summary(row) for row in rows]
    target_path = output_path or MAINTAINABILITY_CSV
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    file_exists = os.path.exists(target_path)
    write_header = True
    mode = "a" if append else "w"

    if append and file_exists and os.path.getsize(target_path) > 0:
        with open(target_path, "r", encoding="utf-8", newline="") as existing:
            first_line = existing.readline().strip()
        expected_header = ",".join(header)
        if first_line == expected_header:
            write_header = False
        else:
            print(f"[WARN] Rewriting {target_path} to match updated maintainability columns.")
            mode = "w"

    with open(target_path, mode, newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)

        if write_header:
            writer.writeheader()

        writer.writerows(maintainability_rows)

    print(f"Maintainability results appended to: {target_path}")


def commit_output_dir(owner: str, repo: str, commit_sha: str) -> str:
    return os.path.join(OUTPUT_FOLDER, "commits", commit_sha)


def remove_legacy_commit_subdirectories(target_dir: str) -> None:
    if not os.path.isdir(target_dir):
        return

    for entry in os.scandir(target_dir):
        if entry.is_dir():
            shutil.rmtree(entry.path, ignore_errors=True)


def write_commit_csv_bundle(owner: str, repo: str, commit_sha: str, rows: list[dict]) -> None:
    commit_rows = [row for row in rows if row.get("File_Path") != "__COMMIT_TOTAL__"]
    target_dir = commit_output_dir(owner, repo, commit_sha)
    os.makedirs(target_dir, exist_ok=True)
    remove_legacy_commit_subdirectories(target_dir)

    write_summary(
        commit_rows,
        output_path=os.path.join(target_dir, "summary_metrics.csv"),
        append=False,
    )
    write_maintainability_summary(
        commit_rows,
        output_path=os.path.join(target_dir, "maintainability_metrics.csv"),
        append=False,
    )
    write_modularity_summary(
        commit_rows,
        output_path=os.path.join(target_dir, "modularity_metrics.csv"),
        append=False,
    )
    write_reliability_summary(
        commit_rows,
        output_path=os.path.join(target_dir, "reliability_metrics.csv"),
        append=False,
    )
    write_security_summary(
        commit_rows,
        output_path=os.path.join(target_dir, "security_metrics.csv"),
        append=False,
    )
    write_understandability_summary(
        commit_rows,
        output_path=os.path.join(target_dir, "understandability_metrics.csv"),
        append=False,
    )


def cleanup_temp_files(*paths):
    for path in paths:
        if path and os.path.exists(path):
            try:
                if os.path.isdir(path):
                    shutil.rmtree(path)
                else:
                    os.remove(path)
            except Exception as e:
                print(f"[WARN] Could not remove temp path {path}: {e}")


def canonicalize_column_name(name: str) -> str:
    return (name or "").strip().lower().replace("-", "_").replace(" ", "_")


def first_matching_column(field_map: dict[str, str], aliases: list[str]) -> str | None:
    for alias in aliases:
        if alias in field_map:
            return field_map[alias]
    return None


def parse_owner_repo_from_value(value: str) -> tuple[str, str]:
    text = (value or "").strip()
    if not text:
        return "", ""

    if text.startswith("http://") or text.startswith("https://"):
        parsed = urlparse(text)
        parts = [part for part in parsed.path.strip("/").split("/") if part]
        if len(parts) >= 2:
            owner = parts[0].strip()
            repo = parts[1].strip()
            if repo.endswith(".git"):
                repo = repo[:-4]
            return owner, repo
        return "", ""

    if "/" in text:
        owner, repo = text.split("/", 1)
        repo = repo[:-4] if repo.endswith(".git") else repo
        return owner.strip(), repo.strip()

    return "", text


def read_commit_jobs_from_csv(csv_path: str) -> list[dict[str, str]]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        content = f.read()

    if not content.strip():
        raise ValueError("CSV file is empty.")

    try:
        dialect = csv.Sniffer().sniff(content[:4096], delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel

    reader = csv.DictReader(io.StringIO(content), dialect=dialect)
    if not reader.fieldnames:
        raise ValueError("CSV file must include a header row.")

    field_map = {canonicalize_column_name(name): name for name in reader.fieldnames}

    owner_column = first_matching_column(field_map, ["owner", "org", "organization"])
    repo_column = first_matching_column(field_map, ["repo", "repository", "repo_name"])
    url_column = first_matching_column(field_map, ["url", "repo_url", "repository_url", "html_url"])
    commit_column = first_matching_column(field_map, ["commit_sha", "commithash", "commit_hash", "sha"])

    if not commit_column:
        raise ValueError(
            "CSV file is missing a commit column. Supported names include: "
            "commit_sha, CommitHash, commit_hash, sha."
        )

    if not owner_column and not repo_column and not url_column:
        raise ValueError(
            "CSV file must include enough repository information. Supported columns include: "
            "owner, repo, repository, url."
        )

    jobs = []
    for row_num, row in enumerate(reader, start=2):
        owner = (row.get(owner_column, "") or "").strip() if owner_column else ""
        repo_value = (row.get(repo_column, "") or "").strip() if repo_column else ""
        url_value = (row.get(url_column, "") or "").strip() if url_column else ""
        commit_sha = (row.get(commit_column, "") or "").strip()

        parsed_owner = ""
        parsed_repo = ""
        if repo_value:
            parsed_owner, parsed_repo = parse_owner_repo_from_value(repo_value)
        if not parsed_owner and not parsed_repo and url_value:
            parsed_owner, parsed_repo = parse_owner_repo_from_value(url_value)

        owner = owner or parsed_owner
        repo = parsed_repo or repo_value

        if not owner and not repo and not commit_sha and not url_value:
            continue

        if not owner or not repo or not commit_sha:
            print(
                f"[WARN] Skipping CSV row {row_num}: could not resolve owner, repo, "
                "and commit SHA from the provided columns."
            )
            continue

        jobs.append({
            "owner": owner,
            "repo": repo,
            "commit_sha": commit_sha,
        })

    if not jobs:
        raise ValueError("No valid commit jobs found in CSV file.")

    return jobs


def run_before_after_metrics(owner: str, repo: str, commit_sha: str, token: str) -> None:
    print(f"\nFetching changed build files for commit: {commit_sha}\n")

    changed_files = get_changed_build_files(owner, repo, commit_sha, token)

    if not changed_files:
        print("No target build files changed in this commit.")
        return

    commit_parent_sha = None
    snapshots_probe = materialize_before_after_files(
        owner=owner,
        repo=repo,
        commit_sha=commit_sha,
        token=token,
        rel_path=changed_files[0]["path"],
    )
    commit_parent_sha = snapshots_probe["parent_sha"]
    cleanup_temp_files(snapshots_probe["before_temp"], snapshots_probe["after_temp"])

    before_project_dir = materialize_project_snapshot(owner, repo, commit_parent_sha, token) if commit_parent_sha else ""
    after_project_dir = materialize_project_snapshot(owner, repo, commit_sha, token)

    try:
        modularity_before = compute_project_modularity(before_project_dir) if before_project_dir else 0.0
        modularity_after = compute_project_modularity(after_project_dir) if after_project_dir else 0.0

        summary_rows = []
        total_comment_lines_before = 0
        total_comment_lines_after = 0
        total_lines_before = 0
        total_lines_after = 0
        total_comment_sentences_before = 0
        total_comment_sentences_after = 0
        total_comment_words_before = 0
        total_comment_words_after = 0
        total_comment_syllables_before = 0
        total_comment_syllables_after = 0

        for file_info in changed_files:
            rel_path = file_info["path"]
            basename = file_info["basename"]
            status = file_info["status"]
            additions = file_info["additions"]
            deletions = file_info["deletions"]
            changes = file_info["changes"]

            print(f"Processing: {rel_path}")

            snapshots = materialize_before_after_files(
                owner=owner,
                repo=repo,
                commit_sha=commit_sha,
                token=token,
                rel_path=rel_path,
            )

            before_temp = snapshots["before_temp"]
            after_temp = snapshots["after_temp"]
            parent_sha = snapshots["parent_sha"]

            try:
                tool = detect_build_tool(rel_path)

                bloc_before = compute_bloc(before_temp) if before_temp else 0
                bloc_after = compute_bloc(after_temp) if after_temp else 0

                cc_before = compute_cc(before_temp, rel_path) if before_temp else 0
                cc_after = compute_cc(after_temp, rel_path) if after_temp else 0
                normalized_cc_before = normalize_metric_by_bloc(cc_before, bloc_before)
                normalized_cc_after = normalize_metric_by_bloc(cc_after, bloc_after)

                halstead_before = compute_halstead_for_snapshot(before_temp, basename) if before_temp else 0.0
                halstead_after = compute_halstead_for_snapshot(after_temp, basename) if after_temp else 0.0
                normalized_hv_before = normalize_metric_by_bloc(halstead_before, bloc_before)
                normalized_hv_after = normalize_metric_by_bloc(halstead_after, bloc_after)
                dependency_stability_before = compute_dependency_stability_for_snapshot(before_temp) if before_temp else {
                    "dependency_count": 0,
                    "fixed_dependency_count": 0,
                    "dynamic_dependency_count": 0,
                    "snapshot_dependency_count": 0,
                    "unknown_dependency_count": 0,
                    "dss": 0.0,
                }
                dependency_stability_after = compute_dependency_stability_for_snapshot(after_temp) if after_temp else {
                    "dependency_count": 0,
                    "fixed_dependency_count": 0,
                    "dynamic_dependency_count": 0,
                    "snapshot_dependency_count": 0,
                    "unknown_dependency_count": 0,
                    "dss": 0.0,
                }
                determinism_before = compute_build_determinism_for_snapshot(before_temp, bloc_before) if before_temp else {
                    "non_deterministic_construct_count": 0,
                    "non_deterministic_summary": "",
                    "bds": 0.0,
                }
                determinism_after = compute_build_determinism_for_snapshot(after_temp, bloc_after) if after_temp else {
                    "non_deterministic_construct_count": 0,
                    "non_deterministic_summary": "",
                    "bds": 0.0,
                }

                comment_ratio_before = compute_comment_ratio_for_snapshot(before_temp) if before_temp else 0.0
                comment_ratio_after = compute_comment_ratio_for_snapshot(after_temp) if after_temp else 0.0
                before_line_stats = compute_line_stats_with_scc(before_temp) if before_temp else None
                after_line_stats = compute_line_stats_with_scc(after_temp) if after_temp else None
                total_comment_lines_before += int((before_line_stats or {}).get("comment", 0))
                total_comment_lines_after += int((after_line_stats or {}).get("comment", 0))
                total_lines_before += int((before_line_stats or {}).get("lines", 0))
                total_lines_after += int((after_line_stats or {}).get("lines", 0))
                comment_readability_before = compute_comment_readability_for_snapshot(before_temp) if before_temp else {
                    "sentence_count": 0,
                    "word_count": 0,
                    "syllable_count": 0,
                    "flesch_reading_ease": 0.0,
                }
                comment_readability_after = compute_comment_readability_for_snapshot(after_temp) if after_temp else {
                    "sentence_count": 0,
                    "word_count": 0,
                    "syllable_count": 0,
                    "flesch_reading_ease": 0.0,
                }
                total_comment_sentences_before += int(comment_readability_before.get("sentence_count", 0))
                total_comment_sentences_after += int(comment_readability_after.get("sentence_count", 0))
                total_comment_words_before += int(comment_readability_before.get("word_count", 0))
                total_comment_words_after += int(comment_readability_after.get("word_count", 0))
                total_comment_syllables_before += int(comment_readability_before.get("syllable_count", 0))
                total_comment_syllables_after += int(comment_readability_after.get("syllable_count", 0))

                style_before = compute_style_conformance_for_snapshot(before_temp, rel_path) if before_temp else 0.0
                style_after = compute_style_conformance_for_snapshot(after_temp, rel_path) if after_temp else 0.0

                clone_before = compute_clone_density_for_snapshot(before_temp) if before_temp else 0.0
                clone_after = compute_clone_density_for_snapshot(after_temp) if after_temp else 0.0

                coupling_before = compute_build_coupling_for_snapshot(before_temp, before_project_dir, bloc_before) if before_temp else {
                    "cp_internal": 0,
                    "cp_external": 0,
                    "cp_total": 0,
                    "ncp_internal": 0.0,
                    "ncp_external": 0.0,
                    "coupling_ratio": 0.0,
                }
                coupling_after = compute_build_coupling_for_snapshot(after_temp, after_project_dir, bloc_after) if after_temp else {
                    "cp_internal": 0,
                    "cp_external": 0,
                    "cp_total": 0,
                    "ncp_internal": 0.0,
                    "ncp_external": 0.0,
                    "coupling_ratio": 0.0,
                }
                edr_before = compute_external_dependency_risk(coupling_before)
                edr_after = compute_external_dependency_risk(coupling_after)

                cohesion_before = compute_build_cohesion_for_snapshot(before_temp) if before_temp else 0.0
                cohesion_after = compute_build_cohesion_for_snapshot(after_temp) if after_temp else 0.0

                before_activity = compute_change_activity_metric(owner, repo, rel_path, parent_sha, token) if parent_sha else empty_change_activity_result()
                after_activity = compute_change_activity_metric(owner, repo, rel_path, commit_sha, token)

                before_smells = compute_smells_for_snapshot(before_temp, tool)
                after_smells = compute_smells_for_snapshot(after_temp, tool)
                before_security_smells = compute_security_smells_for_snapshot(before_temp, tool)
                after_security_smells = compute_security_smells_for_snapshot(after_temp, tool)
                reliability_issues_before = compute_reliability_issue_count(before_smells, before_security_smells)
                reliability_issues_after = compute_reliability_issue_count(after_smells, after_security_smells)
                re_before = compute_reliability_score(reliability_issues_before, bloc_before)
                re_after = compute_reliability_score(reliability_issues_after, bloc_after)
                rm_before = compute_overall_reliability(re_before, dependency_stability_before["dss"], edr_before["edr"])
                rm_after = compute_overall_reliability(re_after, dependency_stability_after["dss"], edr_after["edr"])

                row = {
                    "Commit_SHA": commit_sha,
                    "Parent_SHA": parent_sha or "",
                    "File_Path": rel_path,
                    "File_Name": basename,
                    "Tool": tool,
                    "Status": status,
                    "Additions": additions,
                    "Deletions": deletions,
                    "Changes": changes,
                    "BLOC_Before": bloc_before,
                    "BLOC_After": bloc_after,
                    "Cyclomatic_Complexity_Before": cc_before,
                    "Cyclomatic_Complexity_After": cc_after,
                    "Normalized_CC_Before": normalized_cc_before,
                    "Normalized_CC_After": normalized_cc_after,
                    "Halstead_Volume_Before": halstead_before,
                    "Halstead_Volume_After": halstead_after,
                    "Normalized_HV_Before": normalized_hv_before,
                    "Normalized_HV_After": normalized_hv_after,
                    "Dependency_Count_Before": dependency_stability_before["dependency_count"],
                    "Dependency_Count_After": dependency_stability_after["dependency_count"],
                    "Fixed_Dependency_Count_Before": dependency_stability_before["fixed_dependency_count"],
                    "Fixed_Dependency_Count_After": dependency_stability_after["fixed_dependency_count"],
                    "Dynamic_Dependency_Count_Before": dependency_stability_before["dynamic_dependency_count"],
                    "Dynamic_Dependency_Count_After": dependency_stability_after["dynamic_dependency_count"],
                    "Snapshot_Dependency_Count_Before": dependency_stability_before["snapshot_dependency_count"],
                    "Snapshot_Dependency_Count_After": dependency_stability_after["snapshot_dependency_count"],
                    "Unknown_Dependency_Count_Before": dependency_stability_before["unknown_dependency_count"],
                    "Unknown_Dependency_Count_After": dependency_stability_after["unknown_dependency_count"],
                    "DSS_Before": dependency_stability_before["dss"],
                    "DSS_After": dependency_stability_after["dss"],
                    "DSS_Delta": round(dependency_stability_after["dss"] - dependency_stability_before["dss"], 4),
                    "Non_Deterministic_Constructs_Before": determinism_before["non_deterministic_construct_count"],
                    "Non_Deterministic_Constructs_After": determinism_after["non_deterministic_construct_count"],
                    "Non_Deterministic_Summary_Before": determinism_before["non_deterministic_summary"],
                    "Non_Deterministic_Summary_After": determinism_after["non_deterministic_summary"],
                    "BDS_Before": determinism_before["bds"],
                    "BDS_After": determinism_after["bds"],
                    "BDS_Delta": round(determinism_after["bds"] - determinism_before["bds"], 4),
                    "Comment_Ratio_Before": comment_ratio_before,
                    "Comment_Ratio_After": comment_ratio_after,
                    "Comment_Readability_Before": comment_readability_before["flesch_reading_ease"],
                    "Comment_Readability_After": comment_readability_after["flesch_reading_ease"],
                    "Style_Conformance_Score_Before": style_before,
                    "Style_Conformance_Score_After": style_after,
                    "Clone_Density_Before": clone_before,
                    "Clone_Density_After": clone_after,
                    "CP_Internal_Before": coupling_before["cp_internal"],
                    "CP_Internal_After": coupling_after["cp_internal"],
                    "CP_External_Before": coupling_before["cp_external"],
                    "CP_External_After": coupling_after["cp_external"],
                    "CP_Total_Before": coupling_before["cp_total"],
                    "CP_Total_After": coupling_after["cp_total"],
                    "NCP_Internal_Before": coupling_before["ncp_internal"],
                    "NCP_Internal_After": coupling_after["ncp_internal"],
                    "NCP_External_Before": coupling_before["ncp_external"],
                    "NCP_External_After": coupling_after["ncp_external"],
                    "Coupling_Ratio_Before": coupling_before["coupling_ratio"],
                    "Coupling_Ratio_After": coupling_after["coupling_ratio"],
                    "External_Risk_Factors_Before": edr_before["external_risk_factors"],
                    "External_Risk_Factors_After": edr_after["external_risk_factors"],
                    "EDR_Before": edr_before["edr"],
                    "EDR_After": edr_after["edr"],
                    "EDR_Delta": round(edr_after["edr"] - edr_before["edr"], 4),
                    "Build_Cohesion_Before": cohesion_before,
                    "Build_Cohesion_After": cohesion_after,
                    "Build_Modularity_Before": modularity_before,
                    "Build_Modularity_After": modularity_after,
                    "Churn_Before": before_activity["raw_churn"],
                    "Churn_After": after_activity["raw_churn"],
                    "Change_Frequency_Before": before_activity["raw_change_frequency"],
                    "Change_Frequency_After": after_activity["raw_change_frequency"],
                    "Avg_Logical_LOC_Before": before_activity["avg_logical_loc"],
                    "Avg_Logical_LOC_After": after_activity["avg_logical_loc"],
                    "Normalized_Churn_Before": before_activity["normalized_churn"],
                    "Normalized_Churn_After": after_activity["normalized_churn"],
                    "Normalized_Change_Frequency_Before": before_activity["normalized_change_frequency"],
                    "Normalized_Change_Frequency_After": after_activity["normalized_change_frequency"],
                    "Observation_Window_Days": after_activity["window_days"] or before_activity["window_days"],
                    "Reliability_Issues_Before": reliability_issues_before,
                    "Reliability_Issues_After": reliability_issues_after,
                    "RE_Before": re_before,
                    "RE_After": re_after,
                    "RE_Delta": round(re_after - re_before, 4),
                    "RM_Before": rm_before,
                    "RM_After": rm_after,
                    "RM_Delta": round(rm_after - rm_before, 4),
                    **flatten_smell_result("Before", before_smells, TRACKED_SMELLS),
                    **flatten_smell_result("After", after_smells, TRACKED_SMELLS),
                    **flatten_smell_result("Before", before_security_smells, TRACKED_SECURITY_SMELLS, "Security_Smell"),
                    **flatten_smell_result("After", after_security_smells, TRACKED_SECURITY_SMELLS, "Security_Smell"),
                    "Smell_Count_Delta": after_smells["smell_count"] - before_smells["smell_count"],
                    "Smell_Density_Delta": round(after_smells["smell_density"] - before_smells["smell_density"], 4),
                    "Introduced_Smells": 1 if after_smells["smell_count"] > before_smells["smell_count"] else 0,
                    "Removed_Smells": 1 if after_smells["smell_count"] < before_smells["smell_count"] else 0,
                    "Security_Smell_Count_Delta": after_security_smells["smell_count"] - before_security_smells["smell_count"],
                    "Security_Smell_Density_Delta": round(
                        after_security_smells["smell_density"] - before_security_smells["smell_density"], 4
                    ),
                    "Introduced_Security_Smells": 1 if after_security_smells["smell_count"] > before_security_smells["smell_count"] else 0,
                    "Removed_Security_Smells": 1 if after_security_smells["smell_count"] < before_security_smells["smell_count"] else 0,
                }

                summary_rows.append(row)

                print(
                    f"  File: {basename} | "
                    f"BLOC {bloc_before}->{bloc_after} | "
                    f"CC {cc_before}->{cc_after} | "
                    f"HV {halstead_before}->{halstead_after} | "
                    f"DSS {dependency_stability_before['dss']}->{dependency_stability_after['dss']} | "
                    f"BDS {determinism_before['bds']}->{determinism_after['bds']} | "
                    f"CR {comment_ratio_before}->{comment_ratio_after} | "
                    f"Readability {comment_readability_before['flesch_reading_ease']}->{comment_readability_after['flesch_reading_ease']} | "
                    f"Style {style_before}->{style_after} | "
                    f"CD {clone_before}->{clone_after} | "
                    f"CP {coupling_before['cp_total']}->{coupling_after['cp_total']} | "
                    f"EDR {edr_before['edr']}->{edr_after['edr']} | "
                    f"Cohesion {cohesion_before}->{cohesion_after} | "
                    f"Modularity {modularity_before}->{modularity_after} | "
                    f"Churn {before_activity['raw_churn']}->{after_activity['raw_churn']} | "
                    f"CF {before_activity['raw_change_frequency']}->{after_activity['raw_change_frequency']} | "
                    f"RE {re_before}->{re_after} | "
                    f"RM {rm_before}->{rm_after} | "
                    f"Smells {before_smells['smell_count']}->{after_smells['smell_count']} | "
                    f"Security {before_security_smells['smell_count']}->{after_security_smells['smell_count']}"
                )

            finally:
                cleanup_temp_files(before_temp, after_temp)

        total_before_smells = sum(row.get("Before_Smell_Count", 0) for row in summary_rows)
        total_after_smells = sum(row.get("After_Smell_Count", 0) for row in summary_rows)
        total_before_security_smells = sum(row.get("Before_Security_Smell_Count", 0) for row in summary_rows)
        total_after_security_smells = sum(row.get("After_Security_Smell_Count", 0) for row in summary_rows)
        total_bloc_before = sum(row.get("BLOC_Before", 0) for row in summary_rows)
        total_bloc_after = sum(row.get("BLOC_After", 0) for row in summary_rows)
        total_dependency_count_before = sum(row.get("Dependency_Count_Before", 0) for row in summary_rows)
        total_dependency_count_after = sum(row.get("Dependency_Count_After", 0) for row in summary_rows)
        total_fixed_dependency_count_before = sum(row.get("Fixed_Dependency_Count_Before", 0) for row in summary_rows)
        total_fixed_dependency_count_after = sum(row.get("Fixed_Dependency_Count_After", 0) for row in summary_rows)
        total_dynamic_dependency_count_before = sum(row.get("Dynamic_Dependency_Count_Before", 0) for row in summary_rows)
        total_dynamic_dependency_count_after = sum(row.get("Dynamic_Dependency_Count_After", 0) for row in summary_rows)
        total_snapshot_dependency_count_before = sum(row.get("Snapshot_Dependency_Count_Before", 0) for row in summary_rows)
        total_snapshot_dependency_count_after = sum(row.get("Snapshot_Dependency_Count_After", 0) for row in summary_rows)
        total_unknown_dependency_count_before = sum(row.get("Unknown_Dependency_Count_Before", 0) for row in summary_rows)
        total_unknown_dependency_count_after = sum(row.get("Unknown_Dependency_Count_After", 0) for row in summary_rows)
        total_reliability_issues_before = sum(row.get("Reliability_Issues_Before", 0) for row in summary_rows)
        total_reliability_issues_after = sum(row.get("Reliability_Issues_After", 0) for row in summary_rows)
        total_before_density = round(total_before_smells / max(total_bloc_before, 1), 4)
        total_after_density = round(total_after_smells / max(total_bloc_after, 1), 4)
        total_before_security_density = round(total_before_security_smells / max(total_bloc_before, 1), 4)
        total_after_security_density = round(total_after_security_smells / max(total_bloc_after, 1), 4)
        total_before_summary = ";".join(sorted({
            smell_id
            for row in summary_rows
            for smell_id in (row.get("Before_Smell_Summary", "") or "").split(";")
            if smell_id
        }))
        total_after_summary = ";".join(sorted({
            smell_id
            for row in summary_rows
            for smell_id in (row.get("After_Smell_Summary", "") or "").split(";")
            if smell_id
        }))
        total_before_security_summary = ";".join(sorted({
            smell_id
            for row in summary_rows
            for smell_id in (row.get("Before_Security_Smell_Summary", "") or "").split(";")
            if smell_id
        }))
        total_after_security_summary = ";".join(sorted({
            smell_id
            for row in summary_rows
            for smell_id in (row.get("After_Security_Smell_Summary", "") or "").split(";")
            if smell_id
        }))

        totals_row = {
            "Commit_SHA": commit_sha,
            "Parent_SHA": commit_parent_sha or "",
            "File_Path": "__COMMIT_TOTAL__",
            "File_Name": "__COMMIT_TOTAL__",
            "Tool": "ALL",
            "Status": "SUMMARY",
            "Additions": sum(row.get("Additions", 0) for row in summary_rows),
            "Deletions": sum(row.get("Deletions", 0) for row in summary_rows),
            "Changes": sum(row.get("Changes", 0) for row in summary_rows),
            "BLOC_Before": sum(row.get("BLOC_Before", 0) for row in summary_rows),
            "BLOC_After": sum(row.get("BLOC_After", 0) for row in summary_rows),
            "Cyclomatic_Complexity_Before": sum(row.get("Cyclomatic_Complexity_Before", 0) for row in summary_rows),
            "Cyclomatic_Complexity_After": sum(row.get("Cyclomatic_Complexity_After", 0) for row in summary_rows),
            "Normalized_CC_Before": 0.0,
            "Normalized_CC_After": 0.0,
            "Halstead_Volume_Before": round(sum(row.get("Halstead_Volume_Before", 0.0) for row in summary_rows), 2),
            "Halstead_Volume_After": round(sum(row.get("Halstead_Volume_After", 0.0) for row in summary_rows), 2),
            "Normalized_HV_Before": 0.0,
            "Normalized_HV_After": 0.0,
            "Dependency_Count_Before": total_dependency_count_before,
            "Dependency_Count_After": total_dependency_count_after,
            "Fixed_Dependency_Count_Before": total_fixed_dependency_count_before,
            "Fixed_Dependency_Count_After": total_fixed_dependency_count_after,
            "Dynamic_Dependency_Count_Before": total_dynamic_dependency_count_before,
            "Dynamic_Dependency_Count_After": total_dynamic_dependency_count_after,
            "Snapshot_Dependency_Count_Before": total_snapshot_dependency_count_before,
            "Snapshot_Dependency_Count_After": total_snapshot_dependency_count_after,
            "Unknown_Dependency_Count_Before": total_unknown_dependency_count_before,
            "Unknown_Dependency_Count_After": total_unknown_dependency_count_after,
            "DSS_Before": round(total_fixed_dependency_count_before / max(total_dependency_count_before, 1), 4)
            if total_dependency_count_before > 0 else 0.0,
            "DSS_After": round(total_fixed_dependency_count_after / max(total_dependency_count_after, 1), 4)
            if total_dependency_count_after > 0 else 0.0,
            "DSS_Delta": 0.0,
            "Non_Deterministic_Constructs_Before": sum(row.get("Non_Deterministic_Constructs_Before", 0) for row in summary_rows),
            "Non_Deterministic_Constructs_After": sum(row.get("Non_Deterministic_Constructs_After", 0) for row in summary_rows),
            "Non_Deterministic_Summary_Before": ";".join(sorted({
                item
                for row in summary_rows
                for item in (row.get("Non_Deterministic_Summary_Before", "") or "").split(";")
                if item
            })),
            "Non_Deterministic_Summary_After": ";".join(sorted({
                item
                for row in summary_rows
                for item in (row.get("Non_Deterministic_Summary_After", "") or "").split(";")
                if item
            })),
            "BDS_Before": 0.0,
            "BDS_After": 0.0,
            "BDS_Delta": 0.0,
            "Comment_Ratio_Before": round(total_comment_lines_before / max(total_lines_before, 1), 4),
            "Comment_Ratio_After": round(total_comment_lines_after / max(total_lines_after, 1), 4),
            "Comment_Readability_Before": 0.0,
            "Comment_Readability_After": 0.0,
            "Style_Conformance_Score_Before": "",
            "Style_Conformance_Score_After": "",
            "Clone_Density_Before": "",
            "Clone_Density_After": "",
            "CP_Internal_Before": sum(row.get("CP_Internal_Before", 0) for row in summary_rows),
            "CP_Internal_After": sum(row.get("CP_Internal_After", 0) for row in summary_rows),
            "CP_External_Before": sum(row.get("CP_External_Before", 0) for row in summary_rows),
            "CP_External_After": sum(row.get("CP_External_After", 0) for row in summary_rows),
            "CP_Total_Before": sum(row.get("CP_Total_Before", 0) for row in summary_rows),
            "CP_Total_After": sum(row.get("CP_Total_After", 0) for row in summary_rows),
            "NCP_Internal_Before": 0.0,
            "NCP_Internal_After": 0.0,
            "NCP_External_Before": 0.0,
            "NCP_External_After": 0.0,
            "Coupling_Ratio_Before": 0.0,
            "Coupling_Ratio_After": 0.0,
            "External_Risk_Factors_Before": sum(row.get("External_Risk_Factors_Before", 0) for row in summary_rows),
            "External_Risk_Factors_After": sum(row.get("External_Risk_Factors_After", 0) for row in summary_rows),
            "EDR_Before": 0.0,
            "EDR_After": 0.0,
            "EDR_Delta": 0.0,
            "Build_Cohesion_Before": "",
            "Build_Cohesion_After": "",
            "Build_Modularity_Before": modularity_before,
            "Build_Modularity_After": modularity_after,
            "Churn_Before": sum(row.get("Churn_Before", 0) for row in summary_rows),
            "Churn_After": sum(row.get("Churn_After", 0) for row in summary_rows),
            "Change_Frequency_Before": sum(row.get("Change_Frequency_Before", 0) for row in summary_rows),
            "Change_Frequency_After": sum(row.get("Change_Frequency_After", 0) for row in summary_rows),
            "Avg_Logical_LOC_Before": "",
            "Avg_Logical_LOC_After": "",
            "Normalized_Churn_Before": "",
            "Normalized_Churn_After": "",
            "Normalized_Change_Frequency_Before": "",
            "Normalized_Change_Frequency_After": "",
            "Observation_Window_Days": summary_rows[0].get("Observation_Window_Days", "") if summary_rows else "",
            "Reliability_Issues_Before": total_reliability_issues_before,
            "Reliability_Issues_After": total_reliability_issues_after,
            "RE_Before": compute_reliability_score(total_reliability_issues_before, total_bloc_before),
            "RE_After": compute_reliability_score(total_reliability_issues_after, total_bloc_after),
            "RE_Delta": 0.0,
            "RM_Before": 0.0,
            "RM_After": 0.0,
            "RM_Delta": 0.0,
            "Before_Smell_Count": total_before_smells,
            "After_Smell_Count": total_after_smells,
            "Before_Smell_Density": total_before_density,
            "After_Smell_Density": total_after_density,
            "Before_Smell_Summary": total_before_summary,
            "After_Smell_Summary": total_after_summary,
            "Smell_Count_Delta": total_after_smells - total_before_smells,
            "Smell_Density_Delta": round(total_after_density - total_before_density, 4),
            "Introduced_Smells": 1 if total_after_smells > total_before_smells else 0,
            "Removed_Smells": 1 if total_after_smells < total_before_smells else 0,
            "Before_Security_Smell_Count": total_before_security_smells,
            "After_Security_Smell_Count": total_after_security_smells,
            "Before_Security_Smell_Density": total_before_security_density,
            "After_Security_Smell_Density": total_after_security_density,
            "Before_Security_Smell_Summary": total_before_security_summary,
            "After_Security_Smell_Summary": total_after_security_summary,
            "Security_Smell_Count_Delta": total_after_security_smells - total_before_security_smells,
            "Security_Smell_Density_Delta": round(total_after_security_density - total_before_security_density, 4),
            "Introduced_Security_Smells": 1 if total_after_security_smells > total_before_security_smells else 0,
            "Removed_Security_Smells": 1 if total_after_security_smells < total_before_security_smells else 0,
        }

        totals_row["DSS_Delta"] = round(totals_row["DSS_After"] - totals_row["DSS_Before"], 4)
        totals_row["BDS_Before"] = round(
            max(
                0.0,
                1 - (
                    totals_row["Non_Deterministic_Constructs_Before"]
                    / max(totals_row["BLOC_Before"], 1)
                ),
            ),
            4,
        ) if totals_row["BLOC_Before"] > 0 else 0.0
        totals_row["BDS_After"] = round(
            max(
                0.0,
                1 - (
                    totals_row["Non_Deterministic_Constructs_After"]
                    / max(totals_row["BLOC_After"], 1)
                ),
            ),
            4,
        ) if totals_row["BLOC_After"] > 0 else 0.0
        totals_row["BDS_Delta"] = round(totals_row["BDS_After"] - totals_row["BDS_Before"], 4)
        totals_row["RE_Delta"] = round(totals_row["RE_After"] - totals_row["RE_Before"], 4)

        totals_row["NCP_Internal_Before"] = normalize_metric_by_bloc(
            totals_row["CP_Internal_Before"],
            totals_row["BLOC_Before"],
        )
        totals_row["NCP_Internal_After"] = normalize_metric_by_bloc(
            totals_row["CP_Internal_After"],
            totals_row["BLOC_After"],
        )
        totals_row["NCP_External_Before"] = normalize_metric_by_bloc(
            totals_row["CP_External_Before"],
            totals_row["BLOC_Before"],
        )
        totals_row["NCP_External_After"] = normalize_metric_by_bloc(
            totals_row["CP_External_After"],
            totals_row["BLOC_After"],
        )
        totals_row["Coupling_Ratio_Before"] = round(
            totals_row["CP_External_Before"] / max(totals_row["CP_Total_Before"], 1),
            4,
        )
        totals_row["Coupling_Ratio_After"] = round(
            totals_row["CP_External_After"] / max(totals_row["CP_Total_After"], 1),
            4,
        )
        totals_row["EDR_Before"] = round(
            totals_row["External_Risk_Factors_Before"] / max(totals_row["CP_Total_Before"], 1),
            4,
        )
        totals_row["EDR_After"] = round(
            totals_row["External_Risk_Factors_After"] / max(totals_row["CP_Total_After"], 1),
            4,
        )
        totals_row["EDR_Delta"] = round(totals_row["EDR_After"] - totals_row["EDR_Before"], 4)
        totals_row["RM_Before"] = compute_overall_reliability(
            totals_row["RE_Before"],
            totals_row["DSS_Before"],
            totals_row["EDR_Before"],
        )
        totals_row["RM_After"] = compute_overall_reliability(
            totals_row["RE_After"],
            totals_row["DSS_After"],
            totals_row["EDR_After"],
        )
        totals_row["RM_Delta"] = round(totals_row["RM_After"] - totals_row["RM_Before"], 4)
        totals_row["Normalized_CC_Before"] = normalize_metric_by_bloc(
            totals_row["Cyclomatic_Complexity_Before"],
            totals_row["BLOC_Before"],
        )
        totals_row["Normalized_CC_After"] = normalize_metric_by_bloc(
            totals_row["Cyclomatic_Complexity_After"],
            totals_row["BLOC_After"],
        )
        totals_row["Normalized_HV_Before"] = normalize_metric_by_bloc(
            totals_row["Halstead_Volume_Before"],
            totals_row["BLOC_Before"],
        )
        totals_row["Normalized_HV_After"] = normalize_metric_by_bloc(
            totals_row["Halstead_Volume_After"],
            totals_row["BLOC_After"],
        )
        if total_comment_words_before >= 3 and total_comment_sentences_before > 0:
            totals_row["Comment_Readability_Before"] = round(
                206.835
                - 1.015 * (total_comment_words_before / total_comment_sentences_before)
                - 84.6 * (total_comment_syllables_before / total_comment_words_before),
                2,
            )
        if total_comment_words_after >= 3 and total_comment_sentences_after > 0:
            totals_row["Comment_Readability_After"] = round(
                206.835
                - 1.015 * (total_comment_words_after / total_comment_sentences_after)
                - 84.6 * (total_comment_syllables_after / total_comment_words_after),
                2,
            )

        for smell_id in TRACKED_SMELLS:
            totals_row[f"Before_{smell_id}"] = 1 if any(row.get(f"Before_{smell_id}") for row in summary_rows) else 0
            totals_row[f"After_{smell_id}"] = 1 if any(row.get(f"After_{smell_id}") for row in summary_rows) else 0

        for smell_id in TRACKED_SECURITY_SMELLS:
            totals_row[f"Before_{smell_id}"] = 1 if any(row.get(f"Before_{smell_id}") for row in summary_rows) else 0
            totals_row[f"After_{smell_id}"] = 1 if any(row.get(f"After_{smell_id}") for row in summary_rows) else 0

        summary_rows.append(totals_row)

        write_summary(summary_rows)
        write_maintainability_summary(summary_rows)
        write_modularity_summary(summary_rows)
        write_reliability_summary(summary_rows)
        write_security_summary(summary_rows)
        write_understandability_summary(summary_rows)
        write_commit_csv_bundle(owner, repo, commit_sha, summary_rows)
        print("\nBefore/after analysis completed for all metrics and smells.")

    finally:
        cleanup_temp_files(before_project_dir, after_project_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "Run before/after build metrics for a GitHub commit, or for multiple "
            "commits listed in a CSV file."
        )
    )
    parser.add_argument("owner", nargs="?", help="GitHub repository owner")
    parser.add_argument("repo", nargs="?", help="GitHub repository name")
    parser.add_argument("commit_sha", nargs="?", help="Commit SHA to analyze")
    parser.add_argument(
        "github_token",
        nargs="?",
        help="GitHub token. If omitted, GITHUB_TOKEN is used.",
    )
    parser.add_argument(
        "--csv",
        dest="csv_path",
        help=(
            "Path to a CSV file with columns: owner, repo, commit_sha. "
            "When provided, the positional owner/repo/commit_sha arguments are not required."
        ),
    )
    args = parser.parse_args()

    token = (args.github_token or os.environ.get("GITHUB_TOKEN", "")).strip()
    if not token:
        print("ERROR: GitHub token not provided.")
        sys.exit(1)

    if args.csv_path:
        jobs = read_commit_jobs_from_csv(args.csv_path)
        for job in jobs:
            print(
                f"\n=== Running commit job: {job['owner']}/{job['repo']} "
                f"@ {job['commit_sha']} ==="
            )
            run_before_after_metrics(
                owner=job["owner"],
                repo=job["repo"],
                commit_sha=job["commit_sha"],
                token=token,
            )
        sys.exit(0)

    if not (args.owner and args.repo and args.commit_sha):
        print(
            "Usage: python run_before_after_metrics.py <owner> <repo> <commit_sha> [github_token]\n"
            "   or: python run_before_after_metrics.py --csv <jobs.csv> [github_token]"
        )
        sys.exit(1)

    run_before_after_metrics(args.owner.strip(), args.repo.strip(), args.commit_sha.strip(), token)
