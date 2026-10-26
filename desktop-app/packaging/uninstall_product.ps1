$ErrorActionPreference = 'SilentlyContinue'
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\MoldSense'
$StartMenuFolder = Join-Path ([Environment]::GetFolderPath('Programs')) 'MoldSense'
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'MoldSense.lnk'

Get-Process -Name MoldSense -ErrorAction SilentlyContinue | Stop-Process -Force
Remove-Item -LiteralPath $DesktopShortcut -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath $StartMenuFolder -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item -LiteralPath 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\MoldSense' -Recurse -Force -ErrorAction SilentlyContinue

Add-Type -AssemblyName PresentationFramework
$Choice = [System.Windows.MessageBox]::Show('MoldSense was removed. Your saved sensor logs were preserved in Local AppData.', 'MoldSense Uninstall')
$Cleanup = "Start-Sleep -Milliseconds 900; Remove-Item -LiteralPath '$($InstallRoot.Replace("'","''"))' -Recurse -Force -ErrorAction SilentlyContinue"
Start-Process powershell.exe -WindowStyle Hidden -ArgumentList '-NoProfile','-Command',$Cleanup
