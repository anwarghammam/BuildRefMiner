import org.codehaus.groovy.control.*
import org.codehaus.groovy.ast.*
import org.codehaus.groovy.ast.expr.*
import org.codehaus.groovy.ast.ClassCodeVisitorSupport

if (args.length == 0) {
    println "0,0,0,0"
    System.exit(0)
}

File f = new File(args[0])
if (!f.exists()) {
    println "0,0,0,0"
    System.exit(0)
}

def operators = new HashSet<String>()
def operands  = new HashSet<String>()
long N1 = 0
long N2 = 0

def recordOperator = { String op ->
    if (op != null && op.trim().length() > 0) {
        operators.add(op)
        N1++
    }
}

def recordOperand = { String opd ->
    if (opd != null && opd.trim().length() > 0) {
        operands.add(opd)
        N2++
    }
}

try {
    def config = new CompilerConfiguration()
    def unit = new CompilationUnit(config)
    unit.addSource(f)
    unit.compile(Phases.CONVERSION)

    def visitor = new ClassCodeVisitorSupport() {

        @Override
        protected SourceUnit getSourceUnit() { return null }

        @Override
        void visitMethodCallExpression(MethodCallExpression call) {
            // operator = method name
            recordOperator(call.methodAsString)
            super.visitMethodCallExpression(call)
        }

        @Override
        void visitBinaryExpression(BinaryExpression expr) {
            // operator = binary operator token (==, +, =, etc.)
            recordOperator(expr.operation?.text)
            super.visitBinaryExpression(expr)
        }

        @Override
        void visitDeclarationExpression(DeclarationExpression expr) {
            // operator = declaration operation (usually '=')
            recordOperator(expr.operation?.text)
            super.visitDeclarationExpression(expr)
        }

        @Override
        void visitConstantExpression(ConstantExpression expr) {
            // operand = constant literal (strings/numbers/etc.)
            if (expr.value != null) {
                recordOperand(expr.value.toString())
            }
            super.visitConstantExpression(expr)
        }

        @Override
        void visitVariableExpression(VariableExpression expr) {
            // operand = variable identifiers
            if (expr.name != null) {
                recordOperand(expr.name)
            }
            super.visitVariableExpression(expr)
        }
    }

    // Walk all modules (script + classes)
    unit.ast.modules.each { ModuleNode m ->
        // script-level statements
        m.statementBlock?.visit(visitor)

        // class methods
        m.classes.each { ClassNode cn ->
            cn.methods.each { MethodNode mn ->
                mn.code?.visit(visitor)
            }
        }
    }

    println "${operators.size()},${operands.size()},${N1},${N2}"

} catch (Throwable t) {
    // If parsing fails, return zeros (Python will treat as 0 volume)
    System.err.println("Halstead Groovy AST failed: " + t.toString())
    println "0,0,0,0"
}