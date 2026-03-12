import os
import csv
import re

# Stable Base Directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

INPUT_FOLDER = os.path.join(BASE_DIR, "..", "FilesExamples")
OUTPUT_FOLDER = os.path.join(BASE_DIR, "..", "processed_builds")

BEFORE_FOLDER = os.path.join(OUTPUT_FOLDER, "beforebloc")
AFTER_FOLDER = os.path.join(OUTPUT_FOLDER, "afterbloc")

os.makedirs(BEFORE_FOLDER, exist_ok=True)
os.makedirs(AFTER_FOLDER, exist_ok=True)



# Remove comments from content

def remove_comments(text: str) -> str:
    # XML multi-line comments
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # Groovy/Gradle block comments
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    # Single-line comments //
    text = re.sub(r"//.*", "", text)

    # Full-line hash comments
    text = re.sub(r"^\s*#.*$", "", text, flags=re.MULTILINE)

    return text



# Normalize lines
# - trim whitespace
# - drop empty lines

def normalize_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        lines.append(line)
    return lines



# Reusable BLOC computation for one file
# This is the function the before/after commit runner can call.

def compute_bloc(file_path: str) -> int:
    if not file_path or not os.path.exists(file_path):
        return 0

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = remove_comments(content)
    lines = normalize_lines(content)

    return len(lines)



# Process Each File (for detailed CSV outputs)

def process_file(filepath, summary_data):
    filename = os.path.basename(filepath)
    name_without_ext = filename.replace(".", "_")

    before_path = os.path.join(BEFORE_FOLDER, f"{name_without_ext}_before.csv")
    after_path = os.path.join(AFTER_FOLDER, f"{name_without_ext}_after.csv")

    with open(filepath, "r", encoding="utf-8") as f:
        original_lines = f.readlines()

    # For BLOC logic, use cleaned content
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    cleaned_content = remove_comments(content)
    bloc_lines = normalize_lines(cleaned_content)

  
    # Write BEFORE CSV
   
    with open(before_path, "w", newline="", encoding="utf-8") as before_csv:
        writer = csv.writer(before_csv)
        writer.writerow(["Line_Number", "Content"])

        for i, line in enumerate(original_lines, 1):
            writer.writerow([i, line.rstrip()])

    # Write AFTER CSV
    
    bloc_number = 0
    remaining_bloc_lines = bloc_lines.copy()

    with open(after_path, "w", newline="", encoding="utf-8") as after_csv:
        writer = csv.writer(after_csv)
        writer.writerow(["Line_Number", "Content", "Is_BLOC", "BLOC_Number"])

        for i, line in enumerate(original_lines, 1):
            original_line = line.rstrip()
            stripped = line.strip()

            is_bloc = 0
            bloc_id = ""

            if stripped and stripped in remaining_bloc_lines:
                is_bloc = 1
                bloc_number += 1
                bloc_id = bloc_number

                # remove first matching occurrence only
                remaining_bloc_lines.remove(stripped)

            writer.writerow([i, original_line, is_bloc, bloc_id])

    total_bloc = compute_bloc(filepath)
    summary_data.append([filename, total_bloc])

    print(f"Processed: {filename} | Total BLOC = {total_bloc}")


# Main Function

def main():
    print("Starting BLOC Analysis...\n")

    if not os.path.exists(INPUT_FOLDER):
        print("ERROR: FilesExamples folder not found.")
        return

    summary_data = []

    for file in os.listdir(INPUT_FOLDER):
        if file.endswith((".gradle", ".xml", ".groovy")):
            process_file(os.path.join(INPUT_FOLDER, file), summary_data)

    summary_path = os.path.join(OUTPUT_FOLDER, "summary_metrics.csv")

    # If summary already exists, update/overwrite only BLOC column cleanly
    if os.path.exists(summary_path):
        with open(summary_path, "r", encoding="utf-8") as f:
            existing_rows = list(csv.reader(f))

        if existing_rows:
            header = existing_rows[0]
            rows = existing_rows[1:]

            if "BLOC" in header:
                bloc_index = header.index("BLOC")
            else:
                header.append("BLOC")
                bloc_index = len(header) - 1

            bloc_map = {fname: bloc for fname, bloc in summary_data}
            updated_rows = []

            for row in rows:
                if not row:
                    continue

                filename = row[0]

                if len(row) < len(header):
                    row.extend([""] * (len(header) - len(row)))

                if filename in bloc_map:
                    row[bloc_index] = str(bloc_map[filename])

                updated_rows.append(row)

            with open(summary_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(updated_rows)
        else:
            with open(summary_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(["File_Name", "BLOC"])
                writer.writerows(summary_data)
    else:
        with open(summary_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["File_Name", "BLOC"])
            writer.writerows(summary_data)

    print("\nBLOC Analysis Completed.")
    print("Check processed_builds folder for results.")


# Run Script

if __name__ == "__main__":
    main()