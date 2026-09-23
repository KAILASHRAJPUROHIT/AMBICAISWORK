' Canonical staff shortcut. The catalogue itself is supervised as a Windows
' service; this script only opens its canonical local interface.
CreateObject("WScript.Shell").Run "http://127.0.0.1:7654", 1, False
