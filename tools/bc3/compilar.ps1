# Compila bc3pack.exe (clang-cl de Visual Studio).
Set-Location $PSScriptRoot
$cl = Get-ChildItem "C:\Program Files\Microsoft Visual Studio\18\Community\VC\Tools\Llvm\x64\bin\clang-cl.exe" -ErrorAction SilentlyContinue
if (-not $cl) { $cl = Get-ChildItem "C:\Program Files\Microsoft Visual Studio\*\*\VC\Tools\Llvm\x64\bin\clang-cl.exe" | Select-Object -First 1 }
& $cl.FullName /nologo /O2 /D_CRT_SECURE_NO_WARNINGS bc3pack.c /Fe:bc3pack.exe
