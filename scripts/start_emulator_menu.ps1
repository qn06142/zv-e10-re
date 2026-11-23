param(
    [switch]$CaptureOnly,
    [string]$Output
)
$ErrorActionPreference = 'Stop'
$emulatorRepo = Split-Path -Parent $PSScriptRoot
$emulatorPython = Join-Path $emulatorRepo '.venv\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $emulatorPython)) {
    throw "Repository Python environment is missing: $emulatorPython"
}
$menuArguments = @('-m', 'emulator.menu')
if (-not $CaptureOnly) { $menuArguments += '--window' }
if ($Output) { $menuArguments += @('--output', [System.IO.Path]::GetFullPath($Output)) }
Push-Location -LiteralPath $emulatorRepo
try {
    & $emulatorPython @menuArguments
    if ($LASTEXITCODE -ne 0) { throw "Menu emulator exited with code $LASTEXITCODE" }
}
finally { Pop-Location }
