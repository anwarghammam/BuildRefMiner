import org.codehaus.groovy.control.*
import org.codehaus.groovy.ast.*
import org.codehaus.groovy.ast.stmt.*
import org.codehaus.groovy.ast.ClassCodeVisitorSupport

if (args.length == 0) {
    System.err.println("No input file provided")
    println 1
    System.exit(0)
}

File f = new File(args[0])
if (!f.exists()) {
    System.err.println("File not found: " + f.absolutePath)
    println 1
    System.exit(0)
}

int complexity = 1

try {
    def config = new CompilerConfiguration()
    def unit = new CompilationUnit(config)
    unit.addSource(f)
    unit.compile(Phases.SEMANTIC_ANALYSIS)

    def visitor = new ClassCodeVisitorSupport() {
        @Override
        protected SourceUnit getSourceUnit() { return null }

        @Override
        void visitIfElse(IfStatement stmt) {
            complexity++
            super.visitIfElse(stmt)
        }

        @Override
        void visitForLoop(ForStatement stmt) {
            complexity++
            super.visitForLoop(stmt)
        }

        @Override
        void visitWhileLoop(WhileStatement stmt) {
            complexity++
            super.visitWhileLoop(stmt)
        }

        @Override
        void visitDoWhileLoop(DoWhileStatement stmt) {
            complexity++
            super.visitDoWhileLoop(stmt)
        }

        @Override
        void visitSwitch(SwitchStatement stmt) {
            complexity += (stmt.caseStatements?.size() ?: 0)
            super.visitSwitch(stmt)
        }

        @Override
        void visitCatchStatement(CatchStatement stmt) {
            complexity++
            super.visitCatchStatement(stmt)
        }
    }

    // ✅ Correct: unit.ast is CompileUnit; iterate modules from it
    unit.ast.modules.each { ModuleNode module ->

        // script-level statements (if any)
        module.statementBlock?.visit(visitor)

        // class method bodies
        module.classes.each { ClassNode cn ->
            cn.methods.each { MethodNode mn ->
                mn.code?.visit(visitor)
            }
        }
    }

    println complexity

} catch (Throwable t) {
    System.err.println("Groovy CC failed for: " + f.absolutePath)
    t.printStackTrace()
    println 1
}