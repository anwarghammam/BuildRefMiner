import os
import subprocess

# --------------------------------------------------
# Paths
# --------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_PATH = os.path.join(BASE_DIR, "..")
BUILD_FILES = ["FilesExamples/build.gradle", "FilesExamples/build.xml", "FilesExamples/pom.xml"]

# --------------------------------------------------
# Function to make dummy commit
# --------------------------------------------------
def make_dummy_commit(file_path, commit_msg):
    full_path = os.path.join(REPO_PATH, file_path)
    # Append a dummy comment to the file
    with open(full_path, "a", encoding="utf-8") as f:
        f.write(f"\n// Dummy CF test commit: {commit_msg}\n")

    # Stage and commit
    subprocess.run(["git", "add", file_path], cwd=REPO_PATH)
    subprocess.run(["git", "commit", "-m", commit_msg], cwd=REPO_PATH)

# --------------------------------------------------
# Main
# --------------------------------------------------
def main():
    print("Creating dummy commits for CF testing...")

    for i in range(1, 4):  # create 3 commits per file
        for file in BUILD_FILES:
            make_dummy_commit(file, f"CF Test commit {i} for {os.path.basename(file)}")
            print(f"Committed: {file} (dummy commit {i})")

    print("\nDone! You can now run your CF script to see non-zero results.")

if __name__ == "__main__":
    main()
