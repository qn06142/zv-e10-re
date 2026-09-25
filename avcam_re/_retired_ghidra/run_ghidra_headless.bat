@echo off
REM Fully self-contained Ghidra headless analysis of ZV-E10 av-cam.bin.
REM Sets JAVA_HOME, PATH, GHIDRA_HOME internally. No external env needed.
set JAVA_HOME=C:\Program Files\Eclipse Adoptium\jdk-21.0.12.8-hotspot
set PATH=%JAVA_HOME%\bin;%PATH%
set GHIDRA_HOME=C:\Users\Minhsnguhoa\Downloads\ghidra_12.1.2_PUBLIC
set PROJ=C:\Users\Minhsnguhoa\pmca-re\avcam_re\ghidra_proj
set SCRIPT_DIR=C:\Users\Minhsnguhoa\pmca-re\avcam_re
set BIN=C:\Users\Minhsnguhoa\pmca-re\dumps\av-cam.bin
if not exist "%BIN%" ( echo ERROR: %BIN% missing & exit /b 1 )
if not exist "%PROJ%" mkdir "%PROJ%"
"%GHIDRA_HOME%\support\analyzeHeadless.bat" "%PROJ%" avcam -import "%BIN%" -processor ARM:LE:32:v7 -postScript "%SCRIPT_DIR%\ghidra_headless.py" -scriptPath "%SCRIPT_DIR%"
echo.
echo Done. Output: %SCRIPT_DIR%\out\ghidra_analysis.json
