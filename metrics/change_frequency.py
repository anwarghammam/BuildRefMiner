import os
import csv
import subprocess

# --------------------------------------------------
# Paths
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_PATH = os.path.join(BASE_DIR, "..")  # root of your Git repo
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "processed_builds", "summary_metrics.csv")

# Target build files with folder path included
BUILD_FILES = ["FilesExamples/build.gradle", "FilesExamples/build.xml", "FilesExamples/pom.xml"]

# --------------------------------------------------
# Compute Change Frequency using git log
# --------------------------------------------------
def compute_cf(file_path):
    """
    Counts commits modifying a file using git log
    """
    try:
        # Run git log for the file
        result = subprocess.run(
            ["git", "log", "--pretty=format:%H", "--", file_path],
            cwd=REPO_PATH,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        output = result.stdout.strip()
        if not output:
            return 0
        commits = output.split("\n")
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

    # Add CF column if not present
    if "Change_Frequency" not in header:
        header.append("Change_Frequency")

    updated_rows = []

    for row in rows:
        basename = row[0]  # e.g., "build.gradle"
        file_path = f"FilesExamples/{basename}"  # include folder path

        if os.path.exists(os.path.join(REPO_PATH, file_path)):
            cf_value = compute_cf(file_path)
        else:
            cf_value = 0

        # Ensure row length matches header before appending
        row = row[:len(header)-1]
        row.append(cf_value)
        updated_rows.append(row)

        print(f"{basename} → Change Frequency = {cf_value}")

    # Write updated CSV
    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(updated_rows)

    print("\nChange Frequency successfully added to summary_metrics.csv")

# --------------------------------------------------
if __name__ == "__main__":
    integrate_cf()
