import os
import csv
from pydriller import Repository

# --------------------------------------------------
# Paths
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.join(BASE_DIR, "..")
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "processed_builds", "summary_metrics.csv")

BUILD_EXTENSIONS = [".xml", ".gradle"]

# --------------------------------------------------
def calculate_churn():
    churn_per_file = {}

    for commit in Repository(REPO_DIR).traverse_commits():
        for mod in commit.modified_files:

            if mod.filename and any(mod.filename.endswith(ext) for ext in BUILD_EXTENSIONS):

                filename = mod.filename
                added = mod.added_lines or 0
                deleted = mod.deleted_lines or 0
                churn_value = added + deleted

                churn_per_file[filename] = churn_per_file.get(filename, 0) + churn_value

    return churn_per_file


# --------------------------------------------------
def integrate_churn():
    if not os.path.exists(SUMMARY_FILE):
        print("summary_metrics.csv not found.")
        return

    churn_data = calculate_churn()

    with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    header = reader[0]
    rows = reader[1:]

    if "Churn" not in header:
        header.append("Churn")

    updated_rows = []

    for row in rows:
        filename = os.path.basename(row[0])
        churn_value = churn_data.get(filename, 0)

        row = row[:len(header)-1]
        row.append(churn_value)
        updated_rows.append(row)

        print(f"{filename} → Churn = {churn_value}")

    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(updated_rows)

    print("\nChurn successfully added.")


if __name__ == "__main__":
    integrate_churn()
