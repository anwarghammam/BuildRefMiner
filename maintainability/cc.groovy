import org.codehaus.groovy.control.*
import org.codehaus.groovy.ast.*
import org.codehaus.groovy.ast.expr.*
import org.codehaus.groovy.ast.stmt.*
import org.codehaus.groovy.ast.builder.*
import org.codehaus.groovy.control.customizers.*
import org.codehaus.groovy.control.io.*
import java.nio.file.*

def calculateCyclomaticComplexity(File file) {
    def cc = 1
    def config = new CompilerConfiguration()
    def loader = new GroovyClassLoader(this.class.classLoader, config)
    def sourceUnit = new SourceUnit(file.name, file.text, config, loader, new ErrorCollector(config))
    sourceUnit.parse()
    sourceUnit.completePhase()
    sourceUnit.convert()
    
    def module = sourceUnit.AST
    module.classes.each { classNode ->
        classNode.methods.each { method ->
            method.code?.statements?.each { stmt ->
                if (stmt instanceof IfStatement || stmt instanceof WhileStatement ||
                    stmt instanceof ForStatement || stmt instanceof SwitchStatement ||
                    stmt instanceof CaseStatement || stmt instanceof TernaryExpression) {
                    cc++
                }
            }
        }
    }
    return cc
}

def file = new File('build.gradle') // or any Groovy file
println "Cyclomatic Complexity: " + calculateCyclomaticComplexity(file)