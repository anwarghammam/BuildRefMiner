import os
import csv
import xml.etree.ElementTree as ET
import re
import math

# --------------------------------------------------
# Paths
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(BASE_DIR, "..", "FilesExamples")
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "processed_builds", "summary_metrics.csv")

# --------------------------------------------------
# Halstead for XML files (Ant / Maven)
# --------------------------------------------------
def halstead_xml(file_path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Keep everything up to the last </project> tag to ignore non-XML content
        end_index = content.rfind("</project>")
        if end_index == -1:
            print(f"ERROR: No </project> tag found in {file_path}")
            return 0
        content = content[:end_index + len("</project>")]

        root = ET.fromstring(content)
        operators = []
        operands = []

        def traverse(elem):
            operators.append(elem.tag)
            for key, value in elem.attrib.items():
                operands.append(key)
                operands.append(value)
            if elem.text and elem.text.strip():
                operands.append(elem.text.strip())
            for child in elem:
                operands.append(child.tag)
                traverse(child)

        traverse(root)

        n1 = len(set(operators))
        n2 = len(set(operands))
        N1 = len(operators)
        N2 = len(operands)
        if n1 + n2 == 0:
            return 0
        return int((N1 + N2) * math.log2(n1 + n2))

    except Exception as e:
        print(f"Error parsing XML {file_path}: {e}")
        return 0

# --------------------------------------------------
# Halstead for Gradle DSL
# --------------------------------------------------
def halstead_gradle(file_path):
    try:
        operators = []
        operands = []
        with open(file_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                # operators = keywords, method names, closures
                op_matches = re.findall(r"\b(def|class|if|else|for|while|println|apply|plugins)\b", line)
                operators.extend(op_matches)
                # operands = variable names and string literals
                operand_matches = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", line)
                string_matches = re.findall(r'"(.*?)"', line)
                operands.extend(operand_matches)
                operands.extend(string_matches)

        n1 = len(set(operators))
        n2 = len(set(operands))
        N1 = len(operators)
        N2 = len(operands)

        if n1 + n2 == 0:
            return 0

        return int((N1 + N2) * math.log2(n1 + n2))

    except Exception as e:
        print(f"Error parsing Gradle {file_path}: {e}")
        return 0

# --------------------------------------------------
# Main: integrate Halstead Volume into summary_metrics.csv
# --------------------------------------------------
def integrate_halstead():
    if not os.path.exists(SUMMARY_FILE):
        print("ERROR: summary_metrics.csv not found. Run BLOC + CC + CF first.")
        return

    # Read existing summary
    with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    header = reader[0]
    rows = reader[1:]

    if "Halstead_Volume" not in header:
        header.append("Halstead_Volume")

    updated_rows = []

    for row in rows:
        # Clean filename (remove ../FilesExamples/ prefix)
        filename = os.path.basename(row[0])
        file_path = os.path.join(FILES_DIR, filename)

        # Debug: check file path exists
        print(f"Processing file: {file_path} → Exists: {os.path.exists(file_path)}")

        hv = 0
        if os.path.exists(file_path):
            if filename.endswith(".xml"):
                hv = halstead_xml(file_path)
            elif filename.endswith(".gradle"):
                hv = halstead_gradle(file_path)
            else:
                hv = 0
        else:
            print(f"Warning: {filename} not found!")

        row = row[:len(header)-1]
        row.append(hv)
        updated_rows.append(row)
        print(f"{filename} → Halstead Volume = {hv}")

    # Write updated CSV
    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(updated_rows)

    print("\nHalstead Volume successfully added to summary_metrics.csv")

# --------------------------------------------------
if __name__ == "__main__":
    integrate_halstead()
