import os
import csv
import re

# --------------------------------------------------
# Stable Paths
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INPUT_FOLDER = os.path.join(BASE_DIR, "..", "FilesExamples")
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "processed_builds", "summary_metrics.csv")


# --------------------------------------------------
# Decision Patterns for CC
# --------------------------------------------------
DECISION_PATTERNS = [
    r"\bif\b",
    r"\belse\s+if\b",
    r"\bfor\b",
    r"\bwhile\b",
    r"\bcase\b",
    r"\bwhen\b",
    r"\bcatch\b",
    r"&&",
    r"\|\|"
]


# --------------------------------------------------
# Compute Cyclomatic Complexity
# --------------------------------------------------
def compute_cc(lines):
    cc = 1  # Base complexity per file

    for line in lines:
        for pattern in DECISION_PATTERNS:
            matches = re.findall(pattern, line)
            cc += len(matches)

    return cc


# --------------------------------------------------
# Integrate CC into Existing Summary
# --------------------------------------------------
def integrate_cc():
    if not os.path.exists(SUMMARY_FILE):
        print("ERROR: summary_metrics.csv not found. Run BLOC analyzer first.")
        return

    # Read existing summary
    with open(SUMMARY_FILE, "r", encoding="utf-8") as file:
        reader = list(csv.reader(file))

    header = reader[0]
    rows = reader[1:]

    # Add CC column if not already present
    if "Cyclomatic_Complexity" not in header:
        header.append("Cyclomatic_Complexity")

    updated_rows = []

    for row in rows:
        filename = row[0]
        filepath = os.path.join(INPUT_FOLDER, filename)

        if os.path.exists(filepath):
            with open(filepath, "r", encoding="utf-8") as f:
                lines = f.readlines()
            cc_value = compute_cc(lines)
        else:
            cc_value = 0

        # Ensure row length matches header before appending
        row = row[:len(header)-1]
        row.append(cc_value)

        updated_rows.append(row)

        print(f"Updated {filename} | CC = {cc_value}")

    # Write updated summary back
    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(header)
        writer.writerows(updated_rows)

    print("\nCyclomatic Complexity successfully added to summary_metrics.csv")


# --------------------------------------------------
if __name__ == "__main__":
    integrate_cc()
