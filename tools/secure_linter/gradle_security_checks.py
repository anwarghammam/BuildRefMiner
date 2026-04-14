from __future__ import annotations
import re
from typing import List, Dict, Optional
from datetime import datetime, timedelta
import requests
from lxml import etree
from functools import lru_cache
import semantic_version
version_cache={}

from common.version_utils import fetch_latest_version, is_version_outdated

STALE_THRESHOLD = timedelta(days=365 * 2)


_SIMPLE_DEP = re.compile(
r"^\s*(api|implementation|compileOnly|runtimeOnly|compile|"
    r"testImplementation|testCompile|androidTestImplementation|androidTestCompile)"
    r"\s+['\"]([^:]+):([^:]+):([^'\"]+)['\"]",
    re.MULTILINE
)
_MAP_DEP = re.compile(
     r"^\s*(api|implementation|compileOnly|runtimeOnly|compile|"
     r"testImplementation|testCompile|androidTestImplementation|androidTestCompile)"
    r"\s*\(\s*group\s*=\s*['\"](.+?)['\"],\s*name\s*=\s*['\"](.+?)['\"],"
    r"\s*version\s*=\s*['\"](.+?)['\"]\s*\)",
    re.MULTILINE
)
_KOTLIN_DEP = re.compile(
    r"""^\s*
        (api|implementation)\s*\(\s*        # 1 configuration
        ['"]([^:'"]+):([^:'"]+)['"]\s*      # 2‑3 group / artifact
        \)\s*\{\s*
        version\s*=\s*['"](.+?)['"]\s*      # 4 version
        \}""",
    re.MULTILINE | re.VERBOSE,
)
def _all_deps(gradle_data):
    text = gradle_data["raw_content"]
    for pat in (_SIMPLE_DEP, _MAP_DEP, _KOTLIN_DEP):
        for m in pat.finditer(text):
            try:
                if len(m.groups()) == 4:  # Kotlin‑DSL
                    yield m.group(2), m.group(3), m.group(4)
                else:
                    yield m.group(2), m.group(3), m.group(4)
            except IndexError:
                if len(m.groups()) == 4:  # Kotlin‑DSL
                    yield m.group(2), m.group(3), m.group(4)
                else:  # Groovy patterns (3 groups)
                    yield m.group(2), m.group(3), m.group(4)
MAVEN_SEARCH = "https://search.maven.org/solrsearch/select"
_UA          = {"User-Agent": "secure‑linter/1.2 (+https://github.com/…)"}
@lru_cache(maxsize=1024)                    # ❶ cache results (1 call per G/A)
def _fetch_maven_metadata(group: str, artifact: str) -> Optional[Dict]:

    params = {
        "q": f'g:"{group}" AND a:"{artifact}"',
        "rows": 1, "wt": "json",
        "core": "gav",
        "sort": "version desc",
    }
    try:
        r = requests.get(MAVEN_SEARCH, params=params, timeout=5, headers=_UA)
        if r.status_code in (403, 429):
            import time; time.sleep(1.0)      # gentle back‑off, then retry
            r = requests.get(MAVEN_SEARCH, params=params, timeout=5, headers=_UA)
        r.raise_for_status()
        docs = r.json().get("response", {}).get("docs", [])
        if docs:
            return docs[0]                    # has «timestamp» in ms
    except requests.RequestException:
        pass                                  # fall through to XML fallback

    try:
        path = f"{group.replace('.', '/')}/{artifact}/maven-metadata.xml"
        url  = f"https://repo1.maven.org/maven2/{path}"
        r = requests.get(url, timeout=5, headers=_UA)
        r.raise_for_status()
        xml = etree.fromstring(r.content)
        last_updated = xml.findtext("versioning/lastUpdated")
        if last_updated and last_updated.isdigit():               # YYYYMMDDHHMMSS
            dt = datetime.strptime(last_updated, "%Y%m%d%H%M%S")
            return {"timestamp": int(dt.timestamp() * 1000)}      # mimic Solr doc
    except Exception:
        pass

    return None
