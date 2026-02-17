import os
import csv
import xml.etree.ElementTree as ET
import re

# --------------------------------------------------
# Paths
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(BASE_DIR, "..", "FilesExamples")
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "processed_builds", "summary_metrics.csv")

# --------------------------------------------------
# Helper functions
# --------------------------------------------------

# Halstead for XML files (Ant / Maven)
def halstead_xml(file_path):
    try:
        tree = ET.parse(file_path)
        root = tree.getroot()
        operators = set()
        operands = set()
        # Traverse XML
        for elem in root.iter():
            operators.add(elem.tag)  # tag = operator
            for child in elem:       # child tags = operands
                operands.add(child.tag)
            for key, value in elem.attrib.items():  # attributes = operands
                operands.add(key)
        n1 = len(operators)      # unique operators
        n2 = len(operands)       # unique operands
        N1 = sum(1 for _ in operators)  # total operators (simplified)
        N2 = sum(1 for _ in operands)   # total operands (simplified)
        # Halstead Volume formula
        if n1+n2 == 0:
            return 0
        V = (N1+N2) * (0 if n1+n2==0 else (n1+n2).bit_length())  # simplified log2(n1+n2)
        return int(V)
    except Exception as e:
        print(f"Error parsing XML {file_path}: {e}")
        return 0

# Halstead for Gradle DSL
def halstead_gradle(file_path):
    try:
        operators = set()
        operands = set()
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines:
                line = line.strip()
                if not line or line.startswith("//"):
                    continue
                # Simplified: operators = keywords, method names, closures
                op_matches = re.findall(r"\b(def|class|if|else|for|while|println|apply|plugins)\b", line)
                operators.update(op_matches)
                # operands = variable names and string literals
                operand_matches = re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", line)
                string_matches = re.findall(r'"(.*?)"', line)
                operands.update(operand_matches)
                operands.update(string_matches)
        n1 = len(operators)
        n2 = len(operands)
        N1 = sum(1 for _ in operators)
        N2 = sum(1 for _ in operands)
        if n1+n2 == 0:
            return 0
        V = (N1+N2) * (0 if n1+n2==0 else (n1+n2).bit_length())
        return int(V)
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
        filename = row[0]
        file_path = os.path.join(FILES_DIR, filename)
        hv = 0
        if os.path.exists(file_path):
            if filename.endswith(".xml"):
                hv = halstead_xml(file_path)
            elif filename.endswith(".gradle"):
                hv = halstead_gradle(file_path)
            else:
                hv = 0
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
