import os
import math
import xml.etree.ElementTree as ET
from collections import Counter

def collect_maven_operators_operands(directory):
    operator_counter = Counter()
    operand_counter = Counter()

    for root_dir, _, files in os.walk(directory):
        for file in files:
            if file == "pom.xml":
                file_path = os.path.join(root_dir, file)
                try:
                    tree = ET.parse(file_path)
                    root = tree.getroot()
                    for elem in root.iter():
                        tag = elem.tag.split('}')[-1]  # Operator
                        operator_counter[tag] += 1
                        for child in elem:
                            child_tag = child.tag.split('}')[-1]  # Operand
                            operand_counter[child_tag] += 1
                except Exception as e:
                    print(f"Failed to parse {file_path}: {e}")

    return operator_counter, operand_counter

def calculate_halstead(operator_counter, operand_counter):
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

if __name__ == "__main__":
    directory_path = "../../FilesExamples"  # Replace with your actual directory
    ops, oprnds = collect_maven_operators_operands(directory_path)
    results = calculate_halstead(ops, oprnds)
    for key, value in results.items():
        print(f"{key}: {value}")