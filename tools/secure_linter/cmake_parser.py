import re
def parse_cmake(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    if "cmake_minimum_required" not in content.lower():
        print("Warning: 'cmake_minimum_required' not found; proceeding to parse as CMake file.")

    find_pkg_pattern = re.compile(
r"""find_package\(
            \s*([A-Za-z0-9_]+)            # 1 package
            (?:\s+([^\s\)]+))?            # 2 optional version
            (?:(?:\s+REQUIRED)|\s*)       #   “REQUIRED” is *not* captured
        """,
        re.IGNORECASE | re.VERBOSE,
    )
    packages = []
    for match in find_pkg_pattern.finditer(content):
        pkg = match.group(1)
        version = match.group(2) or ""
        required  = "REQUIRED" in match.group(0).upper()
        packages.append({
            "package": pkg,
            "version": version.strip(),
            "required": required
        })

    target_pattern = re.compile(
        r"(add_executable|add_library)\s*\(\s*([A-Za-z0-9_]+)",
        re.IGNORECASE
    )
    targets = [match.group(2) for match in target_pattern.finditer(content)]

    return {
        "packages": packages,
        "targets": targets,
        "raw_content": content
    }
