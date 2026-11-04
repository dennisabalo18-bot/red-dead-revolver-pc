@echo off
rem Launch with GPU rendering and keep logs in runs\last_out.txt / last_err.txt.
cd /d "%~dp0"
if not exist runs mkdir runs
call "%~dp0env.bat"
set RECOMP_STUB_LOG=1
rem Which code reads the right stick ([LOOKTRACE] lines, src/mouselook.c).
set RDR_MOUSE_TRACE=1
set RECOMP_FF_TRACE=1
build\Release\rdr_recomp.exe > runs\last_out.txt 2> runs\last_err.txt
