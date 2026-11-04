@echo off
rem La carpeta del juego: RDR_JUEGO si está definida, si no ..\juego (ver README).
if defined RDR_JUEGO (set "JUEGO=%RDR_JUEGO%") else (set "JUEGO=%~dp0..\juego")
rem Extrae voces, musica y ambiente del juego a la carpeta audio\ (WAV).
rem Opcional: extraer_audio.bat jack  (solo los archivos cuyo nombre contiene "jack")
cd /d "%~dp0"
python -I "%~dp0..\tools\extraer_audio.py" "%JUEGO%" "%~dp0audio" %1
pause
