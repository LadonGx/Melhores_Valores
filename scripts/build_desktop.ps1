# Gera o executável do app desktop: dist\MelhoresValores\MelhoresValores.exe
# Uso (na raiz do repositório):  powershell -ExecutionPolicy Bypass -File scripts\build_desktop.ps1
# Requer: pnpm, e `pip install -r requirements.txt -r requirements-dev.txt`

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

Write-Host "==> Frontend (pnpm build)"
pnpm build
if ($LASTEXITCODE -ne 0) { throw "pnpm build falhou" }

Write-Host "==> Executável (PyInstaller)"
python -m PyInstaller packaging\melhores_valores.spec --noconfirm --clean --distpath dist --workpath build
if ($LASTEXITCODE -ne 0) { throw "PyInstaller falhou" }

# O executável nunca pode levar dados ou chaves do desenvolvedor
$leaks = Get-ChildItem dist\MelhoresValores -Recurse -File -Include *.env, .env, *.db, *.db-wal, *.db-shm, config.env -ErrorAction SilentlyContinue
if ($leaks) { $leaks | ForEach-Object { Write-Host "ARQUIVO PROIBIDO: $($_.FullName)" }; throw "o build contém dados/configuração do desenvolvedor" }

$size = (Get-ChildItem dist\MelhoresValores -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
Write-Host ("==> OK: dist\MelhoresValores\MelhoresValores.exe ({0:N0} MB na pasta)" -f $size)
