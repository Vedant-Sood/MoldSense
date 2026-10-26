$ErrorActionPreference = 'Stop'
$ProductName = 'MoldSense'
$InstallRoot = Join-Path $env:LOCALAPPDATA 'Programs\MoldSense'
$Executable = Join-Path $InstallRoot 'MoldSense.exe'
$StartMenuFolder = Join-Path ([Environment]::GetFolderPath('Programs')) 'MoldSense'
$DesktopShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'MoldSense.lnk'
$StartShortcut = Join-Path $StartMenuFolder 'MoldSense.lnk'

if (Get-Process -Name MoldSense -ErrorAction SilentlyContinue) {
    Add-Type -AssemblyName PresentationFramework
    [System.Windows.MessageBox]::Show('Close MoldSense before installing this update.', 'MoldSense Setup') | Out-Null
    exit 1
}

New-Item -ItemType Directory -Force -Path $InstallRoot,$StartMenuFolder | Out-Null
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'MoldSense.exe') -Destination $Executable -Force
Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'uninstall_product.ps1') -Destination (Join-Path $InstallRoot 'uninstall_product.ps1') -Force

$Shell = New-Object -ComObject WScript.Shell
foreach ($ShortcutPath in @($DesktopShortcut,$StartShortcut)) {
    $Shortcut = $Shell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $Executable
    $Shortcut.WorkingDirectory = $InstallRoot
    $Shortcut.Description = 'Open MoldSense environmental insights'
    $Shortcut.IconLocation = "$Executable,0"
    $Shortcut.Save()
}

$UninstallKey = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\MoldSense'
New-Item -Path $UninstallKey -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name DisplayName -Value 'MoldSense Research' -PropertyType String -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name DisplayVersion -Value '2.0.0-rc1' -PropertyType String -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name Publisher -Value 'MoldSense' -PropertyType String -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name InstallLocation -Value $InstallRoot -PropertyType String -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name DisplayIcon -Value $Executable -PropertyType String -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name UninstallString -Value "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$(Join-Path $InstallRoot 'uninstall_product.ps1')`"" -PropertyType String -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name NoModify -Value 1 -PropertyType DWord -Force | Out-Null
New-ItemProperty -Path $UninstallKey -Name NoRepair -Value 1 -PropertyType DWord -Force | Out-Null

Start-Process -FilePath $Executable
