param(
    [string]$ArduinoCli = 'arduino-cli',
    [string]$Fqbn = 'esp32:esp32:esp32doit-devkit-v1',
    [int]$Jobs = 4,
    [string]$Python = 'python',
    [string]$ConfigFile = ''
)
$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
& $Python (Join-Path $PSScriptRoot 'setup_bsec.py') --check
if ($LASTEXITCODE -ne 0) { throw 'Install the matching local BSEC SDK before compiling.' }
$CliArgs = @()
if ($ConfigFile) { $CliArgs += @('--config-file', (Resolve-Path -LiteralPath $ConfigFile).Path) }
$CliArgs += @('compile', '--fqbn', $Fqbn, '--jobs', $Jobs,
    '--libraries', (Join-Path $ProjectRoot 'vendor'),
    '--build-path', (Join-Path $ProjectRoot 'build/cache'),
    '--output-dir', (Join-Path $ProjectRoot 'build'), $ProjectRoot)
& $ArduinoCli @CliArgs
if ($LASTEXITCODE -ne 0) { throw 'Firmware compilation failed.' }
# Compile only: no upload, erase, port opening or filesystem formatting.
