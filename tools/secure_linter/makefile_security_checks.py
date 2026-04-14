import re
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional

import requests
from common.version_utils import fetch_latest_version, is_version_outdated
from .makefile_analyzer import MakefileAnalysis


STALE_THRESHOLD = timedelta(days=365 * 2)
VERSION_VAR_RE = re.compile(r'^(?P<pkg>[A-Za-z0-9_\-]+)_VERSION=(?P<ver>\d+\.\d+(?:\.\d+)?)$')
WILDCARD_RE = re.compile(r'\$\(\s*(?:wildcard|eval)\b')
QUOTED_GLOB_RE = re.compile(r"""(['"])([^'"]*\*[^'"]*)\1""")


ABS_PATH_RE = re.compile(
    r"""
    (?:^|[^$\w])            # not preceded by $ or word-char (so not inside a variable)
    (?P<path>
      /(?:[^/\s]+/)*[^/\s"']+            # /foo/bar/baz
      |
      [A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s"']+  # C:\Foo\Bar
    )
    """,
    re.VERBOSE,
)


URL_RE = re.compile(r'(https?://[^\s"\']+)', re.IGNORECASE)
SENSITIVE_RE = re.compile(r'(password|apikey|secret|token)', re.IGNORECASE)
COMMENTED_CMD_RE = re.compile(r'^\s*#.*\b(gcc|javac|mvn|gradle|cmake|compile)\b', re.IGNORECASE)
MAVEN_API = "https://search.maven.org/solrsearch/select"

def _fetch_package_metadata(pkg: str) -> Optional[Dict[str, Any]]:
    try:
        resp = requests.get(
            MAVEN_API,
            params={"q": f'a:"{pkg}"', "rows": 1, "wt": "json", "core": "gav", "sort": "version desc"},
            timeout=5
        )
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])
        return docs[0] if docs else None
    except Exception:
        return None

def check_outdated_version_variables(analysis: MakefileAnalysis) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for var, val in analysis.variables.items():
        m = VERSION_VAR_RE.match(f"{var}={val}")
        if not m:
            continue
        pkg, cur = m.group("pkg"), m.group("ver")
        latest = fetch_latest_version(pkg, pkg)
        if latest and is_version_outdated(cur, latest):
            issues.append({
                "issue": f"Variable '{var}' pins outdated version {cur} (latest is {latest}).",
                "severity": "Medium-High",
            })
    return issues

def check_stale_version_variables(analysis: MakefileAnalysis) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    cutoff = datetime.utcnow() - STALE_THRESHOLD
    for var, val in analysis.variables.items():
        m = VERSION_VAR_RE.match(f"{var}={val}")
        if not m:
            continue
        pkg = m.group("pkg")
        meta = _fetch_package_metadata(pkg)
        if not meta or "timestamp" not in meta:
            continue
        ts = datetime.utcfromtimestamp(meta["timestamp"] / 1000.0)
        if ts < cutoff:
            months = (datetime.utcnow() - ts).days // 30
            issues.append({
                "issue": f"Variable '{var}' package '{pkg}' last released {months} months ago.",
                "severity": "Medium",
            })
    return issues

def check_inconsistent_version_management(analysis: MakefileAnalysis) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    seen: Dict[str, str] = {}
    for var, val in analysis.variables.items():
        if not var.endswith("_VERSION"):
            continue
        if var in seen and seen[var] != val:
            issues.append({
                "issue": f"Inconsistent version for {var}: {seen[var]} vs {val}.",
                "severity": "Medium",
            })
        seen[var] = val
    return issues

def check_duplicate_dependencies(analysis: MakefileAnalysis) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    seen: set[str] = set()
    for tgt in analysis.targets:
        if tgt in seen:
            issues.append({
                "issue": f"Duplicate target definition: {tgt}.",
                "severity": "Low",
            })
        seen.add(tgt)
    return issues

def check_missing_version_information(analysis: MakefileAnalysis) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for var, val in analysis.variables.items():
        if not var.endswith("_VERSION"):
            continue

        semver_re = re.compile(r'^\d+\.\d+(?:\.\d+)*$')
        v=val.strip()
        # empty or no real version (e.g. "Required", "REQUIRED")
        if not semver_re.match(v):
            issues.append({
                "issue": f"Missing or non-numeric version for {var}: {val!r}",
                "severity": "Medium",
            })
    return issues

