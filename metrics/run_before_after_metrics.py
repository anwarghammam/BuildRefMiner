import os
import sys
import csv
import shutil

sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from bloc_analyser import compute_bloc
from cyclomatic_complexity import (
    calculate_ant_cc,
    calculate_maven_cc,
    calculate_groovy_cc,
)
from halstead_volume import compute_halstead
from clone_density import compute_clone_density
from build_cohesion import compute_build_cohesion_value
from build_modularity import compute_project_modularity
from churn import compute_churn_for_file_at_commit
from change_frequency import compute_change_frequency_for_file_at_commit
from github_commits_util import (
    get_changed_build_files,
    materialize_before_after_files,
    materialize_project_snapshot,
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FOLDER = os.path.join(BASE_DIR, "..", "processed_builds")
SUMMARY_CSV = os.path.join(OUTPUT_FOLDER, "summary_metrics.csv")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def detect_build_tool(filename: str) -> str:
    name = os.path.basename(filename).lower()

    if name == "build.xml":
        return "Ant"
    elif name == "pom.xml":
        return "Maven"
    elif name.endswith(".gradle") or name.endswith(".gradle.kts"):
        return "Gradle"
    elif name.endswith(".groovy"):
        return "Gradle/Groovy"
    else:
        return "Unknown"


def compute_cc(snapshot_path: str, original_filename: str) -> int:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return 0

    name = os.path.basename(original_filename).lower()

    if name == "build.xml":
        return calculate_ant_cc(snapshot_path)
    elif name == "pom.xml":
        return calculate_maven_cc(snapshot_path)
    elif name.endswith(".gradle") or name.endswith(".groovy") or name.endswith(".gradle.kts"):
        return calculate_groovy_cc(snapshot_path)
    return 0


def compute_halstead_for_snapshot(snapshot_path: str, original_filename: str) -> float:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return 0.0
    return compute_halstead(os.path.basename(original_filename), snapshot_path)


def compute_clone_density_for_snapshot(snapshot_path: str) -> float:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return 0.0
    return compute_clone_density(snapshot_path)


def compute_build_cohesion_for_snapshot(snapshot_path: str) -> float:
    if not snapshot_path or not os.path.exists(snapshot_path):
        return 0.0
    return compute_build_cohesion_value(snapshot_path)


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
    ]

    with open(SUMMARY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nSummary written to: {SUMMARY_CSV}")


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


def run_before_after_metrics(owner: str, repo: str, commit_sha: str, token: str) -> None:
    print(f"\nFetching changed build files for commit: {commit_sha}\n")

    changed_files = get_changed_build_files(owner, repo, commit_sha, token)

    if not changed_files:
        print("No target build files changed in this commit.")
        return

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
                bloc_before = compute_bloc(before_temp) if before_temp else 0
                bloc_after = compute_bloc(after_temp) if after_temp else 0

                cc_before = compute_cc(before_temp, basename) if before_temp else 0
                cc_after = compute_cc(after_temp, basename) if after_temp else 0

                halstead_before = compute_halstead_for_snapshot(before_temp, basename) if before_temp else 0.0
                halstead_after = compute_halstead_for_snapshot(after_temp, basename) if after_temp else 0.0

                clone_before = compute_clone_density_for_snapshot(before_temp) if before_temp else 0.0
                clone_after = compute_clone_density_for_snapshot(after_temp) if after_temp else 0.0

                cohesion_before = compute_build_cohesion_for_snapshot(before_temp) if before_temp else 0.0
                cohesion_after = compute_build_cohesion_for_snapshot(after_temp) if after_temp else 0.0

                churn_before = compute_churn_for_file_at_commit(rel_path, parent_sha) if parent_sha else 0
                churn_after = churn_before + additions + deletions


                cf_before = compute_change_frequency_for_file_at_commit(rel_path, parent_sha) if parent_sha else 0
                cf_after = cf_before + 1
                row = {
                    "Commit_SHA": commit_sha,
                    "Parent_SHA": parent_sha or "",
                    "File_Path": rel_path,
                    "File_Name": basename,
                    "Tool": detect_build_tool(basename),
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
                }

                summary_rows.append(row)

                print(
                    f"  File: {basename} | "
                    f"BLOC {bloc_before}->{bloc_after} | "
                    f"CC {cc_before}->{cc_after} | "
                    f"HV {halstead_before}->{halstead_after} | "
                    f"CD {clone_before}->{clone_after} | "
                    f"Cohesion {cohesion_before}->{cohesion_after} | "
                    f"Modularity {modularity_before}->{modularity_after} | "
                    f"Churn {churn_before}->{churn_after} | "
                    f"CF {cf_before}->{cf_after}"
                )

            finally:
                cleanup_temp_files(before_temp, after_temp)

        write_summary(summary_rows)
        print("\nBefore/after analysis completed for all metrics.")

    finally:
        cleanup_temp_files(before_project_dir, after_project_dir)


if __name__ == "__main__":
    if len(sys.argv) < 4:
        print("Usage: python run_before_after_metrics.py <owner> <repo> <commit_sha> [github_token]")
        sys.exit(1)

    owner = sys.argv[1].strip()
    repo = sys.argv[2].strip()
    commit_sha = sys.argv[3].strip()

    if len(sys.argv) >= 5:
        token = sys.argv[4].strip()
    else:
        token = os.environ.get("GITHUB_TOKEN", "").strip()

    if not token:
        print("ERROR: GitHub token not provided.")
        sys.exit(1)

    run_before_after_metrics(owner, repo, commit_sha, token)