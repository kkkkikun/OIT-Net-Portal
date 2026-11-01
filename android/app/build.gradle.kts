plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
}

android {
    namespace = "com.oitnetportal"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.oitnetportal"
        minSdk = 26
        targetSdk = 35
        versionCode = 2
        versionName = "1.0.0"

        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    buildFeatures {
        compose = true
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

val pythonProjectDir = layout.buildDirectory.dir("pythonProject")

chaquopy {
    defaultConfig {
        // App 内嵌的 Python 版本。
        // 注意：Chaquopy 要求「构建机的 Python 大小版本必须与这里一致」，
        // 否则构建报 "Couldn't find Python 3.10"（2026-11-01 在 GitHub Actions 上踩过：
        // runner 镜像自带 Python 3.12，而这里要的是 3.10）。
        // 改这个值时，CI 与本地的 Python 版本要一起改。
        version = "3.10"
        pip {
            val customIndex = providers.environmentVariable("PIP_INDEX_URL")
            val extraIndex = providers.environmentVariable("PIP_EXTRA_INDEX_URL")
            val findLinks = providers.environmentVariable("PIP_FIND_LINKS")
            if (customIndex.isPresent) {
                options("--index-url", customIndex.get())
            }
            if (extraIndex.isPresent) {
                options("--extra-index-url", extraIndex.get())
            }
            if (findLinks.isPresent) {
                options("--find-links", findLinks.get())
            }
            // 仅安装构建暂存目录，避免把整个仓库根目录作为 Gradle 输入。
            install(pythonProjectDir.get().asFile.absolutePath)
        }
    }
}

val stagePythonProject = tasks.register<Copy>("stagePythonProject") {
    from(rootProject.projectDir.parentFile) {
        include("pyproject.toml")
        include("oit_portal/**/*.py")
    }
    into(pythonProjectDir)
}

tasks.configureEach {
    if (name.startsWith("install") && name.endsWith("PythonRequirements")) {
        dependsOn(stagePythonProject)
    }
}

kotlin {
    compilerOptions {
        jvmTarget.set(org.jetbrains.kotlin.gradle.dsl.JvmTarget.JVM_17)
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.15.0")
    implementation("androidx.activity:activity-compose:1.9.3")
    implementation("androidx.lifecycle:lifecycle-runtime-compose:2.8.7")
    implementation("androidx.lifecycle:lifecycle-viewmodel-compose:2.8.7")

    implementation(platform("androidx.compose:compose-bom:2024.12.01"))
    implementation("androidx.compose.ui:ui")
    implementation("androidx.compose.material3:material3")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
}
