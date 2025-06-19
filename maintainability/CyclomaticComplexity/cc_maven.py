import xml.etree.ElementTree as ET

def calculate_maven_cc(filepath):
    tree = ET.parse(filepath)
    root = tree.getroot()

    # Maven POM files use namespaces
    ns = {'mvn': 'http://maven.apache.org/POM/4.0.0'}

    cc = 1  # Base complexity

    # Count <profile> blocks
    cc += len(root.findall('.//mvn:profile', ns))

    # Count <activation> blocks (conditionals for profiles)
    cc += len(root.findall('.//mvn:activation', ns))

    # Count <execution> blocks (branching in plugin behavior)
    cc += len(root.findall('.//mvn:execution', ns))

    return cc

cc_score = calculate_maven_cc("../../FilesExamples/pom.xml")
print(f"Ant Cyclomatic Complexity: {cc_score}")