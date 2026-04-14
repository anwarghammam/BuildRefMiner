import csv
import json
import os
import re
import shlex
import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FOLDER = os.path.join(BASE_DIR, "..", "FilesExamples")
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "processed_builds", "summary_metrics.csv")
TOOLS_DIR = os.path.join(BASE_DIR, "..", "tools")
CODENARC_STYLE_CONFIG = os.path.join(BASE_DIR, "..", "config", "codenarc_style.groovy")
DETEKT_STYLE_CONFIG = os.path.join(BASE_DIR, "..", "config", "detekt_style.yml")


def local_name(tag):
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag


def format_score(value):
    if value is None:
        return ""
    rounded = round(value, 2)
    if rounded.is_integer():
        return str(int(rounded))
    return f"{rounded:.2f}"


def compute_style_score(bloc, weighted_violations):
    if bloc is None or bloc <= 0:
        return None

    score = 100 - ((weighted_violations / bloc) * 100)
    return max(0.0, score)


def parse_embedded_json(output):
    for line in output.splitlines():
        candidate = line.strip()
        if not (candidate.startswith("{") and candidate.endswith("}")):
            continue
        try:
            return json.loads(candidate)
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


def is_maven_name(text):
    return bool(re.fullmatch(r"[a-z]+([A-Z][a-z0-9]*)*(\.[a-z]+([A-Z][a-z0-9]*)*)*", text))


def count_xml_indentation_violations(lines):
    violations = 0
    base_indent = None

    for line in lines:
        if not line.strip():
            continue

        if "\t" in line:
            violations += 1
            continue

        match = re.match(r"^( +)", line)
        if not match:
            continue

        spaces = len(match.group(1))
        if base_indent is None and spaces in (2, 4):
            base_indent = spaces
        elif base_indent and spaces % base_indent != 0:
            violations += 1
        elif base_indent is None and spaces not in (2, 4):
            violations += 1

    return violations


def count_line_length_violations(lines, max_length=120):
    return sum(1 for line in lines if len(line.rstrip("\n")) > max_length)


