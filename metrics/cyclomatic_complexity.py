import csv
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FOLDER = os.path.join(BASE_DIR, "..", "FilesExamples")
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "processed_builds", "summary_metrics.csv")
TOOLS_DIR = os.path.join(BASE_DIR, "..", "tools")
CODENARC_CONFIG = os.path.join(BASE_DIR, "..", "config", "codenarc.groovy")
DETEKT_CONFIG = os.path.join(BASE_DIR, "..", "config", "detekt.yml")


def clean_xml_for_parsing(filepath):
    try:
        with open(filepath, "r", encoding="utf-8", errors="replace") as f:
            content = f.read()

        closing_tag = "</project>"
        idx = content.rfind(closing_tag)

        if idx != -1:
            content = content[: idx + len(closing_tag)]

        return content
    except Exception as e:
        print(f"Error cleaning XML file {filepath}: {e}")
        return None


def safe_parse_xml(filepath):
    try:
        cleaned_content = clean_xml_for_parsing(filepath)
        if cleaned_content is None:
            return None

        root = ET.fromstring(cleaned_content)
        return ET.ElementTree(root)

    except ET.ParseError as e:
        print(f"XML Parse Error in {filepath}: {e}")
        return None
    except Exception as e:
        print(f"Unexpected XML Error in {filepath}: {e}")
        return None


def local_name(tag):
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def format_cc_value(value):
    if value is None:
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value)


