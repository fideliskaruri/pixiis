@echo off
cd /d "C:\Program Files\Microsoft Visual Studio\18\Enterprise\VC\Auxiliary\Build"
call vcvarsall.bat x64
echo ---ENV CHECK---
echo INCLUDE=%INCLUDE%
echo LIB=%LIB%
echo VCINSTALLDIR=%VCINSTALLDIR%
