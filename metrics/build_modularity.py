import os
import re
import csv
import xml.etree.ElementTree as ET
from itertools import combinations

# ==================================================
# PATHS
# ==================================================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
FILES_DIR = os.path.join(PROJECT_ROOT, "FilesExamples")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "processed_builds")
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "build_modularity.csv")


# ==================================================
# HELPERS
# ==================================================
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


def rel_path_from_examples(file_path):
    return os.path.relpath(file_path, FILES_DIR).replace("\\", "/")


def is_inside_gradle_multi(file_path):
    rel_path = rel_path_from_examples(file_path)
    return rel_path.startswith("gradle_multi/")


def get_module_label(file_path):
    """
    For multi-module Gradle:
      FilesExamples/gradle_multi/app/build.gradle -> app
      FilesExamples/gradle_multi/lib/build.gradle -> lib
      FilesExamples/gradle_multi/core/build.gradle -> core

    For regular files:
      FilesExamples/pom.xml -> pom.xml
      FilesExamples/build.xml -> build.xml
      FilesExamples/build.gradle -> build.gradle
    """
    rel_path = rel_path_from_examples(file_path)
    filename = os.path.basename(file_path)

    if is_inside_gradle_multi(file_path) and (
        filename.endswith(".gradle") or filename.endswith(".gradle.kts")
    ):
        parts = rel_path.split("/")
        if len(parts) >= 3:
            return parts[1]

    return rel_path


# ==================================================
# COHESION - GRADLE
# ==================================================
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


# ==================================================
# COHESION - MAVEN
# ==================================================
def cohesion_maven(file_path):
    feature_sets = []

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

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

    except Exception:
        pass

    return average_pairwise_jaccard(feature_sets), len(feature_sets)


def extract_maven_artifact_id(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        for child in root:
            if strip_xml_namespace(child.tag) == "artifactId" and child.text:
                return child.text.strip()
    except Exception:
        pass

    return None


def extract_maven_edges(file_path, artifact_to_module):
    edges = set()

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

        for dep in root.iter():
            if strip_xml_namespace(dep.tag) != "dependency":
                continue

            artifact_id = None
            for child in dep:
                if strip_xml_namespace(child.tag) == "artifactId" and child.text:
                    artifact_id = child.text.strip()

            if artifact_id and artifact_id in artifact_to_module:
                edges.add(artifact_to_module[artifact_id])

    except Exception:
        pass

    return edges


# ==================================================
# COHESION - ANT
# ==================================================
def cohesion_ant(file_path):
    feature_sets = []

    try:
        tree = ET.parse(file_path)
        root = tree.getroot()

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

    except Exception:
        pass

    return average_pairwise_jaccard(feature_sets), len(feature_sets)


def extract_ant_edges(file_path):
    return set()


# ==================================================
# DISPATCH
# ==================================================
def compute_build_cohesion(file_path):
    name = os.path.basename(file_path)

    if name.endswith(".gradle") or name.endswith(".gradle.kts"):
        return cohesion_gradle(file_path)

    if name == "pom.xml":
        return cohesion_maven(file_path)

    if name == "build.xml":
        return cohesion_ant(file_path)

    return 0.0, 0


def extract_gradle_edges(file_path, known_modules):
    """
    Matches patterns like:
      implementation project(':core')
      implementation project(":lib")
      dependsOn(":core:someTask")
    """
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


# ==================================================
# COUPLING + MODULARITY
# ==================================================
def compute_cp_external(edge_count, module_count):
    if module_count <= 1:
        return 0.0
    return round(edge_count / (module_count * (module_count - 1)), 4)


def compute_modularity_score(avg_cohesion, cp_external):
    """
    Heuristic modularity score.
    This is not a direct formula from the paper.
    """
    score = 0.65 * avg_cohesion + 0.35 * (1 - cp_external)
    return round(max(0.0, min(1.0, score)), 4)


# ==================================================
# MAIN
# ==================================================
def main():
    files = []

    for dirpath, _, filenames in os.walk(FILES_DIR):
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)

            is_gradle_build = (
                (filename.endswith(".gradle") or filename.endswith(".gradle.kts"))
                and filename not in ("settings.gradle", "settings.gradle.kts")
            )

            if is_gradle_build or filename == "pom.xml" or filename == "build.xml":
                files.append(full_path)

    if not files:
        print("No supported build files found.")
        return

    module_names = {}
    for path in files:
        module_names[path] = get_module_label(path)

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

        if filename.endswith(".gradle") or filename.endswith(".gradle.kts"):
            outgoing = extract_gradle_edges(path, all_module_labels)
            build_system = "Gradle"
        elif filename == "pom.xml":
            outgoing = extract_maven_edges(path, artifact_to_module)
            build_system = "Maven"
        else:
            outgoing = extract_ant_edges(path)
            build_system = "Ant"

        outgoing.discard(module_label)
        adjacency[module_label] = outgoing

        file_rows.append({
            "Module": module_label,
            "File": rel_path_from_examples(path),
            "Build System": build_system,
            "Task Count": task_count,
            "Build Cohesion": cohesion,
            "Outgoing Edges": ", ".join(sorted(outgoing)),
            "Outgoing Edge Count": len(outgoing),
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

    final_rows = []
    for row in file_rows:
        enriched = dict(row)
        enriched["Average Cohesion"] = avg_cohesion
        enriched["Cross-Module Edge Count"] = e_cross
        enriched["CP_External"] = cp_external
        enriched["Build Modularity (Heuristic)"] = modularity_score
        final_rows.append(enriched)

    safe_write_csv(
        OUTPUT_CSV,
        final_rows,
        [
            "Module",
            "File",
            "Build System",
            "Task Count",
            "Build Cohesion",
            "Outgoing Edges",
            "Outgoing Edge Count",
            "Average Cohesion",
            "Cross-Module Edge Count",
            "CP_External",
            "Build Modularity (Heuristic)",
        ]
    )

    print("=" * 80)
    print("BUILD MODULARITY RESULTS")
    print("=" * 80)

    for row in final_rows:
        print(
            f"{row['Module']} | "
            f"{row['Build System']} | "
            f"Tasks = {row['Task Count']} | "
            f"Cohesion = {row['Build Cohesion']} | "
            f"Outgoing = {row['Outgoing Edge Count']}"
        )

    print("\nPROJECT-LEVEL")
    print(f"Modules                    : {module_count}")
    print(f"E_cross                    : {e_cross}")
    print(f"CP_External                : {cp_external}")
    print(f"Average Cohesion           : {avg_cohesion}")
    print(f"Build Modularity Heuristic : {modularity_score}")
    print(f"\nSaved modularity results to: {OUTPUT_CSV}")


if __name__ == "__main__":
    main()