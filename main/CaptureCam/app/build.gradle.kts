import java.util.Properties

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val captureCamLocalProperties = Properties().apply {
    val localFile = rootProject.file("local.properties")
    if (localFile.isFile) localFile.inputStream().use(::load)
}
val sonySshPassword = (
    providers.gradleProperty("SONY_SSH_PASSWORD").orNull
        ?: captureCamLocalProperties.getProperty("sony.ssh.password", "")
).replace("\\", "\\\\").replace("\"", "\\\"")

android {
    namespace = "com.aradhana.capturecam"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.aradhana.capturecam"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
        // Machine-bound camera credential. Supplied by ignored
        // local.properties or -PSONY_SSH_PASSWORD; never committed.
        buildConfigField("String", "SONY_SSH_PASSWORD", "\"$sonySshPassword\"")
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }
    buildFeatures {
        viewBinding = true
        buildConfig = true
    }
}

dependencies {
    val cameraxVersion = "1.3.4"
    implementation("androidx.camera:camera-core:$cameraxVersion")
    implementation("androidx.camera:camera-camera2:$cameraxVersion")
    implementation("androidx.camera:camera-lifecycle:$cameraxVersion")
    implementation("androidx.camera:camera-view:$cameraxVersion")
    implementation("androidx.camera:camera-extensions:$cameraxVersion")

    implementation("com.google.mlkit:barcode-scanning:17.3.0")
    implementation("com.google.mlkit:object-detection:17.0.2")
    // Runs alongside the barcode scanner on the same frame (2026-08-26):
    // shop tags print the human-readable code (e.g. "GR22/131") next to
    // the barcode/QR, so OCR is a second independent decode path that can
    // succeed on a reflective/low-contrast tag where the barcode can't.
    implementation("com.google.mlkit:text-recognition:16.0.1")

    implementation("com.squareup.okhttp3:okhttp:4.12.0")

    // SonyPtpIpController: the ZV-E10 II (and other Access-Authentication-
    // capable Sony bodies) tunnels its PTP-IP control channel through SSH
    // rather than exposing it on a plain TCP port -- confirmed live
    // 2026-08-23 (Sony's own docs: "communication data can be encrypted
    // over an SSH connection" for cameras with access authentication).
    // mwiede's fork, not the original com.jcraft:jsch -- the original is
    // unmaintained and fails modern SSH key-exchange/cipher negotiation
    // against newer OpenSSH servers (this camera runs OpenSSH_7.9).
    implementation("com.github.mwiede:jsch:0.2.17")

    // Official OpenCV Android AAR (Maven Central since 4.9.0 -- normal
    // Gradle dependency, no manual SDK download/import needed). 4.12.0
    // specifically: fixes the 16KB-page-size Android packaging issue that
    // affected earlier releases, and avoids a page-alignment issue
    // reported against 5.0's AAR. Used for org.opencv.tracking.TrackerKCF,
    // the local on-phone tracker that owns frame-to-frame following
    // between the laptop's periodic Grounding DINO corrections.
    implementation("org.opencv:opencv:4.12.0")

    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
    implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.8.4")
    implementation("androidx.work:work-runtime-ktx:2.9.1")
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
    testImplementation("junit:junit:4.13.2")
}
