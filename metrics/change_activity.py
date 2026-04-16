import os

from BLOC import compute_bloc
from github_commits_util import (
    get_file_content_at_commit,
    get_file_stats_for_commit_path,
    list_file_commits_in_window,
    write_temp_file,
)


OBSERVATION_WINDOW_DAYS = 30


def empty_change_activity_result() -> dict:
    return {
        "raw_churn": 0,
        "raw_change_frequency": 0,
        "avg_logical_loc": 0.0,
        "normalized_churn": 0.0,
        "normalized_change_frequency": 0.0,
        "window_days": OBSERVATION_WINDOW_DAYS,
    }


def _average_logical_loc(
    owner: str,
    repo: str,
    file_path: str,
    token: str,
    commits: list[dict],
) -> float:
    samples: list[int] = []
    suffix = os.path.splitext(file_path)[1] or ".txt"

    for commit in commits:
        sha = (commit.get("sha") or "").strip()
        if not sha:
            continue

        content = get_file_content_at_commit(owner, repo, sha, file_path, token)
        if content is None:
            continue

        temp_path = write_temp_file(content, suffix)
        if not temp_path:
            continue

        try:
            samples.append(compute_bloc(temp_path))
        finally:
            try:
                os.remove(temp_path)
            except OSError:
                pass

    if not samples:
        return 0.0

    return round(sum(samples) / len(samples), 4)


def compute_change_activity_for_file_at_commit(
    owner: str,
    repo: str,
    file_path: str,
    commit_sha: str,
    token: str,
    window_days: int = OBSERVATION_WINDOW_DAYS,
) -> dict:
    if not (owner and repo and file_path and commit_sha and token):
        return empty_change_activity_result()

    commits = list_file_commits_in_window(
        owner=owner,
        repo=repo,
        path=file_path,
        token=token,
        until_commit_sha=commit_sha,
        window_days=window_days,
    )

    if not commits:
        result = empty_change_activity_result()
        result["window_days"] = window_days
        return result

    raw_churn = 0
    for commit in commits:
        sha = (commit.get("sha") or "").strip()
        if not sha:
            continue
        stats = get_file_stats_for_commit_path(owner, repo, sha, file_path, token)
        raw_churn += stats["additions"] + stats["deletions"]

    raw_change_frequency = len(commits)
    avg_logical_loc = _average_logical_loc(owner, repo, file_path, token, commits)
    denom = avg_logical_loc if avg_logical_loc > 0 else 1.0

    return {
        "raw_churn": raw_churn,
        "raw_change_frequency": raw_change_frequency,
        "avg_logical_loc": avg_logical_loc,
        "normalized_churn": round(raw_churn / denom, 4),
        "normalized_change_frequency": round((raw_change_frequency / denom) * 100, 4),
        "window_days": window_days,
    }
