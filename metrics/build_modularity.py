import os
import re
import csv
import xml.etree.ElementTree as ET
from itertools import combinations


# PATHS

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
FILES_DIR = os.path.join(PROJECT_ROOT, "FilesExamples")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "processed_builds")
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "build_modularity.csv")



# HELPERS

def safe_write_csv(path, rows, fieldnames):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def strip_xml_namespace(tag):
    return tag.split("}", 1)[-1] if "}" in tag else tag


def strip_gradle_comments(text):
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*", "", text)
    return text


def clean_xml_for_parsing(file_path):
    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        closing_tag = "</project>"
        idx = content.rfind(closing_tag)
        if idx != -1:
            content = content[: idx + len(closing_tag)]

        return content
    except Exception:
        return None


def parse_xml_root(file_path):
    try:
        cleaned = clean_xml_for_parsing(file_path)
        if not cleaned:
            return None
        return ET.fromstring(cleaned)
    except Exception:
        return None


def jaccard_similarity(a, b):
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


def average_pairwise_jaccard(feature_sets):
    if not feature_sets:
        return 0.0
    if len(feature_sets) == 1:
        return 1.0

    scores = []
    for a, b in combinations(feature_sets, 2):
        scores.append(jaccard_similarity(a, b))

    return round(sum(scores) / len(scores), 4) if scores else 0.0


def rel_path_from_examples(file_path, files_dir):
    return os.path.relpath(file_path, files_dir).replace("\\", "/")


def is_inside_gradle_multi(file_path, files_dir):
    rel_path = rel_path_from_examples(file_path, files_dir)
    return rel_path.startswith("gradle_multi/")


def get_module_label(file_path, files_dir):
    rel_path = rel_path_from_examples(file_path, files_dir)
    filename = os.path.basename(file_path)

    if is_inside_gradle_multi(file_path, files_dir) and (
        filename.endswith(".gradle") or filename.endswith(".gradle.kts")
    ):
        parts = rel_path.split("/")
        if len(parts) >= 3:
            return parts[1]

    return rel_path



# COHESION - GRADLE

def parse_gradle_task_blocks(text):
    patterns = [
        r'\btask\s+([A-Za-z_]\w*)\s*\{',
        r'tasks\.register\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\{',
        r'tasks\.named\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\{',
        r'tasks\.create\s*\(\s*["\']([^"\']+)["\']\s*\)\s*\{',
    ]

    matches = []
    for pattern in patterns:
        for match in re.finditer(pattern, text):
            matches.append((match.start(), match.end(), match.group(1)))

    matches.sort(key=lambda x: x[0])

    task_blocks = []
    for _, block_start, task_name in matches:
        brace_count = 1
        i = block_start

        while i < len(text) and brace_count > 0:
            if text[i] == "{":
                brace_count += 1
            elif text[i] == "}":
                brace_count -= 1
            i += 1

        block = text[block_start:i]
        task_blocks.append((task_name, block))

    return task_blocks


def gradle_feature_set(task_block):
    features = set()

    for x in re.findall(r'id\s+["\']([^"\']+)["\']', task_block):
        features.add(f"plugin:{x}")

    for x in re.findall(r'apply\s+plugin:\s*["\']([^"\']+)["\']', task_block):
        features.add(f"plugin:{x}")

    for x in re.findall(
        r'\b(implementation|api|compileOnly|runtimeOnly|testImplementation|annotationProcessor)\b',
        task_block
    ):
        features.add(f"config:{x}")

    for x in re.findall(r'project\s*\(\s*["\']([^"\']+)["\']\s*\)', task_block):
        features.add(f"dep:{x}")

    for x in re.findall(r'\bsourceSets\.(\w+)', task_block):
        features.add(f"sourceSet:{x}")

    for x in re.findall(r'\b(inputs|outputs)\.(\w+)', task_block):
        features.add(f"io:{x[0]}.{x[1]}")

    for x in re.findall(r'findProperty\s*\(\s*["\']([^"\']+)["\']\s*\)', task_block):
        features.add(f"property:{x}")

    for x in re.findall(r'\bext\.(\w+)', task_block):
        features.add(f"property:{x}")

    for x in re.findall(r'apply\s+from:\s*["\']([^"\']+)["\']', task_block):
        features.add(f"script:{x}")

    for x in re.findall(r'\b(doLast|doFirst|dependsOn|mustRunAfter|finalizedBy|copy|delete|exec|javaexec)\b', task_block):
        features.add(f"keyword:{x}")

    return features


