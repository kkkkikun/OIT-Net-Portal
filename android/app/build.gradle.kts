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
        versionCode = 1
        versionName = "0.1.0"

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
        version = "3.10"
        pip {
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
