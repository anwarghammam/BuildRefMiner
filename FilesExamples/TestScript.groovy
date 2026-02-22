class BadStyleClass {

    String BAD_FIELD_NAME = "oops" // FieldName

    def BadMethodName() {
        def VeryLongVariableNameThatExceedsNormalConvention = "value" // VariableName

        (1..60).each { println it } // MethodSize (closure - does NOT increase CC)

        // -------- Decision 1 (if-else) --------
        if (VeryLongVariableNameThatExceedsNormalConvention == "value") {
            println "Matched"
        } else {
            println "Not Matched"
        }

        // -------- Decision 2 (for loop) --------
        for (int i = 0; i < 3; i++) {
            println i
        }

        // -------- Decision 3 (try-catch) --------
        try {
            int x = 10 / 2
        } catch (Exception e) {
            println "Error occurred"
        }
    }

    def methodWithTooManyParameters(p1, p2, p3, p4, p5, p6) { // ParameterName
        println BAD_FIELD_NAME
    }
}