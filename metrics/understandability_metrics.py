import csv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UNDERSTANDABILITY_CSV = os.path.join(BASE_DIR, "..", "results", "understandability_metrics.csv")


def understandability_row_from_summary(row: dict) -> dict:
    return {
        "Commit_SHA": row.get("Commit_SHA", ""),
        "Parent_SHA": row.get("Parent_SHA", ""),
        "File_Path": row.get("File_Path", ""),
        "File_Name": row.get("File_Name", ""),
        "Tool": row.get("Tool", ""),
        "Status": row.get("Status", ""),
        "Normalized_CC_Before": row.get("Normalized_CC_Before", 0.0),
        "Normalized_CC_After": row.get("Normalized_CC_After", 0.0),
        "Normalized_HV_Before": row.get("Normalized_HV_Before", 0.0),
        "Normalized_HV_After": row.get("Normalized_HV_After", 0.0),
        "Comment_Ratio_Before": row.get("Comment_Ratio_Before", 0.0),
        "Comment_Ratio_After": row.get("Comment_Ratio_After", 0.0),
        "Comment_Readability_Before": row.get("Comment_Readability_Before", 0.0),
        "Comment_Readability_After": row.get("Comment_Readability_After", 0.0),
        "Style_Conformance_Score_Before": row.get("Style_Conformance_Score_Before", 0.0),
        "Style_Conformance_Score_After": row.get("Style_Conformance_Score_After", 0.0),
        "Clone_Density_Before": row.get("Clone_Density_Before", 0.0),
        "Clone_Density_After": row.get("Clone_Density_After", 0.0),
    }


def write_understandability_summary(
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
        "Normalized_CC_Before",
        "Normalized_CC_After",
        "Normalized_HV_Before",
        "Normalized_HV_After",
        "Comment_Ratio_Before",
        "Comment_Ratio_After",
        "Comment_Readability_Before",
        "Comment_Readability_After",
        "Style_Conformance_Score_Before",
        "Style_Conformance_Score_After",
        "Clone_Density_Before",
        "Clone_Density_After",
    ]

    understandability_rows = [understandability_row_from_summary(row) for row in rows]
    target_path = output_path or UNDERSTANDABILITY_CSV
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
            print(
                f"[WARN] Rewriting {target_path} to match updated understandability columns."
            )
            mode = "w"

    with open(target_path, mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)

        if write_header:
            writer.writeheader()

        writer.writerows(understandability_rows)

    print(f"Understandability results appended to: {target_path}")
