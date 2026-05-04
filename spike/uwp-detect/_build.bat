@echo off
set "MSVC=C:\Program Files\Microsoft Visual Studio\18\Enterprise\VC\Tools\MSVC\14.50.35717"
set "SDK=C:\Program Files (x86)\Windows Kits\10"
set "SDKVER=10.0.26100.0"
set "LIB=%MSVC%\lib\onecore\x64;%SDK%\Lib\%SDKVER%\ucrt\x64;%SDK%\Lib\%SDKVER%\um\x64"
set "INCLUDE=%MSVC%\include;%SDK%\Include\%SDKVER%\ucrt;%SDK%\Include\%SDKVER%\um;%SDK%\Include\%SDKVER%\shared;%SDK%\Include\%SDKVER%\winrt"
set "PATH=%MSVC%\bin\HostX64\x64;%SDK%\bin\%SDKVER%\x64;%PATH%"
cd /d D:\code\python\pixiis\.worktrees\pane3-uwp\spike\uwp-detect
cargo build --release
