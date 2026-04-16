
# Build Metrics (Gradle, Maven, Ant)

## Contents

- [0. Implemented Metrics Overview](#0-implemented-metrics-overview)
- [1. Complexity](#1-complexity)
- [2. Dependency Quality](#2-dependency-quality)
- [3. Maintainability](#3-maintainability)
- [Maintainability Smells](#maintainability-smells)
- [Security Smells](#security-smells)
- [4. Coupling and Cohesion Metrics](#4-coupling-and-cohesion-metrics)
- [5. Cohesion Notes](#5-cohesion-notes)
- [6. Code Duplication](#6-code-duplication)
- [7. Security Metric](#7-security-metric)
- [8. Build Run Time (BRT) Metric](#8-build-run-time-brt-metric)
- [9. Halstead Complexity Metric: Operator and Operand Definitions for Build Systems](#9-halstead-complexity-metric-operator-and-operand-definitions-for-build-systems)

## 0. Implemented Metrics Overview

The table below summarizes the metrics that are **verifiably implemented in the current codebase** and explains how each one is calculated for the supported build systems.

Scope notes:
- The overview covers metrics implemented in [`metrics/`](/Users/aghammam/Desktop/BuildRefMiner/metrics), the before/after pipeline in [`metrics/run_before_after_metrics.py`](/Users/aghammam/Desktop/BuildRefMiner/metrics/run_before_after_metrics.py), and the smell extractors in [`tools/secure_linter/`](/Users/aghammam/Desktop/BuildRefMiner/tools/secure_linter).
- `Build_Modularity_*` is referenced by the before/after pipeline, but its implementation source is not present in the current workspace, so it is intentionally excluded from the table below.
- The conceptual sections later in this README for items such as the proposed security metric and build run time are documentation notes, not part of this implementation summary.

| Metric | Definition | Gradle / Groovy / Kotlin DSL | Maven (`pom.xml`) | Ant (`build.xml`) |
|--------|------------|------------------------------|-------------------|-------------------|
| `BLOC` | Build lines of code. | Uses `scc --by-file --format json` and takes the `Code` count for `.gradle`, `.groovy`, and `.gradle.kts` files. | Uses `scc` and takes the XML file's `Code` count. | Uses `scc` and takes the XML file's `Code` count. |
| `Cyclomatic_Complexity` | File-level decision/build-logic complexity. | `.gradle` / `.groovy`: runs CodeNarc and sums reported `CyclomaticComplexity` values.<br>`.gradle.kts`: runs detekt with `CyclomaticComplexMethod` threshold forced to `0`, then sums reported complexities. | Starts at `1`, then adds `1` for each `<profile>`, `<activation>`, and `<execution>` tag. | Starts at `1`, then adds `1` for each condition-related tag (`condition`, `available`, `uptodate`, `isset`, `equals`, `contains`, `matches`, `and`, `or`, `not`), each `if` / `unless` attribute, and extra target dependencies beyond the first. |
| `Normalized_CC` | Size-normalized complexity: `Cyclomatic_Complexity / BLOC`. | Same formula after the Gradle/Kotlin CC value is computed. | Same formula after Maven build-logic complexity is computed. | Same formula after Ant build-logic complexity is computed. |
| `Halstead_Volume` | Halstead volume computed as `V = (N1 + N2) * log2(n1 + n2)`. | `.gradle` / `.groovy`: uses a Groovy AST script to count operators and operands, then applies the Halstead formula.<br>`.gradle.kts`: not implemented in the current Halstead pipeline, so the value falls back to `0.0`. | Counts XML tag names as operators and child-tag occurrences as operands, then applies the Halstead formula. | Counts non-`project` / non-`description` XML tags as operators and attribute names as operands, then applies the Halstead formula. |
| `Normalized_HV` | Size-normalized Halstead volume: `Halstead_Volume / BLOC`. | Same formula after the Gradle/Groovy or Kotlin DSL Halstead value is computed. | Same formula after Maven Halstead volume is computed. | Same formula after Ant Halstead volume is computed. |
| `Comment_Ratio` | Ratio of comment lines to total lines. | Uses `scc` line stats and computes `comment / lines` for Gradle/Groovy/Kotlin files. | Uses `scc` line stats and computes `comment / lines`. | Uses `scc` line stats and computes `comment / lines`. |
| `Comment_Readability` | Flesch Reading Ease score of extracted comment text. | Extracts `// ...` and `/* ... */` comments, normalizes the text, counts sentences/words/syllables, then computes Flesch Reading Ease. | Extracts `<!-- ... -->` comments, normalizes the text, then computes Flesch Reading Ease. | Extracts `<!-- ... -->` comments, normalizes the text, then computes Flesch Reading Ease. |
| `Style_Conformance_Score` | Style score in the range `0..100`, computed as `max(0, 100 - ((violations / BLOC) * 100))`. | `.gradle` / `.groovy`: CodeNarc weighted violations, where `weighted_violations = 5*P1 + 3*P2 + P3`.<br>`.gradle.kts`: detekt XML report error count used as the violation total. | Custom XML checks: indentation, line length, Maven-style tag names, and lowercase attribute names. | Custom XML checks: indentation, line length, lowercase tag/attribute names, and target-name format. |
| `Clone_Density` | Fraction of duplicated logic lines in the file. | Preferred path: PMD CPD on Groovy or Kotlin syntax and `cloned_lines / BLOC`.<br>Fallback: repeated normalized intra-file line windows after comment removal. | Preferred path: PMD CPD on XML and `cloned_lines / BLOC`.<br>Fallback: repeated normalized intra-file line windows after comment removal. | Preferred path: PMD CPD on XML and `cloned_lines / BLOC`.<br>Fallback: repeated normalized intra-file line windows after comment removal. |
| `CP_Internal` | Internal coupling count. | `T_int + V_shared + C_internal`, where internal task links, shared properties, and shared config references are detected from the Gradle AST helper or regex fallback. | `T_int + V_shared + C_internal`, where linked plugin executions, reused property references, and repeated configuration tags are counted. | `T_int + V_shared + C_internal`, where target dependencies / `antcall` links, shared property references, and repeated IDs / refs / path-like configs are counted. |
| `CP_External` | External coupling count. | `M + D + P + R + E + U`, where the analyzer counts project-module references, external dependencies, plugins, repositories, external commands/scripts, and env/path/URL resources. | `M + D + P + R + E + U`, where the analyzer counts local modules, non-local dependencies, plugins, repositories, exec/antrun plugins, and env/path/URL resources. | `M + D + P + R + E + U`, where the analyzer counts imported/sub-build modules, JAR dependencies, taskdefs, remote resources, exec/java tasks, and env/path/URL resources. |
| `CP_Total` | Total coupling: `CP_Internal + CP_External`. | Sum of internal and external Gradle coupling components. | Sum of internal and external Maven coupling components. | Sum of internal and external Ant coupling components. |
| `NCP_Internal` | Size-normalized internal coupling: `CP_Internal / BLOC`. | Same normalization formula. | Same normalization formula. | Same normalization formula. |
| `NCP_External` | Size-normalized external coupling: `CP_External / BLOC`. | Same normalization formula. | Same normalization formula. | Same normalization formula. |
| `Coupling_Ratio` | Share of coupling that is external: `CP_External / CP_Total`. | Same ratio after the Gradle coupling components are computed. | Same ratio after the Maven coupling components are computed. | Same ratio after the Ant coupling components are computed. |
| `Build_Cohesion` | Average pairwise Jaccard similarity across extracted build-element feature sets. | Compares task feature sets. `.gradle` / `.groovy` use an AST-based task extractor when available, otherwise regex fallback; `.gradle.kts` uses the regex fallback. Features include shared keywords, properties, dependency references, source sets, I/O config, and scripts. | Compares plugin execution feature sets built from plugin artifact IDs, execution goals, and configuration tags. | Compares target feature sets built from `depends`, `if` / `unless`, task tags, and attribute names. |
| `Churn` | Raw code churn in the observation window: sum of file additions and deletions across matching commits. | Build-system agnostic. Uses GitHub commit history for the file over the configured rolling window. | Same history-based calculation. | Same history-based calculation. |
| `Change_Frequency` | Number of commits touching the file in the observation window. | Build-system agnostic. Counts commits returned by the file-history query. | Same history-based calculation. | Same history-based calculation. |
| `Avg_Logical_LOC` | Average logical LOC of the file across commits in the observation window. | Materializes historical file contents, computes `BLOC` for each snapshot, then averages them. | Same history-based calculation. | Same history-based calculation. |
| `Normalized_Churn` | Size-normalized churn: `Churn / Avg_Logical_LOC`. | Same normalization formula. | Same normalization formula. | Same normalization formula. |
| `Normalized_Change_Frequency` | Size-normalized volatility: `(Change_Frequency / Avg_Logical_LOC) * 100`. | Same normalization formula. | Same normalization formula. | Same normalization formula. |
| `Maintainability_Smell_Count` | Number of maintainability smell findings returned by the shared smell extractor. | Runs the Gradle parser plus Gradle-specific checks for complexity, duplicate code/dependencies, inconsistent version management, missing versions, error handling, suspicious comments, deprecated dependencies, and outdated dependencies. | Runs the Maven parser plus Maven-specific checks for complexity heuristics, duplicates, empty tags, inconsistent management, missing versions, error handling, suspicious comments, deprecated dependencies, and outdated dependencies. | Runs the Ant parser plus Ant-specific checks for complexity, duplicates, empty/incomplete tags, inconsistent dependency management, missing versions, error handling, suspicious comments, deprecated dependencies, and outdated dependencies. |
| `Maintainability_Smell_Density` | Density of maintainability smells: `(smell_count / non_empty_lines) * 1000`. | Same shared extractor formula. | Same shared extractor formula. | Same shared extractor formula. |
| `Maintainability_Smell_Summary` | Semicolon-separated set of maintainability smell IDs present in the file. | Same shared extractor formatting. | Same shared extractor formatting. | Same shared extractor formatting. |
| `Security_Smell_Count` | Number of security smell findings returned by the shared security extractor. | Runs Gradle-specific checks for hardcoded credentials, signing credentials, insecure URLs, wildcard usage/version ranges, and hardcoded paths/URLs. | Runs Maven-specific checks for hardcoded credentials, insecure URLs, wildcard version ranges, and hardcoded paths/URLs. | Runs Ant-specific checks for hardcoded credentials, insecure URLs, wildcard usage, and hardcoded paths/URLs. |
| `Security_Smell_Density` | Density of security smells: `(smell_count / non_empty_lines) * 1000`. | Same shared extractor formula. | Same shared extractor formula. | Same shared extractor formula. |
| `Security_Smell_Summary` | Semicolon-separated set of security smell IDs present in the file. | Same shared extractor formatting. | Same shared extractor formatting. | Same shared extractor formatting. |

## 1. Complexity

A weighted formula:

```
Complexity = w₁ * (1 / CC)
           + w₂ * (1 / HC)
           + w₃ * SCS 
           + w₄ * CR    
           + w₅ * (1 / log(LOC + 2)) 
```

**Where:**
- `CC` = Cyclomatic Complexity for Gradle Groovy DSL and Kotlin DSL, or build-logic complexity for XML build files  
- `HC` = Halstead Complexity
- `SCS` = percentage of lines following style
- `CR` = Comment Ratio (`Comment Lines / Total Lines`)  
- `LOC` = Lines of Code  
- `UDR` = Unused Dependency Ratio  
- `DCR` = Dependency Conflict Ratio  
---

### SCS (Style Conformance Score)

This repo computes style conformance as a normalized score from `0` to `100`.

For CodeNarc-based Gradle style checks:

```
weighted_violations = 5 * P1 + 3 * P2 + 1 * P3
SCS = max(0, 100 - ((weighted_violations / BLOC) * 100))
```

For detekt-based Kotlin DSL checks and the custom XML checks for Maven and Ant:

```
SCS = max(0, 100 - ((violations / BLOC) * 100))
```

**Where:**
- `P1`, `P2`, `P3` = CodeNarc priority counts
- `violations` = total detekt or XML style findings
- `BLOC` = Build Lines of Code from [`metrics/BLOC.py`](/Users/aghammam/Desktop/BuildRefMiner/metrics/BLOC.py)

### Style Tooling

- Gradle Groovy DSL style rules: [`config/codenarc_style.groovy`](/Users/aghammam/Desktop/BuildRefMiner/config/codenarc_style.groovy)
- Kotlin DSL style rules: [`config/detekt_style.yml`](/Users/aghammam/Desktop/BuildRefMiner/config/detekt_style.yml)
- Style scoring pipeline: [`metrics/style_conformance.py`](/Users/aghammam/Desktop/BuildRefMiner/metrics/style_conformance.py)

Repository layout note:
- [`config/`](/Users/aghammam/Desktop/BuildRefMiner/config) stores rule definitions and thresholds used by the metric pipelines.
- [`tools/`](/Users/aghammam/Desktop/BuildRefMiner/tools) stores the vendored tool binaries and launcher scripts used to execute those checks.

### Run Style Scoring

From the repo root:

```bash
export CODENARC_BINARY="$PWD/tools/codenarc/codenarc"
export DETEKT_BINARY="$PWD/tools/detekt/detekt"
python3 metrics/style_conformance.py
```

This writes `Style_Conformance_Score` into [`results/summary_metrics.csv`](/Users/aghammam/Desktop/BuildRefMiner/results/summary_metrics.csv).

In the before/after metrics pipeline, style conformance is also recorded per snapshot as:
- `Style_Conformance_Score_Before`
- `Style_Conformance_Score_After`

Comment ratio is also exported by the before/after pipeline as:
- `Comment_Ratio_Before`
- `Comment_Ratio_After`

The current implementation computes comment ratio as:

```text
Comment_Ratio = Comment_Lines / Total_Lines
```

using line counts returned by `scc`.

Comment readability is also exported by the before/after pipeline as:
- `Comment_Readability_Before`
- `Comment_Readability_After`

The current implementation computes comment readability using the `Flesch Reading Ease` score on extracted comment text from Gradle, Maven, and Ant build files:

```text
FRE = 206.835 - 1.015 * (words / sentences) - 84.6 * (syllables / words)
```

Implementation notes:
- Gradle readability is computed from extracted `//` and `/* ... */` comments
- Maven and Ant readability are computed from extracted `<!-- ... -->` comments
- URLs and some code-like fragments are removed before scoring
- if there is too little comment text, the score defaults to `0.0`

### Complexity Tooling Notes

- `build.gradle` uses CodeNarc for cyclomatic complexity.
- `build.gradle.kts` uses detekt for cyclomatic complexity.
- `build.xml` and `pom.xml` do not have a standard off-the-shelf cyclomatic-complexity tool in this repo.
- For `build.xml` and `pom.xml`, [`metrics/cyclomatic_complexity.py`](/Users/aghammam/Desktop/BuildRefMiner/metrics/cyclomatic_complexity.py) computes a custom structural **Build Logic Complexity** heuristic instead.
- The summary CSV includes a `Complexity_Model` column so the metric source is explicit per file.

For Ant (`build.xml`), the current build-logic complexity heuristic is:

```text
BLC_ant = 1
        + count(condition/operator tags)
        + count(if)
        + count(unless)
        + count(extra dependency edges from depends)
```

Where:
- `condition/operator tags` include `condition`, `available`, `uptodate`, `isset`, `equals`, `contains`, `matches`, `and`, `or`, and `not`
- each `if` and each `unless` attribute contributes `1`
- `extra dependency edges from depends` is `max(0, number_of_dependencies - 1)` per target

This is documented as **Build Logic Complexity** rather than true cyclomatic complexity for XML build files.

For Maven (`pom.xml`), the current build-logic complexity heuristic is:

```text
BLC_maven = 1
          + count(profile)
          + count(activation)
          + count(execution)
```

These components were chosen because they capture the main structural sources of build reasoning in Maven:
- `profile`: represents an alternative build path or configuration branch
- `activation`: represents the condition that enables a profile
- `execution`: represents a concrete plugin-driven build step in the lifecycle

In other words:
- more `profile` elements mean more alternate configurations to reason about
- more `activation` elements mean more conditional behavior
- more `execution` elements mean more explicit workflow steps

This keeps the XML metric simple and explainable while still reflecting branching, conditional activation, and executable build orchestration in `pom.xml`.

### Clone Density

This repo computes clone density with **PMD CPD** in [`metrics/clone_density.py`](/Users/aghammam/Desktop/BuildRefMiner/metrics/clone_density.py).

The score is:

```text
Clone_Density = duplicated_build_logic_lines / BLOC
```

**Where:**
- `duplicated_build_logic_lines` = the union of duplicated line ranges reported by PMD CPD for the file
- `BLOC` = Build Lines of Code from [`metrics/BLOC.py`](/Users/aghammam/Desktop/BuildRefMiner/metrics/BLOC.py)

The implementation currently uses:
- PMD CPD with `--minimum-tokens 20`
- Groovy mode for `.gradle`
- Kotlin mode for `.gradle.kts`
- XML mode for `pom.xml` and `build.xml`

For Gradle files, PMD CPD is run on temporary files with standard parser-friendly extensions:
- `.gradle` is analyzed as temporary `.groovy`
- `.gradle.kts` is analyzed as temporary `.kt`

For Groovy Gradle files, the script also normalizes some interpolation forms before running PMD CPD so tokenization stays stable while preserving duplicated structure.

In practice, the pipeline is:
1. detect the build file type
2. choose the PMD CPD language (`groovy`, `kotlin`, or `xml`)
3. run PMD CPD and collect duplicated line ranges
4. merge overlapping duplicated ranges for the target file
5. divide duplicated lines by BLOC
6. write the result to the `Clone_Density` column in [`results/summary_metrics.csv`](/Users/aghammam/Desktop/BuildRefMiner/results/summary_metrics.csv)

---
## 2. Dependency Quality

A weighted formula:

```
 w₁ * (1 - UDR) + w₂ * (1 - DCR)
```

**Where:**
- `UDR` = Unused Dependency Ratio  
- `DCR` = Dependency Conflict Ratio
---

## 3. Maintainability

```
Maintainability = f(Size, Complexity, Volume, Duplication, Smells, Effort, Volatility)
```

This repo currently tracks the following maintainability indicators:
- `BLOC` for size
- `Cyclomatic Complexity`
- `Halstead Volume`
- `Normalized CC` as `CC / BLOC`
- `Normalized HV` as `HV / BLOC`
- `Style Conformance Score`
- `Comment Ratio`
- `Comment Readability` using Flesch Reading Ease on extracted comment text
- `Clone Density`
- `Smell Density`
- `Code Churn` for effort
- `Change Frequency` for volatility

For each build file `f` in an observation window `T`, code churn is computed as the total number of added and deleted lines across all commits modifying `f`. Change frequency is computed as the number of commits touching `f` during `T`.

In the current before/after pipeline, `T` is implemented as a rolling `30`-day observation window ending at the reference commit.

To make these values comparable across files of different sizes, both metrics are normalized by the average logical LOC of the file in the same window.

```math
\mathrm{Churn}(f, T) = \sum_{c \in T_f} \left(\mathrm{added\_lines}_{c,f} + \mathrm{deleted\_lines}_{c,f}\right)
```

```math
\mathrm{ChangeFrequency}(f, T) = |T_f|
```

```math
\mathrm{NormalizedChurn}(f, T) = \frac{\mathrm{Churn}(f, T)}{\mathrm{AvgLogicalLOC}(f, T)}
```

```math
\mathrm{NormalizedChangeFrequency}(f, T) = \frac{\mathrm{ChangeFrequency}(f, T)}{\mathrm{AvgLogicalLOC}(f, T)} \times 100
```

Where:
- `T_f` is the set of commits in observation window `T` that modify file `f`
- `AvgLogicalLOC(f, T)` is the average logical LOC of file `f` over the same window

These indicators are written into [results/summary_metrics.csv](/Users/aghammam/Desktop/BuildRefMiner/results/summary_metrics.csv) as part of the before/after metrics pipeline. The CSV keeps both the raw values (`Churn_*`, `Change_Frequency_*`, `Cyclomatic_Complexity_*`, `Halstead_Volume_*`) and the normalized values (`Normalized_Churn_*`, `Normalized_Change_Frequency_*`, `Normalized_CC_*`, `Normalized_HV_*`), together with `Avg_Logical_LOC_*`. It also includes readability and documentation-related fields such as `Style_Conformance_Score_*`, `Comment_Ratio_*`, and `Comment_Readability_*`.

### Maintainability Smells

This repo also extracts **maintainability smells** for build files and saves them as part of the before/after metrics pipeline.

Supported build systems:
- `Gradle`
- `Maven`
- `Ant`

The maintainability smell extractor lives in [tools/secure_linter/maintainability_smells.py](/Users/aghammam/Desktop/BuildRefMiner/tools/secure_linter/maintainability_smells.py) and uses build-system-specific parsers and checks under [tools/secure_linter](/Users/aghammam/Desktop/BuildRefMiner/tools/secure_linter).

The current maintainability smell categories are:
- `Complexity`
- `Duplicates`
- `Empty / Incomplete Tags`
- `Inconsistent Dependency Management`
- `Lack of Error Handling`
- `Missing Dependency Version`
- `Suspicious Comments`
- `Deprecated Dependencies`
- `Outdated Dependencies`

These smells are reported per file and also aggregated into the commit-level `__COMMIT_TOTAL__` row in [results/summary_metrics.csv](/Users/aghammam/Desktop/BuildRefMiner/results/summary_metrics.csv).

The summary CSV includes:
- total maintainability smell count before and after the change
- maintainability smell density before and after the change
- maintainability smell summary fields
- one-hot smell columns such as `Before_COMPLEXITY` and `After_OUTDATED_DEPENDENCIES`

### Security Smells

In addition to maintainability smells, the repo extracts a focused set of **security smells** for build configurations.

Supported build systems:
- `Gradle`
- `Maven`
- `Ant`

Current scope note:
- `Makefile` and `CMake` are intentionally not included in the shared `security_smells.py` pipeline at this stage

The shared security smell extractor lives in [tools/secure_linter/security_smells.py](/Users/aghammam/Desktop/BuildRefMiner/tools/secure_linter/security_smells.py). For Ant, the Ant-specific security heuristics are implemented in [tools/secure_linter/ant_security_checks.py](/Users/aghammam/Desktop/BuildRefMiner/tools/secure_linter/ant_security_checks.py).

The current security smell categories are:
- `Hardcoded Credentials`
- `Insecure URLs`
- `Wildcard Usage`
- `Hardcoded Paths/URLs`

These security smells are also written into [results/summary_metrics.csv](/Users/aghammam/Desktop/BuildRefMiner/results/summary_metrics.csv), both per file and in the commit summary row.

The summary CSV includes:
- `Before_Security_Smell_Count` and `After_Security_Smell_Count`
- `Before_Security_Smell_Density` and `After_Security_Smell_Density`
- `Before_Security_Smell_Summary` and `After_Security_Smell_Summary`
- `Security_Smell_Count_Delta` and `Security_Smell_Density_Delta`
- one-hot security smell columns such as `Before_HARDCODED_CREDENTIALS` and `After_WILDCARD_USAGE`

---

## 4. Coupling and Cohesion Metrics

### 4.1 Internal and External Coupling

This repo models coupling for a build file or build module `b` as two separate quantities.

Internal coupling captures how strongly elements inside the same build file depend on one another.

```math
CP_{\mathrm{internal}}(b) = T_{\mathrm{int}} + V_{\mathrm{shared}} + C_{\mathrm{internal}}
```

Where:
- `T_int` = number of internal task or target dependency links
- `V_shared` = number of variables or properties reused by multiple internal elements
- `C_internal` = number of internal configuration references reused across multiple internal elements

External coupling captures how strongly the build file depends on outside modules, libraries, tools, repositories, and environment-specific resources.

```math
CP_{\mathrm{external}}(b) = M + D + P + R + E + U
```

Where:
- `M` = inter-module references
- `D` = external dependencies or libraries
- `P` = plugins or externally defined task types
- `R` = repositories or remote artifact sources
- `E` = external commands or external build/script invocations
- `U` = environment variables, absolute paths, and non-repository URLs

The total coupling value is:

```math
CP(b) = CP_{\mathrm{internal}}(b) + CP_{\mathrm{external}}(b)
```

To make file-level comparisons more meaningful across different build-file sizes, the pipeline also exports normalized coupling:

```math
NCP_{\mathrm{internal}}(b) = \frac{CP_{\mathrm{internal}}(b)}{BLOC(b)}
```

```math
NCP_{\mathrm{external}}(b) = \frac{CP_{\mathrm{external}}(b)}{BLOC(b)}
```

And an external-coupling ratio:

```math
CouplingRatio(b) = \frac{CP_{\mathrm{external}}(b)}{CP(b)}
```

Interpretation:
- a higher `CP_internal` means stronger internal interdependence inside the same file
- a higher `CP_external` means the build file relies more on external modules, tools, repositories, or environment-specific resources
- a higher `CouplingRatio` means coupling is driven more by external factors than by internal structure

### 4.2 Gradle Coupling Calculation

Gradle coupling is implemented in [metrics/build_coupling.py](/Users/aghammam/Desktop/BuildRefMiner/metrics/build_coupling.py). For Groovy DSL files (`.gradle`), the preferred implementation uses the Groovy AST helper [metrics/gradle_coupling_ast.groovy](/Users/aghammam/Desktop/BuildRefMiner/metrics/gradle_coupling_ast.groovy). For Kotlin DSL files (`.gradle.kts`), the pipeline uses the structured fallback in Python.

For Gradle, the current implementation calculates:

- `T_int`: task-to-task links created by `dependsOn`, `mustRunAfter`, `shouldRunAfter`, and `finalizedBy` when the referenced task is declared in the same file
- `V_shared`: local variables, `ext` properties, and `findProperty(...)` references reused by at least two task closures
- `C_internal`: shared internal configuration references reused by at least two task closures, such as `sourceSets.*`, `inputs.*`, `outputs.*`, and `configurations.*`
- `M`: module references declared with `project(':module')`
- `D`: external dependency declarations through dependency configuration methods such as `implementation`, `api`, `runtimeOnly`, and `testImplementation`
- `P`: plugin references declared through `plugins { id(...) }` or `apply plugin: ...`
- `R`: repository references such as `mavenCentral()`, `google()`, `gradlePluginPortal()`, `mavenLocal()`, `jcenter()`, `ivy()`, and `maven { ... }`
- `E`: external script or command usage such as `apply from: ...`, `exec`, `javaexec`, and `commandLine`
- `U`: environment and external resource references such as `System.getenv(...)`, `System.getProperty(...)`, explicit absolute paths, and explicit URLs

This gives Gradle an AST-backed internal/external split that is stronger than plain regex matching for Groovy-based build files.

### 4.3 Maven Coupling Calculation

Maven coupling is implemented through XML tree analysis in [metrics/build_coupling.py](/Users/aghammam/Desktop/BuildRefMiner/metrics/build_coupling.py).

For Maven, the current implementation calculates:

- `T_int`: links between plugin executions inside the same `pom.xml` when executions share the same plugin or lifecycle phase
- `V_shared`: Maven property references such as `${...}` reused across two or more plugin executions
- `C_internal`: configuration element names reused across multiple plugin execution `<configuration>` blocks
- `M`: inter-module references from local reactor-module links, including `<modules><module>...</module></modules>` entries and dependency declarations whose `artifactId` matches another local artifact in the same project snapshot
- `D`: dependency declarations that are not resolved as local modules
- `P`: declared Maven plugins
- `R`: declared `<repository>` and `<pluginRepository>` entries
- `E`: plugins that explicitly bridge to external command execution, currently `exec-maven-plugin` and `maven-antrun-plugin`
- `U`: environment-sensitive and external resource references, including `${env.*}`, `${user.*}`, `systemPath`, absolute filesystem paths, and non-repository URLs

This means Maven internal coupling is based on shared execution structure inside one POM, while external coupling is based on the declared dependencies, plugins, repositories, and environment-dependent references around that POM.

### 4.4 Ant Coupling Calculation

Ant coupling is implemented through XML tree analysis in [metrics/build_coupling.py](/Users/aghammam/Desktop/BuildRefMiner/metrics/build_coupling.py).

For Ant, the current implementation calculates:

- `T_int`: target-to-target links created by `depends="..."` and by `<antcall target="...">` when the referenced target exists in the same `build.xml`
- `V_shared`: Ant property references such as `${property.name}` reused across two or more targets
- `C_internal`: internal reusable configuration references reused across multiple targets, including `refid`, `id`, and shared resource-collection constructs such as `path`, `fileset`, and `patternset`
- `M`: external build-module invocations such as `<import>`, `<include>`, `<subant>`, and `<ant>` when it points to another build file or directory
- `D`: explicit versioned JAR references found in the Ant build content
- `P`: externally defined Ant task types such as `<taskdef>` and `<typedef>`
- `R`: remote resource endpoints used for download-oriented tasks such as `<get src="...">`
- `E`: external command execution through `<exec>` and `<java>`
- `U`: environment and machine-specific references such as `${env.*}`, `environment="..."`, absolute paths, and non-repository URLs

This keeps the Ant version aligned with the same internal/external decomposition used for Gradle and Maven, while reflecting the fact that Ant expresses coupling mainly through targets, imported builds, custom task definitions, and explicit execution tasks.

### 4.5 Coupling Output Columns

In the current metrics pipeline, coupling is exported to [results/summary_metrics.csv](/Users/aghammam/Desktop/BuildRefMiner/results/summary_metrics.csv) with these columns:
- `CP_Internal_*`
- `CP_External_*`
- `CP_Total_*`
- `NCP_Internal_*`
- `NCP_External_*`
- `Coupling_Ratio_*`

These values are emitted for both the before and after snapshots of each changed build file, and they are also aggregated in the commit-level `__COMMIT_TOTAL__` row.

## 5. Cohesion Notes

**Build cohesion** in this project is implemented as a heuristic based on **feature overlap** between build elements, not as a direct graph or pair-counting metric.

For each supported build system, the analyzer extracts a set of features for each relevant build element and then measures how similar those feature sets are to one another.

---

### Elements Used by the Heuristic

| Build system | Element compared | Example extracted features |
|--------------|------------------|----------------------------|
| **Gradle / Groovy / Kotlin DSL** | Task | `keyword:doLast`, `keyword:dependsOn`, `property:outputDir`, `dep::lib`, `sourceSet:main` |
| **Maven** | Plugin execution | `plugin:maven-resources-plugin`, `goal:copy-resources`, `config:outputDirectory`, `config:resource` |
| **Ant** | Target | `depends:init`, `task:mkdir`, `task:copy`, `attr:copy.tofile`, `cond_if:can.run` |

The metric only compares elements for which at least one recognizable feature is extracted.

---

### What Increases Cohesion in This Implementation

| Pattern | Why it increases the score |
|---------|----------------------------|
| **Tasks or targets using the same keywords** | Shared features increase overlap between feature sets. |
| **Repeated use of the same properties or variables** | Matching `property:*` features raise similarity. |
| **Common dependency or execution structure** | Shared `depends:*`, `goal:*`, or `dep:*` features make elements look more alike. |
| **Repeated configuration structure** | Matching `config:*`, `task:*`, or `attr:*` features increase Jaccard similarity. |

---

### What Lowers Cohesion in This Implementation

| Pattern | Why it lowers the score |
|---------|-------------------------|
| **Isolated tasks/targets/executions** | They share few or no extracted features with other elements. |
| **Different configuration styles across elements** | Larger feature-set differences reduce pairwise overlap. |
| **Elements with unique dependencies or properties** | Unique features enlarge the union without increasing the intersection. |

---

### Cohesion Metric Formula

For two build elements with feature sets `A` and `B`, the implementation computes **Jaccard similarity**:

```math
J(A, B) = \frac{|A \cap B|}{|A \cup B|}
```

The final cohesion score is the average of that value across all element pairs:

```math
Cohesion = \operatorname{avg}_{i < j} J(F_i, F_j)
```

Where:
- **`F_i`** is the extracted feature set for build element `i`
- **`J(F_i, F_j)`** is the overlap between two elements' feature sets
- **Cohesion** is reported in the range `0.0` to `1.0`

Special cases in the current implementation:
- If no feature sets are extracted, cohesion is `0.0`
- If exactly one feature set is extracted, cohesion is `1.0`

---

### Example

```groovy
ext.outputDir = "$buildDir/custom"

task compile {
    doLast {
        println outputDir
    }
}

task archive {
    dependsOn compile
    doLast {
        println outputDir
    }
}
```

Approximate extracted feature sets:
- `compile` -> `{keyword:doLast, property:outputDir}`
- `archive` -> `{keyword:dependsOn, keyword:doLast, property:outputDir}`

Pairwise similarity:

```math
\frac{|\{keyword:doLast, property:outputDir\}|}{|\{keyword:dependsOn, keyword:doLast, property:outputDir\}|}
= \frac{2}{3} \approx 0.6667
```

Since there is only one pair in this example, the final cohesion score is also **0.6667**.

> *Note: In this implementation, cohesion rises when build elements share more extracted features, and falls when their feature sets diverge.*


---

## 6. Code Duplication

### Definition

**Code duplication** in build systems refers to identical or near-identical logic repeated across build configuration files. This could include repeated tasks, dependencies, or configuration blocks.

Excessive duplication increases maintenance overhead, makes debugging harder, and reduces the modularity and quality of the build script.

---

### Code Duplication Metric (CDM)

```math
CDM = \frac{\text{Total Duplicated Lines}}{\text{Total Significant Lines}}
```

### Where:

- **Duplicated Lines**: Lines that appear in multiple places (identical or semantically similar).
- **Significant Lines**: All lines excluding comments, whitespace, and boilerplate.

A high CDM indicates high redundancy and poor maintainability.

---

### Example (Gradle)

```groovy
task cleanTemp {
    doLast {
        delete "$buildDir/temp"
    }
}

task cleanCache {
    doLast {
        delete "$buildDir/temp"
    }
}
```

- Here, both tasks perform the same logic.
- This duplication could be avoided by reusing a shared method or task.

---

### Example (Maven)

```xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.8.1</version>
</plugin>
<!-- Repeated again in another profile -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-compiler-plugin</artifactId>
    <version>3.8.1</version>
</plugin>
```

- Plugin configuration repeated across profiles or executions is a form of duplication.

---

### Detection Methods

- **AST-Based Clone Detection**: Normalize and parse the Abstract Syntax Tree of build files to detect structure-level clones.
- **Token-Based Detection**: Count repeated blocks of tokens or lines.
- **Semantic Detection**: Identify logically equivalent code even if written differently.

---

## 7. Security Metric

### Definition

Security in build systems refers to how well the build configuration avoids introducing vulnerabilities through:

- Insecure or outdated dependencies
- Use of scripts or plugins from untrusted sources
- Hardcoded credentials or sensitive information
- Missing integrity verification (e.g., checksums)

---

### Proposed Security Metric (SM)

```math
SM = 1 - \left( \frac{V + H + T + M}{N} \right)
```

### Where:

- `V`: Number of known vulnerable dependencies
- `H`: Number of hardcoded secrets (tokens, passwords, etc.)
- `T`: Number of third-party plugins used without verification (e.g., from unknown repositories)
- `M`: Number of misconfigurations (e.g., unsigned artifacts, skipped verifications)
- `N`: Total number of build components scanned

The result is normalized between 0 (insecure) and 1 (fully secure).

---

### Example: Gradle

```groovy
dependencies {
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.9.0'  // vulnerable version
}

ext.token = "hardcoded-secret-token"
```

Violations:

- 1 vulnerable dependency (`V = 1`)
- 1 hardcoded secret (`H = 1`)
- 0 third-party unverified (`T = 0`)
- 0 misconfigurations (`M = 0`)
- `N = 3`

Security metric:

```math
SM = 1 - (1 + 1 + 0 + 0) / 3 = 1 - 2/3 = 0.33
```

---

### Detection Tools

- **Dependency Scanners**: OWASP Dependency-Check, Snyk, OSS Index
- **Secret Scanners**: TruffleHog, GitLeaks
- **Lint Rules**: Custom Gradle or Maven linters to detect insecure configurations

---

## 8. Build Run Time (BRT) Metric

### Definition

**Build Run Time (BRT)** refers to the total time taken to execute a full build process from start to finish. This includes:

- Dependency resolution
- Compilation
- Testing
- Packaging
- Any custom build steps (e.g., signing, deployment)

BRT is a key performance metric to evaluate the efficiency and responsiveness of build systems such as Gradle, Maven, and Ant.

---

### Metric Formula

```math
BRT = \text{End Time} - \text{Start Time}
```

- **Start Time**: Timestamp when the build begins
- **End Time**: Timestamp when the build completes

### Units:
- Measured in **seconds** or **milliseconds** depending on the granularity

A lower BRT is desirable and indicates a more efficient build configuration.

---


## 9. Halstead Complexity Metric: Operator and Operand Definitions for Build Systems

This document describes how **operators** and **operands** are identified for computing Halstead Complexity in three build systems: **Gradle**, **Maven**, and **Ant**.

The authoritative implementation lives in [`metrics/halstead_volume.py`](/Users/aghammam/Desktop/BuildRefMiner/metrics/halstead_volume.py), with [`metrics/halstead_groovy_ast.groovy`](/Users/aghammam/Desktop/BuildRefMiner/metrics/halstead_groovy_ast.groovy) used as the Gradle/Groovy AST helper.

---

### Gradle (Groovy DSL)

- **Operators**: 
  - Groovy method calls, including DSL entry points and nested DSL blocks such as `plugins {}`, `repositories {}`, `dependencies {}`, `task`, `register`, `named`, `implementation`, and `mavenCentral`
  - Assignment, binary, unary, and ternary/elvis operators such as `=`, `==`, `!`, and `?:`
  - Control-flow constructs such as `if`, `else`, `for`, `while`, `switch`, `case`, and `catch`

- **Operands**:
  - String, numeric, and boolean literals
  - Variable identifiers referenced in expressions
  - Property/member names referenced in expressions such as `project.version`, `rootProject.name`, and `sourceSets.main`
  - Closure parameter names used in task and closure bodies
  - Dependency coordinates, file paths, and URLs when they appear as string literals

> **Note**: DSL blocks are counted through their underlying method calls, so the closure body itself is not counted as a separate operator. The Groovy AST is traversed to extract these nodes, making Gradle Halstead Volume an AST-based approximation of build-script logic rather than a plain-text token count.

---

### Maven (XML-based POM)

- **Operators**:
  - All XML tags, such as `<project>`, `<build>`, `<plugin>`, `<execution>`, etc.

- **Operands**:
  - All child XML tags of the operator tags
  - Example: in `<plugin><artifactId>maven-compiler-plugin</artifactId></plugin>`, `<plugin>` is an operator and `<artifactId>` is an operand

> **Note**: This follows the McIntosh et al. definition used in the repo: every Maven XML tag is counted as an operator, and child XML tags are counted as operands.

---

### Ant (XML-based)

- **Operators**:
  - Ant target and task tags, such as `<target>`, `<property>`, `<mkdir>`, `<javac>`, `<delete>`, and `<echo>`
  - The root `<project>` tag and `<description>` are excluded from the repo's implementation

- **Operands**:
  - Parameter names passed to target or task tags
  - The `name` parameter of `<target>` is excluded

> **Example**: In `<javac srcdir="${src.dir}" destdir="${build.dir}"/>`, `javac` is an operator and `srcdir`, `destdir` are operands.

> **Note**: This follows the McIntosh et al. definition adapted in the repo: ANT targets and tasks are operators, while their parameters are operands, excluding the target `name` parameter.

---

### Formula (All Build Systems)

The Halstead Volume is calculated as:

```
n1 = number of unique operators
n2 = number of unique operands
N1 = total number of operators
N2 = total number of operands

Vocabulary = n1 + n2
Length     = N1 + N2
Volume     = Length * log2(Vocabulary)
```

---
