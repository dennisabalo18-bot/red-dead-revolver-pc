@echo off
rem Launch the recompiled Red Dead Revolver with logs in runs\last_*.txt.
cd /d "%~dp0"
if not exist runs mkdir runs
call "%~dp0env.bat"
set RECOMP_STUB_LOG=1
build\Release\rdr_recomp.exe > runs\last_out.txt 2> runs\last_err.txt
