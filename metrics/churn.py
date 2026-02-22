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

# Only count churn for the build files you care about (prevents counting config/*.xml etc.)
BUILD_FILENAMES = {
    "build.xml",          # Ant
    "pom.xml",            # Maven
    "build.gradle",       # Gradle
    "settings.gradle",    # Gradle (optional)
    "gradle.properties",  # Gradle (optional)
    "TestScript.groovy",  # your Groovy test file
}

# If you want to include other build-related files later, add them here.


# --------------------------------------------------
def calculate_churn(repo_dir: str) -> dict:
    """
    Churn = sum(added_lines + deleted_lines) across commits, per file.
    Returns dict keyed by basename (e.g., build.xml -> churn value).
    """
    churn_per_file = defaultdict(int)

    for commit in Repository(repo_dir).traverse_commits():
        for mod in commit.modified_files:
            # Use new_path/old_path when available (handles renames)
            path = mod.new_path or mod.old_path
            if not path:
                continue

            base = os.path.basename(path)

            # Filter to only the build files we want
            if base not in BUILD_FILENAMES:
                continue

            added = mod.added_lines or 0
            deleted = mod.deleted_lines or 0
            churn_per_file[base] += (added + deleted)

    return dict(churn_per_file)


# --------------------------------------------------
def integrate_churn():
    if not os.path.exists(SUMMARY_FILE):
        print("ERROR: summary_metrics.csv not found. Run BLOC analyzer first.")
        return

    churn_data = calculate_churn(REPO_DIR)

    with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    if not rows:
        print("ERROR: summary_metrics.csv is empty.")
        return

    header = rows[0]
    body = rows[1:]

    if "Churn" not in header:
        header.append("Churn")

    out_rows = []
    for row in body:
        if not row:
            continue

        filename = os.path.basename(row[0])  # summary stores names like build.xml, pom.xml
        churn_value = churn_data.get(filename, 0)

        row = row[:len(header) - 1]
        row.append(churn_value)
        out_rows.append(row)

        print(f"{filename} → Churn = {churn_value}")

    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(out_rows)

    print("\n✅ Churn successfully added to summary_metrics.csv")


# --------------------------------------------------
if __name__ == "__main__":
    integrate_churn()