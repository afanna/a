@echo off
setlocal EnableExtensions

rem ===== Project configuration =====
rem Fill these two paths after the real ArkTS project is checked in.
set "DEVECO_SDK_HOME="
set "JAVA_HOME="

set "BUNDLE_NAME=yyx.test.test"
set "ABILITY_NAME=EntryAbility"
set "MODULE_NAME=entry"

rem Prefer the project wrapper when it exists. Some older notes spell this as
rem hvigrow; the normal DevEco wrapper is hvigorw, so both are supported.
set "PROJECT_ROOT=%~dp0"
set "HVIGOR_CMD=hvigorw"
if exist "%PROJECT_ROOT%hvigorw.bat" set "HVIGOR_CMD=%PROJECT_ROOT%hvigorw.bat"
if exist "%PROJECT_ROOT%hvigorw" set "HVIGOR_CMD=%PROJECT_ROOT%hvigorw"
if exist "%PROJECT_ROOT%hvigrow.bat" set "HVIGOR_CMD=%PROJECT_ROOT%hvigrow.bat"
if exist "%PROJECT_ROOT%hvigrow" set "HVIGOR_CMD=%PROJECT_ROOT%hvigrow"

set "HAP_PATH=%PROJECT_ROOT%%MODULE_NAME%\build\default\outputs\default\%MODULE_NAME%-default-signed.hap"
set "HAP_OUTPUT_DIR=%PROJECT_ROOT%%MODULE_NAME%\build\default\outputs\default"

if "%DEVECO_SDK_HOME%"=="" (
  echo DEVECO_SDK_HOME is not configured.
  exit /b 2
)

if "%JAVA_HOME%"=="" (
  echo JAVA_HOME is not configured.
  exit /b 2
)

if not exist "%JAVA_HOME%\bin\java.exe" (
  echo JAVA_HOME does not contain bin\java.exe: %JAVA_HOME%
  exit /b 2
)

rem DevEco JDK must be ahead of the system JDK for signing tools.
set "PATH=%JAVA_HOME%\bin;%DEVECO_SDK_HOME%\toolchains;%PATH%"

for /f "tokens=1-3 delims=:." %%a in ("%TIME: =0%") do set "RUN_TS=%%a%%b%%c"
set "REMOTE_DIR=/data/local/tmp/tmp_%RUN_TS%"

pushd "%PROJECT_ROOT%" || exit /b 1

echo [1/8] clean
call :run_hvigor clean
if errorlevel 1 goto fail

echo [2/8] assembleHap
call :run_hvigor assembleHap
if errorlevel 1 goto fail

echo [3/8] check HAP output
dir "%HAP_OUTPUT_DIR%\*.hap"

echo [4/8] mkdir remote install directory: %REMOTE_DIR%
hdc shell mkdir -p "%REMOTE_DIR%"
if errorlevel 1 goto fail

echo [5/8] push signed HAP: %HAP_PATH%
hdc file send "%HAP_PATH%" "%REMOTE_DIR%/%MODULE_NAME%-default-signed.hap"
if errorlevel 1 goto fail

echo [6/8] install from device local path
hdc shell bm install -p "%REMOTE_DIR%"
if errorlevel 1 goto fail

echo [7/8] cleanup remote install directory
hdc shell rm -rf "%REMOTE_DIR%"
if errorlevel 1 goto fail

echo [8/8] launch %BUNDLE_NAME%/%ABILITY_NAME%
hdc shell aa force-stop "%BUNDLE_NAME%"
hdc shell aa start -a "%ABILITY_NAME%" -b "%BUNDLE_NAME%" -m "%MODULE_NAME%"
if errorlevel 1 goto fail

popd
echo ArkTS build, install, and launch finished.
pause
exit /b 0

:fail
set "EXIT_CODE=%ERRORLEVEL%"
echo Build/install/launch failed with exit code %EXIT_CODE%.
if not "%REMOTE_DIR%"=="" hdc shell rm -rf "%REMOTE_DIR%" >nul 2>nul
popd
pause
exit /b %EXIT_CODE%

:run_hvigor
if exist "%HVIGOR_CMD%" (
  call "%HVIGOR_CMD%" %*
) else (
  call %HVIGOR_CMD% %*
)
exit /b %ERRORLEVEL%
