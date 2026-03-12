import os
from collections import defaultdict
from pydriller import Repository

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))

BUILD_PATHS = {
    "FilesExamples/build.xml",
    "FilesExamples/pom.xml",
    "FilesExamples/build.gradle",
    "FilesExamples/TestScript.groovy",
    "FilesExamples/gradle_multi/app/build.gradle",
    "FilesExamples/gradle_multi/core/build.gradle",
    "FilesExamples/gradle_multi/lib/build.gradle",
}


def normalize_path(path: str) -> str:
    return (path or "").replace("\\", "/")


def calculate_churn_until_commit(repo_dir: str, target_commit: str) -> dict:
    churn_per_file = defaultdict(int)

    commits = list(Repository(repo_dir).traverse_commits())
    commits.reverse()

    for commit in commits:
        for mod in commit.modified_files:
            path = mod.new_path or mod.old_path
            if not path:
                continue

            rel = normalize_path(path)
            if rel not in BUILD_PATHS:
                continue

            added = mod.added_lines or 0
            deleted = mod.deleted_lines or 0
            churn_per_file[rel] += (added + deleted)

        if commit.hash == target_commit:
            break

    return dict(churn_per_file)


def compute_churn_for_file_at_commit(file_path: str, commit_sha: str, repo_dir: str = REPO_DIR) -> int:
    if not commit_sha:
        return 0
    churn_data = calculate_churn_until_commit(repo_dir, commit_sha)
    rel = normalize_path(file_path)
    return churn_data.get(rel, 0)