# Compila Configuración.exe con el compilador de C# que trae Windows (.NET Framework 4).
#     powershell -ExecutionPolicy Bypass -File tools\launcher\compilar.ps1
# El ícono es assets\iconos\config.ico (tools\iconos.py), solo si se generó.
Set-Location $PSScriptRoot
$icon = Join-Path $PSScriptRoot '..\..\assets\iconos\config.ico'
$args2 = @('/nologo', '/target:winexe', '/codepage:65001', '/optimize+')
if (Test-Path $icon) { $args2 += "/win32icon:$icon" }
$args2 += @('/out:Configuración.exe', '/r:System.Windows.Forms.dll', '/r:System.Drawing.dll', '/r:System.Core.dll', 'Configuracion.cs')
& "$env:WINDIR\Microsoft.NET\Framework64\v4.0.30319\csc.exe" @args2
