import os
import json
import tempfile
import urllib.request
import urllib.error



# Build file filter

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


def is_target_build_file(path: str) -> bool:
    return normalize_path(path) in BUILD_PATHS



# GitHub API helper

def github_get_json(url: str, token: str) -> dict:
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


# Get commit payload

def get_commit_payload(owner: str, repo: str, commit_sha: str, token: str) -> dict:
    url = f"https://api.github.com/repos/{owner}/{repo}/commits/{commit_sha}"
    return github_get_json(url, token)



# Get parent commit SHA

def get_parent_commit_sha(owner: str, repo: str, commit_sha: str, token: str) -> str | None:
    payload = get_commit_payload(owner, repo, commit_sha, token)
    parents = payload.get("parents", [])
    if not parents:
        return None
    return parents[0]["sha"]



# Get changed build files only

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



# Get raw file content from GitHub at specific commit

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
    except Exception:
        return None



# Write content to temp file

def write_temp_file(content: str | None, suffix: str) -> str | None:
    if content is None:
        return None

    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix, mode="w", encoding="utf-8")
    tmp.write(content)
    tmp.close()
    return tmp.name



# Materialize before/after files for one changed file

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

# Materialize full project snapshot for modularity

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