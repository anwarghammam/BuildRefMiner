import subprocess
import re

# === Paths ===
CODENARC_JAR = "../../jarFiles/CodeNarc-3.3.0-all.jar"
GMETRICS_JAR = "../../jarFiles/GMetrics-2.1.0.jar"
SLF4J_API_JAR = "../../jarFiles/slf4j-api-1.7.30.jar"
SLF4J_NOP_JAR = "../../jarFiles/slf4j-nop-1.7.30.jar"
RULESET_FILE = "file:../../config/codenarc.groovy"
BASEDIR = "../../FilesExamples"
OUTPUT_FILE = "output.txt"

# === Java Command ===
classpath = f"{CODENARC_JAR}:{GMETRICS_JAR}:{SLF4J_API_JAR}:{SLF4J_NOP_JAR}"

cmd = [
    "java", "-cp", classpath, "org.codenarc.CodeNarc",
    "-rulesetfiles=" + RULESET_FILE,
    "-report=console:stdout",
    "-basedir=" + BASEDIR,
    "-includes=**/*.groovy,**/*.gradle"
]

# === Run the command and save output ===
with open(OUTPUT_FILE, "w") as out:
    subprocess.run(cmd, stdout=out, stderr=subprocess.STDOUT)

# === Read output and extract violations ===
with open(OUTPUT_FILE, "r") as f:
    output = f.read()

match = re.search(r"Summary:.*?P1=(\d+)\s+P2=(\d+)\s+P3=(\d+)", output)
if match:
    p1, p2, p3 = map(int, match.groups())
    total = p1 + p2 + p3
    print(f"Violations Summary: P1={p1}, P2={p2}, P3={p3}, Total={total}")
else:
    print("No violations found or summary line missing.")