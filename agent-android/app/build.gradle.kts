import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.ksp)
    alias(libs.plugins.hilt)
    alias(libs.plugins.google.services)
}

android {
    namespace = "com.mdmesh.agent"
    compileSdk = 35

    flavorDimensions += "distribution"

    productFlavors {
        create("gms") {
            dimension = "distribution"
            // Production Android Enterprise / Google Play distribution.
            buildConfigField("boolean", "GMS_DISTRIBUTION", "true")
        }
        create("aosp") {
            dimension = "distribution"
            // China-ROM/AOSP distribution. Keep a distinct package so it can coexist with,
            // and never accidentally replace, the GMS Device Owner agent.
            applicationIdSuffix = ".cn"
            versionNameSuffix = "-cn"
            buildConfigField("boolean", "GMS_DISTRIBUTION", "false")
        }
    }

    defaultConfig {
        applicationId = "com.mdmesh.agent"
        minSdk = 24
        targetSdk = 35
        // Release CI overrides these from the git tag (see release/version.sh); the defaults are the
        // dev/debug values. versionCode must stay monotonic across the scheme switch (115 > 16).
        versionCode = (project.findProperty("versionCode") as String?)?.toInt() ?: 16
        versionName = (project.findProperty("versionName") as String?) ?: "0.1.15"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
    }

    signingConfigs {
        // DEBUG: self-signed debug key. A custom DPC must be signed consistently
        // because the Device-Owner binding is tied to the signing certificate; a
        // signature change after provisioning breaks the DO relationship.
        getByName("debug") {
            // Uses the standard Android debug keystore (~/.android/debug.keystore).
        }

        // RELEASE: read from env / a keystore file. Values come from the
        // environment so secrets never live in the repo.
        // TODO(keystore custody): decide where the release keystore lives (CI
        //   secret store / HSM) and who holds it. Re-signing a deployed DPC with a
        //   different key requires a factory reset of every enrolled device, so
        //   key loss is catastrophic — treat custody as a first-class concern.
        create("release") {
            val keystorePath = System.getenv("MDM_RELEASE_STORE_FILE")
            if (keystorePath != null) {
                storeFile = file(keystorePath)
                storePassword = System.getenv("MDM_RELEASE_STORE_PASSWORD")
                keyAlias = System.getenv("MDM_RELEASE_KEY_ALIAS")
                keyPassword = System.getenv("MDM_RELEASE_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        getByName("debug") {
            isDebuggable = true
            signingConfig = signingConfigs.getByName("debug")
            buildConfigField("String", "MDM_BASE_URL", "\"https://mdm.local/\"")
        }
        getByName("release") {
            isMinifyEnabled = true
            isShrinkResources = true
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
            // Only attach the release signing config when the env keystore exists,
            // so debug-only CI checkouts still configure.
            if (System.getenv("MDM_RELEASE_STORE_FILE") != null) {
                signingConfig = signingConfigs.getByName("release")
            }
            // Falls back through the QR/provisioning bundle's own SERVER_URL for Device-Owner
            // enrollment (ServerConfigStore) regardless - this baked-in value is what Lite
            // enrollment (a direct APK install, no provisioning bundle) actually uses at first
            // launch, so it must be the real server, not a placeholder. -PmdmBaseUrl overrides
            // it (release.yml passes the production URL); this default only matters for a local
            // release build run without that flag.
            val mdmBaseUrl = (project.findProperty("mdmBaseUrl") as String? ?: "https://mdm.example.com/")
            buildConfigField("String", "MDM_BASE_URL", "\"$mdmBaseUrl\"")
        }
    }

    buildFeatures {
        buildConfig = true
    }

    compileOptions {
        isCoreLibraryDesugaringEnabled = true   // java.time on minSdk 24 (final dexing)
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    coreLibraryDesugaring(libs.desugar.jdk.libs)

    implementation(project(":proto"))
    implementation(project(":core"))
    implementation(project(":policy"))
    implementation(project(":oem"))
    implementation(project(":kiosk"))
    implementation(project(":remote"))

    // OkHttpClient is :core's implementation-only dependency (NetworkModule provides the instance);
    // AgentModule.provideWallpaperHandler needs the type itself to declare the DI parameter.
    implementation(libs.okhttp)
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.appcompat)
    implementation(libs.androidx.activity.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.service)
    implementation(libs.androidx.biometric)
    implementation(libs.kotlinx.coroutines.android)

    // GMS-only wake channel. The AOSP/China APK deliberately contains neither the Firebase
    // runtime nor the Firebase messaging service; it uses TransportManager + WakeKeepAlive.
    add("gmsImplementation", platform(libs.firebase.bom))
    add("gmsImplementation", libs.firebase.messaging.ktx)

    // WorkManager (scheduling check-in)
    implementation(libs.work.runtime.ktx)

    // DI
    implementation(libs.hilt.android)
    ksp(libs.hilt.compiler)
    implementation(libs.hilt.work)
    ksp(libs.hilt.work.compiler)

    testImplementation(libs.junit)
    androidTestImplementation(libs.androidx.junit)
}

// The Google Services plugin is retained for the gms flavor. It otherwise tries to validate the
// root google-services.json against the deliberately distinct `.cn` package and makes a GMS-free
// AOSP build impossible. AOSP has no Firebase dependency or generated Google resource to consume.
tasks.configureEach {
    if (name.startsWith("processAosp") && name.endsWith("GoogleServices")) {
        enabled = false
    }
}
