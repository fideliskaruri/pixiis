@echo off
REM Build whisper-bench in release mode (Windows / MSVC).
REM Locates VS via vswhere and sources vcvars64.bat for the C++ toolchain.

set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
if not exist "%VSWHERE%" (
  echo vswhere.exe not found at "%VSWHERE%" — install Visual Studio Installer.
  exit /b 1
)

for /f "usebackq tokens=*" %%i in (`"%VSWHERE%" -latest -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do (
  set "VSDIR=%%i"
)
if "%VSDIR%"=="" (
  echo No VS install with the C++ x64 build tools workload was found. Install
  echo "Desktop development with C++" via the Visual Studio Installer.
  exit /b 1
)

REM Sourcing vcvars64.bat with a relative path avoids a known cmd.exe bug where
REM "%~dp0vcvarsall.bat" fails when cmd is launched from outside Windows shells.
pushd "%VSDIR%\VC\Auxiliary\Build"
call vcvars64.bat
set VCVARS_RC=%errorlevel%
popd
if not "%VCVARS_RC%"=="0" (
  echo failed to source vcvars64.bat (rc=%VCVARS_RC%)
  exit /b 1
)

set "PATH=%PATH%;C:\Program Files\CMake\bin"

pushd "%~dp0\.."
cargo build --release
set BUILD_RC=%errorlevel%
popd
exit /b %BUILD_RC%
