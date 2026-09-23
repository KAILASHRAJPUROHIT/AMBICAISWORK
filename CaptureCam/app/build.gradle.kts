plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.aradhana.capturecam"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.aradhana.capturecam"
        minSdk = 26
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
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

    implementation("com.squareup.okhttp3:okhttp:4.12.0")

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
    implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.8.1")
}
