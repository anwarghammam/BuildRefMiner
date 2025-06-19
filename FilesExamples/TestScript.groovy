class BadStyleClass {

    def BadMethodName() {
        def VeryLongVariableNameThatExceedsNormalConvention = "value" // VariableName
        (1..60).each { println it } // MethodSize
    }

    String BAD_FIELD_NAME = "oops" // FieldName

    def methodWithTooManyParameters(p1, p2, p3, p4, p5, p6) { // ParameterName
        println BAD_FIELD_NAME
    }
}