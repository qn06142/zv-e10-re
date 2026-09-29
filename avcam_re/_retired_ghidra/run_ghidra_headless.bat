@echo off
REM Fully self-contained Ghidra headless analysis of ZV-E10 av-cam.bin.
REM Sets JAVA_HOME, PATH, GHIDRA_HOME internally. No external env needed.
REM
REM RETIRED: this project has moved to the retool package (see RETOOL.md); the
REM Ghidra project it drove is no longer in the tree. Kept for reference.
REM
REM Override any of these from the environment before invoking, e.g.
REM   set GHIDRA_HOME=C:\tools\ghidra_12.1.2_PUBLIC && run_ghidra_headless.bat
set "JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot"
set "PATH=%JAVA_HOME%\bin;%PATH%"
if "%GHIDRA_HOME%"=="" set "GHIDRA_HOME=C:\Users\%USERNAME%\Downloads\ghidra_12.1.2_PUBLIC"
set "SCRIPT_DIR=%~dp0"
for %%I in ("%SCRIPT_DIR%..") do set "REPO=%%~fI"
set "PROJ=%SCRIPT_DIR%ghidra_proj"
set "BIN=%REPO%\dumps\av-cam.bin"
if not exist "%BIN%" ( echo ERROR: %BIN% missing & exit /b 1 )
if not exist "%PROJ%" mkdir "%PROJ%"
"%GHIDRA_HOME%\support\analyzeHeadless.bat" "%PROJ%" avcam -import "%BIN%" -processor ARM:LE:32:v7 -postScript "%SCRIPT_DIR%ghidra_headless.py" -scriptPath "%SCRIPT_DIR%"
echo.
echo Done. Output: %SCRIPT_DIR%out\ghidra_analysis.json
