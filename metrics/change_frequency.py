import os
import csv
import subprocess

# --------------------------------------------------
# Paths
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_PATH = os.path.join(BASE_DIR, "..")  # root of your Git repo
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "processed_builds", "summary_metrics.csv")

BUILD_FILES = ["build.gradle", "build.xml", "pom.xml"]

# --------------------------------------------------
# Compute Change Frequency using git log
# --------------------------------------------------
def compute_cf(file_path):
    """
    Counts commits modifying a file using git log
    """
    try:
        # Run git log --name-only --pretty=oneline
        result = subprocess.run(
            ["git", "log", "--pretty=oneline", "--name-only", "--", file_path],
            cwd=REPO_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        output = result.stdout.strip()
        if not output:
            return 0
        # Count commits (each commit has at least one line with hash)
        # We count commits by splitting on empty lines between commit hashes
        commits = set()
        for line in output.split("\n"):
            if line.strip() and not line.startswith(" "):
                commits.add(line.strip().split()[0])
        return len(commits)
    except Exception as e:
        print(f"Error computing CF for {file_path}: {e}")
        return 0

# --------------------------------------------------
# Integrate CF into summary_metrics.csv
# --------------------------------------------------
def integrate_cf():
    if not os.path.exists(SUMMARY_FILE):
        print("ERROR: summary_metrics.csv not found. Run BLOC + CC first.")
        return

    # Read existing summary
    with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    header = reader[0]
    rows = reader[1:]

    if "Change_Frequency" not in header:
        header.append("Change_Frequency")

    updated_rows = []

    for row in rows:
        filename = row[0]
        if filename in BUILD_FILES:
            cf_value = compute_cf(filename)
        else:
            cf_value = 0
        row = row[:len(header)-1]  # ensure length matches header
        row.append(cf_value)
        updated_rows.append(row)
        print(f"{filename} → Change Frequency = {cf_value}")

    # Write updated CSV
    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(updated_rows)

    print("\nChange Frequency successfully added to summary_metrics.csv")

# --------------------------------------------------
if __name__ == "__main__":
    integrate_cf()
