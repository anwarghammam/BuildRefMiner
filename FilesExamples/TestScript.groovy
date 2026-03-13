class BadStyleClass {

    def BadMethodName() {
        def VeryLongVariableNameThatExceedsNormalConvention = "value" // VariableName
        (1..60).each { println it } // MethodSize
    }

    // ===== Added duplicate fragments for Clone Density demo =====
    def cloneBlockA() {
        def x = 1
        if (x > 0) {
            println "CLONE"
        }
        println "END"
    }

    def cloneBlockB() {
        def x = 1
        if (x > 0) {
            println "CLONE"
        }
        println "END"
    }
    // ============================================================

    String BAD_FIELD_NAME = "oops" // FieldName

    def methodWithTooManyParameters(p1, p2, p3, p4, p5, p6) { // ParameterName
        println BAD_FIELD_NAME
    }
    class BuildScriptSimulation {

    def ExampleMethodWithBadName() { // method starts with uppercase
        def VeryLongVariableNameThatExceedsNormalConvention = "This is a long variable name"
        println "This is a very long line that is intentionally written to exceed the maximum allowed length of 120 characters, just to trigger the long line smell detection rule in the sniffer adapter"

        (1..60).each { i ->
            println "Line $i"
        }

        def env = "prod"

        if (env == "prod") {
            println "Production mode"
        }

        switch(env) {
            case "dev":
                println "Development"
                break
            case "prod":
                println "Production"
                break
        }

        def cloneTaskA = {
            def y = 2
            if (y > 0) {
                println "CLONE"
            }
            println "END"
        }

        def cloneTaskB = {
            def y = 2
            if (y > 0) {
                println "CLONE"
            }
            println "END"
        }

        println "End of method"
    }

    class bad_class_name {
        String BAD_FIELD_NAME = "oops"

        def methodWithTooManyParameters(paramOne, paramTwo, paramThree, paramFour, paramFive, paramSix) {
            println BAD_FIELD_NAME
        }
    }
}

// TODO: fix this later
// FIXME: remove duplicate logic
}