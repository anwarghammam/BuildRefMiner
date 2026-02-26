import os
import csv
from collections import defaultdict
from pydriller import Repository

# --------------------------------------------------
# Paths
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.abspath(os.path.join(BASE_DIR, ".."))
SUMMARY_FILE = os.path.join(REPO_DIR, "processed_builds", "summary_metrics.csv")

# Exact paths inside repo (prevents over-counting)
BUILD_PATHS = {
    "FilesExamples/build.xml",
    "FilesExamples/pom.xml",
    "FilesExamples/build.gradle",
    "FilesExamples/TestScript.groovy",
}


# --------------------------------------------------
def normalize_path(path: str) -> str:
    return path.replace("\\", "/")


# --------------------------------------------------
def calculate_churn(repo_dir: str) -> dict:
    churn_per_file = defaultdict(int)

    for commit in Repository(repo_dir).traverse_commits():
        for mod in commit.modified_files:
            path = mod.new_path or mod.old_path
            if not path:
                continue

            rel = normalize_path(path)

            if rel not in BUILD_PATHS:
                continue

            base = os.path.basename(rel)
            added = mod.added_lines or 0
            deleted = mod.deleted_lines or 0

            churn_per_file[base] += (added + deleted)

    return dict(churn_per_file)


# --------------------------------------------------
def integrate_churn():
    if not os.path.exists(SUMMARY_FILE):
        print("ERROR: summary_metrics.csv not found.")
        return

    churn_data = calculate_churn(REPO_DIR)

    with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    if not rows:
        print("ERROR: summary_metrics.csv is empty.")
        return

    header = rows[0]
    body = rows[1:]

    # --------------------------------------------------
    # Find or create Churn column
    # --------------------------------------------------
    if "Churn" in header:
        churn_index = header.index("Churn")
    else:
        header.append("Churn")
        churn_index = len(header) - 1

    updated_rows = []

    for row in body:
        if not row:
            continue

        filename = os.path.basename(row[0])
        churn_value = churn_data.get(filename, 0)

        # Ensure row length matches header
        if len(row) < len(header):
            row.extend([""] * (len(header) - len(row)))

        # ✅ Overwrite churn column value
        row[churn_index] = str(churn_value)

        updated_rows.append(row)

        print(f"{filename} → Churn = {churn_value}")

    # Write updated CSV
    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(updated_rows)

    print("\n✅ Churn column updated successfully.")


# --------------------------------------------------
if __name__ == "__main__":
    integrate_churn()