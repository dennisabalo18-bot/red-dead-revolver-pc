@echo off
rem Launch the recompiled Red Dead Revolver with GPU (D3D11) rendering.
rem The log of the last run is kept in runs\last_err.txt (run_debug.bat adds
rem more tracing).
cd /d "%~dp0"
if not exist runs mkdir runs
call "%~dp0env.bat"
rem Smoke / reticle diagnosis: the fixed-function sprites' matrices, every 2 s.
set RECOMP_FF_TRACE=1
build\Release\rdr_recomp.exe > runs\last_out.txt 2> runs\last_err.txt
