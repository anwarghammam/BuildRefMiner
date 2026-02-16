import os
import re
import csv

class BuildLOCAnalyzer:

    def remove_xml_comments(self, content):
        return re.sub(r'<!--.*?-->', '', content, flags=re.DOTALL)

    def remove_gradle_comments(self, content):
        content = re.sub(r'/\*.*?\*/', '', content, flags=re.DOTALL)
        content = re.sub(r'//.*', '', content)
        return content

    def calculate_bloc(self, content):
        """Count non-empty, non-comment lines"""
        lines = content.splitlines()
        non_empty_lines = [line for line in lines if line.strip() != ""]
        return len(non_empty_lines)


def analyze_and_save_build_files():
    analyzer = BuildLOCAnalyzer()
    build_folder = "../FilesExamples"
    processed_folder = "../processed_builds"

    # Create folder if it doesn't exist
    if not os.path.exists(processed_folder):
        os.makedirs(processed_folder)

    results = []

    for root, dirs, files in os.walk(build_folder):
        for file in files:
            if file in ["build.xml", "pom.xml", "build.gradle"]:
                full_path = os.path.join(root, file)

                # Read original content
                with open(full_path, 'r', encoding='utf-8') as f:
                    original_content = f.read()

                # Clean content
                cleaned_content = analyzer.remove_xml_comments(original_content)
                cleaned_content = analyzer.remove_gradle_comments(cleaned_content)

                # Calculate BLOC
                bloc = analyzer.calculate_bloc(cleaned_content)

                # Save cleaned file to processed_builds/
                cleaned_file_path = os.path.join(processed_folder, file)
                with open(cleaned_file_path, 'w', encoding='utf-8') as f_cleaned:
                    f_cleaned.write(cleaned_content)

                results.append({
                    "file_name": file,
                    "bloc": bloc,
                    "cleaned_path": cleaned_file_path
                })

    # Save CSV with file name and BLOC
    csv_path = os.path.join(processed_folder, "bloc_summary.csv")
    with open(csv_path, "w", newline="") as csvfile:
        writer = csv.writer(csvfile)
        writer.writerow(["File", "BLOC", "Cleaned File Path"])
        for r in results:
            writer.writerow([r["file_name"], r["bloc"], r["cleaned_path"]])

    print("\nBLOC calculation complete!")
    print(f"Cleaned build files saved in {processed_folder}")
    print(f"Summary CSV saved as {csv_path}")


if __name__ == "__main__":
    analyze_and_save_build_files()
