$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$stage = Join-Path $env:TEMP "aradhana-single-notifier"
$zip = Join-Path $env:TEMP "aradhana-single-notifier.zip"
$out = Join-Path $root "AradhanaBankActivityNotifier-OneClick.cmd"
Remove-Item $stage -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $zip -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path "$stage\scripts\assets" -Force | Out-Null
Copy-Item "$root\scripts\bank_activity_notifier.py", "$root\scripts\configure_bank_activity_notifier.py", "$root\scripts\start_bank_activity_notifier.ps1", "$root\scripts\remove_bank_activity_notifier.ps1" "$stage\scripts"
$logo = 'C:\Content\Logos\Logo Dimensions in Reel 30% x=220 y=200.png'
if (Test-Path $logo) { Copy-Item $logo "$stage\scripts\assets\logo.png" }
@'
$ErrorActionPreference = "Stop"
$target = Split-Path -Parent $PSScriptRoot
$start = Join-Path $target "scripts\start_bank_activity_notifier.ps1"
Get-CimInstance Win32_Process -Filter "name = 'pythonw.exe'" | Where-Object { $_.CommandLine -like "*bank_activity_notifier.py*" } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
Unregister-ScheduledTask -TaskName "AradhanaBankActivityNotifier" -Confirm:$false -ErrorAction SilentlyContinue
$action = New-ScheduledTaskAction -Execute "powershell.exe" -Argument "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$start`""
$trigger = New-ScheduledTaskTrigger -AtLogOn
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName "AradhanaBankActivityNotifier" -Action $action -Trigger $trigger -Principal $principal -Description "Aradhana native bank transaction popups." -Force | Out-Null
& $start
& $start -Configure
'@ | Set-Content "$stage\install.ps1" -Encoding UTF8
Compress-Archive -Path "$stage\*" -DestinationPath $zip -Force
$b64 = [Convert]::ToBase64String([IO.File]::ReadAllBytes($zip))
$chunks = for ($i=0; $i -lt $b64.Length; $i += 6000) { $b64.Substring($i, [Math]::Min(6000, $b64.Length - $i)) }
$lines = @('@echo off','setlocal EnableExtensions','fltmc >nul 2>&1','if errorlevel 1 (','  powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -Verb RunAs -FilePath ''%ComSpec%'' -ArgumentList ''/c ""%~f0"" elevated''"','  exit /b',')','set "TARGET=%ProgramData%\AradhanaBankActivityNotifier\release-%RANDOM%%RANDOM%"')
for ($i=0; $i -lt $chunks.Count; $i++) { $lines += "set `"ARADHANA_PAYLOAD_$i=$($chunks[$i])`"" }
$join = (0..($chunks.Count - 1) | ForEach-Object { "`$env:ARADHANA_PAYLOAD_$_" }) -join '+'
$lines += 'powershell.exe -NoProfile -ExecutionPolicy Bypass -Command "$b=' + $join + '; $z=Join-Path $env:TEMP ''aradhana-notifier.zip''; [IO.File]::WriteAllBytes($z,[Convert]::FromBase64String($b)); New-Item -ItemType Directory -Path $env:TARGET -Force | Out-Null; Expand-Archive -Path $z -DestinationPath $env:TARGET -Force"'
$lines += 'powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%TARGET%\install.ps1"'
$lines += 'pause'
Set-Content -LiteralPath $out -Value $lines -Encoding ASCII
Write-Output $out