def check_wildcard_usage(analysis: MakefileAnalysis) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    # in variables
    for var, val in analysis.variables.items():
        if WILDCARD_RE.search(val) or QUOTED_GLOB_RE.search(val) or ("*" in val and not val.startswith("$(")):
            issues.append({
                "issue": f"Potential hidden dependency via wildcard/eval in {var}: {val}.",
                "severity": "Medium",
            })
    # in commands
    for tgt, data in analysis.targets.items():
        for cmd in data["commands"]:
            if WILDCARD_RE.search(cmd) or QUOTED_GLOB_RE.search(cmd) or ("*" in cmd and not cmd.startswith("$(")):
                issues.append({
                    "issue": f"Potential hidden dependency via wildcard/eval in command for {tgt}: {cmd}.",
                    "severity": "Medium",
                })
    return issues

def check_hardcoded_paths_and_urls(analysis: MakefileAnalysis) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    # variables: only catch if the value is quoted
    var_path_pattern = re.compile(r"""(?P<quote>['"])(?P<path>
        (?:/[^\s"'()]+)         # Unix absolute
        |
        [A-Za-z]:\\[^\s"'()]+   # Windows drive
    )(?P=quote)""", re.VERBOSE)

    for var, val in analysis.variables.items():

        for m in var_path_pattern.finditer(val):
                        issues.append({
                                "issue": f"Hardcoded absolute path in variable {var}: {m.group('path')}",
                                "severity": "Low to Medium",
                })
        for url in URL_RE.findall(val):
            issues.append({
                "issue": f"Hardcoded URL in variable {var}: {url}",
                "severity": "High" if url.lower().startswith("http://") else "Low",
            })
    # commands
    for tgt, data in analysis.targets.items():
        for cmd in data["commands"]:
            for m in var_path_pattern.finditer(cmd):
                issues.append({
                    "issue": f"Hardcoded absolute path in command for {tgt}: {m.group('path')}",
                    "severity": "Medium",
                })
            for url in URL_RE.findall(cmd):
                issues.append({
                    "issue": f"Hardcoded URL in command for {tgt}: {url}",
                    "severity": "High" if url.lower().startswith("http://") else "Low",
                })
    return issues

def check_insecure_urls(analysis: MakefileAnalysis) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    # scan raw file for any http:// occurrence
    try:
        with open(analysis._file_path, encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f, start=1):
                if "http://" in line:
                    # pick out full URLs
                    for url in URL_RE.findall(line):
                        if url.lower().startswith("http://"):
                            issues.append({
                                "issue": f"Insecure URL on line {i}: {url}",
                                "severity": "High",
                            })
    except Exception:
        pass
    return issues

def check_sensitive_information(analysis: MakefileAnalysis) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    for var, val in analysis.variables.items():
        if SENSITIVE_RE.search(var) or SENSITIVE_RE.search(val):
            issues.append({
                "issue": f"Hardcoded sensitive info in variable {var}: {val}",
                "severity": "High",
            })
    # commands
    for tgt, data in analysis.targets.items():
        for cmd in data["commands"]:
            if SENSITIVE_RE.search(cmd):
                issues.append({
                    "issue": f"Hardcoded sensitive info in command for {tgt}: {cmd}",
                    "severity": "High",
                })
    return issues
def check_commented_code(analysis: MakefileAnalysis) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    try:
        with open(analysis._file_path, 'r', encoding='utf-8', errors='ignore') as f:
            for i, line in enumerate(f, start=1):
                if COMMENTED_CMD_RE.search(line):
                    issues.append({
                        "issue": f"Commented-out build command on line {i}.",
                        "severity": "Low",
                    })
    except Exception:
        pass
    return issues

def check_error_handling(analysis: MakefileAnalysis) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for tgt, data in analysis.targets.items():
        for cmd in data["commands"]:
            if '|| true' in cmd or '|| :' in cmd:
                issues.append({
                    "issue": f"Lack of error handling in {tgt}: {cmd}",
                    "severity": "Medium",
                })
            if cmd.lstrip().startswith('-'):
                issues.append({
                    "issue": f"Ignoring errors in {tgt} command: {cmd}",
                    "severity": "Medium",
                })
    return issues

def check_complexity(analysis: MakefileAnalysis) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    total_targets = len(analysis.targets)
    max_cmds = max((len(d["commands"]) for d in analysis.targets.values()), default=0)
    if total_targets > 50 or max_cmds > 18:
        issues.append({
            "issue": (
                f"Makefile complexity: {total_targets} targets, "
                f"max {max_cmds} commands in one target."
            ),
            "severity": "Low",
        })
    return issues

