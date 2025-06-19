
ruleset {
    description 'CodeNarc Rules for Gradle Build Script Quality'

    // Basic readability and style rules
 
    Indentation(enabled: true)
    LineLength(enabled: true, length: 120)
    // MethodSize(enabled: true, maxLines: 50)
    // ClassSize(enabled: true, maxLines: 2)

    // Naming conventions
    MethodName(enabled: true)
    VariableName(enabled: true)
    ClassName(enabled: true)
    FieldName(enabled: true)
    ParameterName(enabled: true)
    UnnecessarySemicolon(enabled: true)

    // === Size/Complexity rules (GMetrics plugin) ===
    MethodSize(enabled: true, maxLines: 1)
    ClassSize(enabled: true, maxLines: 2)
    CyclomaticComplexity(enabled: true, maxMethodComplexity: 0.05)
    //NPathComplexity(enabled: true, maxMethodComplexity: 1)

}