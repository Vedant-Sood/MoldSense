param([string]$Python = (Join-Path $PSScriptRoot '.venv/Scripts/python.exe'))
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $Python)) { throw 'Create the project .venv and install requirements.txt first.' }
$researchBuild = Join-Path $PSScriptRoot 'build_research'
$researchDist = Join-Path $PSScriptRoot ('release_research/build_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
# A fresh output avoids deleting prior packages and OneDrive file-lock failures.
# Verify the output target stays inside the project.
$expectedRoot = (Resolve-Path -LiteralPath $PSScriptRoot).Path
$distributionTarget = [IO.Path]::GetFullPath((Join-Path $researchDist 'MoldSense-Research-2.0.0-rc1'))
if (-not $distributionTarget.StartsWith($expectedRoot + [IO.Path]::DirectorySeparatorChar,[StringComparison]::OrdinalIgnoreCase)) { throw 'Unsafe distribution target' }
if (Test-Path -LiteralPath $distributionTarget) {
    $resolvedTarget = (Resolve-Path -LiteralPath $distributionTarget).Path
    if ($resolvedTarget -ne $distributionTarget) { throw 'Unexpected distribution target resolution' }
}
New-Item -ItemType Directory -Force -Path $researchBuild,$researchDist | Out-Null
& $Python -m PyInstaller --noconfirm --onedir --windowed --name MoldSense-Research-2.0.0-rc1 --icon (Join-Path $PSScriptRoot 'assets/moldsense.ico') --add-data ((Join-Path $PSScriptRoot 'assets') + ';assets') --add-data ((Join-Path $PSScriptRoot 'baselines') + ';baselines') --distpath $researchDist --workpath $researchBuild --specpath $researchBuild (Join-Path $PSScriptRoot 'run_dashboard.py')
if ($LASTEXITCODE -ne 0) { throw 'Research executable build failed' }
Write-Host ('Research application: ' + (Join-Path $researchDist 'MoldSense-Research-2.0.0-rc1/MoldSense-Research-2.0.0-rc1.exe'))
# No installer, Startup registration, existing-release deletion or device operation.

Set-Content -LiteralPath (Join-Path $PSScriptRoot 'release_research/latest-build.txt') -Value $researchDist -Encoding utf8
