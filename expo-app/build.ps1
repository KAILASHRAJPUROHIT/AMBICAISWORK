# Aradhana Jewellers — Full Build Script
# Run from project root: C:\Users\kaila\Desktop\aradhana-app

$ErrorActionPreference = "Stop"

Write-Host "=== STEP 1: Clean prebuild ===" -ForegroundColor Cyan
Remove-Item -Recurse -Force "android" -ErrorAction SilentlyContinue
npx expo prebuild --platform android --clean
if ($LASTEXITCODE -ne 0) { Write-Host "Prebuild failed!" -ForegroundColor Red; exit 1 }

Write-Host "`n=== STEP 2: Copy splash video ===" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path "android\app\src\main\res\raw" | Out-Null
Copy-Item "C:\Content\outro.mp4" "android\app\src\main\res\raw\splash_video.mp4"
Write-Host "splash_video.mp4 copied"

Write-Host "`n=== STEP 3: Create fade animations ===" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path "android\app\src\main\res\anim" | Out-Null

@'
<?xml version="1.0" encoding="utf-8"?>
<alpha xmlns:android="http://schemas.android.com/apk/res/android"
    android:fromAlpha="0.0"
    android:toAlpha="1.0"
    android:duration="400"
    android:interpolator="@android:anim/decelerate_interpolator" />
'@ | Set-Content "android\app\src\main\res\anim\fade_in.xml" -Encoding UTF8

@'
<?xml version="1.0" encoding="utf-8"?>
<alpha xmlns:android="http://schemas.android.com/apk/res/android"
    android:fromAlpha="1.0"
    android:toAlpha="0.0"
    android:duration="400"
    android:interpolator="@android:anim/decelerate_interpolator" />
'@ | Set-Content "android\app\src\main\res\anim\fade_out.xml" -Encoding UTF8
Write-Host "fade_in.xml and fade_out.xml created"

Write-Host "`n=== STEP 4: Create SplashActivity ===" -ForegroundColor Cyan
$splashDir = "android\app\src\main\java\com\aradhanajewellers\app"

@'
package com.aradhanajewellers.app

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import android.widget.VideoView
import android.app.Activity
import android.view.WindowManager

class SplashActivity : Activity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        window.addFlags(WindowManager.LayoutParams.FLAG_LAYOUT_NO_LIMITS)

        setContentView(R.layout.activity_splash)

        val videoView = findViewById<VideoView>(R.id.splashVideo)
        val videoUri = Uri.parse("android.resource://$packageName/${R.raw.splash_video}")

        videoView.setVideoURI(videoUri)
        videoView.setOnCompletionListener {
            startActivity(Intent(this, MainActivity::class.java))
            @Suppress("DEPRECATION")
            overridePendingTransition(R.anim.fade_in, R.anim.fade_out)
            finish()
        }
        videoView.setOnErrorListener { _, _, _ ->
            startActivity(Intent(this, MainActivity::class.java))
            @Suppress("DEPRECATION")
            overridePendingTransition(R.anim.fade_in, R.anim.fade_out)
            finish()
            true
        }
        videoView.start()
    }
}
'@ | Set-Content "$splashDir\SplashActivity.kt" -Encoding UTF8
Write-Host "SplashActivity.kt created"

Write-Host "`n=== STEP 5: Create splash layout ===" -ForegroundColor Cyan
New-Item -ItemType Directory -Force -Path "android\app\src\main\res\layout" | Out-Null

@'
<?xml version="1.0" encoding="utf-8"?>
<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:background="#0A2954">

    <VideoView
        android:id="@+id/splashVideo"
        android:layout_width="match_parent"
        android:layout_height="match_parent"
        android:layout_gravity="center" />

</FrameLayout>
'@ | Set-Content "android\app\src\main\res\layout\activity_splash.xml" -Encoding UTF8
Write-Host "activity_splash.xml created"

Write-Host "`n=== STEP 6: Patch AndroidManifest.xml ===" -ForegroundColor Cyan
$manifest = Get-Content "android\app\src\main\AndroidManifest.xml" -Raw

# Add SplashActivity before MainActivity
$splashActivity = @'
    <activity android:name=".SplashActivity" android:configChanges="keyboard|keyboardHidden|orientation|screenSize|screenLayout|uiMode|smallestScreenSize|assetsPaths" android:launchMode="singleTask" android:windowSoftInputMode="adjustResize" android:exported="true" android:screenOrientation="portrait" android:theme="@android:style/Theme.NoTitleBar.Fullscreen">
      <intent-filter>
        <action android:name="android.intent.action.MAIN"/>
        <category android:name="android.intent.category.LAUNCHER"/>
      </intent-filter>
    </activity>
'@

# Remove MAIN/LAUNCHER from MainActivity
$manifest = $manifest -replace '(<activity android:name="\.MainActivity"[^>]*android:exported=")true"', '$1true"'
$manifest = $manifest -replace '(?s)<intent-filter>\s*<action android:name="android\.intent\.action\.MAIN"/>\s*<category android:name="android\.intent\.category\.LAUNCHER"/>\s*</intent-filter>', ''

# Add SplashActivity before MainActivity
$manifest = $manifest -replace '(<activity android:name="\.MainActivity")', "$splashActivity`n    `$1"

$manifest | Set-Content "android\app\src\main\AndroidManifest.xml" -Encoding UTF8
Write-Host "AndroidManifest.xml patched"

Write-Host "`n=== STEP 7: Update styles.xml ===" -ForegroundColor Cyan
$styles = Get-Content "android\app\src\main\res\values\styles.xml" -Raw
if ($styles -notmatch 'windowBackground') {
    $styles = $styles -replace '(<item name="colorPrimary">@color/colorPrimary</item>)', '$1
    <item name="android:windowBackground">@color/splashscreen_background</item>'
    $styles | Set-Content "android\app\src\main\res\values\styles.xml" -Encoding UTF8
    Write-Host "windowBackground added to styles.xml"
} else {
    Write-Host "windowBackground already present"
}

Write-Host "`n=== STEP 8: Update colors.xml ===" -ForegroundColor Cyan
$colors = Get-Content "android\app\src\main\res\values\colors.xml" -Raw
$colors = $colors -replace '(<color name="colorPrimary">)[^<]*(</color>)', '${1}#23519D${2}'
$colors | Set-Content "android\app\src\main\res\values\colors.xml" -Encoding UTF8
Write-Host "colorPrimary updated to #23519D"

Write-Host "`n=== STEP 9: Build release APK ===" -ForegroundColor Cyan
$env:JAVA_HOME = "C:\jdk17\jdk-17.0.14+7"
$env:ANDROID_HOME = "$env:LOCALAPPDATA\Android\Sdk"
Push-Location "android"
.\gradlew.bat assembleRelease --no-daemon
$buildResult = $LASTEXITCODE
Pop-Location

if ($buildResult -ne 0) {
    Write-Host "`nBuild FAILED!" -ForegroundColor Red
    exit 1
}

Write-Host "`n=== BUILD SUCCESS ===" -ForegroundColor Green
$apk = "android\app\build\outputs\apk\release\app-release.apk"
if (Test-Path $apk) {
    $size = (Get-Item $apk).Length / 1MB
    Write-Host "APK: $apk ($([math]::Round($size,1)) MB)" -ForegroundColor Green
}

Write-Host "`n=== STEP 10: Install on Redmi Tab ===" -ForegroundColor Cyan
adb -s 192.168.0.18:33107 install -r $apk
Write-Host "`nDone! Verify on device." -ForegroundColor Green
