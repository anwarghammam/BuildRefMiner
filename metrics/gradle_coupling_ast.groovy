import groovy.json.JsonOutput
import org.codehaus.groovy.ast.*
import org.codehaus.groovy.ast.expr.*
import org.codehaus.groovy.ast.stmt.*
import org.codehaus.groovy.control.*
import org.codehaus.groovy.control.SourceUnit
import org.codehaus.groovy.ast.ClassCodeVisitorSupport

def emptyResult = {
    [
        t_int: 0,
        v_shared: 0,
        c_internal: 0,
        m: 0,
        d: 0,
        p: 0,
        r: 0,
        e: 0,
        u: 0,
    ]
}

if (args.length == 0) {
    println JsonOutput.toJson(emptyResult())
    System.exit(0)
}

File f = new File(args[0])
if (!f.exists()) {
    println JsonOutput.toJson(emptyResult())
    System.exit(0)
}

Set<String> DEPENDENCY_METHODS = [
    "api", "implementation", "compileOnly", "runtimeOnly", "compile",
    "testImplementation", "testCompile", "androidTestImplementation",
    "androidTestCompile", "annotationProcessor", "kapt",
] as Set

Set<String> REPOSITORY_METHODS = [
    "mavenCentral", "google", "gradlePluginPortal",
    "mavenLocal", "jcenter", "ivy", "maven",
] as Set

Set<String> TASK_DEP_METHODS = [
    "dependsOn", "mustRunAfter", "shouldRunAfter", "finalizedBy",
] as Set

Set<String> EXTERNAL_COMMAND_METHODS = [
    "exec", "javaexec", "commandLine",
] as Set

Set<String> taskNames = new LinkedHashSet<>()
Map<String, ClosureExpression> taskClosures = [:]
Set<String> declaredVars = new LinkedHashSet<>()
Set<String> externalModules = new LinkedHashSet<>()
Set<String> externalPlugins = new LinkedHashSet<>()
Set<String> externalRepositories = new LinkedHashSet<>()
Set<String> envResources = new LinkedHashSet<>()
int externalDependencies = 0
int externalCommands = 0

List<String> extractStringLiterals(Expression expr) {
    if (expr == null) {
        return []
    }

    if (expr instanceof ConstantExpression) {
        def value = expr.value
        return value == null ? [] : [value.toString()]
    }

    if (expr instanceof GStringExpression) {
        def text = expr.strings.collect { it.text }.join("")
        return text ? [text] : []
    }

    if (expr instanceof ArgumentListExpression || expr instanceof TupleExpression) {
        return expr.expressions.collectMany { extractStringLiterals(it) }
    }

    if (expr instanceof ListExpression) {
        return expr.expressions.collectMany { extractStringLiterals(it) }
    }

    if (expr instanceof NamedArgumentListExpression) {
        return expr.mapEntryExpressions.collectMany { extractStringLiterals(it.valueExpression) }
    }

    if (expr instanceof MapExpression) {
        return expr.mapEntryExpressions.collectMany { extractStringLiterals(it.valueExpression) }
    }

    if (expr instanceof NamedArgumentListExpression) {
        return expr.mapEntryExpressions.collectMany { extractStringLiterals(it.valueExpression) }
    }

    return []
}

Map<String, String> extractNamedArgs(MethodCallExpression call) {
    Map<String, String> out = [:]
    Expression argsExpr = call.arguments
    List<Expression> expressions = []

    if (argsExpr instanceof TupleExpression) {
        expressions = argsExpr.expressions
    } else if (argsExpr instanceof NamedArgumentListExpression) {
        expressions = [argsExpr]
    }

    expressions.each { expr ->
        if (!(expr instanceof NamedArgumentListExpression)) {
            return
        }
        expr.mapEntryExpressions.each { entry ->
            def key = entry.keyExpression?.text
            def val = extractStringLiterals(entry.valueExpression)
            if (key && val) {
                out[key] = val[0]
            }
        }
    }
    return out
}

