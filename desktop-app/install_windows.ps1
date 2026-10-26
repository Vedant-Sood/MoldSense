$ErrorActionPreference = 'Stop'
$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Venv = Join-Path $AppRoot '.venv'
$PyLauncher = Get-Command py -ErrorAction SilentlyContinue
$PythonExe = Get-Command python -ErrorAction SilentlyContinue
if ($PyLauncher) {
    $PythonCommand = $PyLauncher.Source
    $PythonArguments = @('-3')
} elseif ($PythonExe) {
    $PythonCommand = $PythonExe.Source
    $PythonArguments = @()
} else {
    throw 'Python 3.11 or newer was not found in PATH.'
}
$VersionOkay = & $PythonCommand @PythonArguments -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)"
if ($LASTEXITCODE -ne 0) { throw 'Python 3.11 or newer is required.' }
Write-Host "Using $(& $PythonCommand @PythonArguments --version) from $PythonCommand"
& $PythonCommand @PythonArguments -m venv $Venv
& (Join-Path $Venv 'Scripts\python.exe') -m pip install --upgrade pip
& (Join-Path $Venv 'Scripts\python.exe') -m pip install -r (Join-Path $AppRoot 'requirements.txt')
$Launcher = Join-Path $AppRoot 'MoldSense Dashboard.vbs'
$Pythonw = Join-Path $Venv 'Scripts\pythonw.exe'
$Script = Join-Path $AppRoot 'run_dashboard.py'
$VbsText = 'CreateObject("Wscript.Shell").Run """' + $Pythonw + '"" ""' + $Script + '""", 0, False'
Set-Content -LiteralPath $Launcher -Value $VbsText -Encoding ASCII
Start-Process -FilePath $Launcher
Write-Host 'MoldSense installed and started. Use start_dashboard.ps1 whenever you want to open it again.'
