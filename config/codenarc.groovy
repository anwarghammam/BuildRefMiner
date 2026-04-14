
ruleset {
    description 'CodeNarc Rules for Gradle Build Script Quality'

    // Basic readability and style rules

    Indentation(enabled: true)
    LineLength(enabled: true, length: 120)
    UnnecessarySemicolon(enabled: true)

    // Naming conventions
    MethodName(enabled: true)
    VariableName(enabled: true)
    ClassName(enabled: true)
    FieldName(enabled: true)
    ParameterName(enabled: true)

    // === Size/Complexity rules (GMetrics plugin) ===
    MethodSize(enabled: true, maxLines: 40)
    NestedBlockDepth(enabled: true, maxNestedBlockDepth: 4)
    ParameterCount(enabled: true, maxParameters: 5)
    AbcMetric(enabled: true, maxMethodAbcScore: 20)
    // Keep this enabled for the metric pipeline; threshold 0 forces reporting every method.
    CyclomaticComplexity(enabled: true, maxMethodComplexity: 0)

}
