import os
import csv

# --------------------------------------------------
# Stable Base Directory
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INPUT_FOLDER = os.path.join(BASE_DIR, "..", "FilesExamples")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "..", "processed_builds")

BEFORE_FOLDER = os.path.join(OUTPUT_FOLDER, "beforebloc")
AFTER_FOLDER = os.path.join(OUTPUT_FOLDER, "afterbloc")

os.makedirs(BEFORE_FOLDER, exist_ok=True)
os.makedirs(AFTER_FOLDER, exist_ok=True)


# --------------------------------------------------
# BLOC Logic (Handles Multi-line Comments)
# --------------------------------------------------
def process_file(filepath, summary_data):
    filename = os.path.basename(filepath)
    name_without_ext = filename.replace(".", "_")

    before_path = os.path.join(BEFORE_FOLDER, f"{name_without_ext}_before.csv")
    after_path = os.path.join(AFTER_FOLDER, f"{name_without_ext}_after.csv")

    total_bloc = 0
    bloc_number = 0

    in_multiline_comment = False

    with open(filepath, "r", encoding="utf-8") as f:
        lines = f.readlines()

    # -------------------------
    # Write BEFORE CSV
    # -------------------------
    with open(before_path, "w", newline="", encoding="utf-8") as before_csv:
        writer = csv.writer(before_csv)
        writer.writerow(["Line_Number", "Content"])

        for i, line in enumerate(lines, 1):
            writer.writerow([i, line.rstrip()])

    # -------------------------
    # Write AFTER CSV
    # -------------------------
    with open(after_path, "w", newline="", encoding="utf-8") as after_csv:
        writer = csv.writer(after_csv)
        writer.writerow(["Line_Number", "Content", "Is_BLOC", "BLOC_Number"])

        for i, line in enumerate(lines, 1):
            stripped = line.strip()
            is_bloc = 0
            current_bloc_number = ""

            # Skip empty lines
            if not stripped:
                writer.writerow([i, line.rstrip(), 0, ""])
                continue

            # Handle multi-line comments (Gradle /* */)
            if "/*" in stripped:
                in_multiline_comment = True

            if "<!--" in stripped:
                in_multiline_comment = True

            if in_multiline_comment:
                if "*/" in stripped:
                    in_multiline_comment = False
                if "-->" in stripped:
                    in_multiline_comment = False

                writer.writerow([i, line.rstrip(), 0, ""])
                continue

            # Ignore single-line comments
            if stripped.startswith("//") or stripped.startswith("#"):
                writer.writerow([i, line.rstrip(), 0, ""])
                continue

            # Everything else counts as BLOC
            is_bloc = 1
            total_bloc += 1
            bloc_number += 1
            current_bloc_number = bloc_number

            writer.writerow([i, line.rstrip(), is_bloc, current_bloc_number])

    summary_data.append([filename, total_bloc])

    print(f"Processed: {filename} | Total BLOC = {total_bloc}")


# --------------------------------------------------
# Main Function
# --------------------------------------------------
def main():
    print("Starting BLOC Analysis...\n")

    if not os.path.exists(INPUT_FOLDER):
        print("ERROR: FilesExamples folder not found.")
        return

    summary_data = []

    for file in os.listdir(INPUT_FOLDER):
        if file.endswith((".gradle", ".xml")):
            process_file(os.path.join(INPUT_FOLDER, file), summary_data)

    summary_path = os.path.join(OUTPUT_FOLDER, "summary_metrics.csv")

    with open(summary_path, "w", newline="", encoding="utf-8") as summary_file:
        writer = csv.writer(summary_file)
        writer.writerow(["File_Name", "BLOC"])
        writer.writerows(summary_data)

    print("\nBLOC Analysis Completed.")
    print("Check processed_builds folder for results.")


# --------------------------------------------------
# Run Script
# --------------------------------------------------
if __name__ == "__main__":
    main()