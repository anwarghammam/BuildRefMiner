from __future__ import annotations

import logging
import os
import re
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Set, Tuple, Optional

from lxml import etree
from lxml.etree import _Comment

from common.version_utils import resilient_latest_version as _latest, \
                                 is_version_outdated


logger = logging.getLogger(__name__)

STALE_THRESHOLD = timedelta(days=365 * 2)
MAVEN_API_URL = "https://search.maven.org/solrsearch/select"

def _fetch_package_metadata(group: str, artifact: str) -> Optional[Dict]:
    params = {
        "q": f'g:"{group}" AND a:"{artifact}"',
        "rows": 1,
        "wt": "json",
        "core": "gav",
        "sort": "version desc",
    }
    try:
        resp = requests.get(MAVEN_API_URL, params=params, timeout=5)
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])
        return docs[0] if docs else None
    except requests.RequestException as exc:
        logger.warning("Could not fetch metadata for %s:%s – %s", group, artifact, exc)
        return None


def _dependency_management_index(root) -> Set[Tuple[str, str]]:
    idx: Set[Tuple[str, str]] = set()
    for dm in root.xpath("//*[local-name()='dependencyManagement']"
                         "/*[local-name()='dependencies']"
                         "/*[local-name()='dependency']"):
        g = dm.findtext("*[local-name()='groupId']", default="").strip()
        a = dm.findtext("*[local-name()='artifactId']", default="").strip()
        if g and a:
            idx.add((g, a))
    return idx

def check_inconsistent_dependency_versions(pom_root) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    seen: Dict[str, str] = {}
    for dep in pom_root.findall(".//{*}dependency"):
        g = dep.findtext("{*}groupId", default="").strip()
        a = dep.findtext("{*}artifactId", default="").strip()
        v = dep.findtext("{*}version", default="").strip()
        if not (g and a and v):
            continue
        key = f"{g}:{a}"
        if key in seen and seen[key] != v:
            issues.append({
                "issue": f"Inconsistent versions for {key}: {seen[key]} vs. {v}",
                "severity": "Medium",
            })
        seen[key] = v

    mgmt_versions: Dict[tuple[str, str], str] = {}
    for dm in pom_root.xpath(
            "//*[local-name()='dependencyManagement']"
            "/*[local-name()='dependencies']"
            "/*[local-name()='dependency']"):
        g = dm.findtext("*[local-name()='groupId']", default="").strip()
        a = dm.findtext("*[local-name()='artifactId']", default="").strip()
        v = dm.findtext("*[local-name()='version']", default="").strip()
        if g and a and v:
            mgmt_versions[(g, a)] = v

    for dep in pom_root.xpath(
            "//*[local-name()='dependencies']"
            "[not(ancestor::*[local-name()='dependencyManagement'])]"
            "/*[local-name()='dependency']"):
        g = dep.findtext("*[local-name()='groupId']", default="").strip()
        a = dep.findtext("*[local-name()='artifactId']", default="").strip()
        v = dep.findtext("*[local-name()='version']", default="").strip()
        if (g, a) in mgmt_versions and v and v != mgmt_versions[(g, a)]:
            issues.append({
                "issue": (
                    f"Dependency {g}:{a} declares version {v}, "
                    f"but dependencyManagement sets {mgmt_versions[(g, a)]}"
                ),
                "severity": "Medium",
            })

    return issues

def check_inconsistent_plugin_management(pom_root) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    # 1) Gather pluginManagement versions
    mgmt: Dict[tuple[str, str], str] = {}
    for pm in pom_root.xpath(
            "//*[local-name()='pluginManagement']"
            "/*[local-name()='plugins']"
            "/*[local-name()='plugin']"):
        g = pm.findtext("*[local-name()='groupId']", default="").strip()
        a = pm.findtext("*[local-name()='artifactId']", default="").strip()
        v = pm.findtext("*[local-name()='version']", default="").strip()
        if g and a and v:
            mgmt[(g, a)] = v

    for pl in pom_root.xpath(
            "//*[local-name()='plugins']"
            "[not(ancestor::*[local-name()='pluginManagement'])]"
            "/*[local-name()='plugin']"):
        g = pl.findtext("*[local-name()='groupId']", default="").strip()
        a = pl.findtext("*[local-name()='artifactId']", default="").strip()
        v = pl.findtext("*[local-name()='version']", default="").strip()
        if (g, a) in mgmt and v and v != mgmt[(g, a)]:
            issues.append({
                "issue": (
                    f"Plugin {g}:{a} declares version {v}, "
                    f"but pluginManagement sets {mgmt[(g, a)]}"
                ),
                "severity": "Medium",
            })

    return issues