def count_ant_style_violations(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    tree = ET.parse(filepath)
    root = tree.getroot()

    violations = count_xml_indentation_violations(lines)
    violations += count_line_length_violations(lines)

    for elem in root.iter():
        if local_name(elem.tag) != local_name(elem.tag).lower():
            violations += 1
        for attr in elem.attrib:
            if local_name(attr) != local_name(attr).lower():
                violations += 1

    for target in root.findall(".//target"):
        name = target.attrib.get("name", "")
        if name and not re.fullmatch(r"[a-z0-9\-]+", name):
            violations += 1

    return violations


def count_maven_style_violations(filepath):
    with open(filepath, "r", encoding="utf-8", errors="replace") as f:
        lines = f.readlines()

    tree = ET.parse(filepath)
    root = tree.getroot()

    violations = count_xml_indentation_violations(lines)
    violations += count_line_length_violations(lines)

    for elem in root.iter():
        tag = local_name(elem.tag)
        if not is_maven_name(tag):
            violations += 1

        for attr in elem.attrib:
            attr_name = local_name(attr)
            if not attr_name.islower():
                violations += 1

    return violations


def calculate_gradle_style_violations(filepath):
    codenarc_cmd = resolve_codenarc_command()
    if not codenarc_cmd:
        print(
            "CodeNarc not found. Set CODENARC_CMD, CODENARC_BINARY, or CODENARC_JAR "
            "to analyze Gradle style conformance."
        )
        return None

    if not os.path.exists(CODENARC_STYLE_CONFIG):
        print(f"CodeNarc style config not found: {CODENARC_STYLE_CONFIG}")
        return None

    result = subprocess.run(
        [
            *codenarc_cmd,
            f"-sourcefiles={filepath}",
            f"-rulesetfiles=file:{CODENARC_STYLE_CONFIG}",
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

    p1 = 0
    p2 = 0
    p3 = 0

    for package in payload.get("packages", []):
        package_path = package.get("path", "")
        for file_info in package.get("files", []):
            if not codenarc_file_matches(filepath, package_path, file_info):
                continue

            for violation in file_info.get("violations", []):
                priority = int(violation.get("priority", 3))
                if priority == 1:
                    p1 += 1
                elif priority == 2:
                    p2 += 1
                else:
                    p3 += 1

    return (5 * p1) + (3 * p2) + p3


def calculate_gradle_kts_style_violations(filepath):
    detekt_cmd = resolve_detekt_command()
    if not detekt_cmd:
        print(
            "detekt not found. Set DETEKT_CMD, DETEKT_BINARY, or DETEKT_JAR "
            "to analyze Kotlin DSL style conformance."
        )
        return None

    if not os.path.exists(DETEKT_STYLE_CONFIG):
        print(f"detekt style config not found: {DETEKT_STYLE_CONFIG}")
        return None

    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        suffix=".xml",
        delete=False,
    ) as report_file:
        report_path = report_file.name

    try:
        result = subprocess.run(
            [
                *detekt_cmd,
                "--input",
                filepath,
                "--config",
                DETEKT_STYLE_CONFIG,
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

        tree = ET.parse(report_path)
        total_violations = 0

        for file_elem in tree.getroot().findall("file"):
            if os.path.abspath(file_elem.attrib.get("name", "")) != os.path.abspath(filepath):
                continue
            total_violations += len(file_elem.findall("error"))

        return total_violations
    except ET.ParseError:
        print("detekt returned an invalid XML report.")
        print(result.stderr.strip() or result.stdout.strip())
        return None
    finally:
        if os.path.exists(report_path):
            os.unlink(report_path)


def detect_build_type(filepath):
    filename = os.path.basename(filepath).lower()

    if filename.endswith(".gradle.kts"):
        return "gradle_kts"
    if filename.endswith(".gradle"):
        return "gradle"
    if filename == "pom.xml":
        return "maven"
    if filename == "build.xml":
        return "ant"
    return None


def integrate_style_conformance():
    if not os.path.exists(SUMMARY_FILE):
        print("ERROR: summary_metrics.csv not found. Run BLOC analyzer first.")
        return

    with open(SUMMARY_FILE, "r", encoding="utf-8") as file:
        reader = list(csv.reader(file))

    header = reader[0]
    rows = reader[1:]

    if "BLOC" not in header:
        print("ERROR: BLOC column not found. Run the BLOC analyzer first.")
        return

    bloc_index = header.index("BLOC")

    if "Style_Conformance_Score" not in header:
        header.append("Style_Conformance_Score")

    style_index = header.index("Style_Conformance_Score")
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

        try:
            bloc = int(row[bloc_index])
        except (ValueError, TypeError):
            print(f"Invalid BLOC value for {filename}: {row[bloc_index]}")
            updated_rows.append(row)
            continue

        build_type = detect_build_type(filepath)

        if build_type == "gradle":
            weighted_violations = calculate_gradle_style_violations(filepath)
        elif build_type == "gradle_kts":
            weighted_violations = calculate_gradle_kts_style_violations(filepath)
        elif build_type == "ant":
            weighted_violations = count_ant_style_violations(filepath)
        elif build_type == "maven":
            weighted_violations = count_maven_style_violations(filepath)
        else:
            print(f"Unsupported file skipped: {filename}")
            updated_rows.append(row)
            continue

        score = compute_style_score(bloc, weighted_violations) if weighted_violations is not None else None
        row[style_index] = format_score(score)
        updated_rows.append(row)

        print(
            f"{filename} | {build_type.upper()} Style Score = "
            f"{format_score(score) or 'N/A'}"
        )

    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(updated_rows)

    print("\nStyle conformance successfully integrated into summary_metrics.csv")


if __name__ == "__main__":
    integrate_style_conformance()
