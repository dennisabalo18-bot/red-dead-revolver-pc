# Muestra cada 5 s cuanto lleva el escalado de texturas y despues el pack.
# Ctrl+C para cerrarlo (no corta el proceso).
param([string]$dir = (Get-Location).Path)
while ($true) {
    $esc = Get-Content "$dir\escalar.log" -Raw -ErrorAction SilentlyContinue
    $pack = Get-Content "$dir\pack.log" -Raw -ErrorAction SilentlyContinue
    $linea = "Escalando: esperando..."
    if ($esc) {
        $m = [regex]::Matches($esc, '(\d+)/(\d+)')
        if ($m.Count) { $u = $m[$m.Count - 1]; $linea = "Escalando: $($u.Groups[1].Value) de $($u.Groups[2].Value)" }
        if ($esc -match 'Listo') { $linea = "Escalado: TERMINADO" }
    }
    if ($pack) {
        $m = [regex]::Matches($pack, '(\d+)/(\d+)')
        $p = "Pack: empezando..."
        if ($m.Count) { $u = $m[$m.Count - 1]; $p = "Pack: $($u.Groups[1].Value) de $($u.Groups[2].Value)" }
        if ($pack -match 'texturas y') { $p = "Pack: TERMINADO. Ya podes abrir el juego." }
        $linea = "$linea  |  $p"
    }
    Write-Host ("[{0:HH:mm:ss}] {1}" -f (Get-Date), $linea)
    if ($pack -match 'texturas y') { break }
    Start-Sleep -Seconds 5
}
