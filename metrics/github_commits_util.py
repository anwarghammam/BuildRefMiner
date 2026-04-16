import os
import json
import tempfile
import urllib.request
import urllib.error
from datetime import datetime, timedelta
from functools import lru_cache
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


BUILD_PATHS = {
    "FilesExamples/build.xml",
    "FilesExamples/pom.xml",
    "FilesExamples/build.gradle",
    "FilesExamples/build.gradle.kts",
    "FilesExamples/TestScript.groovy",
    "FilesExamples/gradle_multi/settings.gradle",
    "FilesExamples/gradle_multi/app/build.gradle",
    "FilesExamples/gradle_multi/core/build.gradle",
    "FilesExamples/gradle_multi/lib/build.gradle",
}


def normalize_path(path: str) -> str:
    return (path or "").replace("\\", "/")


def is_target_build_file(path: str) -> bool:
    return normalize_path(path) in BUILD_PATHS


def _with_query(url: str, **params) -> str:
    parsed = urlsplit(url)
    query = dict(parse_qsl(parsed.query, keep_blank_values=True))
    query.update({k: v for k, v in params.items() if v is not None})
    return urlunsplit(parsed._replace(query=urlencode(query)))


@lru_cache(maxsize=2048)
def github_get_json(url: str, token: str):
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "build-metrics-runner",
    }

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        error_body = ""
        try:
            error_body = e.read().decode("utf-8")
        except Exception:
            pass

        raise RuntimeError(
            f"GitHub API request failed.\n"
            f"URL: {url}\n"
            f"HTTP Status: {e.code}\n"
            f"Response: {error_body}"
        )


def get_commit_payload(owner: str, repo: str, commit_sha: str, token: str) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}"
    return github_get_json(url, token)


def get_commit_datetime(owner: str, repo: str, commit_sha: str, token: str) -> datetime | None:
    payload = get_commit_payload(owner, repo, commit_sha, token)
    raw_date = (
        payload.get("commit", {})
        .get("committer", {})
        .get("date")
        or payload.get("commit", {}).get("author", {}).get("date")
    )
    if not raw_date:
        return None
    try:
        return datetime.fromisoformat(raw_date.replace("Z", "+00:00"))
    except ValueError:
        return None


def get_parent_commit_sha(owner: str, repo: str, commit_sha: str, token: str) -> str | None:
    payload = get_commit_payload(owner, repo, commit_sha, token)
    parents = payload.get("parents", [])
    if not parents:
        return None
    return parents[0]["sha"]


def get_changed_build_files(owner: str, repo: str, commit_sha: str, token: str) -> list[dict]:
    payload = get_commit_payload(owner, repo, commit_sha, token)
    files = payload.get("files", [])

    changed = []
    for f in files:
        path = normalize_path(f.get("filename", ""))
        if not is_target_build_file(path):
            continue

        changed.append({
            "path": path,
            "basename": os.path.basename(path),
            "status": f.get("status", ""),
            "additions": f.get("additions", 0),
            "deletions": f.get("deletions", 0),
            "changes": f.get("changes", 0),
        })

    return changed


def github_get_json_paginated(url: str, token: str) -> list[dict]:
    items: list[dict] = []
    page = 1

    while True:
        page_url = _with_query(url, per_page=100, page=page)
        payload = github_get_json(page_url, token)
        if not isinstance(payload, list):
            raise RuntimeError(f"Expected paginated list response for URL: {page_url}")
        if not payload:
            break
        items.extend(payload)
        if len(payload) < 100:
            break
        page += 1

    return items


def list_file_commits_in_window(
    owner: str,
    repo: str,
    path: str,
    token: str,
    until_commit_sha: str,
    window_days: int = 30,
) -> list[dict]:
    commit_dt = get_commit_datetime(owner, repo, until_commit_sha, token)
    if commit_dt is None:
        return []

    since_dt = commit_dt - timedelta(days=window_days)
    base_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    url = _with_query(
        base_url,
        path=normalize_path(path),
        since=since_dt.isoformat(),
        until=commit_dt.isoformat(),
    )
    return github_get_json_paginated(url, token)


@lru_cache(maxsize=4096)
def get_file_content_at_commit(owner: str, repo: str, commit_sha: str, path: str, token: str) -> str | None:
    path = normalize_path(path)
    url = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit_sha}/{path}"

    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "build-metrics-runner",
    }

    req = urllib.request.Request(url, headers=headers)

    try:
        with urllib.request.urlopen(req) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        if e.code == 404:
            return None
        print(f"[WARN] HTTP error fetching {path} at {commit_sha}: {e}")
        return None
    except Exception as e:
        print(f"[WARN] Error fetching {path} at {commit_sha}: {e}")
        return None


def get_file_stats_for_commit_path(
    owner: str,
    repo: str,
    commit_sha: str,
    path: str,
    token: str,
) -> dict[str, int]:
    normalized = normalize_path(path)
    payload = get_commit_payload(owner, repo, commit_sha, token)

    for file_info in payload.get("files", []):
        current_name = normalize_path(file_info.get("filename", ""))
        previous_name = normalize_path(file_info.get("previous_filename", ""))
        if normalized not in {current_name, previous_name}:
            continue
        return {
            "additions": file_info.get("additions", 0) or 0,
            "deletions": file_info.get("deletions", 0) or 0,
            "changes": file_info.get("changes", 0) or 0,
        }

    return {"additions": 0, "deletions": 0, "changes": 0}


def write_temp_file(content: str | None, suffix: str) -> str | None:
    if content is None:
        return None

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="w", encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return tmp.name


def materialize_before_after_files(owner: str, repo: str, commit_sha: str, token: str, rel_path: str) -> dict:
    rel_path = normalize_path(rel_path)
    parent_sha = get_parent_commit_sha(owner, repo, commit_sha, token)

    suffix = os.path.splitext(rel_path)[1] or ".txt"

    before_content = None
    after_content = None

    if parent_sha:
        before_content = get_file_content_at_commit(owner, repo, parent_sha, rel_path, token)

    after_content = get_file_content_at_commit(owner, repo, commit_sha, rel_path, token)

    before_temp = write_temp_file(before_content, suffix)
    after_temp = write_temp_file(after_content, suffix)

    return {
        "parent_sha": parent_sha,
        "commit_sha": commit_sha,
        "path": rel_path,
        "basename": os.path.basename(rel_path),
        "before_temp": before_temp,
        "after_temp": after_temp,
    }


def materialize_project_snapshot(
    owner: str,
    repo: str,
    commit_sha: str,
    token: str,
    build_paths: set[str] | None = None,
) -> str:
    if not commit_sha:
        return ""

    build_paths = build_paths or BUILD_PATHS
    temp_dir = tempfile.mkdtemp(prefix="build_snapshot_")

    for rel_path in build_paths:
        content = get_file_content_at_commit(owner, repo, commit_sha, rel_path, token)
        if content is None:
            continue

        abs_path = os.path.join(temp_dir, rel_path)
        os.makedirs(os.path.dirname(abs_path), exist_ok=True)

        with open(abs_path, "w", encoding="utf-8") as f:
            f.write(content)

    return temp_dir