def extract_complexity_value(message):
    if not message:
        return None

    patterns = [
        r"cyclomatic complexity\s+of\s+(\d+)",
        r"cyclomatic complexity.*?\[(\d+)\]",
        r"complexity\s+of\s+(\d+)",
        r"complexity.*?\[(\d+)\]",
        r"complexity\s*[:=]\s*(\d+)",
        r"mcc\s*[:=]\s*(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, message, flags=re.IGNORECASE)
        if match:
            return int(match.group(1))

    return None


def parse_embedded_json(output):
    for line in output.splitlines():
        candidate = line.strip()
        if not (candidate.startswith("{") and candidate.endswith("}")):
            continue

        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue

    decoder = json.JSONDecoder()

    for index, char in enumerate(output):
        if char != "{":
            continue

        try:
            payload, _ = decoder.raw_decode(output[index:])
            return payload
        except json.JSONDecodeError:
            continue

    return None


def codenarc_file_matches(filepath, package_path, file_info):
    target_path = os.path.abspath(filepath)

    file_path = file_info.get("path")
    if file_path and os.path.abspath(file_path) == target_path:
        return True

    file_name = file_info.get("name")
    if file_name and file_name == os.path.basename(filepath):
        if not package_path:
            return True

        combined_path = os.path.abspath(os.path.join(package_path, file_name))
        if combined_path == target_path:
            return True

    return False


def env_command(env_var):
    value = os.environ.get(env_var)
    if value:
        return shlex.split(value)
    return None


def binary_command(env_var, local_candidates):
    binary = os.environ.get(env_var)
    if binary:
        return [binary]

    for candidate in local_candidates:
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return [candidate]

    return None


def jar_command(env_var, entrypoint=None):
    jar_path = os.environ.get(env_var)
    java_bin = shutil.which("java")

    if not jar_path or not java_bin:
        return None

    if entrypoint:
        return [java_bin, "-cp", jar_path, entrypoint]

    return [java_bin, "-jar", jar_path]


def resolve_codenarc_command():
    return (
        env_command("CODENARC_CMD")
        or binary_command(
            "CODENARC_BINARY",
            [
                os.path.join(TOOLS_DIR, "codenarc", "codenarc"),
                os.path.join(TOOLS_DIR, "codenarc", "CodeNarc"),
                os.path.join(TOOLS_DIR, "codenarc", "bin", "CodeNarc"),
            ],
        )
        or jar_command("CODENARC_JAR", "org.codenarc.CodeNarc")
        or ([shutil.which("codenarc")] if shutil.which("codenarc") else None)
    )


def resolve_detekt_command():
    return (
        env_command("DETEKT_CMD")
        or binary_command(
            "DETEKT_BINARY",
            [
                os.path.join(TOOLS_DIR, "detekt", "detekt"),
                os.path.join(TOOLS_DIR, "detekt", "detekt-cli"),
                os.path.join(TOOLS_DIR, "detekt", "bin", "detekt"),
            ],
        )
        or jar_command("DETEKT_JAR")
        or ([shutil.which("detekt")] if shutil.which("detekt") else None)
    )


def calculate_ant_build_logic_complexity(filepath):
    tree = safe_parse_xml(filepath)
    if tree is None:
        return 0

    root = tree.getroot()
    complexity = 1
    ant_condition_tags = {
        "condition",
        "available",
        "uptodate",
        "isset",
        "equals",
        "contains",
        "matches",
        "and",
        "or",
        "not",
    }

    for elem in root.iter():
        tag = local_name(elem.tag)

        if tag in ant_condition_tags:
            complexity += 1

        if "if" in elem.attrib:
            complexity += 1
        if "unless" in elem.attrib:
            complexity += 1

        if tag == "target":
            depends = elem.attrib.get("depends", "")
            dependencies = [dep.strip() for dep in depends.split(",") if dep.strip()]
            complexity += max(0, len(dependencies) - 1)

    return complexity


def calculate_maven_build_logic_complexity(filepath):
    tree = safe_parse_xml(filepath)
    if tree is None:
        return 0

    root = tree.getroot()
    cc = 1

    for elem in root.iter():
        tag = local_name(elem.tag)

        if tag == "profile":
            cc += 1
        elif tag == "activation":
            cc += 1
        elif tag == "execution":
            cc += 1

    return cc


def calculate_gradle_cc(filepath):
    codenarc_cmd = resolve_codenarc_command()
    if not codenarc_cmd:
        print(
            "CodeNarc not found. Set CODENARC_CMD, CODENARC_BINARY, or CODENARC_JAR "
            "to analyze .gradle files."
        )
        return None

    if not os.path.exists(CODENARC_CONFIG):
        print(f"CodeNarc config not found: {CODENARC_CONFIG}")
        return None

    result = subprocess.run(
        [
            *codenarc_cmd,
            f"-sourcefiles={filepath}",
            f"-rulesetfiles=file:{CODENARC_CONFIG}",
            "-report=json:stdout",
            "-maxPriority1Violations=999999",
            "-maxPriority2Violations=999999",
            "-maxPriority3Violations=999999",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode not in (0, 1):
        print("CodeNarc Error:")
        print(result.stderr.strip() or result.stdout.strip())
        return None

    payload = parse_embedded_json(result.stdout)
    if payload is None:
        print("CodeNarc returned invalid JSON output.")
        print(result.stdout.strip())
        return None

    if isinstance(payload, list):
        payload = payload[0] if payload else {}
    if not isinstance(payload, dict):
        print("CodeNarc returned an unexpected JSON structure.")
        return None

    total_complexity = 0

    for package in payload.get("packages", []):
        package_path = package.get("path", "")
        for file_info in package.get("files", []):
            if not codenarc_file_matches(filepath, package_path, file_info):
                continue

            for violation in file_info.get("violations", []):
                if violation.get("ruleName") != "CyclomaticComplexity":
                    continue

                complexity = extract_complexity_value(violation.get("message", ""))
                if complexity is not None:
                    total_complexity += complexity

    return total_complexity


def detect_detekt_major_version(detekt_cmd):
    try:
        result = subprocess.run(
            [*detekt_cmd, "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError:
        return 1

    version_text = " ".join(
        part for part in [result.stdout.strip(), result.stderr.strip()] if part
    )
    match = re.search(r"(\d+)\.(\d+)\.(\d+)", version_text)
    if not match:
        return 1

    return int(match.group(1))


def calculate_gradle_kts_cc(filepath):
    detekt_cmd = resolve_detekt_command()
    if not detekt_cmd:
        print(
            "detekt not found. Set DETEKT_CMD, DETEKT_BINARY, or DETEKT_JAR "
            "to analyze .gradle.kts files."
        )
        return None

    if not os.path.exists(DETEKT_CONFIG):
        print(f"detekt config not found: {DETEKT_CONFIG}")
        return None

    threshold_key = (
        "allowedComplexity"
        if detect_detekt_major_version(detekt_cmd) >= 2
        else "threshold"
    )

    config_override = f"""
complexity:
  CyclomaticComplexMethod:
    {threshold_key}: 0
""".strip()

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".yml",
        delete=False,
    ) as config_file, tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".xml",
        delete=False,
    ) as report_file:
        config_file.write(config_override)
        config_path = config_file.name
        report_path = report_file.name

    try:
        result = subprocess.run(
            [
                *detekt_cmd,
                "--input",
                filepath,
                "--config",
                f"{DETEKT_CONFIG},{config_path}",
                "--report",
                f"xml:{report_path}",
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode not in (0, 2):
            print("detekt Error:")
            print(result.stderr.strip() or result.stdout.strip())
            return None

        try:
            tree = ET.parse(report_path)
        except ET.ParseError:
            print("detekt returned an invalid XML report.")
            print(result.stderr.strip() or result.stdout.strip())
            return None

        total_complexity = 0

        for file_elem in tree.getroot().findall("file"):
            if os.path.abspath(file_elem.attrib.get("name", "")) != os.path.abspath(filepath):
                continue

            for error in file_elem.findall("error"):
                source = error.attrib.get("source", "")
                message = error.attrib.get("message", "")
                if "CyclomaticComplexMethod" not in source and "CyclomaticComplexMethod" not in message:
                    continue

                complexity = extract_complexity_value(message)
                if complexity is not None:
                    total_complexity += complexity

        return total_complexity
    finally:
        for temp_path in (config_path, report_path):
            if os.path.exists(temp_path):
                os.unlink(temp_path)


def complexity_model_for_build_type(build_type):
    if build_type == "gradle":
        return "Cyclomatic_Complexity_CodeNarc"
    if build_type == "gradle_kts":
        return "Cyclomatic_Complexity_detekt"
    if build_type == "ant":
        return "Build_Logic_Complexity_Ant"
    if build_type == "maven":
        return "Build_Logic_Complexity_Maven"
    return ""


def detect_build_type(filepath):
    filename = os.path.basename(filepath).lower()

    if filename.endswith(".gradle.kts"):
        return "gradle_kts"
    if filename.endswith(".gradle"):
        return "gradle"
    if filename.endswith(".groovy"):
        return "groovy"
    if filename == "pom.xml":
        return "maven"
    if filename == "build.xml":
        return "ant"
    return None


def integrate_cc():
    if not os.path.exists(SUMMARY_FILE):
        print("ERROR: summary_metrics.csv not found. Run BLOC analyzer first.")
        return

    with open(SUMMARY_FILE, "r", encoding="utf-8") as file:
        reader = list(csv.reader(file))

    header = reader[0]
    rows = reader[1:]

    if "Cyclomatic_Complexity" not in header:
        header.append("Cyclomatic_Complexity")
    if "Complexity_Model" not in header:
        header.append("Complexity_Model")

    cc_index = header.index("Cyclomatic_Complexity")
    model_index = header.index("Complexity_Model")

    updated_rows = []

    for row in rows:
        filename = row[0]
        filepath = os.path.join(INPUT_FOLDER, filename)

        if len(row) < len(header):
            row.extend([""] * (len(header) - len(row)))

        if not os.path.exists(filepath):
            print(f"File not found: {filename}")
            updated_rows.append(row)
            continue

        build_type = detect_build_type(filepath)

        if build_type == "ant":
            cc = calculate_ant_build_logic_complexity(filepath)
        elif build_type == "maven":
            cc = calculate_maven_build_logic_complexity(filepath)
        elif build_type == "gradle":
            cc = calculate_gradle_cc(filepath)
        elif build_type == "gradle_kts":
            cc = calculate_gradle_kts_cc(filepath)
        elif build_type == "groovy":
            print(f"Unsupported Groovy file skipped: {filename}")
            updated_rows.append(row)
            continue
        else:
            print(f"Unsupported file skipped: {filename}")
            updated_rows.append(row)
            continue

        row[cc_index] = format_cc_value(cc)
        row[model_index] = complexity_model_for_build_type(build_type)
        updated_rows.append(row)

        label = "CC"
        if build_type in ("ant", "maven"):
            label = "Build Logic Complexity"

        print(
            f"{filename} | {build_type.upper()} {label} = "
            f"{format_cc_value(cc) or 'N/A'}"
        )

    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(updated_rows)

    print("\nComplexity metrics successfully integrated into summary_metrics.csv")


if __name__ == "__main__":
    integrate_cc()
