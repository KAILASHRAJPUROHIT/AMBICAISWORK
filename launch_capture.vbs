' Aradhana Capture Server - launcher (isolated from the main catalogue tool)
' Mirrors launch_tool.vbs exactly, but targets capture_server.py on its own
' port — kept as a fully separate script/log/port-file so relaunching this
' never depends on, or interferes with, the main tool's own launcher.
Dim shell, fso, http, port, url
Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

Const TOOL      = "C:\AradhanaSystems\projects\catalogue-capture\main"
Const PYTHON_EXE = "C:\Users\kaila\AppData\Local\Programs\Python\Python310\python.exe"
Const PORT_FILE = "C:\AradhanaSystems\projects\catalogue-capture\main\capture_port.txt"
Const DEFAULT_PORT = "7660"
Const LOG_FILE  = "C:\AradhanaSystems\projects\catalogue-capture\main\logs\capture_run.log"
Const LOG_MAX_BYTES = 5242880

If fso.FileExists(LOG_FILE) Then
    On Error Resume Next
    If fso.GetFile(LOG_FILE).Size > LOG_MAX_BYTES Then
        Dim oldLog : oldLog = LOG_FILE & ".old"
        If fso.FileExists(oldLog) Then fso.DeleteFile oldLog
        fso.MoveFile LOG_FILE, oldLog
    End If
    On Error GoTo 0
End If

Dim already : already = False
On Error Resume Next
Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
http.Open "GET", "https://127.0.0.1:" & DEFAULT_PORT & "/api/health", False
http.Option(4) = 13056
http.SetTimeouts 1000, 1000, 1500, 1500
http.Send
If Err.Number = 0 Then
    If http.Status = 200 Then already = True
End If
On Error GoTo 0

If Not already Then
    If fso.FileExists(PORT_FILE) Then fso.DeleteFile PORT_FILE

    On Error Resume Next
    Dim logTs : Set logTs = fso.OpenTextFile(LOG_FILE, 8, True)
    logTs.WriteLine "===== launch " & Now & " ====="
    logTs.Close
    On Error GoTo 0

    Dim cmdLine
    cmdLine = "cmd /c " & Chr(34) & PYTHON_EXE & Chr(34) & " " & _
              Chr(34) & TOOL & "\capture_server.py" & Chr(34) & " >> " & _
              Chr(34) & LOG_FILE & Chr(34) & " 2>&1"
    shell.Run cmdLine, 0, False

    Dim tries : tries = 0
    Do While tries < 40
        WScript.Sleep 500
        If fso.FileExists(PORT_FILE) Then
            Dim ts : Set ts = fso.OpenTextFile(PORT_FILE, 1)
            port = Trim(ts.ReadLine())
            ts.Close
            On Error Resume Next
            Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
            http.Open "GET", "https://127.0.0.1:" & port & "/api/health", False
            http.Option(4) = 13056
            http.SetTimeouts 500, 500, 1500, 1500
            http.Send
            If Err.Number = 0 Then
                If http.Status = 200 Then tries = 99
            End If
            On Error GoTo 0
        End If
        tries = tries + 1
    Loop
    If port = "" Then port = DEFAULT_PORT
Else
    port = DEFAULT_PORT
End If

' No browser window opened here — this launcher exists purely for the
' supervisor's automated relaunch-on-crash path, not for a human to run by
' hand and expect a UI to pop up. The staff-facing URL to bookmark is
' https://<lan-ip>:7660/capture, unrelated to this launch action.
