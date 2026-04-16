import json
import os
import re
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter, defaultdict


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
GRADLE_COUPLING_AST_SCRIPT = os.path.join(BASE_DIR, "gradle_coupling_ast.groovy")

ABS_PATH_RE = re.compile(r"(?:^|[^$\w])(?P<path>/(?:[^/\s]+/)*[^/\s\"']+|[A-Za-z]:\\(?:[^\\\s]+\\)*[^\\\s\"']+)")
URL_RE = re.compile(r"https?://[^\s\"'<>]+", re.IGNORECASE)
ENV_RE = re.compile(r"\$\{env\.([A-Za-z0-9_.-]+)\}|\$([A-Z_][A-Z0-9_]*)")
PROPERTY_REF_RE = re.compile(r"\$\{([^}]+)\}")

DEPENDENCY_CONFIGS = {
    "api", "implementation", "compileOnly", "runtimeOnly", "compile",
    "testImplementation", "testCompile", "androidTestImplementation",
    "androidTestCompile", "annotationProcessor", "kapt",
}
TASK_DEP_METHODS = {"dependsOn", "mustRunAfter", "shouldRunAfter", "finalizedBy"}


def normalize_metric_by_bloc(value: float | int, bloc: int) -> float:
    if bloc <= 0:
        return 0.0
    return round(float(value) / bloc, 4)


def empty_coupling_result() -> dict:
    return {
        "cp_internal": 0,
        "cp_external": 0,
        "cp_total": 0,
        "ncp_internal": 0.0,
        "ncp_external": 0.0,
        "coupling_ratio": 0.0,
        "components": {
            "t_int": 0,
            "v_shared": 0,
            "c_internal": 0,
            "m": 0,
            "d": 0,
            "p": 0,
            "r": 0,
            "e": 0,
            "u": 0,
        },
    }


def _finalize_coupling(components: dict[str, int], bloc: int) -> dict:
    cp_internal = int(components["t_int"] + components["v_shared"] + components["c_internal"])
    cp_external = int(components["m"] + components["d"] + components["p"] + components["r"] + components["e"] + components["u"])
    cp_total = cp_internal + cp_external

    result = empty_coupling_result()
    result["components"] = components
    result["cp_internal"] = cp_internal
    result["cp_external"] = cp_external
    result["cp_total"] = cp_total
    result["ncp_internal"] = normalize_metric_by_bloc(cp_internal, bloc)
    result["ncp_external"] = normalize_metric_by_bloc(cp_external, bloc)
    result["coupling_ratio"] = round(cp_external / max(cp_total, 1), 4)
    return result


def _clean_xml_for_parsing(file_path: str) -> str | None:
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
            content = handle.read()
        idx = content.rfind("</project>")
        if idx != -1:
            content = content[: idx + len("</project>")]
        return content
    except Exception:
        return None


def _parse_xml_root(file_path: str):
    cleaned = _clean_xml_for_parsing(file_path)
    if not cleaned:
        return None
    try:
        return ET.fromstring(cleaned)
    except Exception:
        return None


def _local_name(tag: str) -> str:
    return tag.split("}", 1)[-1] if "}" in tag else tag


def _text_or_empty(value: str | None) -> str:
    return (value or "").strip()


def _looks_like_absolute_path(value: str) -> bool:
    return bool(re.fullmatch(r"/[^\"']+|[A-Za-z]:[\\/][^\"']+", value or ""))


def _strip_gradle_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*", "", text)
    return text


