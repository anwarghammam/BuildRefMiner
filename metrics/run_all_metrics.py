import subprocess
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# List metrics in correct order
METRICS = [
    "bloc_analyser.py",          # Must run first (creates/updates summary file)
    "cyclomatic_complexity.py",
    "change_frequency.py",
    "halstead_volume.py",
    "churn.py",
    "clone_density.py"
]


def run_metrics():
    print("\nRunning All Metrics...\n")

    for metric in METRICS:
        metric_path = os.path.join(BASE_DIR, metric)

        if os.path.exists(metric_path):
            print(f"Running {metric}...")
            subprocess.run(["python3", metric_path])
            print("-" * 50)
        else:
            print(f"⚠ {metric} not found. Skipping.")

    print("\nAll metrics executed successfully.")
    print("Check processed_builds/summary_metrics.csv")


if __name__ == "__main__":
    run_metrics()
