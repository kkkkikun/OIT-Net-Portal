plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
    id("org.jetbrains.kotlin.plugin.compose")
    id("com.chaquo.python")
}

import java.util.Properties

// 反馈通道的默认地址在构建期注入：
// 值来自 android/local.properties（已 gitignore），生成的源码只进 APK，不进仓库。
// 真实服务地址因此不会出现在版本控制里。
//
// OpenFeedback 的提交接口不需要客户端密钥，所以这里只注入地址：
// APK 里只有公开的 appId 与服务地址，没有任何服务端凭据。
val feedbackProperties = Properties().apply {
    val localProperties = rootProject.file("local.properties")
    if (localProperties.isFile) {
        localProperties.inputStream().use { load(it) }
    }
}
val feedbackEndpoint = feedbackProperties.getProperty("oit.feedback.endpoint", "")

val generateFeedbackConfig = tasks.register("generateFeedbackConfig") {
    val outputDir = layout.buildDirectory.dir("generated/feedback")
    val endpointValue = feedbackEndpoint
    inputs.property("endpoint", endpointValue)
    outputs.dir(outputDir)
    doLast {
        val target = outputDir.get().asFile.resolve("com/oitnetportal/core")
        target.mkdirs()
        target.resolve("BuildConfigFeedback.kt").writeText(
            """
            package com.oitnetportal.core

            /** 构建期注入的反馈通道默认值；由 Gradle 从 local.properties 生成。 */
            object BuildConfigFeedback {
                const val DEFAULT_ENDPOINT: String = "${endpointValue.replace("\"", "\\\"")}"
            }
            """.trimIndent() + "\n",
            Charsets.UTF_8,
        )
    }
}

android {
    namespace = "com.oitnetportal"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.oitnetportal"
        minSdk = 26
        targetSdk = 35
        versionCode = 3
        versionName = "1.0.1"

        ndk {
            abiFilters += listOf("arm64-v8a", "x86_64")
        }
    }

    buildFeatures {
        compose = true
    }

    sourceSets {
        getByName("main") {
            // 生成任务的输出目录才是源码目录；TaskProvider 本身不能转成路径。
            java.srcDir(layout.buildDirectory.dir("generated/feedback"))
        }
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
    // 编译前必须先生成 BuildConfigFeedback，否则源码里引用不到该对象。
    if (name.startsWith("compile") && name.endsWith("Kotlin")) {
        dependsOn(generateFeedbackConfig)
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

    // OpenFeedback SDK：只用 core（传输 + 离线队列 + 自动重试），
    // 反馈表单仍由本 App 自己的 FeedbackForm 承载。
    // 版本固定，不用动态版本号。
    implementation("com.kkkkikun.openfeedback:openfeedback-core:0.1.0")

    testImplementation("junit:junit:4.13.2")
    testImplementation("org.jetbrains.kotlinx:kotlinx-coroutines-test:1.8.1")
}
