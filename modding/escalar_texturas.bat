@echo off
rem Escala con Upscayl (modelo Digital Art, x4) las texturas de texturas\dump\
rem que todavia no estan en texturas\mejoradas\. Si se corta, ejecutalo de
rem nuevo y sigue donde quedo. Cierra la ventana de Upscayl antes.
rem Otro modelo: escalar_texturas.bat ultrasharp-4x
cd /d "%~dp0"
python -I "%~dp0..\tools\escalar_texturas.py" %1
pause
