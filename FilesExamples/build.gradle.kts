plugins {
    base
}

val deploymentTargets = listOf("dev", "qa", "prod")

fun publishLabel(isSnapshot: Boolean, branchName: String, retryCount: Int): String {
    var label = if (isSnapshot) "snapshot" else "release"

    when (branchName) {
        "main" -> label = "stable"
        "develop" -> label = "beta"
        else -> label = "feature"
    }

    for (attempt in 0 until retryCount) {
        if (attempt > 1 && branchName != "main") {
            label = "retry-$attempt"
        }
    }

    return label
}

tasks.register("describeBuild") {
    doLast {
        deploymentTargets.forEach { target ->
            println("$target -> ${publishLabel(target == "dev", target, 3)}")
        }
    }
}
