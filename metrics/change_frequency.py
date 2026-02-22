import os
import csv
import subprocess

# -------------------------
# Paths
# -------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_FOLDER = os.path.join(BASE_DIR, "..", "processed_builds")
SUMMARY_CSV = os.path.join(OUTPUT_FOLDER, "summary_metrics.csv")

# -------------------------
# Read existing summary_metrics.csv
# -------------------------
summary_data = []

with open(SUMMARY_CSV, newline="", encoding="utf-8") as f:
    reader = csv.reader(f)
    headers = next(reader)  # existing headers: File_Name, BLOC
    summary_data = list(reader)

# -------------------------
# Add Change Frequency for each file
# -------------------------
new_summary_data = []

for row in summary_data:
    filename = row[0]
    # Run git log to count commits touching the file
    file_path = os.path.join(BASE_DIR, "..", "FilesExamples", filename.replace("_", "."))
    cmd = ["git", "log", "--pretty=oneline", "--", file_path]
    result = subprocess.run(cmd, capture_output=True, text=True)
    commits = result.stdout.strip().split("\n")
    commits = [c for c in commits if c]
    change_freq = len(commits)
    
    new_summary_data.append(row + [change_freq])
    print(f"File: {filename} | BLOC = {row[1]} | Change Frequency = {change_freq}")

# -------------------------
# Write updated summary_metrics.csv
# -------------------------
with open(SUMMARY_CSV, "w", newline="", encoding="utf-8") as f:
    writer = csv.writer(f)
    writer.writerow(headers + ["Change_Frequency"])
    writer.writerows(new_summary_data)

print("\nUpdated summary_metrics.csv with Change Frequency!")