ruleset {
    description 'CodeNarc Rules for Gradle Build Script Style Conformance'

    // Formatting and readability
    Indentation(enabled: true)
    LineLength(enabled: true, length: 120)
    UnnecessarySemicolon(enabled: true)

    // Naming conventions
    MethodName(enabled: true)
    VariableName(enabled: true)
    ClassName(enabled: true)
    FieldName(enabled: true)
    ParameterName(enabled: true)
}
