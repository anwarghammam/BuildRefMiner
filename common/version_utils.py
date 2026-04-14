from __future__ import annotations

import os
import json
import time
import random
import logging
import requests
import semantic_version
from lxml import etree
from typing import Optional
from urllib3.util.retry import Retry
from requests.adapters import HTTPAdapter

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def create_resilient_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=3,
        backoff_factor=1.5,
        status_forcelist=[429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount("https://", adapter)
    return session

session = create_resilient_session()
BASE_URL = "https://search.maven.org/solrsearch/select"
HEADERS = {"User-Agent": "secure-linter/1.1 (+https://github.com/…)"}

CACHE_FILE = "maven_cache.json"
if os.path.exists(CACHE_FILE):
    with open(CACHE_FILE, "r") as f:
        CACHE = json.load(f)
else:
    CACHE = {}

def save_cache():
    with open(CACHE_FILE, "w") as f:
        json.dump(CACHE, f)

def fetch_latest_version(group: str, artifact: str) -> Optional[str]:
    key = f"{group}:{artifact}"
    if key in CACHE:
        return CACHE[key] or None

    path = f"{group.replace('.', '/')}/{artifact}/maven-metadata.xml"
    meta_url = f"https://repo1.maven.org/maven2/{path}"
    try:
        resp = session.get(meta_url, timeout=10, headers=HEADERS)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", "5"))
            logger.warning("XML: Rate-limited. Waiting %s seconds before retrying.", wait)
            time.sleep(wait)
            resp = session.get(meta_url, timeout=10, headers=HEADERS)
        resp.raise_for_status()
        xml = etree.fromstring(resp.content)
        release = xml.findtext("versioning/release")
        if release:
            CACHE[key] = release
            save_cache()
            return release
        latest = xml.findtext("versioning/latest")
        if latest:
            CACHE[key] = latest
            save_cache()
            return latest
    except Exception as e:
        logger.warning("XML metadata fetch failed for %s:%s – %s", group, artifact, e)

    params = {
        "q": f'g:"{group}" AND a:"{artifact}"',
        "rows": "1",
        "wt": "json",
        "core": "gav",
        "sort": "version desc",
    }
    try:
        time.sleep(random.uniform(0.5, 1.5))  # gentle throttle
        resp = session.get(BASE_URL, params=params, timeout=10, headers=HEADERS)
        if resp.status_code == 429:
            wait = int(resp.headers.get("Retry-After", "5"))
            logger.warning("Solr: Rate-limited. Waiting %s seconds before retrying.", wait)
            time.sleep(wait)
            resp = session.get(BASE_URL, params=params, timeout=10, headers=HEADERS)
        resp.raise_for_status()
        docs = resp.json().get("response", {}).get("docs", [])
        if docs:
            version = docs[0]["v"]
            CACHE[key] = version
            save_cache()
            return version
    except Exception as e:
        logger.warning("Solr API fetch failed for %s:%s – %s", group, artifact, e)

    CACHE[key] = ""
    save_cache()
    return None

def resilient_latest_version(group: str, artifact: str) -> Optional[str]:
    try:
        ver = fetch_latest_version(group, artifact)
        if ver:
            return ver
    except Exception:
        pass

    try:
        path = f"{group.replace('.', '/')}/{artifact}/maven-metadata.xml"
        resp = requests.get(
            f"https://repo1.maven.org/maven2/{path}",
            timeout=5,
            headers={"User-Agent": "secure‑linter/1.1 (+github.com/...)"}
        )
        resp.raise_for_status()
        xml = etree.fromstring(resp.content)
        return xml.findtext("versioning/release") or xml.findtext("versioning/latest")
    except Exception:
        return None


def is_version_outdated(current: str, latest: str | None) -> bool:
    if not latest:
        return False
    try:
        if current.startswith("${") and current.endswith("}"):
            current = current.strip("${ }")

        return semantic_version.Version.coerce(current) < semantic_version.Version.coerce(latest)
    except ValueError as exc:
        logger.debug("is_version_outdated: could not parse %r or %r: %s", current, latest, exc)
        return False
