import os
import csv
import re

# --------------------------------------------------
# Paths
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(BASE_DIR, "..", "FilesExamples")
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "processed_builds", "summary_metrics.csv")

MIN_CLONE_BLOCK = 3  # minimum repeated block size


# --------------------------------------------------
# Remove comments (XML + Gradle)
# --------------------------------------------------
def remove_comments(content):
    # Remove XML comments
    content = re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)
    # Remove Gradle single-line comments
    content = re.sub(r'//.*', '', content)
    return content


# --------------------------------------------------
# Normalize lines
# --------------------------------------------------
def normalize_lines(content):
    lines = []
    for line in content.splitlines():
        line = line.strip()
        if line:
            line = re.sub(r'\s+', ' ', line)
            lines.append(line)
    return lines


# --------------------------------------------------
# Detect duplicated blocks
# --------------------------------------------------
def detect_clones(lines):
    cloned_lines = set()
    total_lines = len(lines)

    for i in range(total_lines):
        for j in range(i + MIN_CLONE_BLOCK, total_lines):
            block1 = lines[i:i+MIN_CLONE_BLOCK]
            block2 = lines[j:j+MIN_CLONE_BLOCK]

            if block1 == block2 and len(block1) == MIN_CLONE_BLOCK:
                for k in range(MIN_CLONE_BLOCK):
                    cloned_lines.add(i+k)
                    cloned_lines.add(j+k)

    return len(cloned_lines)


# --------------------------------------------------
# Compute Clone Density for one file
# --------------------------------------------------
def compute_clone_density(file_path):
    with open(file_path, "r", encoding="utf-8") as f:
        content = f.read()

    content = remove_comments(content)
    lines = normalize_lines(content)

    if len(lines) == 0:
        return 0

    cloned = detect_clones(lines)
    bloc = len(lines)

    return round(cloned / bloc, 3)


# --------------------------------------------------
# Integrate into summary_metrics.csv
# --------------------------------------------------
def integrate_clone_density():
    if not os.path.exists(SUMMARY_FILE):
        print("summary_metrics.csv not found.")
        return

    with open(SUMMARY_FILE, "r", encoding="utf-8") as f:
        reader = list(csv.reader(f))

    header = reader[0]
    rows = reader[1:]

    if "Clone_Density" not in header:
        header.append("Clone_Density")

    updated_rows = []

    for row in rows:
        filename = os.path.basename(row[0])
        file_path = os.path.join(FILES_DIR, filename)

        if os.path.exists(file_path):
            cd = compute_clone_density(file_path)
        else:
            cd = 0

        row = row[:len(header)-1]
        row.append(cd)
        updated_rows.append(row)

        print(f"{filename} → Clone Density = {cd}")

    with open(SUMMARY_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(updated_rows)

    print("\nClone Density successfully added.")


if __name__ == "__main__":
    integrate_clone_density()
