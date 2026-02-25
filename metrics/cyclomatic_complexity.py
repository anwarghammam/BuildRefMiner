import os
import csv
import subprocess
import xml.etree.ElementTree as ET

# Paths

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FOLDER = os.path.join(BASE_DIR, "..", "FilesExamples")
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "processed_builds", "summary_metrics.csv")


# ANT Cyclomatic Complexity

def calculate_ant_cc(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()

    cc = 1  # Base complexity

    # Target-level conditionals
    for target in root.findall('target'):
        if 'if' in target.attrib:
            cc += 1
        if 'unless' in target.attrib:
            cc += 1

    # Common conditional constructs
    conditionals = [
        './/condition',
        './/available',
        './/uptodate',
        './/isset',
        './/not',
        './/and',      
        './/or',
        './/equals',
        './/contains',
        './/matches'
    ]

    for cond in conditionals:
        cc += len(root.findall(cond))

    # Fail conditions
    for fail in root.findall('.//fail'):
        if 'if' in fail.attrib or 'unless' in fail.attrib:
            cc += 1

    return cc

# MAVEN Cyclomatic Complexity

def calculate_maven_cc(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()

    cc = 1  # Base complexity

    # Detect Maven decision-like constructs
    cc += len(root.findall('.//profile'))
    cc += len(root.findall('.//activation'))
    cc += len(root.findall('.//execution'))

    return cc


# GROOVY / GRADLE Cyclomatic Complexity (AST-based)

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
    if filepath.endswith(".gradle") or filepath.endswith(".groovy"):
        return "groovy"

    if filepath.endswith(".xml"):
        try:
            tree = ET.parse(filepath)
            root = tree.getroot()

            # Maven detection (presence of modelVersion)
            if root.find("modelVersion") is not None:
                return "maven"

            return "ant"

        except ET.ParseError:
            print(f"Invalid XML skipped: {filepath}")
            return None

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

    # Add CC column if missing
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

        # Ensure row matches header length
        row = row[:len(header)-1]
        row.append(cc)
        updated_rows.append(row)

        print(f"{filename} | {build_type.upper()} CC = {cc}")

    # Write updated summary
    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(updated_rows)

    print("\nCyclomatic Complexity successfully integrated into summary_metrics.csv")

if __name__ == "__main__":
    integrate_cc()