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

def strip_namespace(tag_or_attr: str) -> str:
    return tag_or_attr.split('}', 1)[-1] if '}' in tag_or_attr else tag_or_attr

def is_camel_case(s: str) -> bool:
    """
    Checks if a string is camelCase or dot-separated camelCase.
    Examples:
    - groupId         ✅
    - artifactId      ✅
    - java.version    ✅
    - Java_Version    ❌
    - GroupId         ❌
    """
    return bool(re.fullmatch(r"[a-z]+([A-Z][a-z0-9]*)*(\.[a-z]+([A-Z][a-z0-9]*)*)*", s))

def check_tag_and_attribute_casing_maven(root: ET.Element) -> int:
    violations = 0

    for elem in root.iter():
        tag = strip_namespace(elem.tag)
        if not is_camel_case(tag):
            print(f"❌ Tag casing violation: <{tag}>")
            violations += 1

        for attr in elem.attrib:
            attr_name = strip_namespace(attr)
            if not attr_name.islower():
                print(f"❌ Attribute casing violation: {attr_name}")
                violations += 1

    return violations


# def check_pom_naming_conventions(root: ET.Element) -> int:
#     """Checks naming conventions for groupId, artifactId, and property tags."""
#     violations = 0

#     for elem in root.iter():
#         tag = elem.tag.split("}", 1)[-1]  # Remove namespace
#         text = (elem.text or "").strip()

#         if tag == "groupId":
#             if not re.fullmatch(r'[a-z0-9\-\.]+', text):
#                 print(f"❌ Invalid groupId: {text}")
#                 violations += 1

#         if tag == "artifactId":
#             if not re.fullmatch(r'[a-z0-9\-]+', text):  # No dots allowed
#                 print(f"❌ Invalid artifactId: {text}")
#                 violations += 1

#         if tag == "properties":
#             for prop_elem in elem:
#                 prop_tag = prop_elem.tag.split("}", 1)[-1]
                
#                 if not re.fullmatch(r'[a-z0-9]+(\.[a-z0-9]+)*', prop_tag):
#                     print(f"❌ Invalid property name: <{prop_tag}>")
#                     violations += 1

#     return violations


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
   
    violations=check_indentation_maven(lines)+check_line_length_maven(lines)+check_tag_and_attribute_casing_maven(root)
    result= {
        "File": file_path,
        "Indentation": check_indentation_maven(lines),
        "LineLength": check_line_length_maven(lines),
        "TagAndAttributeCasing": check_tag_and_attribute_casing_maven(root),
        #  "NamingConventions": check_pom_naming_conventions(root)
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