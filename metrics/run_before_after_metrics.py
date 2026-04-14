import os
import sys
import csv
import shutil
import argparse

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))

for path in (BASE_DIR, REPO_ROOT):
    if path not in sys.path:
        sys.path.insert(0, path)

from metrics.BLOC import compute_bloc
from cyclomatic_complexity import (
    calculate_ant_build_logic_complexity,
    calculate_maven_build_logic_complexity,
    calculate_gradle_cc,
    calculate_gradle_kts_cc,
)
from halstead_volume import compute_halstead
from clone_density import compute_clone_density
from build_cohesion import compute_build_cohesion_value
from build_modularity import compute_project_modularity
from github_commits_util import (
    get_changed_build_files,
    materialize_before_after_files,
    materialize_project_snapshot,
)
from sniffer_adapter import SnifferAdapter
from style_conformance import (
    calculate_gradle_kts_style_violations,
    calculate_gradle_style_violations,
    compute_style_score,
    count_ant_style_violations,
    count_maven_style_violations,
)

OUTPUT_FOLDER = os.path.join(BASE_DIR, "..", "results")
SUMMARY_CSV = os.path.join(BASE_DIR, "..", "results", "summary_metrics.csv")

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


def normalize_build_type_for_sniffer(tool_name: str) -> str:
    tool_name = (tool_name or "").strip().lower()

    if tool_name == "maven":
        return "maven"
    elif tool_name == "gradle":
        return "gradle"
    elif tool_name == "gradle/groovy":
        return "gradle"
    elif tool_name == "ant":
        return "ant"

    return "unknown"


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


def compute_clone_density_for_snapshot(snapshot_path: str) -> float:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return 0.0
    return compute_clone_density(snapshot_path)


def compute_build_cohesion_for_snapshot(snapshot_path: str) -> float:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return 0.0
    return compute_build_cohesion_value(snapshot_path)


def compute_churn_metric(file_path: str, commit_sha: str) -> int:
    if not commit_sha:
        return 0

    try:
        from churn import compute_churn_for_file_at_commit
    except ModuleNotFoundError as exc:
        if exc.name == "pydriller":
            print("[WARN] pydriller is not installed; Churn metrics will be reported as 0.")
            return 0
        raise

    return compute_churn_for_file_at_commit(file_path, commit_sha)


def compute_change_frequency_metric(file_path: str, commit_sha: str) -> int:
    if not commit_sha:
        return 0

    try:
        from change_frequency import compute_change_frequency_for_file_at_commit
    except ModuleNotFoundError as exc:
        if exc.name == "pydriller":
            print("[WARN] pydriller is not installed; Change Frequency metrics will be reported as 0.")
            return 0
        raise

    return compute_change_frequency_for_file_at_commit(file_path, commit_sha)


def flatten_smell_result(prefix: str, smell_result: dict) -> dict:
    row = {
        f"{prefix}_Smell_Count": smell_result.get("smell_count", 0),
        f"{prefix}_Smell_Density": smell_result.get("smell_density", 0.0),
        f"{prefix}_Smell_Summary": smell_result.get("smell_summary", "")
    }

    smell_ids = {s["smell_id"] for s in smell_result.get("smells", [])}

    tracked_smells = [
        "INSECURE_URL",
        "HARDCODED_PATH",
        "HARDCODED_CREDENTIAL",
        "DUPLICATE_DECLARATION",
        "MISSING_DEPENDENCY_VERSION",
        "WILDCARD_VERSION",
        "EMPTY_TAG",
        "LACK_ERROR_HANDLING",
        "SUSPICIOUS_COMMENT",
        "COMPLEX_BUILD_LOGIC",
        "EXEC_USAGE",
        "DUPLICATE_TARGET",
        "EXCESSIVE_TARGET_DEPENDENCIES",
        "LONG_LINE",
        "BAD_CLASS_NAME",
        "BAD_METHOD_NAME",
        "LONG_VARIABLE_NAME",
        "BAD_FIELD_NAME",
        "TOO_MANY_PARAMETERS",
        "LARGE_LOOP",
        "DUPLICATE_LOGIC_BLOCK",
    ]

    for smell in tracked_smells:
        row[f"{prefix}_{smell}"] = 1 if smell in smell_ids else 0

    return row