def check_deprecated_dependencies(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    cutoff = datetime.utcnow() - STALE_THRESHOLD
    for grp, art, ver in _all_deps(gradle_data):
        meta = _fetch_maven_metadata(grp, art)
        if not meta or "timestamp" not in meta:
            continue
        last = datetime.utcfromtimestamp(meta["timestamp"] / 1000.0)
        if last < cutoff:
            months = (datetime.utcnow() - last).days // 30
            issues.append({
                "issue": f"Dependency {grp}:{art} last released {months} months ago (last: {last.date()})",
                "severity": "Medium-High",
            })
    return issues

CREDS_RE = re.compile(
    r"""(?i)(?<!\w)                 # word‑boundary
        (?:password|apikey|api_key|
           secret|token|pwd|passphrase)
        (?:\s*[:=]\s*|               #  password =
           \s+['"]|                  #  password "…
           \s*\()                    #  password(
    """,
    re.VERBOSE,
)

def check_hardcoded_credentials(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for m in CREDS_RE.finditer(gradle_data["raw_content"]):
        # translate absolute position → line number
        lineno = gradle_data["raw_content"][:m.start()].count("\n") + 1
        snippet = gradle_data["raw_content"].splitlines()[lineno - 1].strip()
        issues.append({
            "issue": f"Hardcoded sensitive info on line {lineno}: {snippet}",
            "severity": "High",
        })
    return issues

def check_hardcoded_signing_credentials(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    pattern = re.compile(r"\b(storePassword|keyPassword)\s+['\"](.+?)['\"]")
    for i, line in enumerate(gradle_data["raw_content"].splitlines(), start=1):
        m = pattern.search(line)
        if m:
            issues.append({
                "issue": f"Hardcoded signing credential {m.group(1)} on line {i}: {m.group(2)}",
                "severity": "High",
            })
    return issues

def check_hardcoded_paths_and_urls(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for quote, path in re.findall(r"(['\"])(/[^'\"]+|[A-Za-z]:[/\\][^'\"]+)\1",
                                  gradle_data["raw_content"]):
        issues.append({"issue": f"Hardcoded absolute path: {path}", "severity": "Medium"})

    for url in re.findall(r"(https?://[^\s'\"{}]+)",
                          gradle_data["raw_content"], re.IGNORECASE):

        if url.lower().startswith("http://"):
            sev = "High"
        else:
            sev = "Low"
        issues.append({"issue": f"Hardcoded URL found: {url}", "severity": sev})
    return issues

def check_missing_version_information(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for dep in gradle_data["dependencies"]:
        grp, art, ver = dep["group"], dep["artifact"], dep["version"]
        if not ver:
            issues.append({
                "issue": f"Missing version information for dependency {grp}:{art}",
                "severity": "Medium",
            })
    return issues

def check_wildcard_version_ranges(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for i, line in enumerate(gradle_data["raw_content"].splitlines(), start=1):
        if re.search(r"""['"][^'"]+:[^'"]+:[^'"]*[\*\[\]\+,][^'"]*['"]""", line):
            issues.append({
                "issue": f"Wildcard/range version on line {i}: {line.strip()}",
                "severity": "Medium",
            })
    return issues

def check_missing_version_in_raw(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    pattern = re.compile(
        r"^\s*(api|implementation|compileOnly|runtimeOnly|compile|testImplementation)"
        r"\s+['\"]([^:]+):([^:'\"]+)['\"]",
        re.MULTILINE
    )
    for i, line in enumerate(gradle_data["raw_content"].splitlines(), start=1):
        if pattern.match(line) and ":" in line and line.count(":") == 1:
            grp, art = pattern.match(line).groups()[1:]
            issues.append({
                "issue": f"Missing version information for dependency {grp}:{art} (line {i})",
                "severity": "Medium",
            })
    return issues
def check_property_based_versions(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    prop_pattern = re.compile(r"^\$\{.+\}$")
    for dep in gradle_data["dependencies"]:
        ver = (dep["version"] or "").strip()
        if prop_pattern.match(ver) or ver.startswith("libs.") or ver.startswith("project("):
            issues.append({
                "issue": f"Property-based/catalog version for {dep['group']}:{dep['artifact']} = {ver}",
                "severity": "Low",
            })
    return issues

def check_catalog_dependencies(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    pattern = re.compile(r"^\s*(api|implementation|compileOnly|runtimeOnly)\s*\(\s*libs\.", re.MULTILINE)
    for i, line in enumerate(gradle_data["raw_content"].splitlines(), start=1):
        if pattern.search(line):
            issues.append({
                "issue": f"Catalog-based dependency on line {i}: {line.strip()}",
                "severity": "Low",
            })
    return issues

def check_project_dependencies(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    pattern = re.compile(r"^\s*(api|implementation)\s*\(\s*project\(", re.MULTILINE)
    for i, line in enumerate(gradle_data["raw_content"].splitlines(), start=1):
        if pattern.search(line):
            issues.append({
                "issue": f"Project-based dependency on line {i}: {line.strip()}",
                "severity": "Low",
            })
    return issues

def check_outdated_dependencies(gradle_data) -> List[Dict[str, str]]:
    issues = []
    for dep in gradle_data["dependencies"]:
        group = dep["group"]
        artifact = dep["artifact"]
        current_version = dep["version"]
        if not group or not artifact or not current_version:
            issues.append({
                "issue": f"Dependency with missing info: group='{group}', artifact='{artifact}', version='{current_version}'",
                "severity": "Medium-High"
            })
            continue

        latest_version = get_latest_version_maven_central(group, artifact)
        if latest_version:
            if is_version_outdated(current_version, latest_version):
                issues.append({
                    "issue": f"Outdated Gradle dependency: {group}:{artifact} (current={current_version}, latest={latest_version})",
                    "severity": "Medium-High"
                })
        else:
            # Could not fetch or no results
            pass
    return issues

def get_latest_version_maven_central(group_id, artifact_id):
    key = f"{group_id}:{artifact_id}"
    if key in version_cache:
        return version_cache[key]

    base_url = "https://search.maven.org/solrsearch/select"
    params = {
        'q': f'g:"{group_id}" AND a:"{artifact_id}"',
        'rows': '1',
        'wt': 'json',
        'core': 'gav',
        'sort': 'version desc'
    }
    try:
        response = requests.get(base_url, params=params, timeout=5)
        if response.status_code == 200:
            data = response.json()
            docs = data.get('response', {}).get('docs', [])
            if docs:
                latest_version = docs[0].get('v')
                version_cache[key] = latest_version
                return latest_version
    except:
        pass
    return None

def is_version_outdated(current_version, latest_version):
    try:
        current = semantic_version.Version.coerce(current_version)
        latest = semantic_version.Version.coerce(latest_version)
        return current < latest
    except:
        return False

def check_inconsistent_version_management(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    lines = gradle_data["raw_content"].splitlines()

    # BOM via platform(...)
    uses_bom = any("platform(" in l for l in lines)
    # property via ${...}
    uses_prop = bool(re.search(r""":\$\{[^}]+\}""", gradle_data["raw_content"]))
    # direct literal
    uses_direct = any(v and not v.startswith("$") for _, _, v in _all_deps(gradle_data))

    if (uses_bom or uses_prop) and uses_direct:
        issues.append({
            "issue": "Inconsistent version management: mix of BOM/platform/property-based and literal versions.",
            "severity": "Medium",
        })
    return issues

def check_duplicate_code(gradle_data):
    issues = []
    lines_seen = {}
    for line in gradle_data["raw_content"].splitlines():
        l = line.strip()
        if len(l) > 20:  # some arbitrary length
            if l in lines_seen:
                issues.append({
                    "issue": f"Likely duplicate code line found: {l[:40]}...",
                    "severity": "Low"
                })
            else:
                lines_seen[l] = True
    return issues

def check_duplicate_dependencies(gradle_data):
    issues = []
    seen = {}
    for dep in gradle_data["dependencies"]:
        combo = f"{dep['group']}:{dep['artifact']}"
        if combo in seen:
            issues.append({
                "issue": f"Duplicate Gradle dependency found: {combo}",
                "severity": "Low"
            })
        else:
            seen[combo] = True
    return issues

def check_suspicious_comment(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for i, line in enumerate(gradle_data["raw_content"].splitlines(), 1):
        if re.search(r"^\s*//.*\b(task|implementation|compile|if|TODO|FIXME)\b", line, re.IGNORECASE):
            issues.append({"issue": f"Suspicious commented code on line {i}: {line.strip()}", "severity": "Low"})
    return issues

def check_missing_or_improper_error_handling(gradle_data) -> List[Dict[str, str]]:
    raw = gradle_data["raw_content"]
    issues: List[Dict[str, str]] = []

    if raw.lstrip().startswith("@file:"):
        return issues

    has_exec = bool(re.search(r"^\s*exec\s*\{", raw, re.MULTILINE))

    if has_exec and "failOnError" not in raw and "failFast" not in raw:
        issues.append({
            "issue": "Missing error-handling directive 'failOnError' or 'failFast'.",
            "severity": "Low",
        })

    if has_exec:
        if re.search(r"failOnError\s*=\s*false", raw):
            issues.append({
                "issue": "Improper error handling: failOnError set to false.",
                "severity": "Medium",
            })

    if re.search(r"failFast\s*=\s*false", raw):
        issues.append({
            "issue": "Improper error handling: failFast set to false.",
            "severity": "Medium",
        })

    if re.search(r"ignoreFailures\s*=\s*true", raw):
        issues.append({
            "issue": "Improper error handling: ignoreFailures set to true.",
            "severity": "Medium",
        })
    return issues

import re
from typing import List, Dict

def check_complexity(gradle_data) -> List[Dict[str, str]]:
    raw = gradle_data["raw_content"]
    issues: List[Dict[str, str]] = []

    # 1) existing “structural” score: count conditionals & task defs
    cond_count = sum(len(re.findall(pat, raw)) for pat in (
        r"\bif\s*\(", r"\bfor\s*\(", r"\bwhile\s*\(", r"\bswitch\s*\(",
    ))
    task_count = len(re.findall(r"\btask\s+\w+", raw))
    structure_score = cond_count + task_count
    if structure_score > 12:
        issues.append({
            "issue": f"Complex logic in Gradle script (score={structure_score} conditionals/tasks).",
            "severity": "Low",
        })

    depth = 0
    max_depth = 0
    in_str = False
    esc = False
    for c in raw:
        if c == "\\" and not esc:
            esc = True
            continue
        if c in ("'", '"') and not esc:
            in_str = not in_str
        esc = False
        if in_str:
            continue

        if c == "{":
            depth += 1
            max_depth = max(max_depth, depth)
        elif c == "}":
            depth = max(depth - 1, 0)

    if max_depth > 3:
        issues.append({
            "issue": f"Nested closures depth = {max_depth}, consider flattening.",
            "severity": "Low",
        })

    return issues


def check_wildcard_usage(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for line in gradle_data["raw_content"].splitlines():
        if re.search(r"\b(fileTree|files)\s*\(", line):
            issues.append({
                "issue": f"Potential hidden dependency via wildcard/fileTree: {line.strip()}",
                "severity": "Medium",
            })
    return issues

def check_insecure_urls(gradle_data) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    url_pattern = re.compile(r"https?://[^\s'\"{}]+", re.IGNORECASE)

    for lineno, line in enumerate(gradle_data["raw_content"].splitlines(), start=1):
        for url in url_pattern.findall(line):
            if url.lower().startswith("http://"):
                issues.append({
                    "issue": f"Insecure URL on line {lineno}: {url}",
                    "severity": "High",
                })

    return issues