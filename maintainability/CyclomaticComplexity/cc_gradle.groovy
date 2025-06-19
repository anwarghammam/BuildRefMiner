import org.codehaus.groovy.ast.builder.AstBuilder
import org.codehaus.groovy.control.CompilePhase
import org.codehaus.groovy.ast.stmt.*
import org.codehaus.groovy.ast.*

int calculateCyclomaticComplexity(File file) {
    def ast = new AstBuilder().buildFromString(CompilePhase.CONVERSION, false, file.text)
    int complexity = 1  // base complexity

    ast.each { node ->
        if (node instanceof BlockStatement) {
            complexity += countDecisionPoints(node)
        }
    }

    return complexity
}

int countDecisionPoints(Statement stmt) {
    int count = 0

    if (stmt instanceof IfStatement) {
        count += 1
        count += countDecisionPoints(stmt.ifBlock)
        count += countDecisionPoints(stmt.elseBlock)
    } else if (stmt instanceof WhileStatement || stmt instanceof ForStatement || stmt instanceof DoWhileStatement) {
        count += 1
        count += countDecisionPoints(stmt.loopBlock)
    } else if (stmt instanceof SwitchStatement) {
        count += stmt.caseStatements.size()
        stmt.caseStatements.each { cs ->
            cs.code?.statements?.each { count += countDecisionPoints(it) }
        }
    } else if (stmt instanceof TryCatchStatement) {
        count += stmt.catchStatements.size()
        stmt.catchStatements.each { cs ->
            count += countDecisionPoints(cs.code)
        }
        if (stmt.finallyStatement) {
            count += countDecisionPoints(stmt.finallyStatement)
        }
        count += countDecisionPoints(stmt.tryStatement)
    } else if (stmt instanceof BlockStatement) {
        stmt.statements.each { s -> count += countDecisionPoints(s) }
    }

    return count
}

// Example usage
def file = new File("../../FilesExamples/build.gradle")  // path to your Gradle/Groovy script
println "Cyclomatic Complexity: ${calculateCyclomaticComplexity(file)}"