ClosureExpression extractClosureArg(MethodCallExpression call) {
    Expression argsExpr = call.arguments
    if (argsExpr instanceof ClosureExpression) {
        return (ClosureExpression) argsExpr
    }
    if (argsExpr instanceof TupleExpression) {
        for (int i = argsExpr.expressions.size() - 1; i >= 0; i--) {
            Expression expr = argsExpr.expressions[i]
            if (expr instanceof ClosureExpression) {
                return (ClosureExpression) expr
            }
        }
    }
    return null
}

String detectTaskName(MethodCallExpression call) {
    def method = call.methodAsString ?: ""
    def objectText = call.objectExpression?.text ?: ""
    def stringArgs = extractStringLiterals(call.arguments)

    if (method == "task" && stringArgs) {
        return stringArgs[0]
    }

    if (["register", "named", "create"].contains(method) && objectText == "tasks" && stringArgs) {
        return stringArgs[0]
    }

    return null
}

boolean looksLikeAbsolutePath(String value) {
    return value ==~ /^\/[^"']+$/ || value ==~ /^[A-Za-z]:[\\\/][^"']+$/
}

void recordResourceIfRelevant(String value, Set<String> envResources) {
    if (!value) {
        return
    }

    if (value.startsWith("http://") || value.startsWith("https://") || looksLikeAbsolutePath(value)) {
        envResources.add(value)
    }
}

try {
    def config = new CompilerConfiguration()
    def unit = new CompilationUnit(config)
    unit.addSource(f)
    unit.compile(Phases.CONVERSION)

    def collector = new ClassCodeVisitorSupport() {
        @Override
        protected SourceUnit getSourceUnit() { return null }

        @Override
        void visitDeclarationExpression(DeclarationExpression expr) {
            def left = expr.leftExpression
            if (left instanceof VariableExpression && left.name) {
                declaredVars.add(left.name)
            }
            super.visitDeclarationExpression(expr)
        }

        @Override
        void visitConstantExpression(ConstantExpression expr) {
            if (expr.value != null) {
                recordResourceIfRelevant(expr.value.toString(), envResources)
            }
            super.visitConstantExpression(expr)
        }

        @Override
        void visitMethodCallExpression(MethodCallExpression call) {
            def method = call.methodAsString ?: ""
            def stringArgs = extractStringLiterals(call.arguments)
            def namedArgs = extractNamedArgs(call)
            def taskName = detectTaskName(call)

            if (taskName) {
                taskNames.add(taskName)
                def closure = extractClosureArg(call)
                if (closure != null) {
                    taskClosures[taskName] = closure
                }
            }

            if (method == "project" && stringArgs) {
                externalModules.addAll(stringArgs.findAll { it.startsWith(":") || it })
            }

            if (DEPENDENCY_METHODS.contains(method)) {
                boolean counted = false
                if (!stringArgs.isEmpty()) {
                    counted = stringArgs.any { it.count(":") >= 2 || (it.count(":") == 1 && !it.startsWith(":")) }
                }
                if (!counted && (call.arguments instanceof TupleExpression)) {
                    counted = call.arguments.expressions.any { it instanceof NamedArgumentListExpression || it instanceof MapExpression }
                }
                if (counted) {
                    externalDependencies++
                }
            }

            if (method == "id" && stringArgs) {
                externalPlugins.add(stringArgs[0])
            }

            if (method == "apply") {
                if (namedArgs.containsKey("plugin")) {
                    externalPlugins.add(namedArgs["plugin"])
                }
                if (namedArgs.containsKey("from")) {
                    externalCommands++
                    recordResourceIfRelevant(namedArgs["from"], envResources)
                }
            }

            if (REPOSITORY_METHODS.contains(method)) {
                externalRepositories.add(method)
                stringArgs.each { value -> recordResourceIfRelevant(value, envResources) }
            }

            if (EXTERNAL_COMMAND_METHODS.contains(method)) {
                externalCommands++
            }

            if ((method == "getenv" && call.objectExpression?.text == "System") || method == "getProperty") {
                stringArgs.each { value -> envResources.add("env:${value}") }
            }

            super.visitMethodCallExpression(call)
        }
    }

    unit.ast.modules.each { ModuleNode m ->
        m.statementBlock?.visit(collector)
        m.classes.each { ClassNode cn ->
            cn.methods.each { MethodNode mn ->
                mn.code?.visit(collector)
            }
        }
    }

    Map<String, Set<String>> taskDependencyRefs = [:].withDefault { new LinkedHashSet<>() }
    Map<String, Set<String>> taskPropertyRefs = [:].withDefault { new LinkedHashSet<>() }
    Map<String, Set<String>> taskConfigRefs = [:].withDefault { new LinkedHashSet<>() }

    taskClosures.each { String taskName, ClosureExpression closureExpr ->
        def taskVisitor = new ClassCodeVisitorSupport() {
            @Override
            protected SourceUnit getSourceUnit() { return null }

            @Override
            void visitMethodCallExpression(MethodCallExpression call) {
                def method = call.methodAsString ?: ""
                def stringArgs = extractStringLiterals(call.arguments)

                if (TASK_DEP_METHODS.contains(method)) {
                    taskDependencyRefs[taskName].addAll(stringArgs)
                }

                if (method == "findProperty" && stringArgs) {
                    taskPropertyRefs[taskName].add("property:${stringArgs[0]}")
                }

                if (method == "property" && stringArgs) {
                    taskPropertyRefs[taskName].add("property:${stringArgs[0]}")
                }

                if (["inputs", "outputs", "sourceSets", "configurations"].contains(method)) {
                    taskConfigRefs[taskName].add("config:${method}")
                }

                super.visitMethodCallExpression(call)
            }

            @Override
            void visitVariableExpression(VariableExpression expr) {
                if (expr.name && declaredVars.contains(expr.name)) {
                    taskPropertyRefs[taskName].add("var:${expr.name}")
                }
                super.visitVariableExpression(expr)
            }

            @Override
            void visitPropertyExpression(PropertyExpression expr) {
                def text = expr.text ?: ""
                if (text.startsWith("ext.")) {
                    taskPropertyRefs[taskName].add("property:${expr.propertyAsString}")
                }
                if (
                    text.startsWith("sourceSets.") ||
                    text.startsWith("inputs.") ||
                    text.startsWith("outputs.") ||
                    text.startsWith("configurations.")
                ) {
                    taskConfigRefs[taskName].add("config:${text}")
                }
                super.visitPropertyExpression(expr)
            }
        }

        closureExpr.code?.visit(taskVisitor)
    }

    int tInt = 0
    taskDependencyRefs.each { String sourceTask, Set<String> refs ->
        refs.each { ref ->
            if (ref && taskNames.contains(ref) && ref != sourceTask) {
                tInt++
            }
        }
    }

    Map<String, Set<String>> propertyUsage = [:].withDefault { new LinkedHashSet<>() }
    taskPropertyRefs.each { String taskName, Set<String> refs ->
        refs.each { ref -> propertyUsage[ref].add(taskName) }
    }
    int vShared = propertyUsage.count { _, tasks -> tasks.size() >= 2 }

    Map<String, Set<String>> configUsage = [:].withDefault { new LinkedHashSet<>() }
    taskConfigRefs.each { String taskName, Set<String> refs ->
        refs.each { ref -> configUsage[ref].add(taskName) }
    }
    int cInternal = configUsage.count { _, tasks -> tasks.size() >= 2 }

    println JsonOutput.toJson([
        t_int: tInt,
        v_shared: vShared,
        c_internal: cInternal,
        m: externalModules.size(),
        d: externalDependencies,
        p: externalPlugins.size(),
        r: externalRepositories.size(),
        e: externalCommands,
        u: envResources.size(),
    ])
} catch (Throwable t) {
    System.err.println("Gradle coupling AST failed: " + t.toString())
    println JsonOutput.toJson(emptyResult())
}
