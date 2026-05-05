@echo off
cd /d "C:\Program Files\Microsoft Visual Studio\18\Enterprise\Common7\Tools"
call VsDevCmd.bat -arch=x64 -host_arch=x64 >nul
set "PATH=C:\Users\fwachira\.cargo\bin;%PATH%"
cd /d D:\code\python\pixiis\.worktrees\pane8-controller\frontend\src-tauri
cargo %*