def _parse_gradle_task_blocks(text: str) -> list[tuple[str, str]]:
    patterns = [
        r"\btask\s+([A-Za-z_]\w*)\s*\{",
        r"tasks\.register\s*\(\s*[\"']([^\"']+)[\"']\s*\)\s*\{",
        r"tasks\.named\s*\(\s*[\"']([^\"']+)[\"']\s*\)\s*\{",
        r"tasks\.create\s*\(\s*[\"']([^\"']+)[\"']\s*\)\s*\{",
    ]
    matches: list[tuple[int, str]] = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            matches.append((match.start(), match.group(1)))
    matches.sort(key=lambda item: item[0])

    blocks: list[tuple[str, str]] = []
    for start_pos, task_name in matches:
        open_brace = text.find("{", start_pos)
        if open_brace == -1:
            continue
        depth = 1
        i = open_brace + 1
        while i < len(text) and depth > 0:
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
            i += 1
        blocks.append((task_name, text[start_pos:i]))
    return blocks


def _run_gradle_coupling_ast(file_path: str) -> dict | None:
    if not os.path.exists(GRADLE_COUPLING_AST_SCRIPT):
        return None

    try:
        result = subprocess.run(
            ["groovy", GRADLE_COUPLING_AST_SCRIPT, file_path],
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return None

    if result.returncode != 0:
        return None

    payload = (result.stdout or "").strip()
    if not payload:
        return None

    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return None

    required = {"t_int", "v_shared", "c_internal", "m", "d", "p", "r", "e", "u"}
    if not required.issubset(data.keys()):
        return None
    return {key: int(data[key] or 0) for key in required}


def _gradle_coupling_fallback(file_path: str) -> dict[str, int]:
    with open(file_path, "r", encoding="utf-8", errors="ignore") as handle:
        raw = _strip_gradle_comments(handle.read())

    task_blocks = _parse_gradle_task_blocks(raw)
    task_names = {name for name, _ in task_blocks}
    dependency_edges: set[tuple[str, str]] = set()
    property_usage: dict[str, set[str]] = defaultdict(set)
    config_usage: dict[str, set[str]] = defaultdict(set)

    for task_name, block in task_blocks:
        for rel_name in TASK_DEP_METHODS:
            for dep in re.findall(rf"\b{rel_name}\s*\(?\s*[\"']([^\"']+)[\"']", block):
                if dep in task_names and dep != task_name:
                    dependency_edges.add((task_name, dep))

        for prop in re.findall(r"findProperty\s*\(\s*[\"']([^\"']+)[\"']\s*\)", block):
            property_usage[f"property:{prop}"].add(task_name)
        for prop in re.findall(r"\bext\.(\w+)", block):
            property_usage[f"property:{prop}"].add(task_name)

        for token in re.findall(r"\b(sourceSets\.\w+|inputs\.\w+|outputs\.\w+|configurations\.\w+)", block):
            config_usage[f"config:{token}"].add(task_name)

    t_int = len(dependency_edges)
    v_shared = sum(1 for tasks in property_usage.values() if len(tasks) >= 2)
    c_internal = sum(1 for tasks in config_usage.values() if len(tasks) >= 2)

    modules = {
        dep.strip(":").split(":")[-1]
        for dep in re.findall(r"project\s*\(\s*[\"']([^\"']+)[\"']\s*\)", raw)
    }

    dep_count = 0
    simple_dep = re.compile(
        r"^\s*(api|implementation|compileOnly|runtimeOnly|compile|testImplementation|testCompile|androidTestImplementation|androidTestCompile|annotationProcessor|kapt)\s*(?:\(\s*)?[\"']([^:'\"]+):([^:'\"]+):([^\"']+)[\"']",
        re.MULTILINE,
    )
    dep_count += len(simple_dep.findall(raw))
    map_dep = re.compile(
        r"^\s*(api|implementation|compileOnly|runtimeOnly|compile|testImplementation|testCompile|androidTestImplementation|androidTestCompile|annotationProcessor|kapt)\s*\(?\s*group\s*[:=]\s*[\"'](.+?)[\"']\s*,\s*name\s*[:=]\s*[\"'](.+?)[\"']\s*,\s*version\s*[:=]\s*[\"'](.+?)[\"']",
        re.MULTILINE,
    )
    dep_count += len(map_dep.findall(raw))

    plugins = set(re.findall(r"\bid\s*[('\"]+\s*([A-Za-z0-9_.-]+)[\"']", raw))
    plugins.update(re.findall(r"apply\s+plugin:\s*[\"']([^\"']+)[\"']", raw))

    repositories = set()
    for repo in ("mavenCentral", "google", "gradlePluginPortal", "mavenLocal", "jcenter", "ivy", "maven"):
        if re.search(rf"\b{repo}\b", raw):
            repositories.add(repo)

    external_commands = len(re.findall(r"\b(exec|javaexec|commandLine)\b", raw))
    external_commands += len(re.findall(r"apply\s+from:\s*[\"']([^\"']+)[\"']", raw))

    resources = set()
    for url in URL_RE.findall(raw):
        resources.add(url)
    for match in ABS_PATH_RE.finditer(raw):
        resources.add(match.group("path"))
    for env_match in ENV_RE.findall(raw):
        name = env_match[0] or env_match[1]
        if name:
            resources.add(f"env:{name}")
    for env_call in re.findall(r"System\.getenv\s*\(\s*[\"']([^\"']+)[\"']\s*\)", raw):
        resources.add(f"env:{env_call}")

    return {
        "t_int": t_int,
        "v_shared": v_shared,
        "c_internal": c_internal,
        "m": len(modules),
        "d": dep_count,
        "p": len(plugins),
        "r": len(repositories),
        "e": external_commands,
        "u": len(resources),
    }


def _artifact_ids_in_project(project_dir: str | None) -> set[str]:
    if not project_dir or not os.path.isdir(project_dir):
        return set()

    artifact_ids: set[str] = set()
    for dirpath, _, filenames in os.walk(project_dir):
        if "pom.xml" not in filenames:
            continue
        pom_path = os.path.join(dirpath, "pom.xml")
        root = _parse_xml_root(pom_path)
        if root is None:
            continue
        for child in root:
            if _local_name(child.tag) == "artifactId" and (child.text or "").strip():
                artifact_ids.add(child.text.strip())
                break
    return artifact_ids


def _maven_dependency_coordinates(dep: ET.Element) -> tuple[str, str]:
    group_id = ""
    artifact_id = ""
    for child in dep:
        tag = _local_name(child.tag)
        text = _text_or_empty(child.text)
        if tag == "groupId":
            group_id = text
        elif tag == "artifactId":
            artifact_id = text
    return group_id, artifact_id


def _maven_repository_urls(root: ET.Element) -> set[str]:
    urls: set[str] = set()
    for elem in root.iter():
        if _local_name(elem.tag) not in {"repository", "pluginRepository"}:
            continue
        for child in elem.iter():
            if _local_name(child.tag) == "url":
                url = _text_or_empty(child.text)
                if url:
                    urls.add(url)
    return urls


def _iter_xml_text_and_attribute_values(elem: ET.Element):
    text = _text_or_empty(elem.text)
    if text:
        yield text
    for value in elem.attrib.values():
        stripped = _text_or_empty(value)
        if stripped:
            yield stripped


def _analyze_maven(file_path: str, project_dir: str | None) -> dict[str, int]:
    root = _parse_xml_root(file_path)
    if root is None:
        return empty_coupling_result()["components"]

    local_artifacts = _artifact_ids_in_project(project_dir)

    current_artifact = ""
    for child in root:
        if _local_name(child.tag) == "artifactId" and (child.text or "").strip():
            current_artifact = child.text.strip()
            break

    executions: list[dict] = []
    property_usage = Counter()
    config_usage = Counter()

    for plugin in root.iter():
        if _local_name(plugin.tag) != "plugin":
            continue

        plugin_artifact = ""
        for child in plugin:
            if _local_name(child.tag) == "artifactId" and (child.text or "").strip():
                plugin_artifact = child.text.strip()
                break

        for executions_elem in plugin.findall(".//{*}executions"):
            for execution in executions_elem:
                if _local_name(execution.tag) != "execution":
                    continue

                phase = ""
                props: set[str] = set()
                configs: set[str] = set()

                for ex_child in execution.iter():
                    tag = _local_name(ex_child.tag)
                    text = _text_or_empty(ex_child.text)
                    if tag == "phase" and text:
                        phase = text
                    for prop in PROPERTY_REF_RE.findall(text):
                        props.add(prop)

                    if tag == "configuration":
                        for cfg_child in ex_child.iter():
                            cfg_tag = _local_name(cfg_child.tag)
                            if cfg_tag != "configuration":
                                configs.add(cfg_tag)

                for prop in props:
                    property_usage[prop] += 1
                for cfg in configs:
                    config_usage[cfg] += 1

                executions.append({
                    "plugin": plugin_artifact,
                    "phase": phase,
                })

    linked_pairs: set[tuple[int, int]] = set()
    for i, left in enumerate(executions):
        for j in range(i + 1, len(executions)):
            right = executions[j]
            same_plugin = left["plugin"] and left["plugin"] == right["plugin"]
            same_phase = left["phase"] and left["phase"] == right["phase"]
            if same_plugin or same_phase:
                linked_pairs.add((i, j))

    local_module_names: set[str] = set()
    for modules_elem in root.iter():
        if _local_name(modules_elem.tag) != "modules":
            continue
        for child in modules_elem:
            if _local_name(child.tag) == "module":
                module_name = _text_or_empty(child.text)
                if module_name:
                    local_module_names.add(module_name.split("/")[-1])

    modules = len(local_module_names)
    dependencies = 0
    for dep in root.iter():
        if _local_name(dep.tag) != "dependency":
            continue
        _, artifact_id = _maven_dependency_coordinates(dep)
        if artifact_id and artifact_id in local_artifacts and artifact_id != current_artifact:
            modules += 1
        else:
            dependencies += 1

    plugins = sum(1 for elem in root.iter() if _local_name(elem.tag) == "plugin")
    repositories = sum(1 for elem in root.iter() if _local_name(elem.tag) in {"repository", "pluginRepository"})

    external_exec_plugins = 0
    for plugin in root.iter():
        if _local_name(plugin.tag) != "plugin":
            continue
        artifact_id = ""
        for child in plugin:
            if _local_name(child.tag) == "artifactId" and (child.text or "").strip():
                artifact_id = child.text.strip()
                break
        if artifact_id in {"exec-maven-plugin", "maven-antrun-plugin"}:
            external_exec_plugins += 1

    repository_urls = _maven_repository_urls(root)
    env_resources: set[str] = set()

    raw = open(file_path, "r", encoding="utf-8", errors="ignore").read()
    for prop in re.findall(r"\$\{(env\.[^}]+|user\.[^}]+)\}", raw):
        env_resources.add(prop)

    for elem in root.iter():
        tag = _local_name(elem.tag)
        for value in _iter_xml_text_and_attribute_values(elem):
            if tag == "systemPath":
                env_resources.add("systemPath")
            if _looks_like_absolute_path(value):
                env_resources.add(value)
            for url in URL_RE.findall(value):
                if url not in repository_urls:
                    env_resources.add(url)

    return {
        "t_int": len(linked_pairs),
        "v_shared": sum(1 for count in property_usage.values() if count >= 2),
        "c_internal": sum(1 for count in config_usage.values() if count >= 2),
        "m": modules,
        "d": dependencies,
        "p": plugins,
        "r": repositories,
        "e": external_exec_plugins,
        "u": len(env_resources),
    }


def _analyze_ant(file_path: str) -> dict[str, int]:
    root = _parse_xml_root(file_path)
    if root is None:
        return empty_coupling_result()["components"]

    targets: dict[str, ET.Element] = {}
    for elem in root:
        if _local_name(elem.tag) == "target":
            name = (elem.attrib.get("name") or "").strip()
            if name:
                targets[name] = elem

    t_int = 0
    property_usage: dict[str, set[str]] = defaultdict(set)
    config_usage: dict[str, set[str]] = defaultdict(set)

    for target_name, elem in targets.items():
        depends = [dep.strip() for dep in elem.attrib.get("depends", "").split(",") if dep.strip()]
        for dep in depends:
            if dep in targets and dep != target_name:
                t_int += 1

        text_blob = ET.tostring(elem, encoding="unicode")
        for prop in PROPERTY_REF_RE.findall(text_blob):
            property_usage[prop].add(target_name)

        for child in elem.iter():
            child_tag = _local_name(child.tag)
            if child_tag == "antcall":
                called_target = _text_or_empty(child.attrib.get("target"))
                if called_target and called_target in targets and called_target != target_name:
                    t_int += 1
            if "refid" in child.attrib and child.attrib["refid"].strip():
                config_usage[f"refid:{child.attrib['refid'].strip()}"].add(target_name)
            if "id" in child.attrib and child.attrib["id"].strip():
                config_usage[f"id:{child.attrib['id'].strip()}"].add(target_name)
            if child_tag in {"path", "fileset", "patternset"}:
                config_usage[f"tag:{child_tag}"].add(target_name)

    raw = open(file_path, "r", encoding="utf-8", errors="ignore").read()
    dependencies = len(set(re.findall(r"[A-Za-z0-9_.-]+-[A-Za-z0-9_.+-]+\.jar", raw)))

    remote_resources = set()
    exec_count = 0
    plugins = 0
    modules = 0
    env_resources = set()

    for prop in re.findall(r"\$\{(env\.[^}]+)\}", raw):
        env_resources.add(prop)

    for elem in root.iter():
        tag = _local_name(elem.tag)
        if tag in {"import", "include", "subant"}:
            modules += 1
        elif tag == "ant":
            antfile = _text_or_empty(elem.attrib.get("antfile"))
            ant_dir = _text_or_empty(elem.attrib.get("dir"))
            if antfile or ant_dir:
                modules += 1
        if tag in {"taskdef", "typedef"}:
            plugins += 1
        if tag in {"exec", "java"}:
            exec_count += 1
        for attr, value in elem.attrib.items():
            stripped = _text_or_empty(value)
            if not stripped:
                continue
            if attr == "environment":
                env_resources.add(f"env:{stripped}")
            if URL_RE.fullmatch(stripped):
                if tag == "get" or attr in {"src", "url"}:
                    remote_resources.add(stripped)
                else:
                    env_resources.add(stripped)
            if _looks_like_absolute_path(stripped):
                env_resources.add(stripped)

    return {
        "t_int": t_int,
        "v_shared": sum(1 for targets_set in property_usage.values() if len(targets_set) >= 2),
        "c_internal": sum(1 for targets_set in config_usage.values() if len(targets_set) >= 2),
        "m": modules,
        "d": dependencies,
        "p": plugins,
        "r": len(remote_resources),
        "e": exec_count,
        "u": len(env_resources),
    }


def compute_build_coupling(file_path: str, project_dir: str | None = None, bloc: int | None = None) -> dict:
    if not file_path or not os.path.exists(file_path):
        return empty_coupling_result()

    name = os.path.basename(file_path).lower()
    local_bloc = bloc if bloc is not None else 0

    if name.endswith(".gradle") or name.endswith(".groovy"):
        components = _run_gradle_coupling_ast(file_path) or _gradle_coupling_fallback(file_path)
        return _finalize_coupling(components, local_bloc)

    if name.endswith(".gradle.kts"):
        components = _gradle_coupling_fallback(file_path)
        return _finalize_coupling(components, local_bloc)

    if name == "pom.xml":
        components = _analyze_maven(file_path, project_dir)
        return _finalize_coupling(components, local_bloc)

    if name == "build.xml":
        components = _analyze_ant(file_path)
        return _finalize_coupling(components, local_bloc)

    return empty_coupling_result()
