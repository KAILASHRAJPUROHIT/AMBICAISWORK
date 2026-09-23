$ErrorActionPreference = "Stop"
Add-Type -AssemblyName System.IO.Compression.FileSystem
Add-Type -AssemblyName System.IO.Compression
$root = "c:\AradhanaSystems\projects\print-router"
Set-Location $root

Write-Host "=== 1. Building Release Binaries ==="
dotnet build AradhanaPrintControl.slnx -c Release

Write-Host "=== 2. Publishing Ambic.PrintNode ==="
Remove-Item -Recurse -Force "$root\publish\node" -ErrorAction SilentlyContinue
dotnet publish "$root\src\Ambic.PrintNode\Ambic.PrintNode.csproj" -c Release -o "$root\publish\node"

Write-Host "=== 3. Publishing Ambic.PrintConsole ==="
Remove-Item -Recurse -Force "$root\publish\console" -ErrorAction SilentlyContinue
dotnet publish "$root\src\Ambic.PrintConsole\Ambic.PrintConsole.csproj" -c Release -o "$root\publish\console"

Write-Host "=== 4. Assembling Staging Area ==="
Remove-Item -Recurse -Force "$root\publish\stage" -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$root\publish\stage" | Out-Null
New-Item -ItemType Directory -Path "$root\publish\stage\assets" | Out-Null

Copy-Item -Path "$root\publish\node\*" -Destination "$root\publish\stage" -Recurse -Force
Copy-Item -Path "$root\publish\console\*" -Destination "$root\publish\stage" -Recurse -Force

# Assets
Copy-Item -Path "$root\assets\office-sales-voucher-format-reference.png" -Destination "$root\publish\stage\assets\office-sales-voucher-format-reference.png" -Force
Copy-Item -Path "$root\assets\app.ico" -Destination "$root\publish\stage\app.ico" -Force
Copy-Item -Path "$root\assets\app.ico" -Destination "$root\publish\stage\assets\app.ico" -Force
Copy-Item -Path "$root\assets\letterhead_front.jpeg" -Destination "$root\publish\stage\assets\letterhead_front.jpeg" -Force
Copy-Item -Path "$root\assets\letterhead_back.jpeg" -Destination "$root\publish\stage\assets\letterhead_back.jpeg" -Force
Copy-Item -Path "$root\assets\overlay_merge.py" -Destination "$root\publish\stage\assets\overlay_merge.py" -Force

# Cleanup any non-Windows runtimes in staging to keep payload small, but preserve runtimes\win*
if (Test-Path "$root\publish\stage\runtimes") {
    Get-ChildItem -Path "$root\publish\stage\runtimes" -Directory | Where-Object { $_.Name -notlike "win*" } | Remove-Item -Recurse -Force
}

# Verify System.ServiceProcess.ServiceController.dll (the real 92KB implementation, not the 34KB ref assembly)
$serviceControllerImpl = "$root\publish\stage\runtimes\win\lib\net10.0\System.ServiceProcess.ServiceController.dll"
if (Test-Path $serviceControllerImpl) {
    Copy-Item -Path $serviceControllerImpl -Destination "$root\publish\stage\System.ServiceProcess.ServiceController.dll" -Force
    Write-Host "Copied 92KB System.ServiceProcess.ServiceController.dll to stage root."
}

# Verify e_sqlite3.dll
$sqliteNative = "$root\publish\stage\runtimes\win-x64\native\e_sqlite3.dll"
if (Test-Path $sqliteNative) {
    Copy-Item -Path $sqliteNative -Destination "$root\publish\stage\e_sqlite3.dll" -Force
    Write-Host "Copied native e_sqlite3.dll to stage root."
}

Write-Host "=== 5. Creating payload.zip ==="
$zipPath = "$root\src\Ambic.PrintInstaller\payload.zip"
Remove-Item -Force $zipPath -ErrorAction SilentlyContinue
[System.IO.Compression.ZipFile]::CreateFromDirectory("$root\publish\stage", $zipPath, [System.IO.Compression.CompressionLevel]::Optimal, $false)
$zipSize = (Get-Item $zipPath).Length / 1MB
Write-Host "payload.zip created: $([math]::Round($zipSize, 2)) MB"

Write-Host "=== 6. Publishing Self-Contained PrintServer-Setup.exe ==="
Remove-Item -Recurse -Force "$root\publish\installer_out" -ErrorAction SilentlyContinue
dotnet publish "$root\src\Ambic.PrintInstaller\Ambic.PrintInstaller.csproj" -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -o "$root\publish\installer_out"

$setupExe = "$root\publish\installer_out\Ambic.PrintInstaller.exe"
if (Test-Path $setupExe) {
    Copy-Item -Path $setupExe -Destination "$root\PrintServer-Setup.exe" -Force
    Copy-Item -Path $setupExe -Destination "$root\publish\PrintServer-Setup.exe" -Force
    $desktopPath = [System.IO.Path]::Combine([System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop), "PrintServer-Setup.exe")
    Copy-Item -Path $setupExe -Destination $desktopPath -Force
    $exeSize = (Get-Item "$root\PrintServer-Setup.exe").Length / 1MB
    Write-Host "SUCCESS: PrintServer-Setup.exe generated: $([math]::Round($exeSize, 2)) MB"
    Write-Host "Deployed to:"
    Write-Host "  - $root\PrintServer-Setup.exe"
    Write-Host "  - $root\publish\PrintServer-Setup.exe"
    Write-Host "  - $desktopPath"
} else {
    Write-Error "Ambic.PrintInstaller.exe was not found in output!"
}
