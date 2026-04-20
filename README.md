# Build Quality Attributes and Metrics for Gradle, Maven, and Ant

This document describes the quality attributes currently measured for build scripts in this project and the low-level metrics used to characterize each attribute.

The README is intentionally methodology-first:
- it documents only metrics that are currently computed by the pipeline
- it groups metrics by quality attribute rather than by implementation script
- it focuses on metric definitions, formulas, and build-system-specific calculation rules

Supported build systems:
- Gradle Groovy DSL: `.gradle` and `.groovy`
- Gradle Kotlin DSL: `.gradle.kts`
- Maven: `pom.xml`
- Ant: `build.xml`

## Contents

- [1. Scope and Conventions](#1-scope-and-conventions)
- [2. Quality Attribute Overview](#2-quality-attribute-overview)
- [3. Complexity](#3-complexity)
- [4. Dependency Quality](#4-dependency-quality)
- [5. Determinism and Reproducibility](#5-determinism-and-reproducibility)
- [6. Maintainability](#6-maintainability)
- [7. Coupling and Cohesion](#7-coupling-and-cohesion)
- [8. Evolution and Change Activity](#8-evolution-and-change-activity)
- [9. Security](#9-security)
- [10. Reliability](#10-reliability)

## 1. Scope and Conventions

### 1.1 Output Convention

The before/after pipeline reports most metrics with paired fields:
- `*_Before`
- `*_After`
- `*_Delta` when a direct delta is meaningful

When the GitHub commit runner is used, the pipeline also creates a per-commit output directory:
- `results/commits/<commit_sha>/`

That directory contains one CSV per focused view for the changed build files in that commit:
- `summary_metrics.csv`
- `maintainability_metrics.csv`
- `understandability_metrics.csv`
- `modularity_metrics.csv`
- `security_metrics.csv`
- `reliability_metrics.csv`

Each CSV stores one row per changed build file in that commit, including the full `File_Path`, the `File_Name`, and the metrics for that quality view. The pipeline does not create separate per-file CSV folders inside the commit directory.

The formulas below are written for a single build file `b`. The pipeline applies the same definitions to both snapshots.

### 1.2 Common Base Measures

Several quality attributes reuse the same base quantities.

| Symbol / Metric | Definition | Calculation |
|---|---|---|
| `BLOC(b)` | Build lines of code for build file `b`. | Obtained from `scc` as the `Code` count for the file. |
| `Lines(b)` | Total physical line count. | Obtained from `scc` as the `Lines` count. |
| `CommentLines(b)` | Number of comment lines. | Obtained from `scc` as the `Comment` count. |
| `NonEmptyLines(b)` | Number of non-blank lines. | Available as an auxiliary line-count measure when blank-line filtering is needed. |

### 1.3 Scope Notes

- `Build_Modularity_*` fields are referenced by the pipeline, but the implementation source is not present in the current workspace. They are therefore not treated as documented metrics in this README.
- Conceptual or proposed metrics that are not currently computed by the pipeline are intentionally omitted.
- When a metric is unsupported for a specific build syntax, that limitation is stated explicitly in the relevant section.

## 2. Quality Attribute Overview

| Quality Attribute | Low-Level Metrics | Derived / Aggregate Metrics |
|---|---|---|
| Complexity | `BLOC`, `Cyclomatic_Complexity`, `Normalized_CC`, `Halstead_Volume`, `Normalized_HV` | none |
| Dependency Quality | `Dependency_Count`, `Fixed_Dependency_Count`, `Dynamic_Dependency_Count`, `Snapshot_Dependency_Count`, `Unknown_Dependency_Count` | `DSS` |
| Determinism and Reproducibility | `Non_Deterministic_Constructs`, `Non_Deterministic_Summary` | `BDS` |
| Understandability | `Style_Conformance_Score`, `Comment_Ratio`, `Comment_Readability`, `Normalized_CC`, `Normalized_HV`, `Clone_Density` | methodology-level `US` |
| Maintainability | `BLOC`, `Cyclomatic_Complexity`, `Normalized_CC`, `Halstead_Volume`, `Normalized_HV`, `Clone_Density`, `Maintainability_Smell_Count`, `Maintainability_Smell_Density`, `Maintainability_Smell_Summary` | methodology-level `Maintainability` |
| Coupling and Cohesion | `CP_Internal`, `CP_External`, `CP_Total`, `NCP_Internal`, `NCP_External`, `Coupling_Ratio`, `Build_Cohesion` | `EDR` reuses coupling components |
| Modularity | `CP_Internal`, `CP_External`, `NCP_Internal`, `NCP_External`, `Build_Cohesion`, `Clone_Density` | methodology-level `MS`; focused `modularity_metrics.csv` export |
| Evolution and Change Activity | `Churn`, `Change_Frequency`, `Avg_Logical_LOC`, `Normalized_Churn`, `Normalized_Change_Frequency` | none |
| Security | `Security_Smell_Count`, `Security_Smell_Density`, `Security_Smell_Summary`, `HARDCODED_CREDENTIALS`, `INSECURE_URLS`, `WILDCARD_USAGE`, `HARDCODED_PATHS_AND_URLS`, `DEPRECATED_DEPENDENCIES`, `OUTDATED_DEPENDENCIES` | focused `security_metrics.csv` export |
| Reliability | `RE`, `DSS`, `EDR` | focused `reliability_metrics.csv` export |

`Style_Conformance_Score` is a normalized metric in the `0..1` range:

```text
Style_Conformance_Score(b) = max(0, 1 - (violations(b) / BLOC(b)))
```

The pipeline also emits a focused understandability output file:
- `results/understandability_metrics.csv`

## 3. Complexity

Complexity captures the structural and cognitive burden of understanding and modifying a build script.

### 3.1 Low-Level Metrics

| Metric | Definition | Formula |
|---|---|---|
| `BLOC` | Build lines of code. | `BLOC(b) = code_lines(b)` |
| `Cyclomatic_Complexity` | File-level decision or build-logic complexity. | Build-system-specific calculation described below. |
| `Normalized_CC` | Size-normalized complexity. | `Normalized_CC(b) = Cyclomatic_Complexity(b) / BLOC(b)` |
| `Halstead_Volume` | Halstead volume of the build script. | `HV(b) = (N1 + N2) * log2(n1 + n2)` |
| `Normalized_HV` | Size-normalized Halstead volume. | `Normalized_HV(b) = Halstead_Volume(b) / BLOC(b)` |

### 3.2 Build-System-Specific Calculation

#### Gradle Groovy DSL

- `Cyclomatic_Complexity` is computed with CodeNarc and aggregated at file level.
- `Halstead_Volume` is computed from a Groovy AST-based operator/operand extractor.

#### Gradle Kotlin DSL

- `Cyclomatic_Complexity` is computed with detekt by summing file-level `CyclomaticComplexMethod` findings.
- `Halstead_Volume` is currently not implemented for Kotlin DSL in this pipeline, so the emitted value is `0.0`.

#### Maven

`Cyclomatic_Complexity` is implemented as a build-logic complexity heuristic:

```text
BLC_maven = 1 + count(profile) + count(activation) + count(execution)
```

`Halstead_Volume` is computed from XML structure:
- operators: XML tag names
- operands: child-tag occurrences

#### Ant

`Cyclomatic_Complexity` is implemented as a build-logic complexity heuristic:

```text
BLC_ant = 1
        + count(condition/operator tags)
        + count(if attributes)
        + count(unless attributes)
        + count(extra dependency edges from depends)
```

`Halstead_Volume` is computed from XML structure:
- operators: non-`project` and non-`description` XML tags
- operands: attribute names

## 4. Dependency Quality

Dependency quality reflects how explicitly and stably a build file declares the external artifacts it consumes.

### 4.1 Low-Level Metrics

| Metric | Definition | Formula |
|---|---|---|
| `Dependency_Count` | Total number of detected dependencies considered by the parser. | Count of parsed dependency declarations. |
| `Fixed_Dependency_Count` | Dependencies pinned to a fixed release version. | Count of dependencies classified as `fixed`. |
| `Dynamic_Dependency_Count` | Dependencies declared with dynamic or range-based versions. | Count of dependencies classified as `dynamic`. |
| `Snapshot_Dependency_Count` | Dependencies declared with snapshot-style versions. | Count of dependencies classified as `snapshot`. |
| `Unknown_Dependency_Count` | Dependencies whose version cannot be resolved to a concrete version from file contents. | Count of dependencies classified as `unknown`. |
| `DSS` | Dependency Stability Score. | `DSS(b) = Fixed_Dependency_Count(b) / Dependency_Count(b)` |

If `Dependency_Count(b) = 0`, the implementation returns:

```text
DSS(b) = 0.0
```

### 4.2 Version Classes

| Class | Meaning | Examples |
|---|---|---|
| `fixed` | Explicit pinned release version. | `1.2.3` |
| `dynamic` | Range, floating, or mutable version expression. | `1.+`, `[1.0,2.0)`, `latest.release` |
| `snapshot` | Snapshot-style mutable version. | `1.2.3-SNAPSHOT` |
| `unknown` | Version not concretely recoverable from file contents. | unresolved property or catalog reference |

### 4.3 Build-System-Specific Calculation

#### Gradle

- Dependency declarations are extracted from string-style and map-style dependency declarations.
- Local property-resolution heuristics are applied before classifying versions.

#### Maven

- Dependency versions are read from dependency declarations.
- If a dependency omits a local version, the pipeline consults local `dependencyManagement` when available.
- Local `<properties>` are resolved before classification.

#### Ant

- Dependencies are inferred from versioned JAR references found in XML attribute values.
- Versions are extracted from JAR file names after resolving simple property references.

## 5. Determinism and Reproducibility

Determinism measures the degree to which a build script avoids constructs that can make repeated executions produce variable results.

### 5.1 Low-Level Metrics

| Metric | Definition | Formula |
|---|---|---|
| `Non_Deterministic_Constructs` | Number of detected non-deterministic constructs. | Count of lines matching any supported non-deterministic construct family. |
| `Non_Deterministic_Summary` | Set of non-deterministic construct families present. | Semicolon-separated set of detected construct labels. |
| `BDS` | Build Script Determinism Score. | `BDS(b) = max(0, 1 - (Non_Deterministic_Constructs(b) / BLOC(b)))` |

If `BLOC(b) = 0`, the implementation returns:

```text
BDS(b) = 0.0
```

### 5.2 Non-Deterministic Construct Families

| Family | Meaning | Representative Examples |
|---|---|---|
| `TIME` | Time-dependent values introduced at build time. | `System.currentTimeMillis()`, `Instant.now()`, `new Date()`, `${maven.build.timestamp}` |
| `RANDOMNESS` | Randomness sources that may change outputs between runs. | `Math.random()`, `new Random()`, `SecureRandom`, `UUID.randomUUID()` |
| `NON_REPRODUCIBLE_STEP` | Explicit mutable fetch or checkout steps. | `curl`, `wget`, `Invoke-WebRequest`, `git clone`, `svn checkout`, Ant `<get>` |

### 5.3 Build-System Coverage

`BDS` is implemented for all supported build systems:
- Gradle
- Maven
- Ant

The current detector is text-based and scans the file contents for the construct families above.

## 6. Maintainability

Maintainability captures how easy a build script is to inspect, modify, and evolve without introducing extra effort or breakage.

For maintainability, this project now considers only:
- `BLOC`
- `Cyclomatic_Complexity`
- `Halstead_Volume`
- `Clone_Density`
- maintainability smells

The pipeline also emits a maintainability-focused output file:
- `results/maintainability_metrics.csv`

### 6.0 Attribute-Level Formula

A maintainability score can be expressed as:

```text
Maintainability(b) =
(
  1 / (1 + BLOC(b))
  + 1 / (1 + Normalized_CC(b))
  + 1 / (1 + Normalized_HV(b))
  + (1 - Clone_Density(b))
  + (1 - MSD(b))
) / 5
```

Where:
- `Normalized_CC(b)` = `Cyclomatic_Complexity(b) / BLOC(b)`
- `Normalized_HV(b)` = `Halstead_Volume(b) / BLOC(b)`
- `MSD(b)` = `Maintainability_Smell_Density`

Interpretation:
- lower build size, lower control-flow complexity, and lower Halstead volume increase maintainability
- higher duplication reduces maintainability through `1 - Clone_Density(b)`
- higher smell density reduces maintainability through inverse normalization

### 6.1 Core Maintainability Metrics

| Metric | Definition | Formula |
|---|---|---|
| `BLOC` | Build lines of code. | `BLOC(b) = code_lines(b)` |
| `Cyclomatic_Complexity` | File-level decision or build-logic complexity. | Build-system-specific calculation described in Section 3.2. |
| `Normalized_CC` | Size-normalized cyclomatic complexity used in the maintainability CSV. | `Normalized_CC(b) = Cyclomatic_Complexity(b) / BLOC(b)` |
| `Halstead_Volume` | Halstead volume of the build script. | `HV(b) = (N1 + N2) * log2(n1 + n2)` |
| `Normalized_HV` | Size-normalized Halstead volume used in the maintainability CSV. | `Normalized_HV(b) = Halstead_Volume(b) / BLOC(b)` |
| `Clone_Density` | Fraction of duplicated build logic lines. | `Clone_Density(b) = duplicated_build_logic_lines(b) / BLOC(b)` |

### 6.2 Maintainability Smell Metrics

| Metric | Definition | Formula |
|---|---|---|
| `Maintainability_Smell_Count` | Number of maintainability smell findings. | Count of detected maintainability smells. |
| `Maintainability_Smell_Density` | Smell density normalized by build lines of code. | `Maintainability_Smell_Density(b) = Maintainability_Smell_Count(b) / BLOC(b)` |
| `Maintainability_Smell_Summary` | Set of maintainability smell categories present. | Semicolon-separated set of smell identifiers. |

The maintainability-focused CSV includes:
- `BLOC_Before` and `BLOC_After`
- `Cyclomatic_Complexity_Before` and `Cyclomatic_Complexity_After`
- `Normalized_CC_Before` and `Normalized_CC_After`
- `Halstead_Volume_Before` and `Halstead_Volume_After`
- `Normalized_HV_Before` and `Normalized_HV_After`
- `Clone_Density_Before` and `Clone_Density_After`
- `Maintainability_Smell_Count_Before` and `Maintainability_Smell_Count_After`
- `Maintainability_Smell_Density_Before` and `Maintainability_Smell_Density_After`
- `Maintainability_Smell_Summary_Before` and `Maintainability_Smell_Summary_After`

Tracked maintainability smell categories:
- `EMPTY_INCOMPLETE_TAGS`
- `INCONSISTENT_DEPENDENCY_MANAGEMENT`
- `LACK_OF_ERROR_HANDLING`
- `MISSING_DEPENDENCY_VERSION`
- `SUSPICIOUS_COMMENTS`
- `DEPRECATED_DEPENDENCIES`
- `OUTDATED_DEPENDENCIES`

### 6.3 Calculation Notes

- `BLOC`, `Cyclomatic_Complexity`, and `Halstead_Volume` reuse the definitions from Section 3.
- `Clone_Density` is computed with PMD CPD when available, with a repeated-line-window fallback when the preferred duplication path is unavailable.
- Maintainability smells are counted without weighting; each finding contributes equally to the smell count.

## 7. Coupling and Cohesion

Coupling and cohesion describe the extent to which build logic is externally connected and internally related.

### 7.1 Coupling Metrics

| Metric | Definition | Formula |
|---|---|---|
| `CP_Internal` | Internal coupling among elements inside the same build file. | `CP_Internal(b) = T_int + V_shared + C_internal` |
| `CP_External` | Coupling driven by external modules, artifacts, repositories, tools, and resources. | `CP_External(b) = M + D + P + R + E + U` |
| `CP_Total` | Total coupling. | `CP_Total(b) = CP_Internal(b) + CP_External(b)` |
| `NCP_Internal` | Size-normalized internal coupling. | `NCP_Internal(b) = CP_Internal(b) / BLOC(b)` |
| `NCP_External` | Size-normalized external coupling. | `NCP_External(b) = CP_External(b) / BLOC(b)` |
| `Coupling_Ratio` | Share of total coupling that is external. | `Coupling_Ratio(b) = CP_External(b) / CP_Total(b)` |

Component meanings:
- `T_int`: internal task or target dependency links
- `V_shared`: variables or properties shared by multiple internal elements
- `C_internal`: internal configuration references reused across elements
- `M`: inter-module references
- `D`: external dependencies
- `P`: plugins
- `R`: repositories or remote artifact sources
- `E`: external commands or build-script execution hooks
- `U`: environment variables, absolute paths, and URL-based resources

### 7.2 Cohesion Metric

| Metric | Definition | Formula |
|---|---|---|
| `Build_Cohesion` | Average pairwise feature overlap among build elements. | Average pairwise Jaccard similarity across extracted element feature sets. |

The elements compared depend on the build system:
- Gradle: task feature sets
- Maven: plugin execution feature sets
- Ant: target feature sets

### 7.3 Modularity Formula

Modularity is not currently exported as a standalone implemented pipeline field in this workspace, but it can be operationalized from cohesion and coupling as:

```text
MS(b) =
(
  Build_Cohesion(b)
  + (1 - Coupling_Ratio(b))
  + 1 / (1 + NCP_External(b))
  + (1 - Clone_Density(b))
) / 4
```

Where:
- `MS(b)` = modularity score
- `Build_Cohesion(b)` rewards stronger internal relatedness of build elements
- `1 - Coupling_Ratio(b)` rewards a lower proportion of external coupling
- `1 / (1 + NCP_External(b))` rewards lower size-normalized external coupling
- `1 - Clone_Density(b)` rewards lower duplication across build logic

Interpretation:
- higher cohesion, lower external coupling, and lower duplication indicate stronger modularity

The pipeline also emits a focused modularity output file with the separately tracked low-level metrics:
- `results/modularity_metrics.csv`

The modularity-focused CSV includes:
- `CP_Internal_Before` and `CP_Internal_After`
- `CP_External_Before` and `CP_External_After`
- `NCP_Internal_Before` and `NCP_Internal_After`
- `NCP_External_Before` and `NCP_External_After`
- `Build_Cohesion_Before` and `Build_Cohesion_After`
- `Clone_Density_Before` and `Clone_Density_After`

## 8. Evolution and Change Activity

Evolution metrics characterize how frequently a build file changes and how much code churn it experiences over time.

### 8.1 Low-Level Metrics

| Metric | Definition | Formula |
|---|---|---|
| `Churn` | Total added and deleted lines over the observation window. | `Churn(f, T) = sum(added_lines + deleted_lines)` |
| `Change_Frequency` | Number of commits touching the file during the observation window. | `Change_Frequency(f, T) = number_of_commits_touching_f` |
| `Avg_Logical_LOC` | Average logical LOC of the file over historical snapshots in the window. | Mean historical `BLOC` across the observation window. |
| `Normalized_Churn` | Size-normalized churn. | `Normalized_Churn(f, T) = Churn(f, T) / Avg_Logical_LOC(f, T)` |
| `Normalized_Change_Frequency` | Size-normalized change frequency. | `Normalized_Change_Frequency(f, T) = (Change_Frequency(f, T) / Avg_Logical_LOC(f, T)) * 100` |

The current before/after pipeline uses a rolling observation window ending at the analyzed commit.

## 9. Security

Security is characterized through smell-based indicators rather than a single aggregate security score.

### 9.0 Attribute-Level Formula

A security score can be operationalized directly from the security smell density:

```text
SS(b) = max(0, 1 - (Security_Smell_Count(b) / max(BLOC(b), 1)))
```

Equivalently, using the documented density metric:

```text
SS(b) = max(0, 1 - Security_Smell_Density(b))
```

Where:
- `SS(b)` = security score
- `Security_Smell_Count(b)` counts security smell findings
- `Security_Smell_Density(b)` normalizes those findings by build lines of code

Interpretation:
- more security smells imply lower security

### 9.1 Security Smell Metrics

| Metric | Definition | Formula |
|---|---|---|
| `Security_Smell_Count` | Number of detected security smell findings. | Count of detected security smells. |
| `Security_Smell_Density` | Security smell density normalized by build lines of code. | `Security_Smell_Density(b) = Security_Smell_Count(b) / BLOC(b)` |
| `Security_Smell_Summary` | Set of security smell categories present. | Semicolon-separated set of smell identifiers. |

Tracked security smell categories:
- `HARDCODED_CREDENTIALS`
- `INSECURE_URLS`
- `WILDCARD_USAGE`
- `HARDCODED_PATHS_AND_URLS`
- `DEPRECATED_DEPENDENCIES`
- `OUTDATED_DEPENDENCIES`

The pipeline also emits a focused security output file:
- `results/security_metrics.csv`

The security-focused CSV includes:
- `Before_Security_Smell_Count` and `After_Security_Smell_Count`
- `Before_Security_Smell_Density` and `After_Security_Smell_Density`
- `Before_Security_Smell_Summary` and `After_Security_Smell_Summary`
- `Before_HARDCODED_CREDENTIALS` and `After_HARDCODED_CREDENTIALS`
- `Before_INSECURE_URLS` and `After_INSECURE_URLS`
- `Before_WILDCARD_USAGE` and `After_WILDCARD_USAGE`
- `Before_HARDCODED_PATHS_AND_URLS` and `After_HARDCODED_PATHS_AND_URLS`
- `Before_DEPRECATED_DEPENDENCIES` and `After_DEPRECATED_DEPENDENCIES`
- `Before_OUTDATED_DEPENDENCIES` and `After_OUTDATED_DEPENDENCIES`

## 10. Reliability

Reliability captures build-script robustness using issue density, dependency stability, and external-system reliance.

### 10.1 Low-Level and Derived Metrics

| Metric | Definition | Formula |
|---|---|---|
| `Reliability_Issues` | Total count of reliability-relevant smell findings. | `RI(b) = HC(b) + IU(b) + WU(b) + HP(b) + DD(b) + OD(b)` |
| `RE` | Issue-based reliability score. | `RE(b) = max(0, 1 - (RI(b) / BLOC(b)))` |
| `EDR` | External Dependency Risk. | `EDR(b) = (D + P + R + E + U) / CP_Total(b)` |
| `RM` | Overall reliability metric. | `RM(b) = (RE(b) + DSS(b) + (1 - EDR(b))) / 3` |

Where:
- `HC` = hardcoded credentials count
- `IU` = insecure URLs count
- `WU` = wildcard usage count
- `HP` = hardcoded paths or URLs count
- `DD` = deprecated dependencies count
- `OD` = outdated dependencies count

### 10.2 Reliability Interpretation

- higher `RE` means fewer reliability issues per build line
- higher `DSS` means a larger share of dependencies are pinned to fixed versions
- lower `EDR` means less reliance on external systems

The pipeline also emits a focused reliability output file:
- `results/reliability_metrics.csv`

The reliability-focused CSV includes:
- `RE_Before` and `RE_After`
- `DSS_Before` and `DSS_After`
- `EDR_Before` and `EDR_After`
- higher `RM` therefore indicates a more reliable build file overall

### 10.3 Attribute-Level Formula

The overall reliability metric used in this project is:

```text
RM(b) = (RE(b) + DSS(b) + (1 - EDR(b))) / 3
```

This combines:
- issue-based reliability through `RE`
- dependency stability through `DSS`
- reduced external-system exposure through `1 - EDR`

### 10.4 External Dependency Risk Details

`EDR` is derived from the coupling model:

```text
EDR(b) = (D + P + R + E + U) / CP_Total(b)
```

Local module links `M` are intentionally excluded from the `EDR` numerator because they represent project-internal structure rather than reliance on external systems.

### 10.5 Composite Reliability Scope

The current implementation keeps two reliability views:
- `RE`: issue-based reliability derived only from reliability issues and `BLOC`
- `RM`: overall reliability derived from `RE`, `DSS`, and `EDR`

`BDS` is intentionally not folded into `RM` in the current pipeline; it remains a separate determinism attribute.
