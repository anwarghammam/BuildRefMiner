import os
import csv
import re
from collections import defaultdict

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(BASE_DIR, "..", "FilesExamples")
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "processed_builds", "summary_metrics.csv")

# Minimum clone block size
MIN_CLONE_LEN = 5


# Remove comments (XML + Groovy/Gradle)
def remove_comments(text: str) -> str:
    # XML comments <!-- ... -->
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # Groovy/Gradle block comments /* ... */
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    # Single-line comments //
    text = re.sub(r"//.*", "", text)

    # Optional: lines starting with #
    text = re.sub(r"^\s*#.*$", "", text, flags=re.MULTILINE)

    return text


# Normalize lines
# - trim whitespace
# - remove empty lines
# - compress multiple spaces
def normalize_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"\s+", " ", line)
        lines.append(line)
    return lines


# Detect cloned lines within a file (Type-I)
# A line is cloned if it belongs to any k-line window repeated >= 2 times.
def detect_cloned_lines(lines: list[str], k: int) -> int:
    n = len(lines)
    if n < k:
        return 0

    windows = defaultdict(list)

    for i in range(n - k + 1):
        window = tuple(lines[i:i + k])
        windows[window].append(i)

    cloned = set()
    for starts in windows.values():
        if len(starts) >= 2:
            for s in starts:
                for idx in range(s, s + k):
                    cloned.add(idx)

    return len(cloned)


# Compute Clone Density for one file
# Clone Density = cloned_lines / total_logic_lines
def compute_clone_density(file_path: str) -> float:
    if not file_path or not os.path.exists(file_path):
        return 0.0

    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = remove_comments(content)
    lines = normalize_lines(content)

    if not lines:
        return 0.0

    cloned_lines = detect_cloned_lines(lines, MIN_CLONE_LEN)
    total_logic_lines = len(lines)

    return round(cloned_lines / total_logic_lines, 3)


# Integrate into summary_metrics.csv
def integrate_clone_density() -> None:
    print("\n=== Running Clone Density Metric ===")

    if not os.path.exists(SUMMARY_FILE):
        print(f"ERROR: summary_metrics.csv not found at: {SUMMARY_FILE}")
        print("Run BLOC first to create the summary file.")
        return

    if not os.path.exists(FILES_DIR):
        print(f"ERROR: FilesExamples folder not found at: {FILES_DIR}")
        return

    with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    if not rows:
        print("ERROR: summary_metrics.csv is empty.")
        return

    old_header = rows[0]
    old_body = rows[1:]

    keep_col_indices = []
    new_header = []
    for idx, col in enumerate(old_header):
        if re.search(r"clone", col, flags=re.IGNORECASE):
            continue
        keep_col_indices.append(idx)
        new_header.append(col)

    new_header.append("Clone_Density")

    updated_rows = []

    for row in old_body:
        if not row:
            continue

        cleaned = []
        for idx in keep_col_indices:
            cleaned.append(row[idx] if idx < len(row) else "")

        filename = os.path.basename(cleaned[0]) if cleaned else ""
        file_path = os.path.join(FILES_DIR, filename)

        if filename and os.path.exists(file_path):
            cd = compute_clone_density(file_path)
        else:
            cd = 0.0

        cleaned.append(str(cd))
        updated_rows.append(cleaned)

        print(f"{filename} -> Clone Density = {cd}")

    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(new_header)
        w.writerows(updated_rows)

    print("\n✅ Clone Density added as a single column: Clone_Density")
    print(f"Updated file: {SUMMARY_FILE}")


if __name__ == "__main__":
    integrate_clone_density()