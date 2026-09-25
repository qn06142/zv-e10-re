@echo off
REM retool launcher -- works regardless of the PowerShell execution policy.
REM Usage:  retool.cmd doctor
REM         retool.cmd analyze avcam --force
REM         retool.cmd symbols apply avcam
REM         retool.cmd export avcam
setlocal
cd /d "%~dp0"

set "PY="
if exist ".venv-re\bin\python.exe" set "PY=.venv-re\bin\python.exe"
if exist ".venv-re\Scripts\python.exe" set "PY=.venv-re\Scripts\python.exe"
if not defined PY (
  for %%P in (python python3 py) do (
    if not defined PY if not "%%~P"=="py" (
      for /f "delims=" %%I in ('where %%P 2^>nul') do if not defined PY set "PY=%%I"
    )
  )
)
if not defined PY (
  echo ERROR: no Python found. Create one with:  python -m venv .venv-re
  exit /b 1
)

"%PY%" -m retool %*
exit /b %ERRORLEVEL%
