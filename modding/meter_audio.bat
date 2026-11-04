@echo off
rem La carpeta del juego: RDR_JUEGO si está definida, si no ..\juego (ver README).
if defined RDR_JUEGO (set "JUEGO=%RDR_JUEGO%") else (set "JUEGO=%~dp0..\juego")
rem Mete en el juego los WAV editados de audio\reemplazos\ (mismo nombre que
rem al extraerlos). Rehace los stream*.dat en mods\; el original no se toca.
rem Para volver al audio original: borra la carpeta mods\.
cd /d "%~dp0"
python -I "%~dp0..\tools\meter_audio.py" "%JUEGO%" "%~dp0audio\reemplazos" "%~dp0mods"
pause
