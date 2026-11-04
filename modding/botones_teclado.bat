@echo off
rem La carpeta del juego: RDR_JUEGO si está definida, si no ..\juego (ver README).
if defined RDR_JUEGO (set "JUEGO=%RDR_JUEGO%") else (set "JUEGO=%~dp0..\juego")
rem Cambia los botones de Xbox de los textos del juego (A, B, X, Y, gatillos)
rem por las teclas de PC: Espacio, C, E, R y los botones del raton.
rem Deja los archivos cambiados en mods\ (el original no se toca).
rem Para volver a los botones de Xbox: botones_teclado.bat quitar
cd /d "%~dp0"
python -I "%~dp0..\tools\botones_teclado.py" "%JUEGO%" "%~dp0mods" %1
rem El juego copia los niveles a su cache del disco duro y despues los lee
rem de ahi: se vacia para que los vuelva a copiar (ya con o sin las teclas).
for %%d in (lvls_sng lvls_m2 lvls_m4) do if exist "%LOCALAPPDATA%\xboxrecomp\Cache\%%d" rd /s /q "%LOCALAPPDATA%\xboxrecomp\Cache\%%d"
echo Cache de niveles vaciada: la primera carga de cada nivel tarda un poco mas.
pause
