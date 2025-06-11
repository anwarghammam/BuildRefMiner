
# Build Metrics (Gradle, Maven, Ant)

## 1- Complexity

A weighted formula:

```
Complexity = w₁ * (1 / CC)
           + w₂ * (1 / HC)
           + w₃ * SCS 
           + w₄ * CR    
           + w₅ * (1 / log(LOC + 2)) 
           + w₆ * (1 - UDR) 
           + w₇ * (1 - DCR)
```

**Where:**
- `CC` = Cyclomatic Complexity  
- `HC` = Halsted Complexity
- `SCS` = % of lines following style. 
- `CR` = Comment Ratio   (Comment Lines / Total Lines))  
- `LOC` = Lines of Code  
- `UDR` = Unused Dependency Ratio  
- `DCR` = Dependency Conflict Ratio  

---

### SCS (Style conformance)

```
SCS = (1 - V / LOC) * 100
```

- `V` = (number of lines containing violations)  
- `LOC` = Lines of Code

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

**Metric Formula:**
```math
Cohesion = \frac{\text{# of Dependent Targets}}{\text{Total Target Pairs}}
```

---

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
