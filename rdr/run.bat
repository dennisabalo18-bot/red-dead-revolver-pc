@echo off
rem Launch the recompiled Red Dead Revolver.
rem Logs are discarded: writing them costs ~20% speed. Use run_debug.bat
rem to keep them in runs\last_out.txt and runs\last_err.txt.
cd /d "%~dp0"
call "%~dp0env.bat"
build\Release\rdr_recomp.exe >nul 2>nul
