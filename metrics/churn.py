from change_activity import compute_change_activity_for_file_at_commit


def compute_churn_for_file_at_commit(
    owner: str,
    repo: str,
    file_path: str,
    commit_sha: str,
    token: str,
) -> int:
    result = compute_change_activity_for_file_at_commit(owner, repo, file_path, commit_sha, token)
    return int(result["raw_churn"])
