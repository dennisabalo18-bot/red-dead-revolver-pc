@echo off
rem Crea texturas\textures.pack con las imagenes de texturas\mejoradas\
rem (mismo nombre que en texturas\dump\). El juego lo carga al arrancar.
cd /d "%~dp0"
if not exist texturas\mejoradas mkdir texturas\mejoradas
python -I "%~dp0..\tools\texturas_pack.py" "%~dp0texturas\mejoradas" "%~dp0texturas\textures.pack"
pause
