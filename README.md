
# Build Metrics (Gradle, Maven, Ant)

## 1- Complexity

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
- `HC` = Halsted Complexity
- `SCS` = % of lines following style. 
- `CR` = Comment Ratio   (Comment Lines / Total Lines))  
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
## 2- Dependency Quality

A weighted formula:

```
 w₁ * (1 - UDR) + w₂ * (1 - DCR)
```

**Where:**
- `UDR` = Unused Dependency Ratio  
- `DCR` = Dependency Conflict Rat
---

## 2- Maintainability

```
Maintainability = f(Complexity, Coupling, Cohesion, Dependency Quality)
```


---

## 3- Coupling and Cohesion Metrics

## 🧹 1. Gradle

### ✅ **Coupling (Gradle)**

**Definition**: Measures the extent to which a build script depends on external scripts, modules, plugins, or classes.

**Sources of Coupling in Gradle:**
- `apply from: 'common.gradle'` → external script
- `apply plugin: 'custom-plugin'` → external plugin
- `project(':lib')` → external module
- `import some.external.Class` → imported Java/Groovy classes
- `task X { dependsOn ':other:task' }` → external task dependency

**Metric Formula:**
```math
Coupling = \frac{\text{# of External References}}{\text{Total References}}
```

**Example:**
```groovy
apply from: '../common.gradle'
apply plugin: 'custom-plugin'
import org.apache.commons.io.FileUtils

task clean { dependsOn ':lib:clean' }
```

- External References: 4  
- Total References: 5  
- Coupling = 4 / 5 = 0.80

---

### ✅ **Cohesion (Gradle)**

**Definition**: Measures how closely related the tasks in a build script are to one another.

**Indicators of Cohesion:**
- Tasks sharing variables (e.g., `buildDir`, `ext`)
- Tasks depending on other tasks *within the same script*
- Shared configuration blocks or logic

**Metric Formula:**
```math
Cohesion = \frac{\text{# of Related Task Pairs}}{\text{Total Task Pairs}}
```

**Example:**
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

- Related Task Pairs: 1 (`compile ↔ archive`)  
- Total Task Pairs: 1  
- Cohesion = 1 / 1 = 1.0

---

## 🛠 2. Maven

### ✅ **Coupling (Maven)**

**Sources of Coupling in Maven:**
- `<plugin>` elements referencing external coordinates
- `<parent>` elements
- `<dependency>` referencing external modules
- `<import>` scope or system-scope references

**Metric Formula:**
```math
Coupling = \frac{\text{# of External References}}{\text{Total References}}
```

**Example:**
```xml
<parent>
  <groupId>org.springframework.boot</groupId>
</parent>
<dependencies>
  <dependency>
    <groupId>com.external.lib</groupId>
  </dependency>
</dependencies>
```

- External References: 2  
- Total References: 2  
- Coupling = 1.0

---

### ✅ **Cohesion (Maven)**

**Indicators of Cohesion:**
- `<executions>` of plugins that refer to each other
- Shared `<properties>` used across multiple plugin executions
- Profile inheritance of common settings

**Metric Formula:**
```math
Cohesion = \frac{\text{# of Related Plugin Executions}}{\text{Total Executions}}
```

---

## 🛠 3. Ant

### ✅ **Coupling (Ant)**

**Sources of Coupling:**
- `<import file="common.xml" />` or `<include file="common.xml" />`
- `<taskdef>` defining tasks via external `.jar` or class
- `<property file="config.properties" />`

**Metric Formula:**
```math
Coupling = \frac{\text{# of External Imports}}{\text{Total Task References}}
```

---

### ✅ **Cohesion (Ant)**

**Indicators:**
- Targets depending on other targets (`depends="compile"`)
- Use of shared properties
- Sequential usage of common files or paths


## 🔁 Unified Metric for All Build Systems

