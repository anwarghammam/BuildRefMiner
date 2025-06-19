import os
import re

def is_effective_line(line, file_type):
    line = line.strip()
    if not line:
        return False  # Skip blank lines
    if file_type == 'gradle':
        return not line.startswith('//')  # Skip single-line comments
    elif file_type == 'xml':
        return not (line.startswith('<!--') and line.endswith('-->'))  # Skip full-line XML comments
    return True

def count_effective_lines_in_file(filepath):
    _, ext = os.path.splitext(filepath)
    file_type = None
    if ext == '.gradle' or ext == '.groovy':
        file_type = 'gradle'
    elif ext == '.xml':
        file_type = 'xml'
    else:
        return 0

    effective_lines = 0
    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if is_effective_line(line, file_type):
                effective_lines += 1
    return effective_lines

def count_lines_in_directory(root_dir):
    totals = {'gradle': 0, 'xml': 0}
    for subdir, _, files in os.walk(root_dir):
        for file in files:
            print(file)
            filepath = os.path.join(subdir, file)
            if file.endswith('.gradle') or file.endswith('.groovy'):
                totals['gradle'] += count_effective_lines_in_file(filepath)
            elif file.endswith('.xml'):
                totals['xml'] += count_effective_lines_in_file(filepath)
    return totals

# Example usage:
if __name__ == '__main__':
    directory = '../../FilesExamples'  # <-- change this
    result = count_lines_in_directory(directory)
    print(f"Effective Gradle lines: {result['gradle']}")
    print(f"Effective Maven/Ant lines: {result['xml']}")