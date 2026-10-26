Option Explicit
Dim files, shell, appRoot, pythonExe, script
Set files = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
appRoot = files.GetParentFolderName(WScript.ScriptFullName)
pythonExe = files.BuildPath(appRoot, ".venv\Scripts\pythonw.exe")
If Not files.FileExists(pythonExe) Then pythonExe = "pythonw.exe"
script = files.BuildPath(appRoot, "run_dashboard.py")
shell.CurrentDirectory = appRoot
shell.Run Chr(34) & pythonExe & Chr(34) & " " & Chr(34) & script & Chr(34), 0, False