def write_summary(rows: list[dict]) -> None:
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
        "Halstead_Volume_Before",
        "Halstead_Volume_After",
        "Style_Conformance_Score_Before",
        "Style_Conformance_Score_After",
        "Clone_Density_Before",
        "Clone_Density_After",
        "Build_Cohesion_Before",
        "Build_Cohesion_After",
        "Build_Modularity_Before",
        "Build_Modularity_After",
        "Churn_Before",
        "Churn_After",
        "Change_Frequency_Before",
        "Change_Frequency_After",
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

        "Before_INSECURE_URL",
        "Before_HARDCODED_PATH",
        "Before_HARDCODED_CREDENTIAL",
        "Before_DUPLICATE_DECLARATION",
        "Before_MISSING_DEPENDENCY_VERSION",
        "Before_WILDCARD_VERSION",
        "Before_EMPTY_TAG",
        "Before_LACK_ERROR_HANDLING",
        "Before_SUSPICIOUS_COMMENT",
        "Before_COMPLEX_BUILD_LOGIC",
        "Before_EXEC_USAGE",
        "Before_DUPLICATE_TARGET",
        "Before_EXCESSIVE_TARGET_DEPENDENCIES",
        "Before_LONG_LINE",
        "Before_BAD_CLASS_NAME",
        "Before_BAD_METHOD_NAME",
        "Before_LONG_VARIABLE_NAME",
        "Before_BAD_FIELD_NAME",
        "Before_TOO_MANY_PARAMETERS",
        "Before_LARGE_LOOP",
        "Before_DUPLICATE_LOGIC_BLOCK",

        "After_INSECURE_URL",
        "After_HARDCODED_PATH",
        "After_HARDCODED_CREDENTIAL",
        "After_DUPLICATE_DECLARATION",
        "After_MISSING_DEPENDENCY_VERSION",
        "After_WILDCARD_VERSION",
        "After_EMPTY_TAG",
        "After_LACK_ERROR_HANDLING",
        "After_SUSPICIOUS_COMMENT",
        "After_COMPLEX_BUILD_LOGIC",
        "After_EXEC_USAGE",
        "After_DUPLICATE_TARGET",
        "After_EXCESSIVE_TARGET_DEPENDENCIES",
        "After_LONG_LINE",
        "After_BAD_CLASS_NAME",
        "After_BAD_METHOD_NAME",
        "After_LONG_VARIABLE_NAME",
        "After_BAD_FIELD_NAME",
        "After_TOO_MANY_PARAMETERS",
        "After_LARGE_LOOP",
        "After_DUPLICATE_LOGIC_BLOCK",
    ]

    file_exists = os.path.exists(SUMMARY_CSV)
    write_header = True

    if file_exists and os.path.getsize(SUMMARY_CSV) > 0:
        write_header = False

    with open(SUMMARY_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)

        if write_header:
            writer.writeheader()

        writer.writerows(rows)

    print(f"\nResults appended to: {SUMMARY_CSV}")


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


