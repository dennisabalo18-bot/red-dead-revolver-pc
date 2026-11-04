# Arma la carpeta del port para el jugador, en dist\Red Dead Revolver PC:
#
#   RedDeadRevolver.exe, SDL3.dll   el juego (de rdr-apex\build\Release)
#   Configuración.exe               los ajustes, fuera del juego (tools\launcher)
#   Game\                           el jugador pega acá su juego descomprimido
#   Mods-Extras\texturas\           textures.pack (opcional)
#   Mods-Extras\videos\             los .mp4 mejorados (opcional)
#   LEEME.txt
#
#   powershell -ExecutionPolicy Bypass -File tools\armar_paquete.ps1            solo el programa
#   powershell -ExecutionPolicy Bypass -File tools\armar_paquete.ps1 -Prueba    además enlaza (sin copiar,
#       sin gastar espacio) el juego, las texturas y los videos de esta PC, para probar el paquete.
#   Las texturas de -Prueba son las de BC3 (modding\texturas\textures_bc3.pack, 2,6 GB);
#   -SinComprimir usa el original de 11 GB (textures.pack).
#   -Release además arma dist\RedDeadRevolverPC.zip para subir a GitHub (Releases): solo el
#       programa, sin juego, texturas ni videos (eso se baja aparte y se pega en Mods-Extras).
param([switch]$Prueba, [switch]$SinComprimir, [switch]$Release)
$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot
$out = Join-Path $repo 'dist\Red Dead Revolver PC'
$rel = Join-Path $repo 'rdr-apex\build\Release'

& (Join-Path $PSScriptRoot 'launcher\compilar.ps1')
New-Item -ItemType Directory -Force -Path $out, "$out\Game", "$out\Mods-Extras\texturas", "$out\Mods-Extras\videos" | Out-Null
Copy-Item "$rel\rdr_recomp.exe" "$out\RedDeadRevolver.exe" -Force
Copy-Item "$rel\SDL3.dll" $out -Force
Copy-Item (Join-Path $PSScriptRoot 'launcher\Configuración.exe') $out -Force
# extract-xiso (BSD, in@fishtank.com): saca el juego de una ISO de Xbox a Game.
New-Item -ItemType Directory -Force -Path "$out\Herramientas\extract-xiso" | Out-Null
Copy-Item (Join-Path $PSScriptRoot 'extract-xiso\*') "$out\Herramientas\extract-xiso" -Force

