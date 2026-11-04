@echo off
rem Ventana para pasar los videos mejorados a 60 fps con RIFE + deband, uno por uno.
cd /d "%~dp0.."
start "" pythonw tools\videos_app.py --60
