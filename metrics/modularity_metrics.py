import csv
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODULARITY_CSV = os.path.join(BASE_DIR, "..", "results", "modularity_metrics.csv")


def modularity_row_from_summary(row: dict) -> dict:
    return {
        "Commit_SHA": row.get("Commit_SHA", ""),
        "Parent_SHA": row.get("Parent_SHA", ""),
        "File_Path": row.get("File_Path", ""),
        "File_Name": row.get("File_Name", ""),
        "Tool": row.get("Tool", ""),
        "Status": row.get("Status", ""),
        "CP_Internal_Before": row.get("CP_Internal_Before", 0),
        "CP_Internal_After": row.get("CP_Internal_After", 0),
        "CP_External_Before": row.get("CP_External_Before", 0),
        "CP_External_After": row.get("CP_External_After", 0),
        "NCP_Internal_Before": row.get("NCP_Internal_Before", 0.0),
        "NCP_Internal_After": row.get("NCP_Internal_After", 0.0),
        "NCP_External_Before": row.get("NCP_External_Before", 0.0),
        "NCP_External_After": row.get("NCP_External_After", 0.0),
        "Build_Cohesion_Before": row.get("Build_Cohesion_Before", 0.0),
        "Build_Cohesion_After": row.get("Build_Cohesion_After", 0.0),
        "Clone_Density_Before": row.get("Clone_Density_Before", 0.0),
        "Clone_Density_After": row.get("Clone_Density_After", 0.0),
    }


def write_modularity_summary(
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
        "CP_Internal_Before",
        "CP_Internal_After",
        "CP_External_Before",
        "CP_External_After",
        "NCP_Internal_Before",
        "NCP_Internal_After",
        "NCP_External_Before",
        "NCP_External_After",
        "Build_Cohesion_Before",
        "Build_Cohesion_After",
        "Clone_Density_Before",
        "Clone_Density_After",
    ]

    modularity_rows = [modularity_row_from_summary(row) for row in rows]
    target_path = output_path or MODULARITY_CSV
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
            print(f"[WARN] Rewriting {target_path} to match updated modularity columns.")
            mode = "w"

    with open(target_path, mode, newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)

        if write_header:
            writer.writeheader()

        writer.writerows(modularity_rows)

    print(f"Modularity results appended to: {target_path}")
