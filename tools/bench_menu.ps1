# Drive Red Dead Revolver to the main menu with a scripted pad, then sample
# the window title's FPS. Extra environment variables are passed as
# "NAME=value" arguments.
#   powershell -File bench_menu.ps1 RECOMP_RASTER_MT_MIN=1024
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Vars)

$ErrorActionPreference = 'Stop'
$root = 'C:\rdr-port\rdr'
foreach ($k in 'RECOMP_AC97_READY', 'RECOMP_PB_EXEC', 'RECOMP_FB_WINDOW', 'RECOMP_USB',
               'RECOMP_KEYBOARD', 'RECOMP_CONTIG_AVOID_IMAGE') { Set-Item "Env:$k" '1' }
$env:RECOMP_VBLANK = 'paced'
$env:RECOMP_PAD_SCRIPT = '30000:start,34000:a,38000:start,42000:a,46000:start,50000:a'
foreach ($v in $Vars) { $n, $val = $v -split '=', 2; Set-Item "Env:$n" $val }

$tag = if ($Vars) { ($Vars -join '_') -replace '[^A-Za-z0-9_=]', '' } else { 'base' }
# Logs discarded: writing them costs the executor ~20% of its time.
Start-Process cmd -ArgumentList '/c', 'build\Release\rdr_recomp.exe >nul 2>nul' `
    -WorkingDirectory $root -WindowStyle Hidden | Out-Null
Start-Sleep -Seconds 85
$p = Get-Process rdr_recomp
$fps = @()
for ($i = 0; $i -lt 8; $i++) {
    Start-Sleep -Seconds 2
    $p.Refresh()
    if ($p.MainWindowTitle -match 'FPS: ([0-9.]+) \| draws: (\d+)') {
        $fps += [double]$Matches[1]
        $draws = $Matches[2]
    }
}
if (-not $p.HasExited) { Stop-Process -Id $p.Id -Force }
$avg = if ($fps) { ($fps | Measure-Object -Average).Average } else { 0 }
'{0,-36} menu FPS avg {1,5:N1}  samples [{2}]  draws/frame {3}' -f $tag, $avg, ($fps -join ' '), $draws
