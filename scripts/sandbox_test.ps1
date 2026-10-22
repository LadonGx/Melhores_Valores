# Abre o executável gerado dentro do Windows Sandbox: uma máquina Windows limpa e
# descartável (sem Python, Node, Docker, Chrome nem os seus dados), como a de um testador.
#
# Pré-requisitos:
#   1. Build feito: scripts\build_desktop.ps1  (gera dist\MelhoresValores)
#   2. Windows Sandbox habilitado (uma vez, como administrador, e reiniciar):
#        Enable-WindowsOptionalFeature -Online -FeatureName Containers-DisposableClientVM -All
#
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\sandbox_test.ps1
# O que conferir no Sandbox: a janela abre zerada, uma busca traz resultados (Edge do
# Sandbox no nível 2), fechar a janela encerra o app, e reabrir mantém os produtos.

$ErrorActionPreference = "Stop"
$dist = Join-Path (Split-Path $PSScriptRoot -Parent) "dist\MelhoresValores"
if (-not (Test-Path "$dist\MelhoresValores.exe")) { throw "Build não encontrado em $dist — rode scripts\build_desktop.ps1" }
if (-not (Test-Path "$env:WINDIR\System32\WindowsSandbox.exe")) { throw "Windows Sandbox não está habilitado (veja o cabeçalho deste script)" }

$wsb = Join-Path $env:TEMP "melhores-valores-sandbox.wsb"
@"
<Configuration>
  <MappedFolders>
    <MappedFolder>
      <HostFolder>$dist</HostFolder>
      <SandboxFolder>C:\MelhoresValores</SandboxFolder>
      <ReadOnly>true</ReadOnly>
    </MappedFolder>
  </MappedFolders>
  <LogonCommand>
    <Command>C:\MelhoresValores\MelhoresValores.exe</Command>
  </LogonCommand>
</Configuration>
"@ | Set-Content -Path $wsb -Encoding UTF8

Write-Host "Abrindo o Windows Sandbox com $dist (somente leitura)..."
Start-Process $wsb