def check_outdated_dependencies(pom_root) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for dep in pom_root.findall(".//{*}dependency"):
        g = dep.findtext("{*}groupId", default="").strip()
        a = dep.findtext("{*}artifactId", default="").strip()
        v = dep.findtext("{*}version", default="").strip()

        if not (g and a and v):
            issues.append({
                "issue": f"Missing GAV for dependency: {g}:{a}:{v}",
                "severity": "Medium-High",
            })
            continue

        latest = _latest(g, a)
        if latest is None:
            logger.debug("No latest version for %s:%s", g, a)
            continue

        try:
            if is_version_outdated(v, latest):
                issues.append({
                    "issue": f"Outdated dependency: {g}:{a} (current {v}, latest {latest})",
                    "severity": "Medium",
                })
        except Exception as exc:
            logger.debug("Version compare failed for %s:%s (%s vs %s): %s", g, a, v, latest, exc)

    return issues

def check_missing_dependency_versions(pom_root) -> List[Dict[str, str]]:
    managed = _dependency_management_index(pom_root)
    issues: List[Dict[str, str]] = []
    for dep in pom_root.findall(".//{*}dependency"):
        g = dep.findtext("{*}groupId", default="").strip()
        a = dep.findtext("{*}artifactId", default="").strip()
        if (g, a) in managed:
            continue
        e = dep.find("{*}version")
        if e is None or not (e.text or "").strip():
            issues.append({
                "issue": f"Missing version info for dependency {g}:{a}",
                "severity": "Medium",
            })
    return issues

def check_deprecated_dependencies(pom_root) -> List[Dict[str, str]]:
    cutoff = datetime.utcnow() - STALE_THRESHOLD
    issues: List[Dict[str, str]] = []

    for dep in pom_root.findall(".//{*}dependency"):
        g = dep.findtext("{*}groupId", default="").strip()
        a = dep.findtext("{*}artifactId", default="").strip()
        if not (g and a):
            continue

        meta = _fetch_package_metadata(g, a)
        if not meta or "timestamp" not in meta:
            continue

        last = datetime.utcfromtimestamp(meta["timestamp"] / 1000.0)
        if last < cutoff:
            months = (datetime.utcnow() - last).days // 30
            issues.append({
                "issue": (
                    f"Dependency '{g}:{a}' last released {months} months ago "
                    f"(last: {last.date()})"
                ),
                "severity": "Medium-High",
            })
    return issues

def check_duplicate_dependencies(pom_root) -> List[Dict[str, str]]:
    seen: Set[str] = set()
    issues: List[Dict[str, str]] = []
    for dep in pom_root.findall(".//{*}dependency"):
        combo = f"{dep.findtext('{*}groupId','').strip()}:{dep.findtext('{*}artifactId','').strip()}"
        if combo in seen:
            issues.append({"issue": f"Duplicate dependency declared: {combo}", "severity": "Low"})
        else:
            seen.add(combo)
    return issues


def check_duplicate_plugins(pom_root) -> List[Dict[str, str]]:
    seen: Set[str] = set()
    issues: List[Dict[str, str]] = []
    for pl in pom_root.findall(".//{*}plugin"):
        combo = f"{pl.findtext('{*}groupId','').strip()}:{pl.findtext('{*}artifactId','').strip()}"
        if combo in seen:
            issues.append({"issue": f"Duplicate plugin declared: {combo}", "severity": "Low"})
        else:
            seen.add(combo)
    return issues

def check_suspicious_comments(pom_root) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for c in pom_root.xpath("//comment()"):
        t = (c.text or "").strip()
        if re.search(r"<[A-Za-z][^>]*>.*</[A-Za-z]+>", t):
            snippet = t.replace("\n", " ")[:40] + "…"
            issues.append({"issue": f"Suspicious commented-out code: {snippet}", "severity": "Low"})
    return issues

def check_hardcoded_paths_and_urls(pom_root) -> List[Dict[str, str]]:
    from lxml.etree import _Comment
    issues: List[Dict[str, str]] = []
    for elem in pom_root.iter():
        if isinstance(elem, _Comment):
            continue
        tag = etree.QName(elem.tag).localname.lower()
        text = (elem.text or "").strip()
        if not text:
            continue

        if os.path.isabs(text):
            issues.append({"issue": f"Hardcoded absolute path in <{tag}>: {text}", "severity": "Medium"})

        if "http://" in text:
            issues.append({
                "issue": f"Insecure URL in <{tag}>: {text}",
                "severity": "High",
            })
        elif text.startswith("https://"):
            issues.append({"issue": f"Hardcoded URL in <{tag}>: {text}", "severity": "Low"})

    return issues

