import org.codehaus.groovy.control.*
import org.codehaus.groovy.ast.*
import org.codehaus.groovy.ast.expr.*
import org.codehaus.groovy.ast.stmt.*
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
        void visitPrefixExpression(PrefixExpression expr) {
            // operator = prefix operator token (!, ++, --, etc.)
            recordOperator(expr.operation?.text)
            super.visitPrefixExpression(expr)
        }

        @Override
        void visitPostfixExpression(PostfixExpression expr) {
            // operator = postfix operator token (++ , --)
            recordOperator(expr.operation?.text)
            super.visitPostfixExpression(expr)
        }

        @Override
        void visitUnaryMinusExpression(UnaryMinusExpression expr) {
            recordOperator("-")
            super.visitUnaryMinusExpression(expr)
        }

        @Override
        void visitUnaryPlusExpression(UnaryPlusExpression expr) {
            recordOperator("+")
            super.visitUnaryPlusExpression(expr)
        }

        @Override
        void visitBitwiseNegationExpression(BitwiseNegationExpression expr) {
            recordOperator("~")
            super.visitBitwiseNegationExpression(expr)
        }

        @Override
        void visitNotExpression(NotExpression expr) {
            recordOperator("!")
            super.visitNotExpression(expr)
        }

        @Override
        void visitTernaryExpression(TernaryExpression expr) {
            recordOperator("?:")
            super.visitTernaryExpression(expr)
        }

        @Override
        void visitShortTernaryExpression(ElvisOperatorExpression expr) {
            recordOperator("?:")
            super.visitShortTernaryExpression(expr)
        }

        @Override
        void visitIfElse(IfStatement stmt) {
            recordOperator("if")
            if (!(stmt.elseBlock instanceof EmptyStatement)) {
                recordOperator("else")
            }
            super.visitIfElse(stmt)
        }

        @Override
        void visitForLoop(ForStatement stmt) {
            recordOperator("for")
            super.visitForLoop(stmt)
        }

        @Override
        void visitWhileLoop(WhileStatement stmt) {
            recordOperator("while")
            super.visitWhileLoop(stmt)
        }

        @Override
        void visitDoWhileLoop(DoWhileStatement stmt) {
            recordOperator("doWhile")
            super.visitDoWhileLoop(stmt)
        }

        @Override
        void visitSwitch(SwitchStatement stmt) {
            recordOperator("switch")
            super.visitSwitch(stmt)
        }

        @Override
        void visitCaseStatement(CaseStatement stmt) {
            recordOperator("case")
            super.visitCaseStatement(stmt)
        }

        @Override
        void visitCatchStatement(CatchStatement stmt) {
            recordOperator("catch")
            super.visitCatchStatement(stmt)
        }

        @Override
        void visitClosureExpression(ClosureExpression expr) {
            expr.parameters?.each { param ->
                if (param?.name != null) {
                    recordOperand(param.name)
                }
            }
            super.visitClosureExpression(expr)
        }

        @Override
        void visitPropertyExpression(PropertyExpression expr) {
            // operand = property/member names in chains like project.version
            if (expr.propertyAsString != null) {
                recordOperand(expr.propertyAsString)
            }
            super.visitPropertyExpression(expr)
        }

        @Override
        void visitAttributeExpression(AttributeExpression expr) {
            // operand = attribute/member names in expressions like object.@field
            if (expr.propertyAsString != null) {
                recordOperand(expr.propertyAsString)
            }
            super.visitAttributeExpression(expr)
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
