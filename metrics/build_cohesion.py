import os
import re
import csv
import xml.etree.ElementTree as ET
from itertools import combinations

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(BASE_DIR, ".."))
FILES_DIR = os.path.join(PROJECT_ROOT, "FilesExamples")
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "processed_builds")
OUTPUT_CSV = os.path.join(OUTPUT_DIR, "build_cohesion.csv")


def safe_write_csv(path, rows, fieldnames):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


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


# Gradle/Groovy cohesion

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
    for start_pos, _, task_name in matches:
        open_brace = text.find("{", start_pos)
        if open_brace == -1:
            continue

        brace_count = 1
        i = open_brace + 1

        while i < len(text) and brace_count > 0:
            if text[i] == "{":
                brace_count += 1
            elif text[i] == "}":
                brace_count -= 1
            i += 1

        block = text[start_pos:i]
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


def analyze_gradle_file(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        text = strip_gradle_comments(f.read())

    task_blocks = parse_gradle_task_blocks(text)
    feature_sets = []

    for _, block in task_blocks:
        features = gradle_feature_set(block)
        if features:
            feature_sets.append(features)

    return {
        "Module": os.path.basename(file_path),
        "Build System": "Gradle",
        "Task Count": len(task_blocks),
        "Build Cohesion": average_pairwise_jaccard(feature_sets),
    }



# Maven cohesion

def maven_execution_feature_sets(file_path):
    feature_sets = []
    root = parse_xml_root(file_path)
    if root is None:
        return feature_sets

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

    return feature_sets


def analyze_maven_file(file_path):
    feature_sets = maven_execution_feature_sets(file_path)
    return {
        "Module": os.path.basename(file_path),
        "Build System": "Maven",
        "Task Count": len(feature_sets),
        "Build Cohesion": average_pairwise_jaccard(feature_sets),
    }


# Ant cohesion

def ant_target_feature_set(target_elem):
    features = set()

    if "depends" in target_elem.attrib:
        for dep in target_elem.attrib["depends"].split(","):
            dep = dep.strip()
            if dep:
                features.add(f"depends:{dep}")

    if "if" in target_elem.attrib:
        features.add(f"cond_if:{target_elem.attrib['if']}")
    if "unless" in target_elem.attrib:
        features.add(f"cond_unless:{target_elem.attrib['unless']}")

    for elem in target_elem.iter():
        tag = strip_xml_namespace(elem.tag)
        if tag != "target":
            features.add(f"task:{tag}")

        for attr_name, attr_value in elem.attrib.items():
            features.add(f"attr:{tag}.{attr_name}")

    return features


def analyze_ant_file(file_path):
    feature_sets = []
    root = parse_xml_root(file_path)
    if root is None:
        return {
            "Module": os.path.basename(file_path),
            "Build System": "Ant",
            "Task Count": 0,
            "Build Cohesion": 0.0,
        }

    for elem in root:
        if strip_xml_namespace(elem.tag) == "target":
            features = ant_target_feature_set(elem)
            if features:
                feature_sets.append(features)

    return {
        "Module": os.path.basename(file_path),
        "Build System": "Ant",
        "Task Count": len(feature_sets),
        "Build Cohesion": average_pairwise_jaccard(feature_sets),
    }


def analyze_file(file_path):
    name = os.path.basename(file_path).lower()

    if name.endswith(".gradle") or name.endswith(".gradle.kts") or name.endswith(".groovy"):
        return analyze_gradle_file(file_path)

    if name.endswith("pom.xml"):
        return analyze_maven_file(file_path)

    if name.endswith("build.xml"):
        return analyze_ant_file(file_path)

    return None


def compute_build_cohesion_value(file_path: str) -> float:
    result = analyze_file(file_path)
    if not result:
        return 0.0
    return float(result.get("Build Cohesion", 0.0))