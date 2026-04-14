# detekt Setup

This folder contains the local detekt setup used by the Kotlin DSL cyclomatic-complexity and style-conformance pipelines in this repo.

## Requirements

- Java
- `curl`
- `unzip`

Check them with:

```bash
java -version
curl --version
unzip -v
```

If Java is missing on macOS with Homebrew:

```bash
brew install openjdk
```

## Files In This Folder

- `detekt`
  Wrapper script that runs the detekt CLI jar from `lib/`
- `lib/`
  Folder that should contain the downloaded detekt CLI jar

## Required Jar

This setup expects a detekt CLI jar in `lib/`, typically named something like:

- `detekt-cli-1.23.8-all.jar`

The wrapper script looks for `detekt-cli*.jar` inside `lib/`.

## Download The Jar

Run this from the repo root:

```bash
cd /Users/aghammam/Desktop/BuildRefMiner
curl -L -o /tmp/detekt-cli.zip https://github.com/detekt/detekt/releases/download/v1.23.8/detekt-cli-1.23.8.zip
rm -rf /tmp/detekt-cli
unzip -q /tmp/detekt-cli.zip -d /tmp/detekt-cli
cp /tmp/detekt-cli/detekt-cli-1.23.8/lib/detekt-cli-1.23.8-all.jar /Users/aghammam/Desktop/BuildRefMiner/tools/detekt/lib/
```

Notes:

- The current local setup is pinned to detekt `1.23.8`.
- The Python metric pipeline supports both detekt `1.x` and `2.x`, but this README uses the latest stable `1.x` CLI release because it is the latest stable release on detekt's GitHub releases page.

## Test detekt

Run:

```bash
/Users/aghammam/Desktop/BuildRefMiner/tools/detekt/detekt --help
```

If that prints the detekt CLI help, the setup is working.

## Run detekt Manually

To analyze one Kotlin DSL build file with the maintainability config:

```bash
/Users/aghammam/Desktop/BuildRefMiner/tools/detekt/detekt \
  --input /Users/aghammam/Desktop/BuildRefMiner/FilesExamples/build.gradle.kts \
  --config /Users/aghammam/Desktop/BuildRefMiner/config/detekt.yml \
  --report xml:/tmp/detekt-report.xml
```

To analyze one Kotlin DSL build file with the style-only config:

```bash
/Users/aghammam/Desktop/BuildRefMiner/tools/detekt/detekt \
  --input /Users/aghammam/Desktop/BuildRefMiner/FilesExamples/build.gradle.kts \
  --config /Users/aghammam/Desktop/BuildRefMiner/config/detekt_style.yml \
  --report xml:/tmp/detekt-style-report.xml
```

## Use It In The Metric Pipeline

Set the environment variable and run the Python script:

```bash
cd /Users/aghammam/Desktop/BuildRefMiner
export DETEKT_BINARY="$PWD/tools/detekt/detekt"
python3 metrics/cyclomatic_complexity.py
python3 metrics/style_conformance.py
```

## Style Conformance Formula

For Kotlin DSL files analyzed with detekt, the repo computes style score as:

```text
Style_Conformance_Score = max(0, 100 - ((violations / BLOC) * 100))
```

Where:

- `violations` is the number of detekt findings produced by [`config/detekt_style.yml`](/Users/aghammam/Desktop/BuildRefMiner/config/detekt_style.yml)
- `BLOC` comes from `metrics/bloc_analyser.py`

## Troubleshooting

If you see:

```text
detekt CLI jar not found in .../tools/detekt/lib
```

then one of these is true:

- `lib/` is empty
- the jar has not been copied into `tools/detekt/lib/`
- the wrapper script path is wrong

Quick checks:

```bash
ls /Users/aghammam/Desktop/BuildRefMiner/tools/detekt/lib
echo "$DETEKT_BINARY"
```

Official references:

- https://detekt.dev/docs/gettingstarted/cli/
- https://github.com/detekt/detekt/releases
