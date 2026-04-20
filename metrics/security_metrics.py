import csv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SECURITY_CSV = os.path.join(BASE_DIR, "..", "results", "security_metrics.csv")

TRACKED_SECURITY_METRICS = [
    "HARDCODED_CREDENTIALS",
    "INSECURE_URLS",
    "WILDCARD_USAGE",
    "HARDCODED_PATHS_AND_URLS",
    "DEPRECATED_DEPENDENCIES",
    "OUTDATED_DEPENDENCIES",
]


def _smell_flags(prefix: str, summary: str) -> dict:
    smell_ids = {item.strip() for item in (summary or "").split(";") if item.strip()}
    return {
        f"{prefix}_{smell_id}": 1 if smell_id in smell_ids else 0
        for smell_id in TRACKED_SECURITY_METRICS
    }


def security_row_from_summary(row: dict) -> dict:
    before_summary = row.get("Before_Security_Smell_Summary", "")
    after_summary = row.get("After_Security_Smell_Summary", "")

    return {
        "Commit_SHA": row.get("Commit_SHA", ""),
        "Parent_SHA": row.get("Parent_SHA", ""),
        "File_Path": row.get("File_Path", ""),
        "File_Name": row.get("File_Name", ""),
        "Tool": row.get("Tool", ""),
        "Status": row.get("Status", ""),
        "Before_Security_Smell_Count": row.get("Before_Security_Smell_Count", 0),
        "After_Security_Smell_Count": row.get("After_Security_Smell_Count", 0),
        "Before_Security_Smell_Density": row.get("Before_Security_Smell_Density", 0.0),
        "After_Security_Smell_Density": row.get("After_Security_Smell_Density", 0.0),
        "Before_Security_Smell_Summary": before_summary,
        "After_Security_Smell_Summary": after_summary,
        **_smell_flags("Before", before_summary),
        **_smell_flags("After", after_summary),
    }


def write_security_summary(
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
        "Before_Security_Smell_Count",
        "After_Security_Smell_Count",
        "Before_Security_Smell_Density",
        "After_Security_Smell_Density",
        "Before_Security_Smell_Summary",
        "After_Security_Smell_Summary",
    ]
    header.extend([f"Before_{smell_id}" for smell_id in TRACKED_SECURITY_METRICS])
    header.extend([f"After_{smell_id}" for smell_id in TRACKED_SECURITY_METRICS])

    security_rows = [security_row_from_summary(row) for row in rows]
    target_path = output_path or SECURITY_CSV
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
            print(f"[WARN] Rewriting {target_path} to match updated security columns.")
            mode = "w"

    with open(target_path, mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)

        if write_header:
            writer.writeheader()

        writer.writerows(security_rows)

    print(f"Security results appended to: {target_path}")
