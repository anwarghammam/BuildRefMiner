import os
import csv
import re
import shlex
import shutil
import subprocess
import tempfile
from collections import defaultdict

from BLOC import compute_bloc

# Paths
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILES_DIR = os.path.join(BASE_DIR, "..", "FilesExamples")
SUMMARY_FILE = os.path.join(BASE_DIR, "..", "results", "summary_metrics.csv")
TOOLS_DIR = os.path.join(BASE_DIR, "..", "tools")

# Fallback heuristic settings
MIN_CLONE_LEN = 5

# PMD CPD setting
DEFAULT_MIN_TOKENS = 20


def env_command(env_var):
    value = os.environ.get(env_var)
    if value:
        return shlex.split(value)
    return None


def binary_command(env_var, local_candidates):
    binary = os.environ.get(env_var)
    if binary:
        return [binary]

    for candidate in local_candidates:
        if os.path.exists(candidate) and os.access(candidate, os.X_OK):
            return [candidate]

    return None


def resolve_pmd_command():
    return (
        env_command("PMD_CMD")
        or binary_command(
            "PMD_BINARY",
            [
                os.path.join(TOOLS_DIR, "pmd", "bin", "pmd"),
                os.path.join(TOOLS_DIR, "pmd", "pmd"),
            ],
        )
        or ([shutil.which("pmd")] if shutil.which("pmd") else None)
    )


def detect_cpd_language(file_path: str) -> str | None:
    name = os.path.basename(file_path).lower()
    if name.endswith(".gradle") or name.endswith(".groovy"):
        return "groovy"
    if name.endswith(".gradle.kts"):
        return "kotlin"
    if name in ("build.xml", "pom.xml") or name.endswith(".xml"):
        return "xml"
    return None


def cpd_input_suffix(file_path: str) -> str:
    name = os.path.basename(file_path).lower()
    if name.endswith(".gradle") or name.endswith(".groovy"):
        return ".groovy"
    if name.endswith(".gradle.kts"):
        return ".kt"
    return os.path.splitext(file_path)[1] or ".txt"


def preprocess_for_cpd(file_path: str, content: str) -> str:
    name = os.path.basename(file_path).lower()

    if name.endswith((".gradle", ".groovy")):
        # PMD's Groovy CPD lexer is sensitive to some Gradle/Groovy interpolation
        # forms in sample build scripts. Normalize them while preserving the
        # overall duplicated structure for token-based clone detection.
        content = re.sub(r"/\*.*?\*/", "", content, flags=re.DOTALL)
        content = re.sub(r"//.*", "", content)
        content = re.sub(r"\$\{[^}]+\}", "INTERP", content)
        content = re.sub(r"\$[A-Za-z_][A-Za-z0-9_]*", "INTERP", content)

    return content


def parse_cpd_csv(output: str) -> dict[str, set[int]]:
    cloned_lines_by_file: dict[str, set[int]] = defaultdict(set)
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    if len(lines) <= 1:
        return cloned_lines_by_file

    reader = csv.reader(lines)
    header = next(reader, None)
    if not header:
        return cloned_lines_by_file

    for row in reader:
        if len(row) < 5:
            continue

        try:
            duplicated_lines = int(row[0])
            occurrences = int(row[2])
        except ValueError:
            continue

        expected_fields = 3 + (2 * occurrences)
        if len(row) < expected_fields:
            continue

        for idx in range(3, expected_fields, 2):
            try:
                start_line = int(row[idx])
            except ValueError:
                continue

            file_path = os.path.abspath(row[idx + 1])
            end_line = start_line + duplicated_lines - 1
            cloned_lines_by_file[file_path].update(range(start_line, end_line + 1))

    return cloned_lines_by_file


def compute_clone_density_with_pmd(file_path: str, min_tokens: int = DEFAULT_MIN_TOKENS) -> float | None:
    pmd_cmd = resolve_pmd_command()
    language = detect_cpd_language(file_path)
    if not pmd_cmd or not language:
        return None

    temp_path = None
    cpd_target = file_path

    try:
        # PMD CPD recognizes standard Groovy/Kotlin extensions, so Gradle files
        # are analyzed through temporary copies with equivalent language suffixes.
        if os.path.basename(file_path).lower().endswith((".gradle", ".gradle.kts")):
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                content = preprocess_for_cpd(file_path, f.read())

            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                suffix=cpd_input_suffix(file_path),
                delete=False,
            ) as temp_file:
                temp_file.write(content)
                temp_path = temp_file.name
                cpd_target = temp_path

        result = subprocess.run(
            [
                *pmd_cmd,
                "cpd",
                "--minimum-tokens",
                str(min_tokens),
                "--language",
                language,
                "--format",
                "csv",
                "--no-fail-on-violation",
                "--no-fail-on-error",
                "--encoding",
                "UTF-8",
                cpd_target,
            ],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode not in (0, 4, 5):
            stderr_text = (result.stderr or "").strip()
            stdout_text = (result.stdout or "").strip()
            combined_output = stderr_text or stdout_text

            if "GroovySyntaxError" in combined_output or "Unexpected character" in combined_output:
                print(
                    f"[WARN] PMD CPD could not parse {file_path}; "
                    "falling back to heuristic clone detection."
                )
            elif combined_output:
                first_line = combined_output.splitlines()[0]
                print(f"[WARN] PMD CPD failed for {file_path}: {first_line}")
            else:
                print(f"[WARN] PMD CPD failed for {file_path}; falling back to heuristic clone detection.")
            return None

        cloned_lines_by_file = parse_cpd_csv(result.stdout)
        target_path = os.path.abspath(cpd_target)
        cloned_lines = len(cloned_lines_by_file.get(target_path, set()))

        total_logic_lines = compute_bloc(file_path)
        if total_logic_lines <= 0:
            return 0.0

        return round(cloned_lines / total_logic_lines, 3)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


# Fallback heuristic: intra-file Type-I clones using repeated line windows.
def remove_comments(text: str) -> str:
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    text = re.sub(r"//.*", "", text)
    text = re.sub(r"^\s*#.*$", "", text, flags=re.MULTILINE)
    return text


def normalize_lines(text: str) -> list[str]:
    lines = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        line = re.sub(r"\s+", " ", line)
        lines.append(line)
    return lines


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


def compute_clone_density_fallback(file_path: str) -> float:
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


def compute_clone_density(file_path: str) -> float:
    if not file_path or not os.path.exists(file_path):
        return 0.0

    pmd_density = compute_clone_density_with_pmd(file_path)
    if pmd_density is not None:
        return pmd_density

    return compute_clone_density_fallback(file_path)


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
        writer = csv.writer(f)
        writer.writerow(new_header)
        writer.writerows(updated_rows)

    print("\n✅ Clone Density added as a single column: Clone_Density")
    print(f"Updated file: {SUMMARY_FILE}")


if __name__ == "__main__":
    integrate_clone_density()
