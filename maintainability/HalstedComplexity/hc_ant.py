import os
import xml.etree.ElementTree as ET
import math
from collections import Counter

def collect_operators_operands_across_ant_files(directory):
    excluded_tags = {"project", "property", "description"}

    operator_counter = Counter()
    operand_counter = Counter()

    for root_dir, _, files in os.walk(directory):
        for file in files:
            # we need to change this to xml only

            if file.endswith("build.xml"):
                try:
                    tree = ET.parse(os.path.join(root_dir, file))
                    root = tree.getroot()
                    for elem in root.iter():
                        tag = elem.tag
                        if tag not in excluded_tags:
                            operator_counter[tag] += 1
                            for attr_key, attr_val in elem.attrib.items():
                                if not (tag == "target" and attr_key == "name"):
                                    operand_counter[attr_val] += 1
                except Exception as e:
                    print(f"[!] Failed to parse {file}: {e}")
    print(operand_counter)
    return operator_counter, operand_counter

def calculate_aggregated_halstead(operator_counter, operand_counter):
    n1 = len(operator_counter)
    n2 = len(operand_counter)
    N1 = sum(operator_counter.values())
    N2 = sum(operand_counter.values())

    n = n1 + n2
    N = N1 + N2

    volume = N * math.log2(n) if n > 0 else 0
    difficulty = (n1 / 2) * (N2 / n2) if n2 > 0 else 0
    effort = difficulty * volume

    return {
        "Distinct Operators (n1)": n1,
        "Distinct Operands (n2)": n2,
        "Total Operators (N1)": N1,
        "Total Operands (N2)": N2,
        "Vocabulary (n)": n,
        "Length (N)": N,
        "Volume": round(volume, 2),
        "Difficulty": round(difficulty, 2),
        "Effort": round(effort, 2)
    }

# === USAGE ===
if __name__ == "__main__":
    project_dir = "../../FilesExamples"  # Change this
    ops, oprnds = collect_operators_operands_across_ant_files(project_dir)
    results = calculate_aggregated_halstead(ops, oprnds)

    print("📊 Aggregated Halstead Complexity for Ant Project:")
    for k, v in results.items():
        print(f"{k}: {v}")