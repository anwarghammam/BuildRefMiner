import os
import csv

# --------------------------------------------------
# Stable Base Directory
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INPUT_FOLDER = os.path.join(BASE_DIR, "..", "FilesExamples")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "..", "processed_builds")

BEFORE_FOLDER = os.path.join(OUTPUT_FOLDER, "before")
AFTER_FOLDER = os.path.join(OUTPUT_FOLDER, "after")

os.makedirs(BEFORE_FOLDER, exist_ok=True)
os.makedirs(AFTER_FOLDER, exist_ok=True)


# --------------------------------------------------
# Line Classification
# --------------------------------------------------
def classify_line(line):
    stripped = line.strip()

    if not stripped:
        return "BLANK"

    if stripped.startswith("//") or stripped.startswith("#"):
        return "COMMENT"

    return "CODE"


# --------------------------------------------------
# Process File
# --------------------------------------------------
def process_file(filepath, summary_data):
    filename = os.path.basename(filepath)
    name_without_ext = filename.replace(".", "_")

    before_path = os.path.join(BEFORE_FOLDER, f"{name_without_ext}_before.csv")
    after_path = os.path.join(AFTER_FOLDER, f"{name_without_ext}_after.csv")

    total_lines = 0
    total_blank = 0
    total_comments = 0
    total_bloc = 0

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # -------------------------
    # BEFORE CSV
    # -------------------------
    with open(before_path, "w", newline="", encoding="utf-8") as before_csv:
        writer = csv.writer(before_csv)
        writer.writerow(["Line_Number", "Content"])

        for i, line in enumerate(lines, 1):
            writer.writerow([i, line.rstrip()])

    # -------------------------
    # AFTER CSV
    # -------------------------
    with open(after_path, "w", newline="", encoding="utf-8") as after_csv:
        writer = csv.writer(after_csv)
        writer.writerow(["Line_Number", "Content", "Type"])

        for i, line in enumerate(lines, 1):
            total_lines += 1
            line_type = classify_line(line)

            if line_type == "BLANK":
                total_blank += 1
            elif line_type == "COMMENT":
                total_comments += 1
            else:
                total_bloc += 1

            writer.writerow([i, line.rstrip(), line_type])

    bloc_ratio = round(total_bloc / total_lines, 3) if total_lines > 0 else 0

    summary_data.append([
        filename,
        total_lines,
        total_bloc,
        total_comments,
        total_blank,
        bloc_ratio
    ])

    print(f"Processed: {filename}")
    print(f"  Total Lines: {total_lines}")
    print(f"  BLOC: {total_bloc}")
    print(f"  Comments: {total_comments}")
    print(f"  Blank: {total_blank}")
    print(f"  BLOC Ratio: {bloc_ratio}\n")


# --------------------------------------------------
# Main
# --------------------------------------------------
def main():
    print("Starting Advanced BLOC Analysis...\n")

    if not os.path.exists(INPUT_FOLDER):
        print("ERROR: FilesExamples folder not found.")
        return

    summary_data = []

    for file in os.listdir(INPUT_FOLDER):
        if file.endswith((".gradle", ".xml")):
            process_file(os.path.join(INPUT_FOLDER, file), summary_data)

    # -------------------------
    # Write Summary CSV
    # -------------------------
    summary_path = os.path.join(OUTPUT_FOLDER, "summary_metrics.csv")

    with open(summary_path, "w", newline="", encoding="utf-8") as summary_file:
        writer = csv.writer(summary_file)
        writer.writerow([
            "File_Name",
            "Total_Lines",
            "BLOC",
            "Comment_Lines",
            "Blank_Lines",
            "BLOC_Ratio"
        ])
        writer.writerows(summary_data)

    print("BLOC Analysis Completed.")
    print("Summary file created at: processed_builds/summary_metrics.csv")


# --------------------------------------------------
if __name__ == "__main__":
    main()