def cohesion_gradle(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        text = strip_gradle_comments(f.read())

    task_blocks = parse_gradle_task_blocks(text)
    feature_sets = []

    for _, block in task_blocks:
        features = gradle_feature_set(block)
        if features:
            feature_sets.append(features)

    return average_pairwise_jaccard(feature_sets), len(task_blocks)



# COHESION - MAVEN

def cohesion_maven(file_path):
    feature_sets = []
    root = parse_xml_root(file_path)
    if root is None:
        return 0.0, 0

    for plugin in root.iter():
        if strip_xml_namespace(plugin.tag) != "plugin":
            continue

        plugin_artifact = None

        for child in plugin:
            tag = strip_xml_namespace(child.tag)

            if tag == "artifactId" and child.text:
                plugin_artifact = child.text.strip()

            elif tag == "executions":
                for execution in child:
                    if strip_xml_namespace(execution.tag) != "execution":
                        continue

                    features = set()

                    if plugin_artifact:
                        features.add(f"plugin:{plugin_artifact}")

                    for ex_child in execution:
                        ex_tag = strip_xml_namespace(ex_child.tag)

                        if ex_tag == "goals":
                            for goal in ex_child:
                                if goal.text:
                                    features.add(f"goal:{goal.text.strip()}")

                        elif ex_tag == "configuration":
                            for conf in ex_child.iter():
                                conf_tag = strip_xml_namespace(conf.tag)
                                if conf_tag != "configuration":
                                    features.add(f"config:{conf_tag}")

                    if features:
                        feature_sets.append(features)

    return average_pairwise_jaccard(feature_sets), len(feature_sets)


def extract_maven_artifact_id(file_path):
    root = parse_xml_root(file_path)
    if root is None:
        return None

    for child in root:
        if strip_xml_namespace(child.tag) == "artifactId" and child.text:
            return child.text.strip()

    return None


def extract_maven_edges(file_path, artifact_to_module):
    edges = set()
    root = parse_xml_root(file_path)
    if root is None:
        return edges

    for dep in root.iter():
        if strip_xml_namespace(dep.tag) != "dependency":
            continue

        artifact_id = None
        for child in dep:
            if strip_xml_namespace(child.tag) == "artifactId" and child.text:
                artifact_id = child.text.strip()

        if artifact_id and artifact_id in artifact_to_module:
            edges.add(artifact_to_module[artifact_id])

    return edges



# COHESION - ANT

def cohesion_ant(file_path):
    feature_sets = []
    root = parse_xml_root(file_path)
    if root is None:
        return 0.0, 0

    for elem in root:
        if strip_xml_namespace(elem.tag) == "target":
            features = set()

            if "depends" in elem.attrib:
                for dep in elem.attrib["depends"].split(","):
                    dep = dep.strip()
                    if dep:
                        features.add(f"depends:{dep}")

            for child in elem.iter():
                tag = strip_xml_namespace(child.tag)
                if tag != "target":
                    features.add(f"task:{tag}")

            if features:
                feature_sets.append(features)

    return average_pairwise_jaccard(feature_sets), len(feature_sets)


def extract_ant_edges(file_path):
    return set()



# DISPATCH

def compute_build_cohesion(file_path):
    name = os.path.basename(file_path)

    if name.endswith(".gradle") or name.endswith(".gradle.kts") or name.endswith(".groovy"):
        return cohesion_gradle(file_path)

    if name == "pom.xml":
        return cohesion_maven(file_path)

    if name == "build.xml":
        return cohesion_ant(file_path)

    return 0.0, 0


def extract_gradle_edges(file_path, known_modules):
    edges = set()

    with open(file_path, "r", encoding="utf-8") as f:
        text = strip_gradle_comments(f.read())

    for dep in re.findall(r'project\s*\(\s*["\']([^"\']+)["\']\s*\)', text):
        dep_name = dep.strip(":").strip()
        if dep_name in known_modules:
            edges.add(dep_name)

    for dep in re.findall(r'["\']:(.+?):[^"\']+["\']', text):
        dep_name = dep.strip()
        if dep_name in known_modules:
            edges.add(dep_name)

    return edges



# COUPLING + MODULARITY

def compute_cp_external(edge_count, module_count):
    if module_count <= 1:
        return 0.0
    return round(edge_count / (module_count * (module_count - 1)), 4)


def compute_modularity_score(avg_cohesion, cp_external):
    score = 0.65 * avg_cohesion + 0.35 * (1 - cp_external)
    return round(max(0.0, min(1.0, score)), 4)


def compute_project_modularity(files_dir: str) -> float:
    files = []

    for dirpath, _, filenames in os.walk(files_dir):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)

            is_gradle_build = (
                (filename.endswith(".gradle") or filename.endswith(".gradle.kts") or filename.endswith(".groovy"))
                and filename not in ("settings.gradle", "settings.gradle.kts")
            )

            if is_gradle_build or filename == "pom.xml" or filename == "build.xml":
                files.append(full_path)

    if not files:
        return 0.0

    module_names = {}
    for path in files:
        module_names[path] = get_module_label(path, files_dir)

    all_module_labels = set(module_names.values())

    artifact_to_module = {}
    for path in files:
        if os.path.basename(path) == "pom.xml":
            artifact_id = extract_maven_artifact_id(path)
            if artifact_id:
                artifact_to_module[artifact_id] = module_names[path]

    file_rows = []
    adjacency = {}

    for path in files:
        filename = os.path.basename(path)
        module_label = module_names[path]

        cohesion, task_count = compute_build_cohesion(path)

        if filename.endswith(".gradle") or filename.endswith(".gradle.kts") or filename.endswith(".groovy"):
            outgoing = extract_gradle_edges(path, all_module_labels)
        elif filename == "pom.xml":
            outgoing = extract_maven_edges(path, artifact_to_module)
        else:
            outgoing = extract_ant_edges(path)

        outgoing.discard(module_label)
        adjacency[module_label] = outgoing

        file_rows.append({
            "Module": module_label,
            "Task Count": task_count,
            "Build Cohesion": cohesion,
        })

    unique_edges = set()
    for src, targets in adjacency.items():
        for dst in targets:
            if src != dst:
                unique_edges.add((src, dst))

    e_cross = len(unique_edges)
    module_count = len(file_rows)

    avg_cohesion = 0.0
    if module_count > 0:
        avg_cohesion = round(
            sum(row["Build Cohesion"] for row in file_rows) / module_count,
            4
        )

    cp_external = compute_cp_external(e_cross, module_count)
    modularity_score = compute_modularity_score(avg_cohesion, cp_external)
    return modularity_score


def main():
    modularity = compute_project_modularity(FILES_DIR)
    print(f"Build Modularity (Heuristic): {modularity}")


if __name__ == "__main__":
    main()