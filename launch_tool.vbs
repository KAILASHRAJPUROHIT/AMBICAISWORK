' Aradhana Catalogue Tool – launcher
Dim shell, fso, http, port, url
Set shell = CreateObject("WScript.Shell")
Set fso   = CreateObject("Scripting.FileSystemObject")

Const TOOL      = "C:\Users\kaila\Desktop\JewelleryCatalogTool"
Const PORT_FILE = "C:\Users\kaila\Desktop\JewelleryCatalogTool\port.txt"
Const DEFAULT_PORT = "7654"
Const LOG_FILE  = "C:\Users\kaila\Desktop\JewelleryCatalogTool\logs\run.log"
Const LOG_MAX_BYTES = 5242880  ' 5 MB — rotate one generation past this

' ── Rotate the run log so it never grows unbounded, but still leaves a ──────
' trail for the next morning's review after an unattended overnight run —
' previously ALL diagnostic output went to the stdout of a hidden window
' with nothing capturing it anywhere.
If fso.FileExists(LOG_FILE) Then
    On Error Resume Next
    If fso.GetFile(LOG_FILE).Size > LOG_MAX_BYTES Then
        Dim oldLog : oldLog = LOG_FILE & ".old"
        If fso.FileExists(oldLog) Then fso.DeleteFile oldLog
        fso.MoveFile LOG_FILE, oldLog
    End If
    On Error GoTo 0
End If

' ── Check if server is already up ────────────────────────────────────────────
' NOTE: VBScript's "And" does not short-circuit — "Err.Number = 0 And
' http.Status = 200" used to evaluate http.Status even when Send had
' already failed, and reading .Status on a failed request throws its own
' error, which could leave `already` set True even though the server was
' genuinely down. That made the launcher skip starting the server and just
' open a browser tab to a dead port ("unable to connect"). Splitting the
' Err.Number check into its own guard avoids ever touching .Status unless
' the request actually succeeded.
Dim already : already = False
On Error Resume Next
Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
http.Open "GET", "http://127.0.0.1:" & DEFAULT_PORT & "/", False
http.SetTimeouts 1000, 1000, 1500, 1500
http.Send
If Err.Number = 0 Then
    If http.Status = 200 Then already = True
End If
On Error GoTo 0

' ── Start server only if not already running ─────────────────────────────────
If Not already Then
    ' Remove stale port.txt so we can detect fresh start
    If fso.FileExists(PORT_FILE) Then fso.DeleteFile PORT_FILE

    ' Stamp a launch marker so the log makes sense when read the next morning
    On Error Resume Next
    Dim logTs : Set logTs = fso.OpenTextFile(LOG_FILE, 8, True) ' 8 = append, create if missing
    logTs.WriteLine "===== launch " & Now & " ====="
    logTs.Close
    On Error GoTo 0

    ' Redirect stdout/stderr through cmd so every print()/traceback lands in
    ' run.log instead of vanishing into a hidden window's stdout. No outer
    ' wrapping quote around the whole "/c ..." argument — cmd.exe parses
    ' ">>"/"2>&1" as redirection operators directly in the command line it's
    ' handed; only the file paths themselves need quoting (they may contain
    ' spaces even though this particular install path doesn't).
    Dim cmdLine
    cmdLine = "cmd /c py -3.11 """ & TOOL & "\app.py"" >> """ & LOG_FILE & """ 2>&1"
    shell.Run cmdLine, 0, False

    ' Wait up to 20 s for server to write port.txt and start responding
    Dim tries : tries = 0
    Do While tries < 40
        WScript.Sleep 500
        If fso.FileExists(PORT_FILE) Then
            Dim ts : Set ts = fso.OpenTextFile(PORT_FILE, 1)
            port = Trim(ts.ReadLine())
            ts.Close
            ' Verify it's actually accepting connections
            On Error Resume Next
            Set http = CreateObject("WinHttp.WinHttpRequest.5.1")
            http.Open "GET", "http://127.0.0.1:" & port & "/", False
            http.SetTimeouts 500, 500, 1500, 1500
            http.Send
            If Err.Number = 0 Then
                If http.Status = 200 Then tries = 99 ' signal success
            End If
            On Error GoTo 0
        End If
        tries = tries + 1
    Loop
    If port = "" Then port = DEFAULT_PORT
Else
    port = DEFAULT_PORT
End If

url = "http://127.0.0.1:" & port
shell.Run url, 1, False
