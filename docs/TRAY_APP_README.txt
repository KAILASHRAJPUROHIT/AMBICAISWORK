Aradhana Jewellers - Ornate NX AutoPrint Tray App v2

PURPOSE
-------
Automatically clicks only the standard Windows Print button for a Print dialog
that belongs to the confirmed Ornate executable:

Process: ONX
Path:    D:\Ornnx\ONX.exe

It does not use SendKeys, global Enter, mouse movement, a PowerShell loop,
a Scheduled Task, or a Windows Service.

WHY NOT A WINDOWS SERVICE?
--------------------------
Windows services run in Session 0 and cannot reliably interact with a Print
dialog displayed in the logged-in user's desktop session. This tray app runs in
the correct interactive user session.

FILES
-----
AradhanaOrnateAutoPrint.cs
    C# source code.

Build_Aradhana_Ornate_AutoPrint.bat
    Compiles the source using the Windows .NET Framework C# compiler.

Install_Aradhana_Ornate_AutoPrint.bat
    Copies the EXE to C:\ProgramData\Aradhana\OrnateAutoPrintTray
    and adds a current-user HKCU Run entry so it launches after login.

Uninstall_Aradhana_Ornate_AutoPrint.bat
    Removes the startup entry, stops the app, and removes its installed folder.

INSTALL
-------
1. Extract all files into one folder.
2. Run Build_Aradhana_Ornate_AutoPrint.bat.
3. Confirm AradhanaOrnateAutoPrint.exe appears.
4. Right-click Install_Aradhana_Ornate_AutoPrint.bat and Run as administrator.
5. Look for the tray icon near the Windows clock.

TEST
----
A. Ornate print must auto-confirm.
B. Keep Ornate open, then print from Notepad. Notepad must remain untouched.
C. Reboot, log in, open Ornate, and test again.

LOG
---
C:\ProgramData\Aradhana\OrnateAutoPrintTray\OrnateAutoPrint.log

SECURITY NOTE
-------------
This is locally compiled unsigned software. Antivirus may still inspect or block
it. Do not disable antivirus globally. If NPAV blocks the normal tray EXE,
submit/review that exact EXE with your NPAV administrator/vendor rather than
adding broad exclusions.


V2 FIX
------
Uses C# syntax compatible with the older .NET Framework compiler included with Windows.