def read_commit_jobs_from_csv(csv_path: str) -> list[dict[str, str]]:
    if not os.path.exists(csv_path):
        raise FileNotFoundError(f"CSV file not found: {csv_path}")

    with open(csv_path, "r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        if not reader.fieldnames:
            raise ValueError("CSV file must include a header row.")

        field_map = {canonicalize_column_name(name): name for name in reader.fieldnames}
        required = ["owner", "repo", "commit_sha"]
        missing = [name for name in required if name not in field_map]
        if missing:
            raise ValueError(
                "CSV file is missing required columns: "
                + ", ".join(missing)
            )

        jobs = []
        for row_num, row in enumerate(reader, start=2):
            owner = (row.get(field_map["owner"], "") or "").strip()
            repo = (row.get(field_map["repo"], "") or "").strip()
            commit_sha = (row.get(field_map["commit_sha"], "") or "").strip()

            if not owner and not repo and not commit_sha:
                continue

            if not owner or not repo or not commit_sha:
                print(
                    f"[WARN] Skipping CSV row {row_num}: owner, repo, and commit_sha "
                    "must all be non-empty."
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

    sniffer = SnifferAdapter()

    parent_sha = None
    snapshots_probe = materialize_before_after_files(
        owner=owner,
        repo=repo,
        commit_sha=commit_sha,
        token=token,
        rel_path=changed_files[0]["path"],
    )
    parent_sha = snapshots_probe["parent_sha"]
    cleanup_temp_files(snapshots_probe["before_temp"], snapshots_probe["after_temp"])

    before_project_dir = materialize_project_snapshot(owner, repo, parent_sha, token) if parent_sha else ""
    after_project_dir = materialize_project_snapshot(owner, repo, commit_sha, token)

    try:
        modularity_before = compute_project_modularity(before_project_dir) if before_project_dir else 0.0
        modularity_after = compute_project_modularity(after_project_dir) if after_project_dir else 0.0

        summary_rows = []

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
                sniffer_build_type = normalize_build_type_for_sniffer(tool)

                bloc_before = compute_bloc(before_temp) if before_temp else 0
                bloc_after = compute_bloc(after_temp) if after_temp else 0

                cc_before = compute_cc(before_temp, rel_path) if before_temp else 0
                cc_after = compute_cc(after_temp, rel_path) if after_temp else 0

                halstead_before = compute_halstead_for_snapshot(before_temp, basename) if before_temp else 0.0
                halstead_after = compute_halstead_for_snapshot(after_temp, basename) if after_temp else 0.0

                style_before = compute_style_conformance_for_snapshot(before_temp, rel_path) if before_temp else 0.0
                style_after = compute_style_conformance_for_snapshot(after_temp, rel_path) if after_temp else 0.0

                clone_before = compute_clone_density_for_snapshot(before_temp) if before_temp else 0.0
                clone_after = compute_clone_density_for_snapshot(after_temp) if after_temp else 0.0

                cohesion_before = compute_build_cohesion_for_snapshot(before_temp) if before_temp else 0.0
                cohesion_after = compute_build_cohesion_for_snapshot(after_temp) if after_temp else 0.0

                churn_before = compute_churn_metric(rel_path, parent_sha) if parent_sha else 0
                churn_after = churn_before + additions + deletions

                cf_before = compute_change_frequency_metric(rel_path, parent_sha) if parent_sha else 0
                cf_after = cf_before + 1

                before_smells = sniffer.detect_smells(before_temp, sniffer_build_type) if before_temp else sniffer.empty_result()
                after_smells = sniffer.detect_smells(after_temp, sniffer_build_type) if after_temp else sniffer.empty_result()

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
                    "Halstead_Volume_Before": halstead_before,
                    "Halstead_Volume_After": halstead_after,
                    "Style_Conformance_Score_Before": style_before,
                    "Style_Conformance_Score_After": style_after,
                    "Clone_Density_Before": clone_before,
                    "Clone_Density_After": clone_after,
                    "Build_Cohesion_Before": cohesion_before,
                    "Build_Cohesion_After": cohesion_after,
                    "Build_Modularity_Before": modularity_before,
                    "Build_Modularity_After": modularity_after,
                    "Churn_Before": churn_before,
                    "Churn_After": churn_after,
                    "Change_Frequency_Before": cf_before,
                    "Change_Frequency_After": cf_after,
                    **flatten_smell_result("Before", before_smells),
                    **flatten_smell_result("After", after_smells),
                    "Smell_Count_Delta": after_smells["smell_count"] - before_smells["smell_count"],
                    "Smell_Density_Delta": round(after_smells["smell_density"] - before_smells["smell_density"], 4),
                    "Introduced_Smells": 1 if after_smells["smell_count"] > before_smells["smell_count"] else 0,
                    "Removed_Smells": 1 if after_smells["smell_count"] < before_smells["smell_count"] else 0,
                }

                summary_rows.append(row)

                print(
                    f"  File: {basename} | "
                    f"BLOC {bloc_before}->{bloc_after} | "
                    f"CC {cc_before}->{cc_after} | "
                    f"HV {halstead_before}->{halstead_after} | "
                    f"Style {style_before}->{style_after} | "
                    f"CD {clone_before}->{clone_after} | "
                    f"Cohesion {cohesion_before}->{cohesion_after} | "
                    f"Modularity {modularity_before}->{modularity_after} | "
                    f"Churn {churn_before}->{churn_after} | "
                    f"CF {cf_before}->{cf_after} | "
                    f"Smells {before_smells['smell_count']}->{after_smells['smell_count']}"
                )

            finally:
                cleanup_temp_files(before_temp, after_temp)

        write_summary(summary_rows)
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
