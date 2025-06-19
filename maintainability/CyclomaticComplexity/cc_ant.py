import xml.etree.ElementTree as ET

def calculate_ant_cc(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()

    cc = 1  # Base complexity

    # 1. Target-level conditionals
    for target in root.findall('target'):
        if 'if' in target.attrib:
            cc += 1
        if 'unless' in target.attrib:
            cc += 1

    # 2. Common conditional constructs
    conditionals = [
        './/condition',
        './/available',
        './/uptodate',
        './/isset',
        './/not',
        './/and',
        './/or',
        './/equals',
        './/contains',
        './/matches'
    ]

    for cond in conditionals:
        cc += len(root.findall(cond))

    # 3. Fail conditions (with branching effect)
    for fail in root.findall('.//fail'):
        if 'if' in fail.attrib or 'unless' in fail.attrib:
            cc += 1

    return cc


cc_score = calculate_ant_cc("../../FilesExamples/build.xml")
print(f"Ant Cyclomatic Complexity: {cc_score}")