### ✅ **Coupling (Unified Formula):**
```math
Coupling = \frac{\text{# of External References (imports, plugins, cross-modules)}}{\text{Total References (tasks, plugins, properties)}}
```

### ✅ **Cohesion (Unified Formula):**
```math
Cohesion = \frac{\text{# of Internally Related Pairs}}{\text{Total Possible Pairs}}
```

- Related pairs: Shared variables, inter-task/target/plugin execution  
- Total pairs: \( \frac{n(n - 1)}{2} \) for `n` tasks/targets/executions

 Unified Reference Types

We can define references under two categories:

🔹 External References (counted in numerator):


	•	Imported scripts or modules (Gradle apply from, Ant <import>, Maven <parent>)
	•	External plugins or taskdefs
	•	External dependencies (libraries, classes, modules)
	•	External property files or property inheritance

🔸 Total References (counted in denominator):


	•	All of the above, plus:
	•	Local tasks/targets/plugins
	•	Internal dependsOn or depends
	•	Internal property and variable usages

⸻

🧮 Coupling Metric (Unified):

Coupling = \frac{\text{# of External References}}{\text{Total References}}





# ✨ What is Cohesion?

**Cohesion** refers to how closely related and interconnected different parts of a build script are. In Gradle, this typically means analyzing how tasks, variables, plugins, and configuration blocks relate to one another.

---

## ✅ Elements Contributing to Cohesion in Gradle

| Element                        | Contributes to Cohesion? | Explanation |
|-------------------------------|---------------------------|-------------|
| **Tasks**                     | ✅                        | Tasks that depend on each other or use shared logic/variables. |
| **Shared Variables (`ext`)**  | ✅                        | When defined variables (e.g., `ext.outputDir`) are used by multiple tasks. |
| **Common Configuration Blocks** | ✅                      | Settings reused across multiple plugins/tasks. |
| **Plugin Configurations**     | ✅                        | Plugins that configure multiple build components similarly. |
| **Custom Functions/Methods**  | ✅                        | Reusable logic used in different script sections. |
| **Internal Property References** | ✅                    | Use of project-level values (`buildDir`, `version`) across multiple places. |

---

## ❌ What Does NOT Contribute to Cohesion

| Element                   | Reason |
|---------------------------|--------|
| **Isolated Tasks**        | No shared dependencies, variables, or logic. |
| **Independent Blocks**    | Defined elements that don’t interact with others. |
| **Unused `ext` Properties** | Declared but not used elsewhere. |

---

## 🧰 Cohesion Metric Formula (Refined)

```math
Cohesion = \frac{\text{# of Related Element Pairs}}{\text{Total Element Pairs}}
```

Where:
- **Element** = tasks, configuration blocks, variables, plugin configurations
- **Related Pair** = two elements that share a variable, logic, or have a task dependency
- **Total Pairs** = \( \frac{n(n-1)}{2} \), for `n` elements considered

---

## 📅 Example

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

- **Elements**: `compile`, `archive`, `outputDir`
- **Related Pairs**: `compile-archive` (shared variable + dependency)
- **Total Pairs**: 3
- **Cohesion** = 1 / 3 ≈ **0.33** (if counting only 1 strong relation)

> *Note: More shared variables or inter-task dependencies would increase cohesion.*


---

## 3- Code Duplication


## 🌐 Definition

**Code duplication** in build systems refers to identical or near-identical logic repeated across build configuration files. This could include repeated tasks, dependencies, or configuration blocks.

Excessive duplication increases maintenance overhead, makes debugging harder, and reduces the modularity and quality of the build script.

---

## 🔢 Code Duplication Metric (CDM)

```math
CDM = \frac{\text{Total Duplicated Lines}}{\text{Total Significant Lines}}
```

### Where:

- **Duplicated Lines**: Lines that appear in multiple places (identical or semantically similar).
- **Significant Lines**: All lines excluding comments, whitespace, and boilerplate.

A high CDM indicates high redundancy and poor maintainability.

---

## 🎓 Example (Gradle)

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

## 📚 Example (Maven)

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

## 🔍 Detection Methods

- **AST-Based Clone Detection**: Normalize and parse the Abstract Syntax Tree of build files to detect structure-level clones.
- **Token-Based Detection**: Count repeated blocks of tokens or lines.
- **Semantic Detection**: Identify logically equivalent code even if written differently.

---

# 🧬 Definition

Security in build systems refers to the extent to which the build configuration protects the software from introducing vulnerabilities via:

- Insecure or outdated dependencies
- Use of scripts or plugins from untrusted sources
- Hardcoded credentials or sensitive information
- Missing integrity verification (e.g., checksums)

---

## 🖐️ Proposed Security Metric (SM)

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

## 🧪 Examples

### Example 1: Gradle

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

Security Metric:

```math
SM = 1 - (1 + 1 + 0 + 0) / 3 = 1 - 2/3 = 0.33
```

---

## 🔍 Detection Tools

- **Dependency Scanners**: OWASP Dependency-Check, Snyk, OSS Index
- **Secret Scanners**: TruffleHog, GitLeaks
- **Lint Rules**: Custom Gradle or Maven linters to detect insecure configurations

---

# ⏱️ Build Run Time (BRT) Metric

## 🧬 Definition

**Build Run Time (BRT)** refers to the total time taken to execute a full build process from start to finish. This includes:

- Dependency resolution
- Compilation
- Testing
- Packaging
- Any custom build steps (e.g., signing, deployment)

BRT is a key performance metric to evaluate the efficiency and responsiveness of build systems such as Gradle, Maven, and Ant.

---

## 🧮 Metric Formula

```math
BRT = \text{End Time} - \text{Start Time}
```

- **Start Time**: Timestamp when the build begins
- **End Time**: Timestamp when the build completes

### Units:
- Measured in **seconds** or **milliseconds** depending on the granularity

A lower BRT is desirable and indicates a more efficient build configuration.

---


# 📘 Halstead Complexity Metric: Operator and Operand Definitions for Build Systems

This document describes how **operators** and **operands** are identified for computing Halstead Complexity in three build systems: **Gradle**, **Maven**, and **Ant**.

The authoritative implementation lives in [`metrics/halstead_volume.py`](/Users/aghammam/Desktop/BuildRefMiner/metrics/halstead_volume.py), with [`metrics/halstead_groovy_ast.groovy`](/Users/aghammam/Desktop/BuildRefMiner/metrics/halstead_groovy_ast.groovy) used as the Gradle/Groovy AST helper.

---

## 🔧 Gradle (Groovy DSL)

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

## 🧩 Maven (XML-based POM)

- **Operators**:
  - All XML tags, such as `<project>`, `<build>`, `<plugin>`, `<execution>`, etc.

- **Operands**:
  - All child XML tags of the operator tags
  - Example: in `<plugin><artifactId>maven-compiler-plugin</artifactId></plugin>`, `<plugin>` is an operator and `<artifactId>` is an operand

> **Note**: This follows the McIntosh et al. definition used in the repo: every Maven XML tag is counted as an operator, and child XML tags are counted as operands.

---

## 🛠️ Ant (XML-based)

- **Operators**:
  - Ant target and task tags, such as `<target>`, `<property>`, `<mkdir>`, `<javac>`, `<delete>`, and `<echo>`
  - The root `<project>` tag and `<description>` are excluded from the repo's implementation

- **Operands**:
  - Parameter names passed to target or task tags
  - The `name` parameter of `<target>` is excluded

> **Example**: In `<javac srcdir="${src.dir}" destdir="${build.dir}"/>`, `javac` is an operator and `srcdir`, `destdir` are operands.

> **Note**: This follows the McIntosh et al. definition adapted in the repo: ANT targets and tasks are operators, while their parameters are operands, excluding the target `name` parameter.

---

## 📏 Formula (All Build Systems)

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
