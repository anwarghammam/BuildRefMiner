import os
import csv
import subprocess
import xml.etree.ElementTree as ET

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FOLDER = os.path.join(BASE_DIR, "..", "FilesExamples")
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "processed_builds", "summary_metrics.csv")



# XML cleaning helper
# Keeps only content up to the final </project>

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


# Safe XML parse helper

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



# Namespace-safe local tag extractor

def local_name(tag):
    if "}" in tag:
        return tag.split("}", 1)[1]
    return tag



# ANT Cyclomatic Complexity

def calculate_ant_cc(filepath):
    tree = safe_parse_xml(filepath)
    if tree is None:
        return 0

    root = tree.getroot()
    cc = 1

    for elem in root.iter():
        if local_name(elem.tag) == "target":
            if "if" in elem.attrib:
                cc += 1
            if "unless" in elem.attrib:
                cc += 1

    ant_condition_tags = {
        "condition",
        "available",
        "uptodate",
        "isset",
        "not",
        "and",
        "or",
        "equals",
        "contains",
        "matches",
    }

    for elem in root.iter():
        if local_name(elem.tag) in ant_condition_tags:
            cc += 1

    for elem in root.iter():
        if local_name(elem.tag) == "fail":
            if "if" in elem.attrib or "unless" in elem.attrib:
                cc += 1

    return cc



# MAVEN Cyclomatic Complexity

def calculate_maven_cc(filepath):
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



# GROOVY / GRADLE Cyclomatic Complexity

def calculate_groovy_cc(filepath):
    try:
        groovy_script_path = os.path.join(BASE_DIR, "gradle_cc.groovy")

        result = subprocess.run(
            ["groovy", groovy_script_path, filepath],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            print("Groovy Error:")
            print(result.stderr)
            return 1

        output = result.stdout.strip()

        if not output:
            print("Groovy returned empty output.")
            return 1

        return int(output)

    except Exception as e:
        print(f"Error running Groovy CC on {filepath}: {e}")
        return 1


# Detect Build Type

def detect_build_type(filepath):
    filename = os.path.basename(filepath).lower()

    if filename.endswith(".gradle") or filename.endswith(".groovy"):
        return "groovy"
    if filename == "pom.xml":
        return "maven"
    if filename == "build.xml":
        return "ant"
    return None


# Integrate Into Summary

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

    updated_rows = []

    for row in rows:
        filename = row[0]
        filepath = os.path.join(INPUT_FOLDER, filename)

        if not os.path.exists(filepath):
            print(f"File not found: {filename}")
            updated_rows.append(row)
            continue

        build_type = detect_build_type(filepath)

        if build_type == "ant":
            cc = calculate_ant_cc(filepath)
        elif build_type == "maven":
            cc = calculate_maven_cc(filepath)
        elif build_type == "groovy":
            cc = calculate_groovy_cc(filepath)
        else:
            print(f"Unsupported file skipped: {filename}")
            updated_rows.append(row)
            continue

        row = row[:len(header) - 1]
        row.append(cc)
        updated_rows.append(row)

        print(f"{filename} | {build_type.upper()} CC = {cc}")

    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(updated_rows)

    print("\nCyclomatic Complexity successfully integrated into summary_metrics.csv")


if __name__ == "__main__":
    integrate_cc()