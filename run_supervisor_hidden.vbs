' Hidden-window wrapper for the AMBICCatalogueSupervisor scheduled task.
' The task previously invoked powershell.exe directly, which — regardless of
' the task's own "Hidden" setting (that only hides the task from the Task
' Scheduler UI, not the process window) — pops a visible console every time
' it fires on its 5-minute schedule. Routing through WScript.Shell.Run with
' windowStyle=0 is the same trick launch_tool.vbs already uses to keep the
' actual app.py process invisible; this applies it to the outer supervisor
' check itself so nothing flashes on screen at all.
Dim shell, fso, tool
Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")
tool = fso.GetParentFolderName(WScript.ScriptFullName)
Dim cmdLine
cmdLine = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File """ & tool & "\supervisor.ps1"""
shell.Run cmdLine, 0, True
