import os
import csv
import math
import subprocess
import xml.etree.ElementTree as ET
from collections import Counter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_FOLDER = os.path.join(BASE_DIR, "..", "FilesExamples")
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "results", "summary_metrics.csv")

GROOVY_HALSTEAD_SCRIPT = os.path.join(BASE_DIR, "halstead_groovy_ast.groovy")


def halstead_from_counts(n1, n2, N1, N2):
    vocab = n1 + n2
    length = N1 + N2
    volume = length * math.log2(vocab) if vocab > 0 and length > 0 else 0.0
    difficulty = (n1 / 2) * (N2 / n2) if n2 > 0 else 0.0
    effort = difficulty * volume
    return round(volume, 2), round(difficulty, 2), round(effort, 2)



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
        print(f"[XML] Parse error in {filepath}: {e}")
        return None
    except Exception as e:
        print(f"[XML] Unexpected error in {filepath}: {e}")
        return None


# ANT 
def ant_operator_operand_counters(filepath):
    excluded_tags = {"project", "description"}
    op = Counter()
    opd = Counter()

    tree = safe_parse_xml(filepath)
    if tree is None:
        return op, opd

    root = tree.getroot()

    for elem in root.iter():
        tag = elem.tag.split("}")[-1]
        if tag in excluded_tags:
            continue

        op[tag] += 1

        for attr_key, _attr_val in elem.attrib.items():
            if not (tag == "target" and attr_key == "name"):
                opd[attr_key] += 1

    return op, opd


def ant_counts(filepath):
    op, opd = ant_operator_operand_counters(filepath)

    n1 = len(op)
    n2 = len(opd)
    N1 = sum(op.values())
    N2 = sum(opd.values())
    return n1, n2, N1, N2


# MAVEN 
def maven_operator_operand_counters(filepath):
    op = Counter()
    opd = Counter()

    tree = safe_parse_xml(filepath)
    if tree is None:
        return op, opd

    root = tree.getroot()

    for elem in root.iter():
        tag = elem.tag.split("}")[-1]
        op[tag] += 1

        for child in list(elem):
            child_tag = child.tag.split("}")[-1]
            opd[child_tag] += 1

    return op, opd


def maven_counts(filepath):
    op, opd = maven_operator_operand_counters(filepath)

    n1 = len(op)
    n2 = len(opd)
    N1 = sum(op.values())
    N2 = sum(opd.values())
    return n1, n2, N1, N2


#GROOVY/GRADLE 
def groovy_counts(filepath):
    if not os.path.exists(GROOVY_HALSTEAD_SCRIPT):
        raise FileNotFoundError(f"Missing: {GROOVY_HALSTEAD_SCRIPT}")

    res = subprocess.run(
        ["groovy", GROOVY_HALSTEAD_SCRIPT, filepath],
        capture_output=True,
        text=True
    )

    if res.returncode != 0:
        print(f"[GROOVY] Failed on {filepath}\n{res.stderr}")
        return 0, 0, 0, 0

    out = res.stdout.strip()
    if not out or "," not in out:
        print(f"[GROOVY] Unexpected output on {filepath}: {out}")
        return 0, 0, 0, 0

    n1, n2, N1, N2 = [int(x) for x in out.split(",")]
    return n1, n2, N1, N2


def compute_halstead(filename, filepath):
    try:
        if filename == "build.xml":
            n1, n2, N1, N2 = ant_counts(filepath)
        elif filename == "pom.xml":
            n1, n2, N1, N2 = maven_counts(filepath)
        elif filename.endswith(".gradle") or filename.endswith(".groovy"):
            n1, n2, N1, N2 = groovy_counts(filepath)
        else:
            return 0.0

        volume, _, _ = halstead_from_counts(n1, n2, N1, N2)
        print(f"{filename} | Halstead Volume = {volume} (n1={n1}, n2={n2}, N1={N1}, N2={N2})")
        return volume

    except Exception as e:
        print(f"[ERROR] {filename}: {e}")
        return 0.0


def integrate_halstead():
    if not os.path.exists(SUMMARY_FILE):
        print("ERROR: summary_metrics.csv not found. Run BLOC analyzer first.")
        return

    with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    header = rows[0]
    data = rows[1:]

    if "Halstead_Volume" not in header:
        header.append("Halstead_Volume")

    out_rows = []
    for row in data:
        filename = row[0]
        filepath = os.path.join(INPUT_FOLDER, filename)

        row = row[:len(header) - 1]

        if not os.path.exists(filepath):
            row.append(0.0)
            out_rows.append(row)
            print(f"{filename} | missing -> Halstead Volume = 0")
            continue

        volume = compute_halstead(filename, filepath)
        row.append(volume)
        out_rows.append(row)

    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(out_rows)

    print("\n✅ Halstead Volume integrated into summary_metrics.csv")


if __name__ == "__main__":
    integrate_halstead()
