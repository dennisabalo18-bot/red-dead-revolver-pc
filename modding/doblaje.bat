@echo off
rem Mesa de doblaje en el navegador: cada frase con su texto (transcrito
rem solo), el original para escuchar y donde pegar/soltar el audio nuevo.
rem Marca hechas y pendientes. Cierra esta ventana para salir.
cd /d "%~dp0"
python -P "%~dp0..\tools\doblaje.py"
pause