def check_insecure_urls(pom_root) -> List[Dict[str, str]]:

    issues: List[Dict[str, str]] = []
    url_pattern = re.compile(r"https?://[^\s<>]+", re.IGNORECASE)

    for elem in pom_root.iter():
        if isinstance(elem, _Comment):
            continue

        tag = etree.QName(elem.tag).localname
        text = (elem.text or "").strip()
        for url in url_pattern.findall(text):
            if url.lower().startswith("http://"):
                issues.append({
                    "issue": f"Insecure URL in <{tag}> text: {url}",
                    "severity": "High",
                })
        for attr, val in elem.items():
            for url in url_pattern.findall(val):
                if url.lower().startswith("http://"):
                    issues.append({
                        "issue": f"Insecure URL in attribute '{attr}' of <{tag}>: {url}",
                        "severity": "High",
                    })

    return issues

def check_empty_xml_tags(pom_root) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for elem in pom_root.xpath("//*[not(node())]"):
        name = etree.QName(elem.tag).localname.lower()
        if name in {"url", "license", "licenses", "developer", "developers", "scm"}:
            issues.append({"issue": f"<{name}> is empty – supply required metadata.", "severity": "Low"})
    return issues

def check_lack_of_error_handling(pom_root) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []

    for pl in pom_root.findall(".//{*}plugin"):
        if not pl.findall("{*}executions/*"):
            continue

        config = pl.find("{*}configuration")
        found = False

        if config is not None:
            fo = config.find("{*}failOnError")

            if fo is not None:
                found = True

                if (fo.text or "").strip().lower() == "false":
                    issues.append({
                        "issue": "failOnError set to false – lacks error handling.",
                        "severity": "Medium",
                    })
            oe = config.find("{*}onError")

            if oe is not None:
                found = True

        if not found:
            issues.append({
                "issue": "Plugin execution lacks error-handling directive (<failOnError> or <onError>).",
                "severity": "Low",
            })

    for pm in pom_root.findall(".//{*}plugin"):
        skip = pm.find(".//{*}skip")

        if skip is not None and (skip.text or "").strip().lower() == "true":
            issues.append({
                "issue": "skip=true found in plugin config – poor error handling.",
                "severity": "Medium",
            })
    return issues

def check_complex_heuristics(pom_root) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    # 1) count profiles & executions
    profiles = pom_root.findall(".//{*}profile")
    executions = pom_root.findall(".//{*}execution")
    if len(profiles) > 3 or len(executions) > 10:
        issues.append({
            "issue": f"Complex build structure: {len(profiles)} profiles, {len(executions)} executions.",
            "severity": "Low",
        })

    def depth(node, lvl=0):
        m = lvl
        for c in node:
            m = max(m, depth(c, lvl+1))
        return m
    d = depth(pom_root)
    if d > 8:
        issues.append({
            "issue": f"Complex POM: XML nesting depth {d}.",
            "severity": "Low",
        })

    return issues

def check_wildcard_version_ranges(pom_root) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    for dep in pom_root.findall(".//{*}dependency"):
        v = dep.findtext("{*}version", default="").strip()
        if v and any(c in v for c in "*[],()+"):
            g = dep.findtext("{*}groupId", default="").strip()
            a = dep.findtext("{*}artifactId", default="").strip()
            issues.append({"issue": f"Wildcard/range version for {g}:{a} = {v}", "severity": "Medium"})
    return issues

def check_hardcoded_credentials(pom_root) -> List[Dict[str, str]]:
    issues: List[Dict[str, str]] = []
    pat = re.compile(r"\b(password|apikey|secret|token)\b", re.IGNORECASE)
    from lxml.etree import _Comment

    for elem in pom_root.iter():
        if isinstance(elem, _Comment):
            continue
        tag = etree.QName(elem.tag).localname
        txt = (elem.text or "").strip()
        if txt and pat.search(txt) and not txt.startswith("${"):
            issues.append({
                "issue": f"Hardcoded sensitive info in <{tag}>: {txt}",
                "severity": "High",
            })

        for name, val in elem.items():
            if val and pat.search(val) and not val.startswith("${"):
                issues.append({
                    "issue": f"Hardcoded sensitive attribute '{name}' in <{tag}>: {val}",
                    "severity": "High",
                })
    return issues

def check_missing_dependency_versions(pom_root) -> List[Dict[str, str]]:
    managed = _dependency_management_index(pom_root)
    has_parent = pom_root.find("{*}parent") is not None

    issues: List[Dict[str, str]] = []
    for dep in pom_root.findall(".//{*}dependency"):
        g = dep.findtext("{*}groupId",    default="").strip()
        a = dep.findtext("{*}artifactId", default="").strip()

        if (g, a) in managed or has_parent:
            continue

        e = dep.find("{*}version")
        if e is None or not (e.text or "").strip():
            issues.append({
                "issue": f"Missing version info for dependency {g}:{a}",
                "severity": "Medium",
            })
    return issues
