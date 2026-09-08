plugins {
    id("com.android.application")
}

android {
    namespace = "com.ornate.nx.mlkitextension"
    compileSdk = 35

    defaultConfig {
        applicationId = "com.ornate.nx.mlkitextension"
        minSdk = 23
        targetSdk = 35
        versionCode = 1
        versionName = "test"
    }

    sourceSets["main"].java.srcDir("../../ux-extension-src/src")

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
}

dependencies {
    implementation("com.google.mlkit:text-recognition:16.0.1")
    implementation("com.google.mlkit:text-recognition-devanagari:16.0.1")
    // play-services-mlkit-document-scanner intentionally removed: replaced by
    // DocumentWebScanActivity (WebView + the existing proven capture page),
    // see its class doc for why. Kept out so it never gets re-merged by
    // accident into the vendor smali tree.
}
