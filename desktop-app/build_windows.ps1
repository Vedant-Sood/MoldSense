$ErrorActionPreference = 'Stop'
$AppRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$Python = Join-Path $AppRoot '.venv\Scripts\python.exe'
if (-not (Test-Path $Python)) { throw 'Run install_windows.ps1 once to create the development environment.' }

& $Python -m pip install -r (Join-Path $AppRoot 'requirements-build.txt')
if ($LASTEXITCODE -ne 0) { throw 'Build dependency installation failed.' }

$BuildDirectory = Join-Path $AppRoot 'build'
$DistDirectory = Join-Path $AppRoot 'dist'
$ReleaseDirectory = Join-Path $AppRoot 'release'
$ProjectRoot = (Resolve-Path -LiteralPath $AppRoot).Path
foreach ($Target in @($BuildDirectory,$DistDirectory)) {
    if (Test-Path $Target) {
        $Resolved = (Resolve-Path -LiteralPath $Target).Path
        if (-not $Resolved.StartsWith($ProjectRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw "Unsafe build target: $Resolved" }
        Remove-Item -LiteralPath $Resolved -Recurse -Force
    }
}
New-Item -ItemType Directory -Force -Path $ReleaseDirectory | Out-Null

& $Python -m PyInstaller --noconfirm --clean --onefile --windowed `
    --name MoldSense `
    --icon (Join-Path $AppRoot 'assets\moldsense.ico') `
    --version-file (Join-Path $AppRoot 'packaging\version_info.txt') `
    --add-data "$(Join-Path $AppRoot 'assets');assets" `
    --add-data "$(Join-Path $AppRoot 'baselines');baselines" `
    --distpath $DistDirectory `
    --workpath $BuildDirectory `
    --specpath $BuildDirectory `
    (Join-Path $AppRoot 'run_dashboard.py')

$ApplicationExe = Join-Path $DistDirectory 'MoldSense.exe'
if (-not (Test-Path $ApplicationExe)) { throw 'PyInstaller did not produce MoldSense.exe.' }
Copy-Item -LiteralPath $ApplicationExe -Destination (Join-Path $ReleaseDirectory 'MoldSense-Portable.exe') -Force

$Payload = Join-Path $BuildDirectory 'installer_payload'
New-Item -ItemType Directory -Force -Path $Payload | Out-Null
Copy-Item -LiteralPath $ApplicationExe -Destination (Join-Path $Payload 'MoldSense.exe')
Copy-Item -LiteralPath (Join-Path $AppRoot 'packaging\install.cmd') -Destination $Payload
Copy-Item -LiteralPath (Join-Path $AppRoot 'packaging\install_product.ps1') -Destination $Payload
Copy-Item -LiteralPath (Join-Path $AppRoot 'packaging\uninstall_product.ps1') -Destination $Payload

$SetupExe = Join-Path $ReleaseDirectory 'MoldSense-Setup-2.0.0-rc1.exe'
$SedPath = Join-Path $BuildDirectory 'MoldSense-Setup.sed'
if (Test-Path -LiteralPath $SetupExe) { Remove-Item -LiteralPath $SetupExe -Force }
$Sed = @"
[Version]
Class=IEXPRESS
SEDVersion=3
[Options]
PackagePurpose=InstallApp
ShowInstallProgramWindow=0
HideExtractAnimation=0
UseLongFileName=1
InsideCompressed=0
CAB_FixedSize=0
CAB_ResvCodeSigning=0
RebootMode=N
InstallPrompt=%InstallPrompt%
DisplayLicense=
FinishMessage=%FinishMessage%
TargetName=$SetupExe
FriendlyName=MoldSense Setup
AppLaunched=install.cmd
PostInstallCmd=<None>
AdminQuietInstCmd=install.cmd
UserQuietInstCmd=install.cmd
SourceFiles=SourceFiles
[Strings]
InstallPrompt=Install MoldSense User Dashboard?
FinishMessage=MoldSense has been installed and added to your desktop.
FILE0=MoldSense.exe
FILE1=install.cmd
FILE2=install_product.ps1
FILE3=uninstall_product.ps1
[SourceFiles]
SourceFiles0=$Payload\
[SourceFiles0]
%FILE0%=
%FILE1%=
%FILE2%=
%FILE3%=
"@
Set-Content -LiteralPath $SedPath -Value $Sed -Encoding ASCII
& "$env:WINDIR\System32\iexpress.exe" /N $SedPath
for ($Attempt = 0; $Attempt -lt 120 -and -not (Test-Path $SetupExe); $Attempt++) { Start-Sleep -Seconds 1 }
if (-not (Test-Path $SetupExe)) { throw 'IExpress did not produce the setup executable.' }

Get-ChildItem -LiteralPath $ReleaseDirectory -Filter '~MoldSense-Setup-2.0.0-rc1*' | Remove-Item -Force
$PortableExe = Join-Path $ReleaseDirectory 'MoldSense-Portable.exe'
$Hashes = Get-FileHash $PortableExe,$SetupExe -Algorithm SHA256
$HashLines = $Hashes | ForEach-Object { "$($_.Hash)  $([IO.Path]::GetFileName($_.Path))" }
Set-Content -LiteralPath (Join-Path $ReleaseDirectory 'SHA256SUMS.txt') -Value $HashLines -Encoding ASCII

Get-FileHash $PortableExe,$SetupExe -Algorithm SHA256 | Format-Table Path,Hash
Write-Host "Build complete: $SetupExe"
