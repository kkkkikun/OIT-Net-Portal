pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        // OpenFeedback SDK：由 OpenFeedback 服务端以只读静态 Maven 仓库提供。
        // 版本在 build.gradle.kts 里固定，不使用动态版本号。
        maven {
            name = "openfeedback"
            url = uri(
                providers.gradleProperty("oit.openfeedback.mavenUrl")
                    .getOrElse("https://feedback.example.com/maven/")
            )
        }
        google()
        mavenCentral()
    }
}

rootProject.name = "OIT-Net-Portal-Android"
include(":app")
