

import org.codehaus.groovy.ast.*
import org.codehaus.groovy.ast.expr.*
import org.codehaus.groovy.ast.stmt.*
import org.codehaus.groovy.ast.builder.AstBuilder
import org.codehaus.groovy.control.CompilePhase

import java.util.concurrent.atomic.AtomicInteger

def collectGradleOperatorsOperands(File file) {
    def operators = [] as Set
    def operands = [] as Set
    def totalOperators = new AtomicInteger(0)
    def totalOperands = new AtomicInteger(0)
    def visited = Collections.newSetFromMap(new IdentityHashMap<>())

    def traverse
    traverse = { ASTNode node ->
        if (node == null || visited.contains(node)) return
        visited.add(node)

        if (node instanceof MethodCallExpression) {
            def method = node.methodAsString
            if (method) {
                operators << method
                totalOperators.incrementAndGet()
            }

            def args = node.arguments
            if (args instanceof ArgumentListExpression) {
                args.expressions.each { expr ->
                    if (expr instanceof ConstantExpression && expr.value instanceof String) {
                        operands << expr.value
                        totalOperands.incrementAndGet()
                    }
                }
            }
        } else if (node instanceof DeclarationExpression || node instanceof BinaryExpression) {
            def op = node.operation?.text
            if (op) {
                operators << op
                totalOperators.incrementAndGet()
            }

            def right = node.rightExpression
            if (right instanceof ConstantExpression && right.value instanceof String) {
                operands << right.value
                totalOperands.incrementAndGet()
            }
        }

        node.properties.each { key, value ->
            if (value instanceof ASTNode) {
                traverse(value)
            } else if (value instanceof Collection) {
                value.each {
                    if (it instanceof ASTNode) {
                        traverse(it)
                    }
                }
            }
        }
    }

    def ast = new AstBuilder().buildFromString(CompilePhase.CONVERSION, false, file.text)
    ast.each { traverse(it) }

    return [operators, operands, totalOperators.get(), totalOperands.get()]
}

def calculateHalsteadComplexity(File file) {
    def (operators, operands, N1, N2) = collectGradleOperatorsOperands(file)
    def n1 = operators.size()
    def n2 = operands.size()
    def vocabulary = n1 + n2
    def length = N1 + N2
    def volume = (vocabulary > 0 && length > 0) ? length * (Math.log(vocabulary) / Math.log(2)) : 0

    println "\n📄 File: ${file}"
    println "📊 Halstead Complexity Metrics:"
    println "Unique Operators (n1): ${n1}"
    println "Unique Operands (n2): ${n2}"
    println "Total Operators (N1): ${N1}"
    println "Total Operands (N2): ${N2}"
    println "Vocabulary: ${vocabulary}"
    println "Length: ${length}"
    println "Volume: ${volume.round(2)}"
}

// Run on all Gradle files recursively
new File("../../FilesExamples").eachFileRecurse { file ->
    if (file.name == "build.gradle") {
        calculateHalsteadComplexity(file)
    }
}