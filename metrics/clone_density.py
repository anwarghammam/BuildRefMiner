import os
import csv
import re
from collections import defaultdict

# --------------------------------------------------
# Paths
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(BASE_DIR, "..", "FilesExamples")
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "processed_builds", "summary_metrics.csv")

# Minimum clone block size (paper commonly uses 5)
MIN_CLONE_LEN = 5


# --------------------------------------------------
# Remove comments (XML + Groovy/Gradle)
# --------------------------------------------------
def remove_comments(text: str) -> str:
    # Remove XML comments <!-- ... -->
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # Remove block comments /* ... */
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)

    # Remove single-line comments //
    text = re.sub(r"//.*", "", text)

    return text


# --------------------------------------------------
# Normalize lines
# - trim whitespace
# - remove empty lines
# - compress multiple spaces
# --------------------------------------------------
def normalize_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"\s+", " ", line)
        lines.append(line)
    return lines


# --------------------------------------------------
# Detect cloned lines within a file
# --------------------------------------------------
def detect_cloned_lines(lines: list[str], k: int) -> int:
    n = len(lines)
    if n < k:
        return 0

    windows = defaultdict(list)

    # Build sliding windows
    for i in range(n - k + 1):
        window = tuple(lines[i:i + k])
        windows[window].append(i)

    cloned = set()

    # Any window appearing ≥2 times is a clone
    for starts in windows.values():
        if len(starts) >= 2:
            for s in starts:
                for idx in range(s, s + k):
                    cloned.add(idx)

    return len(cloned)


# --------------------------------------------------
# Compute Clone Density for one file
# --------------------------------------------------
def compute_clone_density(file_path: str) -> float:
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = remove_comments(content)
    lines = normalize_lines(content)

    if not lines:
        return 0.0

    cloned_lines = detect_cloned_lines(lines, MIN_CLONE_LEN)
    total_logic_lines = len(lines)

    return round(cloned_lines / total_logic_lines, 3)


# --------------------------------------------------
# Integrate into summary_metrics.csv
# --------------------------------------------------
def integrate_clone_density():
    if not os.path.exists(SUMMARY_FILE):
        print("summary_metrics.csv not found.")
        return

    with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
        rows = list(csv.reader(f))

    header = rows[0]
    body = rows[1:]

    if "Clone_Density" not in header:
        header.append("Clone_Density")

    updated_rows = []

    for row in body:
        filename = os.path.basename(row[0])
        file_path = os.path.join(FILES_DIR, filename)

        if os.path.exists(file_path):
            density = compute_clone_density(file_path)
        else:
            density = 0.0

        row = row[:len(header)-1]
        row.append(density)
        updated_rows.append(row)

        print(f"{filename} -> Clone Density = {density}")

    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(updated_rows)

    print("\nClone Density successfully added to summary_metrics.csv")


# --------------------------------------------------
if __name__ == "__main__":
    integrate_clone_density()