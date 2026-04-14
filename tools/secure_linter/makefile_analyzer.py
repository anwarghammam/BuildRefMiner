import subprocess
import re
import os
from subprocess import TimeoutExpired

class MakefileAnalysis:
    def __init__(self):
        self.variables = {}
        self.targets = {}
        self._file_path: str | None = None

def looks_like_makefile(path: str) -> bool:
    import re

    try:
        snippet = open(path, encoding='utf-8', errors='ignore').read(1024)
    except OSError:
        return False

    has_rule = bool(re.search(r'^\s*[A-Za-z0-9_.\-/]+:.*$', snippet, re.MULTILINE))
    has_cmd  = bool(re.search(r'^(?:\t| {4,})\S', snippet, re.MULTILINE))
    has_var  = bool(re.search(r'^[A-Za-z_][A-Za-z0-9_]*\s*=\s*[^=\n]', snippet, re.MULTILINE))
    has_inc  = bool(re.search(r'^\s*(?:include|\.include)\s+\S+', snippet, re.MULTILINE))
    return has_rule or has_cmd or has_var or has_inc


def try_run_make_print_data_base(makefile_path: str) -> str | None:
    cmd = [
        "make",
        "-pn",
        "_all",
        "--keep-going",
        "--no-builtin-rules",
        "-f", makefile_path
    ]
    try:
        result = subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10  # give up after 10s
        )
        return result.stdout
    except (subprocess.CalledProcessError, FileNotFoundError, TimeoutExpired):
        return None

def naive_parse_makefile(makefile_path: str) -> MakefileAnalysis:
    analysis = MakefileAnalysis()
    analysis._file_path = makefile_path
    if not os.path.isfile(makefile_path):
        return analysis

    with open(makefile_path, "r", encoding="utf-8", errors="ignore") as f:
        lines = f.readlines()

    current_target = None
    for raw_line in lines:
        line = raw_line.rstrip("\r\n")
        # variable assignment
        if '=' in line and not line.strip().startswith('#'):
            name, val = line.split('=', 1)
            name = name.strip()
            val = val.strip()
            if name and not name.startswith('.'):
                analysis.variables[name] = val
        # target definition
        elif re.match(r'^[A-Za-z0-9_.\-/]+:.*$', line):
            parts = line.split(':', 1)
            tgt = parts[0].strip()
            deps = parts[1].split('#',1)[0].strip().split() if parts[1].strip() else []
            analysis.targets[tgt] = {'deps': deps, 'commands': []}
            current_target = tgt
        # command line
        elif line.startswith('\t') or re.match(r'^[ ]{4,}', line):
            cmd = line.lstrip()
            if current_target:
                analysis.targets[current_target]['commands'].append(cmd)
        else:
            current_target = None

    return analysis

def parse_makefile_database(makefile_path: str) -> MakefileAnalysis:
    try:
        with open(makefile_path, encoding='utf-8', errors='ignore') as f:
            head = f.read(8192)
        if '$(shell' in head:
            # too expensive or side-effectful: use naive fallback
            return naive_parse_makefile(makefile_path)
    except Exception:
        pass


    output = try_run_make_print_data_base(makefile_path)

    if not output:
        return naive_parse_makefile(makefile_path)

    analysis = MakefileAnalysis()
    analysis._file_path = makefile_path
    in_vars = in_files = False
    current_target = None

    for line in output.splitlines():
        line = line.rstrip("\r\n")
        if line.startswith("# Variables:"):
            in_vars, in_files = True, False
            continue
        if line.startswith("# Files:"):
            in_vars, in_files = False, True
            continue

        if in_vars and '=' in line:
            name, val = line.split('=', 1)
            name = name.strip()
            val = val.strip()
            if name and not name.startswith('.'):
                analysis.variables[name] = val
        elif in_files:
            if re.match(r'^\S.*:', line):
                parts = line.split(':', 1)
                tgt = parts[0].strip()
                deps = parts[1].split('#',1)[0].strip().split() if parts[1].strip() else []
                analysis.targets[tgt] = {'deps': deps, 'commands': []}
                current_target = tgt
            elif line.startswith('\t') or re.match(r'^[ ]{4,}', line):
                cmd = line.lstrip()
                if current_target:
                    analysis.targets[current_target]['commands'].append(cmd)
            else:
                current_target = None

    return analysis
