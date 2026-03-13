import os
import re
from typing import Dict, List, Any


class SnifferAdapter:
    """
    Sniffer-inspired smell detector for Maven, Gradle/Groovy, and Ant build files.
    Designed for integration into the before/after metrics pipeline.
    """

    def detect_smells(self, file_path: str, build_type: str) -> Dict[str, Any]:
        if not file_path or not os.path.exists(file_path):
            return self._empty_result()

        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        build_type = (build_type or "").lower().strip()
        smells: List[Dict[str, str]] = []

        smells.extend(self._detect_common_smells(content))

        if build_type == "maven":
            smells.extend(self._detect_maven_smells(content))
        elif build_type == "gradle":
            smells.extend(self._detect_gradle_smells(content))
        elif build_type == "ant":
            smells.extend(self._detect_ant_smells(content))

        return self._format_result(file_path, smells)

    def empty_result(self) -> Dict[str, Any]:
        return self._empty_result()

    def _detect_common_smells(self, content: str) -> List[Dict[str, str]]:
        smells = []

        # Insecure URLs
        for match in re.finditer(r"http://[^\s\"'<]+", content, flags=re.IGNORECASE):
            smells.append({
                "smell_id": "INSECURE_URL",
                "issue": f"Insecure URL found: {match.group(0)}",
                "severity": "HIGH"
            })

        # Hardcoded paths
        path_patterns = [
            r"[A-Za-z]:\\[^\s\"']+",
            r"/Users/[^\s\"']+",
            r"/home/[^\s\"']+",
            r"/tmp/[^\s\"']+",
            r"/var/[^\s\"']+"
        ]
        for pattern in path_patterns:
            for match in re.finditer(pattern, content):
                smells.append({
                    "smell_id": "HARDCODED_PATH",
                    "issue": f"Hardcoded path found: {match.group(0)}",
                    "severity": "MEDIUM"
                })

        # Suspicious comments
        for match in re.finditer(r"(TODO|FIXME|HACK|XXX)\b.*", content, flags=re.IGNORECASE):
            smells.append({
                "smell_id": "SUSPICIOUS_COMMENT",
                "issue": match.group(0).strip(),
                "severity": "LOW"
            })

        # Hardcoded credentials
        credential_patterns = [
            r"password\s*[:=]\s*[\"'][^\"']+[\"']",
            r"passwd\s*[:=]\s*[\"'][^\"']+[\"']",
            r"token\s*[:=]\s*[\"'][^\"']+[\"']",
            r"secret\s*[:=]\s*[\"'][^\"']+[\"']",
            r"username\s*[:=]\s*[\"'][^\"']+[\"']"
        ]
        for pattern in credential_patterns:
            for match in re.finditer(pattern, content, flags=re.IGNORECASE):
                smells.append({
                    "smell_id": "HARDCODED_CREDENTIAL",
                    "issue": f"Possible hardcoded credential: {match.group(0)}",
                    "severity": "HIGH"
                })

        # Duplicate non-empty lines heuristic
        lines = [line.strip() for line in content.splitlines() if line.strip()]
        seen = set()
        duplicates = set()

        for line in lines:
            if line in seen and len(line) > 10:
                duplicates.add(line)
            seen.add(line)

        for dup in duplicates:
            smells.append({
                "smell_id": "DUPLICATE_DECLARATION",
                "issue": f"Duplicate declaration found: {dup[:120]}",
                "severity": "MEDIUM"
            })

        return smells

    def _detect_maven_smells(self, content: str) -> List[Dict[str, str]]:
        smells = []

        dependency_blocks = re.findall(r"<dependency>(.*?)</dependency>", content, flags=re.DOTALL)
        for dep in dependency_blocks:
            if "<version>" not in dep:
                smells.append({
                    "smell_id": "MISSING_DEPENDENCY_VERSION",
                    "issue": "Maven dependency without explicit version",
                    "severity": "MEDIUM"
                })

        for match in re.finditer(r"<version>\s*[\*\+].*?</version>", content, flags=re.DOTALL):
            smells.append({
                "smell_id": "WILDCARD_VERSION",
                "issue": f"Wildcard version used: {match.group(0)}",
                "severity": "MEDIUM"
            })

        for match in re.finditer(r"<([A-Za-z0-9_\-]+)>\s*</\1>", content):
            smells.append({
                "smell_id": "EMPTY_TAG",
                "issue": f"Empty XML tag found: {match.group(0)}",
                "severity": "LOW"
            })

        if re.search(r"<onError>\s*continue\s*</onError>", content, flags=re.IGNORECASE):
            smells.append({
                "smell_id": "LACK_ERROR_HANDLING",
                "issue": "Maven build continues on error",
                "severity": "HIGH"
            })

        return smells

    def _detect_gradle_smells(self, content: str) -> List[Dict[str, str]]:
        smells = []

        # -----------------------------
        # 1. Gradle dependency smells
        # -----------------------------
        dep_patterns_missing_version = [
            r"(implementation|api|compileOnly|runtimeOnly|testImplementation)\s+[\"'][^:\"']+:[^:\"']+[\"']",
            r"(implementation|api|compileOnly|runtimeOnly|testImplementation)\([\"'][^:\"']+:[^:\"']+[\"']\)"
        ]
        for pattern in dep_patterns_missing_version:
            for match in re.finditer(pattern, content):
                smells.append({
                    "smell_id": "MISSING_DEPENDENCY_VERSION",
                    "issue": f"Gradle dependency may be missing version: {match.group(0)}",
                    "severity": "MEDIUM"
                })

        for match in re.finditer(r"[\"'][^\"']+:[^\"']+:[\*\+][^\"']*[\"']", content):
            smells.append({
                "smell_id": "WILDCARD_VERSION",
                "issue": f"Wildcard dependency version found: {match.group(0)}",
                "severity": "MEDIUM"
            })

        if re.search(r"\bexec\b", content):
            smells.append({
                "smell_id": "COMPLEX_BUILD_LOGIC",
                "issue": "Use of exec detected in Gradle/Groovy script",
                "severity": "MEDIUM"
            })

        # -----------------------------
        # 2. Groovy / CodeNarc-like smells
        # -----------------------------

        # Long lines
        for i, line in enumerate(content.splitlines(), start=1):
            if len(line) > 120:
                smells.append({
                    "smell_id": "LONG_LINE",
                    "issue": f"Line {i} exceeds 120 characters",
                    "severity": "LOW"
                })

        # Bad class names: class bad_class_name
        for match in re.finditer(r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)", content):
            class_name = match.group(1)
            if "_" in class_name or class_name.islower():
                smells.append({
                    "smell_id": "BAD_CLASS_NAME",
                    "issue": f"Non-conventional class name: {class_name}",
                    "severity": "LOW"
                })

        # Bad method names: def ExampleName() or names with uppercase first char
        for match in re.finditer(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(", content):
            method_name = match.group(1)
            if method_name and method_name[0].isupper():
                smells.append({
                    "smell_id": "BAD_METHOD_NAME",
                    "issue": f"Non-conventional method name: {method_name}",
                    "severity": "LOW"
                })

        # Very long variable names
        for match in re.finditer(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*=", content):
            var_name = match.group(1)
            if len(var_name) > 25:
                smells.append({
                    "smell_id": "LONG_VARIABLE_NAME",
                    "issue": f"Very long variable name: {var_name}",
                    "severity": "LOW"
                })

        # Uppercase field names that look like constants but are mutable fields
        for match in re.finditer(r"\bString\s+([A-Z_]{3,})\s*=", content):
            field_name = match.group(1)
            smells.append({
                "smell_id": "BAD_FIELD_NAME",
                "issue": f"Possible non-conventional field name: {field_name}",
                "severity": "LOW"
            })

        # Too many method parameters
        for match in re.finditer(r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)\s*\(([^)]*)\)", content):
            method_name = match.group(1)
            params = [p.strip() for p in match.group(2).split(",") if p.strip()]
            if len(params) > 5:
                smells.append({
                    "smell_id": "TOO_MANY_PARAMETERS",
                    "issue": f"Method {method_name} has too many parameters: {len(params)}",
                    "severity": "MEDIUM"
                })

        # Large each/range loops e.g. (1..60).each
        for match in re.finditer(r"\((\d+)\s*\.\.\s*(\d+)\)\.each", content):
            start = int(match.group(1))
            end = int(match.group(2))
            if (end - start + 1) > 50:
                smells.append({
                    "smell_id": "LARGE_LOOP",
                    "issue": f"Large loop detected: ({start}..{end}).each",
                    "severity": "LOW"
                })

        # Switch + if in same method/file as a rough complexity indicator
        control_count = 0
        control_count += len(re.findall(r"\bif\s*\(", content))
        control_count += len(re.findall(r"\bswitch\s*\(", content))
        control_count += len(re.findall(r"\bcase\s+", content))
        if control_count >= 4:
            smells.append({
                "smell_id": "COMPLEX_BUILD_LOGIC",
                "issue": f"High control-flow complexity detected ({control_count} control constructs)",
                "severity": "MEDIUM"
            })

        # Duplicate closure/task block heuristic: normalize closure bodies
        closure_blocks = re.findall(r"def\s+\w+\s*=\s*\{(.*?)\}", content, flags=re.DOTALL)
        normalized_blocks = []
        for block in closure_blocks:
            normalized = re.sub(r"\s+", " ", block.strip())
            normalized_blocks.append(normalized)

        seen_blocks = set()
        for block in normalized_blocks:
            if len(block) > 20:
                if block in seen_blocks:
                    smells.append({
                        "smell_id": "DUPLICATE_LOGIC_BLOCK",
                        "issue": "Duplicate closure/task logic block detected",
                        "severity": "MEDIUM"
                    })
                    break
                seen_blocks.add(block)

        return smells

    def _detect_ant_smells(self, content: str) -> List[Dict[str, str]]:
        smells = []

        for match in re.finditer(r'<target\s+[^>]*depends="([^"]+)"', content):
            deps = [x.strip() for x in match.group(1).split(",") if x.strip()]
            if len(deps) >= 4:
                smells.append({
                    "smell_id": "EXCESSIVE_TARGET_DEPENDENCIES",
                    "issue": f"Ant target has many dependencies: {len(deps)}",
                    "severity": "MEDIUM"
                })

        if re.search(r"<exec\b", content):
            smells.append({
                "smell_id": "EXEC_USAGE",
                "issue": "Ant exec task found",
                "severity": "MEDIUM"
            })

        if re.search(r'failonerror\s*=\s*["\']false["\']', content, flags=re.IGNORECASE):
            smells.append({
                "smell_id": "LACK_ERROR_HANDLING",
                "issue": "Ant task has failonerror='false'",
                "severity": "HIGH"
            })

        targets = re.findall(r'<target\s+name="([^"]+)"', content)
        seen = set()
        for target in targets:
            if target in seen:
                smells.append({
                    "smell_id": "DUPLICATE_TARGET",
                    "issue": f"Duplicate Ant target found: {target}",
                    "severity": "MEDIUM"
                })
            seen.add(target)

        return smells

    def _format_result(self, file_path: str, smells: List[Dict[str, str]]) -> Dict[str, Any]:
        loc = self._count_loc(file_path)
        smell_count = len(smells)
        smell_density = round((smell_count / max(loc, 1)) * 1000, 4)
        smell_summary = ";".join(sorted(set(s["smell_id"] for s in smells))) if smells else ""

        return {
            "smells": smells,
            "smell_count": smell_count,
            "smell_density": smell_density,
            "smell_summary": smell_summary
        }

    def _count_loc(self, file_path: str) -> int:
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
            return sum(1 for line in f if line.strip())

    def _empty_result(self) -> Dict[str, Any]:
        return {
            "smells": [],
            "smell_count": 0,
            "smell_density": 0.0,
            "smell_summary": ""
        }