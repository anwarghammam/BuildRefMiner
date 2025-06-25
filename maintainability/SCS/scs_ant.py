import re
import xml.etree.ElementTree as ET
import os

# === R1: Indentation ===

def check_indentation(lines):
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
                    # Invalid initial indentation (not 2 or 4)
                    violations += 1

    return violations


# === R2: Line Length ===

def check_line_length(lines):
    violations=0
    for line in lines:
        if len(line.strip()) > 80:
            violations+= 1
    return violations

# === R3: check_tag_and_attribute_casing ===
def check_tag_and_attribute_casing(root: ET.Element) -> int:
    violations= 0
    for elem in root.iter():
        if elem.tag != elem.tag.lower():
            violations += 1
    
        for attr in elem.attrib:
            if attr != attr.lower():
                violations += 1
    return violations


def check_target_name_convention(root: ET.Element) -> int:
    violations= 0
    for target in root.findall(".//target"):
        name = target.attrib.get("name", "")
        if not re.match(r'^[a-z0-9\-]+$', name):
            violations += 1
       
    return violations


def run_checks(file_path: str):
    violations=0
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        raw_text = ''.join(lines)
        tree = ET.parse(file_path)
        root = tree.getroot()
    except Exception as e:
        return {"error": str(e)}

    results = {
        "Indentation": check_indentation(lines),
        "LineLength": check_line_length(lines),
        "TagAndAttributeCasing": check_tag_and_attribute_casing(root),
        "TargetNameConvention": check_target_name_convention(root)
    }
    return results, violations

# Scan directory for build.xml files and run checks
def run_checks_in_directory(base_dir="../../FilesExamples"):
    results = []
    violations=[]
    for root_dir, _, files in os.walk(base_dir):
        for file in files:
            if file == "build.xml":
                file_path = os.path.join(root_dir, file)
                result,violation = run_checks(file_path)
                results.append(result)
                violations.append(violation)
    return results

# Execute the checker across the directory
all_results = run_checks_in_directory()
print(all_results)