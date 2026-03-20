Set WshShell = CreateObject("WScript.Shell")
WshShell.Run "cmd /c taskkill /F /IM python.exe /FI ""WINDOWTITLE eq *streamlit*""", 0, False
WshShell.Run "cmd /c taskkill /F /IM python.exe /FI ""COMMANDLINE eq *dashboard*""", 0, False
