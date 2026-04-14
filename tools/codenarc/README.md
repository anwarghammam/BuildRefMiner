# CodeNarc Setup

This folder contains the local CodeNarc setup used by the Gradle cyclomatic-complexity and style-conformance pipelines in this repo.

## Requirements

- Java
- Maven

Check them with:

```bash
java -version
mvn -version
```

If they are missing on macOS with Homebrew:

```bash
brew install openjdk maven
```

## Files In This Folder

- `codenarc`
  Wrapper script that runs `org.codenarc.CodeNarc` with the jars in `lib/`
- `pom.xml`
  Maven file used to download CodeNarc and its runtime dependencies
- `lib/`
  Downloaded jars needed to run CodeNarc locally

## Required Jars

The `lib/` folder should contain CodeNarc plus its runtime dependencies. In this repo, that includes jars like:

- `CodeNarc-3.7.0.jar`
- `GMetrics-2.1.0.jar`
- `groovy-3.0.23.jar`
- `groovy-ant-3.0.23.jar`
- `groovy-json-3.0.23.jar`
- `groovy-xml-3.0.23.jar`
- `logback-classic-1.2.13.jar`
- `logback-core-1.2.13.jar`
- `slf4j-api-1.7.35.jar`
- Ant support jars and a few transitive dependencies

You do not need to download these one by one. Maven populates `lib/` for you.

## Download The Jars

Run this from the repo root:

```bash
cd /Users/aghammam/Desktop/BuildRefMiner
mvn -q -f tools/codenarc/pom.xml dependency:copy-dependencies -DincludeScope=runtime -DoutputDirectory=/Users/aghammam/Desktop/BuildRefMiner/tools/codenarc/lib
```

Note:

- Use the absolute output directory above.
- A relative `tools/codenarc/lib` path can create an unwanted nested folder depending on where Maven is launched from.

## Test CodeNarc

Run:

```bash
/Users/aghammam/Desktop/BuildRefMiner/tools/codenarc/codenarc -help
```

If that prints the CodeNarc CLI help, the setup is working.

## Run CodeNarc Manually

To analyze one Gradle file with the maintainability and complexity ruleset:

```bash
/Users/aghammam/Desktop/BuildRefMiner/tools/codenarc/codenarc \
  -sourcefiles=/Users/aghammam/Desktop/BuildRefMiner/FilesExamples/build.gradle \
  -rulesetfiles=file:/Users/aghammam/Desktop/BuildRefMiner/config/codenarc.groovy \
  -report=json:stdout
```

Important files:

- Ruleset: `/Users/aghammam/Desktop/BuildRefMiner/config/codenarc.groovy`
- Style-only ruleset: `/Users/aghammam/Desktop/BuildRefMiner/config/codenarc_style.groovy`
- Example Gradle file: `/Users/aghammam/Desktop/BuildRefMiner/FilesExamples/build.gradle`

To analyze one Gradle file with the style-only ruleset:

```bash
/Users/aghammam/Desktop/BuildRefMiner/tools/codenarc/codenarc \
  -sourcefiles=/Users/aghammam/Desktop/BuildRefMiner/FilesExamples/build.gradle \
  -rulesetfiles=file:/Users/aghammam/Desktop/BuildRefMiner/config/codenarc_style.groovy \
  -report=json:stdout
```

## Use It In The Metric Pipeline

Set the environment variable and run the Python script:

```bash
cd /Users/aghammam/Desktop/BuildRefMiner
export CODENARC_BINARY="$PWD/tools/codenarc/codenarc"
python3 metrics/cyclomatic_complexity.py
python3 metrics/style_conformance.py
```

## Style Conformance Formula

For Gradle files analyzed with CodeNarc, the repo computes style score as:

```text
weighted_violations = 5 * P1 + 3 * P2 + 1 * P3
Style_Conformance_Score = max(0, 100 - ((weighted_violations / BLOC) * 100))
```

Where:

- `P1`, `P2`, `P3` come from CodeNarc rule priorities
- `BLOC` comes from `metrics/bloc_analyser.py`

## Troubleshooting

If you see:

```text
Could not find or load main class org.codenarc.CodeNarc
```

then one of these is true:

- `lib/` is empty
- the jars were copied into the wrong folder
- `CODENARC_BINARY` points at the wrong script

Quick checks:

```bash
ls /Users/aghammam/Desktop/BuildRefMiner/tools/codenarc/lib
echo "$CODENARC_BINARY"
```
