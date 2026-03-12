import os
from collections import defaultdict
from datetime import timedelta
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


def get_commit_date(repo_dir: str, target_commit: str):
    for commit in Repository(repo_dir).traverse_commits():
        if commit.hash == target_commit:
            return commit.committer_date
    return None


def calculate_change_frequency_until_commit(repo_dir: str, target_commit: str) -> dict:
    target_date = get_commit_date(repo_dir, target_commit)
    if target_date is None:
        return {}

    since_date = target_date - timedelta(days=30)
    cf_per_file = defaultdict(int)

    commits = list(Repository(repo_dir, since=since_date, to=target_date).traverse_commits())

    for commit in commits:
        touched_in_this_commit = set()

        for mod in commit.modified_files:
            path = mod.new_path or mod.old_path
            if not path:
                continue

            rel = normalize_path(path)
            if rel not in BUILD_PATHS:
                continue

            touched_in_this_commit.add(rel)

        for rel in touched_in_this_commit:
            cf_per_file[rel] += 1

    return dict(cf_per_file)


def compute_change_frequency_for_file_at_commit(file_path: str, commit_sha: str, repo_dir: str = REPO_DIR) -> int:
    if not commit_sha:
        return 0
    cf_data = calculate_change_frequency_until_commit(repo_dir, commit_sha)
    rel = normalize_path(file_path)
    return cf_data.get(rel, 0)