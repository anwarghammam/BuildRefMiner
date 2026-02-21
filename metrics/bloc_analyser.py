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
# Process Each File (Robust BLOC Logic)
# --------------------------------------------------
def process_file(filepath, summary_data):
    filename = os.path.basename(filepath)
    name_without_ext = filename.replace(".", "_")

    before_path = os.path.join(BEFORE_FOLDER, f"{name_without_ext}_before.csv")
    after_path = os.path.join(AFTER_FOLDER, f"{name_without_ext}_after.csv")

    total_bloc = 0
    bloc_number = 0

    in_xml_comment = False
    in_block_comment = False  # For /* */

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
            original_line = line.rstrip()
            stripped = line.strip()

            # Skip empty lines
            if not stripped:
                writer.writerow([i, original_line, 0, ""])
                continue

            # --------------------------------------------------
            # Handle XML Multi-line Comments <!-- -->
            # --------------------------------------------------
            if not in_xml_comment and "<!--" in stripped:
                if "-->" in stripped:
                    # Inline XML comment
                    stripped = stripped.split("<!--")[0].strip()
                    if not stripped:
                        writer.writerow([i, original_line, 0, ""])
                        continue
                else:
                    in_xml_comment = True
                    writer.writerow([i, original_line, 0, ""])
                    continue

            elif in_xml_comment:
                if "-->" in stripped:
                    in_xml_comment = False
                writer.writerow([i, original_line, 0, ""])
                continue

            # --------------------------------------------------
            # Handle Gradle Multi-line Comments /* */
            # --------------------------------------------------
            if not in_block_comment and "/*" in stripped:
                if "*/" in stripped:
                    # Inline block comment
                    before_comment = stripped.split("/*")[0].strip()
                    if not before_comment:
                        writer.writerow([i, original_line, 0, ""])
                        continue
                    stripped = before_comment
                else:
                    in_block_comment = True
                    writer.writerow([i, original_line, 0, ""])
                    continue

            elif in_block_comment:
                if "*/" in stripped:
                    in_block_comment = False
                writer.writerow([i, original_line, 0, ""])
                continue

            # --------------------------------------------------
            # Remove inline single-line comments //
            # --------------------------------------------------
            if "//" in stripped:
                stripped = stripped.split("//")[0].strip()

            # Remove full-line # comments
            if stripped.startswith("#"):
                writer.writerow([i, original_line, 0, ""])
                continue

            # If nothing remains after stripping
            if not stripped:
                writer.writerow([i, original_line, 0, ""])
                continue

            # --------------------------------------------------
            # Count as BLOC
            # --------------------------------------------------
            total_bloc += 1
            bloc_number += 1

            writer.writerow([i, original_line, 1, bloc_number])

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