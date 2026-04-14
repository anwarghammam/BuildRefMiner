import re
def parse_gradle(file_path):
    dependencies = []
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
        # Patterns for both no-version and pinned-version, with or without parentheses
        pattern_dep = re.compile(
            r"^\s*(api|implementation|compileOnly|runtimeOnly|compile|testImplementation"
                   r"|testCompile|androidTestImplementation|androidTestCompile)"     
                   r"\s*  # optional whitespace before ("
                   r"(?:\(\s*)?"
                   r"['\"]([^:'\"]+):([^:'\"]+)"  # group:artifact
                   r"(?::([^'\"]+))?"  # optional :version
                   r"['\"]\s*\)?",  # close optional )
               re.MULTILINE | re.VERBOSE
        )


    for match in pattern_dep.finditer(content):
        groups = match.groups()
        if len(groups) != 4:
            continue
        config_type, group_id, artifact_id, version = groups
        dependencies.append({
            'config': config_type.strip(),
            'group': group_id.strip(),
            'artifact': artifact_id.strip(),
            'version': (version or "").strip(),
        })

    pattern_map = re.compile(
        r"^\s*(api|implementation|compile|compileOnly|runtimeOnly|testImplementation"
               r"|testCompile|androidTestImplementation|androidTestCompile)"
        r"\s+group\s*:\s*['\"](.+?)['\"],\s*name\s*:\s*['\"](.+?)['\"],"
        r"\s*version\s*:\s*['\"](.+?)['\"]",
        re.MULTILINE
    )

    for match in pattern_map.finditer(content):
        config_type, group_id, artifact_id, version = match.groups()
        dependencies.append({
            'config': config_type,
            'group': group_id.strip(),
            'artifact': artifact_id.strip(),
            'version': version.strip()
        })

    repo_pattern = re.compile(r"maven\s*\{\s*url\s+['\"](.+?)['\"]", re.MULTILINE)
    repositories = repo_pattern.findall(content)

    data = {
        'dependencies': dependencies,
        'repositories': repositories,
        'raw_content': content
    }
    return data
