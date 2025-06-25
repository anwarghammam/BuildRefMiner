import re
import xml.etree.ElementTree as ET
from typing import Tuple, List, Dict
import os
# === Maven Style Rule Functions ===

def check_indentation_maven(lines: List[str]) -> int:
    """Checks that indentation uses only spaces and is consistently 2 or 4."""
    violations = 0
    base_indent = None
    for line in lines:
        if line.strip():
            if '\t' in line:
                violations += 1
                continue
            match = re.match(r'^( +)', line)
            if match:
                spaces = len(match.group(1))
                if base_indent is None and spaces in (2, 4):
                    base_indent = spaces
                elif base_indent and spaces % base_indent != 0:
                    violations += 1
                elif base_indent is None and spaces not in (2, 4):
                    violations += 1
    return violations

def check_line_length_maven(lines: List[str], max_length: int = 120) -> int:
    """Checks for lines longer than the max allowed length."""
    return sum(1 for line in lines if len(line.strip()) > max_length)

def strip_namespace(tag):
    return tag.split('}', 1)[-1] if '}' in tag else tag

def check_tag_and_attribute_casing_maven(root: ET.Element) -> int:
    violations = 0
    for elem in root.iter():
        tag = strip_namespace(elem.tag)
        if tag != tag.lower():
            print("element violated", elem.tag)
            violations += 1

        for attr in elem.attrib:
            attr_name = strip_namespace(attr)
            if attr_name != attr_name.lower():
                print("attribute violated", elem.attrib)
                violations += 1
    return violations


def check_pom_naming_conventions(root: ET.Element) -> int:
    """Checks naming conventions for groupId, artifactId, and property names."""
    violations = 0

    for elem in root.iter():
        # Check groupId and artifactId for lowercase and valid format
        if elem.tag in ("groupId", "artifactId"):
            text = elem.text or ""
            if not re.match(r'^[a-z0-9\-\.]+$', text):
                violations += 1
            if elem.tag == "artifactId" and '.' in text:
                violations += 1  # artifactId should not contain dots

        # Check property names under <properties>
        if elem.tag == "properties":
            for child in elem:
                if not re.match(r'^[a-z0-9]+(\.[a-z0-9]+)*$', child.tag):
                    violations += 1

    return violations


def run_maven_checks(file_path: str):
    """Runs all Maven style checks on a given pom.xml file."""
    violations=0
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        tree = ET.parse(file_path)
        root = tree.getroot()
    except Exception as e:
        return {"File": file_path, "Error": str(e)}
   
    violations=check_indentation_maven(lines)+check_line_length_maven(lines)+check_tag_and_attribute_casing_maven(root)+check_pom_naming_conventions(root)
    result= {
        "File": file_path,
        "Indentation": check_indentation_maven(lines),
        "LineLength": check_line_length_maven(lines),
        "TagAndAttributeCasing": check_tag_and_attribute_casing_maven(root),
         "NamingConventions": check_pom_naming_conventions(root)
    }

    return result,violations
def run_checks_in_directory(base_dir="../../FilesExamples"):
    results = []
    violations=[]
    for root_dir, _, files in os.walk(base_dir):
        for file in files:
            if file == "pom.xml":
                file_path = os.path.join(root_dir, file)
                result,violation = run_maven_checks(file_path)
                results.append(result)
                violations.append(violation)
    return results,violations

# Execute the checker across the directory
all_results = run_checks_in_directory()
print(all_results)