$utf8 = New-Object System.Text.UTF8Encoding($true)
[IO.File]::WriteAllText("$out\Game\PEGAR ACA EL JUEGO.txt", @"
Copiá acá tu copia de Red Dead Revolver de Xbox, descomprimida.
Si tenés una ISO, arrastrala sobre "Instalar juego desde ISO.bat" (en la carpeta de arriba).

Tiene que quedar default.xbe dentro de esta carpeta (o dentro de una carpeta adentro de esta),
junto con front.dat, swat.dat, stream0.dat... y las carpetas bik, lvls_m2, lvls_m4 y lvls_sng.

Este paquete no trae ningún archivo del juego: necesitás tu propia copia.
"@, $utf8)
[IO.File]::WriteAllText("$out\Mods-Extras\LEEME.txt", @"
Extras opcionales. El juego los usa solo si están.

  texturas\textures.pack   texturas mejoradas (F6 en el juego las prende y apaga)
  videos\<nombre>.mp4      videos mejorados; reemplazan al del juego con el mismo nombre

Lo que bajes podés descomprimirlo acá tal cual: el juego también busca en subcarpetas.
Un archivo suelto acá con el nombre de uno del juego (por ejemplo stream0.dat) reemplaza al original.
"@, $utf8)
[IO.File]::WriteAllText("$out\Mods-Extras\texturas\PEGAR ACA textures.pack.txt", @"
Pegá acá textures.pack (las texturas mejoradas que bajaste aparte).
"@, $utf8)
[IO.File]::WriteAllText("$out\Mods-Extras\videos\PEGAR ACA LOS VIDEOS.txt", @"
Pegá acá los .mp4 de los videos mejorados que bajaste aparte (attract.mp4, rslogo.mp4, titles.mp4...).
"@, $utf8)
[IO.File]::WriteAllText("$out\LEEME.txt", @"
RED DEAD REVOLVER - Port de PC
==============================

1. Poné tu juego de Xbox en la carpeta Game:
     - si tenés la ISO, arrastrala sobre "Instalar juego desde ISO.bat";
     - si ya está descomprimido, copiá sus archivos dentro de Game.
2. Opcional, las texturas y los videos mejorados (se bajan aparte):
     textures.pack  ->  Mods-Extras\texturas
     los .mp4       ->  Mods-Extras\videos
3. Abrí Configuración.exe, elegí los ajustes y tocá JUGAR.
   (También podés abrir RedDeadRevolver.exe directo.)

En el juego:  F2 menú de ajustes   F6 texturas mejoradas sí/no   F11 pantalla completa
              F9 libera el ratón

No incluye ningún archivo del juego. Necesitás tu propia copia legítima.
Solo funciona la versión PAL (Europa) de Xbox: su default.xbe pesa 4.452.352 bytes.
Con otra versión (por ejemplo la NTSC de EE. UU.) el juego lo avisa al arrancar y no se abre.
extract-xiso es de in@fishtank.com (licencia en Herramientas\extract-xiso).
"@, $utf8)
# El .bat sin BOM (cmd no lo entiende) y con chcp 65001 para los acentos.
[IO.File]::WriteAllText("$out\Instalar juego desde ISO.bat", (@'
@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"
set "ISO=%~1"
if not "%ISO%"=="" goto tengo
for %%f in (*.iso Game\*.iso) do set "ISO=%%f"
if not "%ISO%"=="" goto tengo
echo No encontré ninguna ISO.
echo Arrastrá la ISO de Red Dead Revolver (Xbox) sobre este archivo,
echo o copiala a esta carpeta y volvé a abrirlo.
pause
exit /b 1

:tengo
dir /s /b "Game\default.xbe" >nul 2>&1
if errorlevel 1 goto extraer
echo Ya hay un juego en la carpeta Game. Si querés reinstalarlo, vaciala primero.
pause
exit /b 0

:extraer
echo Extrayendo "%ISO%" en Game...
"Herramientas\extract-xiso\extract-xiso.exe" -d "Game" -x "%ISO%"
dir /s /b "Game\default.xbe" >nul 2>&1
if errorlevel 1 goto mal
echo.
echo Listo. Ya podés abrir Configuración.exe y jugar.
echo La ISO ya no hace falta: si querés, borrala.
pause
exit /b 0

:mal
echo.
echo No se pudo extraer el juego. ¿Es la ISO de Red Dead Revolver de Xbox?
pause
exit /b 1
'@).Replace("`r`n", "`n").Replace("`n", "`r`n"), (New-Object System.Text.UTF8Encoding($false)))

# Los ajustes de partida (los mismos que "Valores por defecto" del launcher y F2 en el juego).
# Solo si no hay uno: el de una prueba anterior tiene los ajustes que eligió el jugador.
$ini = @"
# Ajustes del menú F2 (se reescribe solo). Configuración.exe también los cambia.
render_scale=x2 (1280x960)
widescreen=Sí (nativo del juego)
window=1920x1080
fullscreen=Sí
aniso=x16
tex_dump=No
vsync=Sí
fps=Sí
language=Español
mouse_sens2=1
mouse_sens_y=100%
mouse_aim=200%
mouse_cap2=Sin límite
mouse_invert_y=No
mouse_mode=Directo (como Black)
pack_art=Sí
botones=Automático
modo_rapido=No
"@
$utf8nb = New-Object System.Text.UTF8Encoding($false)
if (-not (Test-Path "$out\rdr_menu.ini")) { [IO.File]::WriteAllText("$out\rdr_menu.ini", $ini, $utf8nb) }

if ($Prueba) {
    $game = if ($env:RDR_JUEGO) { $env:RDR_JUEGO } else { Join-Path $repo 'juego' }
    $link = Join-Path $out 'Game\Red Dead Revolver'
    if (-not (Test-Path $link)) { cmd /c mklink /J "$link" "$game" | Out-Null }
    $name = if ($SinComprimir) { 'textures.pack' } else { 'textures_bc3.pack' }
    $pack = Join-Path $repo "modding\texturas\$name"
    $dst = Join-Path $out 'Mods-Extras\texturas\textures.pack'
    if (Test-Path $dst) { Remove-Item $dst -Force }
    New-Item -ItemType HardLink -Path $dst -Target $pack | Out-Null
    Get-ChildItem (Join-Path $repo 'modding\mods\videos\*.mp4') | ForEach-Object {
        $d = Join-Path $out ("Mods-Extras\videos\" + $_.Name)
        if (Test-Path $d) { Remove-Item $d -Force }
        New-Item -ItemType HardLink -Path $d -Target $_.FullName | Out-Null
    }
    Write-Host 'Prueba: juego, texturas y videos enlazados (no ocupan espacio extra).'
}
if ($Release) {
    # Una copia limpia: sin el juego, las texturas, los videos, los registros ni ajustes de prueba.
    $tmp = Join-Path $repo 'dist\release\Red Dead Revolver PC'
    if (Test-Path (Split-Path $tmp)) { Remove-Item (Split-Path $tmp) -Recurse -Force }
    New-Item -ItemType Directory -Force -Path "$tmp\Game", "$tmp\Mods-Extras\texturas", "$tmp\Mods-Extras\videos" | Out-Null
    foreach ($f in 'RedDeadRevolver.exe', 'SDL3.dll', 'Configuración.exe', 'LEEME.txt', 'Instalar juego desde ISO.bat') {
        Copy-Item "$out\$f" $tmp
    }
    Copy-Item "$out\Herramientas" $tmp -Recurse
    Copy-Item "$out\Game\PEGAR ACA EL JUEGO.txt" "$tmp\Game"
    Copy-Item "$out\Mods-Extras\LEEME.txt" "$tmp\Mods-Extras"
    Copy-Item "$out\Mods-Extras\texturas\PEGAR ACA textures.pack.txt" "$tmp\Mods-Extras\texturas"
    Copy-Item "$out\Mods-Extras\videos\PEGAR ACA LOS VIDEOS.txt" "$tmp\Mods-Extras\videos"
    [IO.File]::WriteAllText("$tmp\rdr_menu.ini", $ini, $utf8nb)
    $zip = Join-Path $repo 'dist\RedDeadRevolverPC.zip'
    if (Test-Path $zip) { Remove-Item $zip -Force }
    # A mano, para que las rutas usen / (las de CreateFromDirectory llevan \ y otros programas no las entienden).
    Add-Type -AssemblyName System.IO.Compression, System.IO.Compression.FileSystem
    $base = Split-Path $tmp
    $arch = [IO.Compression.ZipFile]::Open($zip, 'Create', [Text.Encoding]::UTF8)
    Get-ChildItem $tmp -Recurse -File | ForEach-Object {
        $name = $_.FullName.Substring($base.Length + 1).Replace('\', '/')
        [void][IO.Compression.ZipFileExtensions]::CreateEntryFromFile($arch, $_.FullName, $name, 'Optimal')
    }
    $arch.Dispose()
    Write-Host ("Release: $zip ({0:N0} MB)" -f ((Get-Item $zip).Length / 1MB))
}
Write-Host "Listo: $out"
