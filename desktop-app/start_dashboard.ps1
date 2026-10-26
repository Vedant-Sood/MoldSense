$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $AppRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw 'Run install_windows.ps1 first.' }
& $Python (Join-Path $AppRoot 'run_dashboard.py')
