<#
.SYNOPSIS
    Entry point for the pmca-re binary analysis pipeline (retool / rizin).

.DESCRIPTION
    Finds a usable Python (prefers the project venv, falls back to any python
    on PATH) and forwards all arguments to `python -m retool`.

.EXAMPLE
    .\retool.ps1 doctor
    .\retool.ps1 analyze avcam --force
    .\retool.ps1 symbols apply avcam
    .\retool.ps1 export avcam
    .\retool.ps1 xrefs avcam 0x7e8e88
#>
[CmdletBinding()]
param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Args
)

$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

# --- locate a python ---
$py = $null
foreach ($cand in @("$root\.venv-re\bin\python.exe", "$root\.venv-re\Scripts\python.exe")) {
    if (Test-Path $cand) { $py = $cand; break }
}
if (-not $py) {
    $cmd = Get-Command python, python3, py -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { $py = $cmd.Source }
}
if (-not $py) {
    Write-Error "No Python found. Install Python 3.11+ or run: python -m venv .venv-re"
    exit 1
}

# --- locate rizin (config value, then PATH) ---
$rizin = $env:RETOOL_RIZIN
if (-not $rizin) {
    $rz = Get-ChildItem "$root\.tools\rizin" -Recurse -Filter 'rizin.exe' -ErrorAction SilentlyContinue |
          Select-Object -First 1
    if ($rz) { $rizin = $rz.FullName }
    elseif (Get-Command rizin -ErrorAction SilentlyContinue) { $rizin = (Get-Command rizin).Source }
}

& $py -m retool @Args
exit $LASTEXITCODE
