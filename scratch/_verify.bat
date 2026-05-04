@echo off
set "MSVC=C:\Program Files\Microsoft Visual Studio\18\Enterprise\VC\Tools\MSVC\14.50.35717"
set "SDK=C:\Program Files (x86)\Windows Kits\10"
set "SDKVER=10.0.26100.0"
set "LIB=%MSVC%\lib\onecore\x64;%SDK%\Lib\%SDKVER%\ucrt\x64;%SDK%\Lib\%SDKVER%\um\x64"
set "PATH=%MSVC%\bin\HostX64\x64;%SDK%\bin\%SDKVER%\x64;C:\Users\fwachira\.cargo\bin;%PATH%"
cd /d D:\code\python\pixiis\.worktrees\pane8-controller\scratch\controller_verify
cargo %*
