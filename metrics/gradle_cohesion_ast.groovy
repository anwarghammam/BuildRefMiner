import groovy.json.JsonOutput
import org.codehaus.groovy.ast.*
import org.codehaus.groovy.ast.expr.*
import org.codehaus.groovy.control.*
import org.codehaus.groovy.control.SourceUnit
import org.codehaus.groovy.ast.ClassCodeVisitorSupport

def emptyResult = {
    [
        task_count: 0,
        feature_sets: [],
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

Set<String> KEYWORD_METHODS = [
    "doLast", "doFirst", "dependsOn", "mustRunAfter", "shouldRunAfter",
    "finalizedBy", "copy", "delete", "exec", "javaexec",
] as Set

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

    return []
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

try {
    def config = new CompilerConfiguration()
    def unit = new CompilationUnit(config)
    unit.addSource(f)
    unit.compile(Phases.CONVERSION)

    Set<String> taskNames = new LinkedHashSet<>()
    Map<String, ClosureExpression> taskClosures = [:]
    Set<String> declaredVars = new LinkedHashSet<>()

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
        void visitMethodCallExpression(MethodCallExpression call) {
            def taskName = detectTaskName(call)
            if (taskName) {
                taskNames.add(taskName)
                def closure = extractClosureArg(call)
                if (closure != null) {
                    taskClosures[taskName] = closure
                }
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

    List<List<String>> featureSets = []

    taskClosures.each { String taskName, ClosureExpression closureExpr ->
        Set<String> features = new LinkedHashSet<>()

        def taskVisitor = new ClassCodeVisitorSupport() {
            @Override
            protected SourceUnit getSourceUnit() { return null }

            @Override
            void visitMethodCallExpression(MethodCallExpression call) {
                def method = call.methodAsString ?: ""
                def stringArgs = extractStringLiterals(call.arguments)

                if (KEYWORD_METHODS.contains(method)) {
                    features.add("keyword:${method}")
                }

                if (DEPENDENCY_METHODS.contains(method)) {
                    features.add("config:${method}")
                }

                if (method == "project" && stringArgs) {
                    stringArgs.each { value -> features.add("dep:${value}") }
                }

                if (method == "findProperty" && stringArgs) {
                    features.add("property:${stringArgs[0]}")
                }

                if (method == "property" && stringArgs) {
                    features.add("property:${stringArgs[0]}")
                }

                if (["inputs", "outputs", "sourceSets", "configurations"].contains(method)) {
                    features.add("config:${method}")
                }

                super.visitMethodCallExpression(call)
            }

            @Override
            void visitVariableExpression(VariableExpression expr) {
                if (expr.name && declaredVars.contains(expr.name)) {
                    features.add("property:${expr.name}")
                }
                super.visitVariableExpression(expr)
            }

            @Override
            void visitPropertyExpression(PropertyExpression expr) {
                def text = expr.text ?: ""
                if (text.startsWith("ext.")) {
                    features.add("property:${expr.propertyAsString}")
                }
                if (text.startsWith("sourceSets.")) {
                    features.add("sourceSet:${expr.propertyAsString}")
                    features.add("config:${text}")
                }
                if (
                    text.startsWith("inputs.") ||
                    text.startsWith("outputs.") ||
                    text.startsWith("configurations.")
                ) {
                    features.add("config:${text}")
                }
                super.visitPropertyExpression(expr)
            }
        }

        closureExpr.code?.visit(taskVisitor)

        if (!features.isEmpty()) {
            featureSets.add(features.toList().sort())
        }
    }

    println JsonOutput.toJson([
        task_count: taskNames.size(),
        feature_sets: featureSets,
    ])
} catch (Throwable t) {
    System.err.println("Gradle cohesion AST failed: " + t.toString())
    println JsonOutput.toJson(emptyResult())
}
