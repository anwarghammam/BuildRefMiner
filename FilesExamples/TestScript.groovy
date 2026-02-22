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
}