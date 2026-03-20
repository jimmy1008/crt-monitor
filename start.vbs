Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)
WshShell.CurrentDirectory = strDir

If Not fso.FolderExists(strDir & "\data") Then
    fso.CreateFolder(strDir & "\data")
End If

Dim rc
rc = WshShell.Run("cmd /c python --version > nul 2>&1", 0, True)

If rc <> 0 Then
    Dim ans
    ans = MsgBox("Python not found. Install automatically?" & vbCrLf & "(About 1-2 minutes)", vbYesNo + vbQuestion, "CRT Monitor")

    If ans = vbNo Then
        WScript.Quit
    End If

    Dim installRc
    installRc = WshShell.Run("cmd /c winget install Python.Python.3.13 --accept-package-agreements --accept-source-agreements --scope machine > data\python_install.log 2>&1", 1, True)

    Dim envPath
    envPath = WshShell.RegRead("HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\Environment\Path")
    Dim userPath
    On Error Resume Next
    userPath = WshShell.RegRead("HKCU\Environment\Path")
    If Err.Number <> 0 Then userPath = ""
    On Error GoTo 0
    WshShell.Environment("Process")("Path") = envPath & ";" & userPath

    rc = WshShell.Run("cmd /c python --version > nul 2>&1", 0, True)
    If rc <> 0 Then
        MsgBox "Python install failed. Please reboot and try again.", vbExclamation, "CRT Monitor"
        WScript.Quit
    End If
End If

If Not fso.FileExists(strDir & "\data\.installed") Then
    WshShell.Run "cmd /c echo Installing dependencies... && python -m pip install --upgrade pip > data\install.log 2>&1 && python -m pip install -r requirements.txt >> data\install.log 2>&1 && echo ok > data\.installed", 1, True

    If Not fso.FileExists(strDir & "\data\.installed") Then
        Dim logMsg
        logMsg = ""
        If fso.FileExists(strDir & "\data\install.log") Then
            Set f = fso.OpenTextFile(strDir & "\data\install.log", 1)
            If Not f.AtEndOfStream Then logMsg = f.ReadAll
            f.Close
        End If
        MsgBox "Install failed!" & vbCrLf & vbCrLf & Left(logMsg, 800), vbCritical, "CRT Monitor"
        WScript.Quit
    End If
End If

WshShell.Run "cmd /c python -m streamlit run dashboard.py --server.headless true --server.port 8520 > data\server.log 2>&1", 0, False

Dim ready, i
ready = False
For i = 1 To 30
    WScript.Sleep 1000
    On Error Resume Next
    Set http = CreateObject("MSXML2.ServerXMLHTTP")
    http.SetTimeouts 1000, 1000, 1000, 1000
    http.Open "GET", "http://localhost:8520/_stcore/health", False
    http.Send
    If Err.Number = 0 And http.Status = 200 Then
        ready = True
    End If
    Set http = Nothing
    On Error GoTo 0
    If ready Then Exit For
Next

If ready Then
    WshShell.Run "http://localhost:8520"
Else
    Dim serverLog
    serverLog = ""
    If fso.FileExists(strDir & "\data\server.log") Then
        Set f = fso.OpenTextFile(strDir & "\data\server.log", 1)
        If Not f.AtEndOfStream Then serverLog = f.ReadAll
        f.Close
    End If
    MsgBox "Launch failed!" & vbCrLf & vbCrLf & Left(serverLog, 600), vbExclamation, "CRT Monitor"
End If
