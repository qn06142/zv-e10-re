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
foreach ($cand in @(
    "$root\.venv\Scripts\python.exe",
    "$root\.venv\bin\python.exe",
    "$root\.venv-re\Scripts\python.exe",
    "$root\.venv-re\bin\python.exe"
)) {
    if (Test-Path $cand) { $py = $cand; break }
}
if (-not $py) {
    $cmd = Get-Command python, python3, py -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($cmd) { $py = $cmd.Source }
}
if (-not $py) {
    Write-Error "No Python found. Install Python 3.11+ or run: python -m venv .venv"
    exit 1
}

# --- locate rizin and rz-bin (config value, then scripts/tools/ directory, then PATH) ---
if (-not $env:RETOOL_RIZIN) {
    $rz = Get-ChildItem "$root\scripts\tools\rizin" -Recurse -Filter 'rizin.exe' -ErrorAction SilentlyContinue |
          Select-Object -First 1
    if (-not $rz) {
        $rz = Get-ChildItem "$root\.tools\rizin" -Recurse -Filter 'rizin.exe' -ErrorAction SilentlyContinue |
              Select-Object -First 1
    }
    if ($rz) {
        $env:RETOOL_RIZIN = $rz.FullName
    } elseif (Get-Command rizin -ErrorAction SilentlyContinue) {
        $env:RETOOL_RIZIN = (Get-Command rizin).Source
    }
}

if (-not $env:RETOOL_RZBIN) {
    if ($env:RETOOL_RIZIN) {
        $rzbinCand = Join-Path (Split-Path -Parent $env:RETOOL_RIZIN) "rz-bin.exe"
        if (Test-Path $rzbinCand) {
            $env:RETOOL_RZBIN = $rzbinCand
        }
    }
    if (-not $env:RETOOL_RZBIN) {
        $rzb = Get-ChildItem "$root\scripts\tools\rizin" -Recurse -Filter 'rz-bin.exe' -ErrorAction SilentlyContinue |
               Select-Object -First 1
        if (-not $rzb) {
            $rzb = Get-ChildItem "$root\.tools\rizin" -Recurse -Filter 'rz-bin.exe' -ErrorAction SilentlyContinue |
                   Select-Object -First 1
        }
        if ($rzb) {
            $env:RETOOL_RZBIN = $rzb.FullName
        } elseif (Get-Command rz-bin -ErrorAction SilentlyContinue) {
            $env:RETOOL_RZBIN = (Get-Command rz-bin).Source
        }
    }
}

& $py -m retool @Args
exit $LASTEXITCODE
