import csv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
RELIABILITY_CSV = os.path.join(BASE_DIR, "..", "results", "reliability_metrics.csv")


def reliability_row_from_summary(row: dict) -> dict:
    return {
        "Commit_SHA": row.get("Commit_SHA", ""),
        "Parent_SHA": row.get("Parent_SHA", ""),
        "File_Path": row.get("File_Path", ""),
        "File_Name": row.get("File_Name", ""),
        "Tool": row.get("Tool", ""),
        "Status": row.get("Status", ""),
        "RE_Before": row.get("RE_Before", 0.0),
        "RE_After": row.get("RE_After", 0.0),
        "DSS_Before": row.get("DSS_Before", 0.0),
        "DSS_After": row.get("DSS_After", 0.0),
        "EDR_Before": row.get("EDR_Before", 0.0),
        "EDR_After": row.get("EDR_After", 0.0),
    }


def write_reliability_summary(
    rows: list[dict],
    output_path: str | None = None,
    append: bool = True,
) -> None:
    header = [
        "Commit_SHA",
        "Parent_SHA",
        "File_Path",
        "File_Name",
        "Tool",
        "Status",
        "RE_Before",
        "RE_After",
        "DSS_Before",
        "DSS_After",
        "EDR_Before",
        "EDR_After",
    ]

    reliability_rows = [reliability_row_from_summary(row) for row in rows]
    target_path = output_path or RELIABILITY_CSV
    os.makedirs(os.path.dirname(target_path), exist_ok=True)

    file_exists = os.path.exists(target_path)
    write_header = True
    mode = "a" if append else "w"

    if append and file_exists and os.path.getsize(target_path) > 0:
        with open(target_path, "r", encoding="utf-8", newline="") as existing:
            first_line = existing.readline().strip()
        expected_header = ",".join(header)
        if first_line == expected_header:
            write_header = False
        else:
            print(f"[WARN] Rewriting {target_path} to match updated reliability columns.")
            mode = "w"

    with open(target_path, mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)

        if write_header:
            writer.writeheader()

        writer.writerows(reliability_rows)

    print(f"Reliability results appended to: {target_path}")
