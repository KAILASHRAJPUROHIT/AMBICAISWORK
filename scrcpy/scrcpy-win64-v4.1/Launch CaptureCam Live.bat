@echo off
cd /d "%~dp0"
set ADB=%~dp0adb.exe
adb.exe connect 192.168.0.6:5555
scrcpy.exe -s 192.168.0.6:5555 --window-title "CaptureCam Live" --max-size 900
