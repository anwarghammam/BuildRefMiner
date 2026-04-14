import os
import sys
import csv
import json
import argparse
import subprocess
import tempfile

# Stable Base Directory

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

OUTPUT_FOLDER = os.path.join(BASE_DIR, "..", "processed_builds")
SCC_BINARY = os.path.join(BASE_DIR, "..", "tools", "scc", "scc")

os.makedirs(OUTPUT_FOLDER, exist_ok=True)

def compute_bloc_with_scc(file_path: str) -> int | None:
    if not os.path.exists(SCC_BINARY):
        return None

    try:
        result = subprocess.run(
            [SCC_BINARY, "--by-file", "--format", "json", file_path],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout)
    except (subprocess.SubprocessError, json.JSONDecodeError, OSError):
        return None

    if not payload:
        return 0

    file_entries = payload[0].get("Files", [])
    if not file_entries:
        return int(payload[0].get("Code", 0))

    return int(file_entries[0].get("Code", 0))


def compute_bloc_from_content(filename: str, content: str) -> int:
    suffix = os.path.splitext(filename)[1] or ".txt"

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            suffix=suffix,
            delete=False,
        ) as temp_file:
            temp_file.write(content)
            temp_path = temp_file.name

        return compute_bloc(temp_path)
    finally:
        if "temp_path" in locals() and os.path.exists(temp_path):
            os.unlink(temp_path)


def update_summary(summary_data: list[list[str | int]]) -> None:
    summary_path = os.path.join(OUTPUT_FOLDER, "summary_metrics.csv")

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

            existing_filenames = {row[0] for row in updated_rows if row}
            for filename, bloc in summary_data:
                if filename not in existing_filenames:
                    new_row = [""] * len(header)
                    new_row[0] = filename
                    new_row[bloc_index] = str(bloc)
                    updated_rows.append(new_row)

            with open(summary_path, "w", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(header)
                writer.writerows(updated_rows)
            return

    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["File_Name", "BLOC"])
        writer.writerows(summary_data)



# Reusable BLOC computation for one file
# This is the function the before/after commit runner can call.

def compute_bloc(file_path: str) -> int:
    if not file_path or not os.path.exists(file_path):
        return 0

    scc_bloc = compute_bloc_with_scc(file_path)
    if scc_bloc is not None:
        return scc_bloc

    return 0

def process_content(filename: str, content: str, summary_data):
    total_bloc = compute_bloc_from_content(filename, content)
    summary_data.append([filename, total_bloc])
    print(f"Processed: {filename} | Total BLOC = {total_bloc}")


def process_file(filepath, summary_data):
    filename = os.path.basename(filepath)
    total_bloc = compute_bloc(filepath)
    summary_data.append([filename, total_bloc])
    print(f"Processed: {filename} | Total BLOC = {total_bloc}")


# Main Function

def main():
    print("Starting BLOC Analysis...\n")
    parser = argparse.ArgumentParser(
        description="Compute BLOC for build files and store results in summary_metrics.csv."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="File paths to analyze.",
    )
    parser.add_argument(
        "--name",
        help="Logical file name to use when reading file content from stdin.",
    )
    args = parser.parse_args()

    summary_data = []

    if args.paths:
        for path in args.paths:
            if path.endswith((".gradle", ".gradle.kts", ".xml", ".groovy")):
                process_file(path, summary_data)
    elif not sys.stdin.isatty():
        if not args.name:
            print("ERROR: --name is required when providing file content via stdin.")
            return
        process_content(args.name, sys.stdin.read(), summary_data)
    else:
        print("ERROR: Provide file paths or pipe file content through stdin with --name.")
        return

    update_summary(summary_data)

    print("\nBLOC Analysis Completed.")
    print("Check processed_builds folder for results.")


# Run Script

if __name__ == "__main__":
    main()
