@echo off
rem La carpeta del juego: RDR_JUEGO si está definida, si no ..\juego (ver README).
if defined RDR_JUEGO (set "JUEGO=%RDR_JUEGO%") else (set "JUEGO=%~dp0..\juego")
rem Saca las texturas de los escenarios (DXT) directo de los archivos del
rem juego a texturas\dump\, con los mismos nombres que el volcado de F2.
cd /d "%~dp0"
python -I "%~dp0..\tools\extraer_texturas.py" "%JUEGO%" "%~dp0texturas\dump"
pause
