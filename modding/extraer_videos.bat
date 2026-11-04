@echo off
rem Saca las cinematicas del juego (Bink, 720x480) a mods\videos como MP4
rem de alta calidad (H.264 CRF 12 + AAC 320k), listas para mejorarlas.
rem El juego reproduce el MP4 de mods\videos en lugar de su .bik: un video
rem mejorado se pone ahi con el mismo nombre. Sin la carpeta, vuelven los .bik.
rem Usa bik\ (la version de 30 fps); bik50\ es la misma en 25 fps (PAL).
rem Los .bik originales no se tocan. Necesita ffmpeg (ya instalado con winget).
setlocal
if defined RDR_JUEGO (set "JUEGO=%RDR_JUEGO%") else (set "JUEGO=%~dp0..\juego")
set "SALIDA=%~dp0mods\videos"
if not exist "%SALIDA%" mkdir "%SALIDA%"
for %%f in ("%JUEGO%\bik\*.bik") do (
    if exist "%SALIDA%\%%~nf.mp4" (
        echo ya esta %%~nf.mp4
    ) else (
        echo %%~nxf
        ffmpeg -v error -stats -i "%%f" -c:v libx264 -preset slow -crf 12 -pix_fmt yuv420p -c:a aac -b:a 320k "%SALIDA%\%%~nf.mp4"
    )
)
echo.
echo Listo: los videos estan en %SALIDA%
pause
