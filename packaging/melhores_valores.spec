# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller: gera dist/MelhoresValores/MelhoresValores.exe (modo pasta, --onedir).

Uso: scripts/build_desktop.ps1  (roda `pnpm build` e depois este spec)

- --onedir: abre mais rápido e gera menos alerta de antivírus que --onefile.
- Leva só o código, o frontend buildado (web_dist/) e o driver do Playwright.
  NÃO leva navegador (usa o Edge/Chrome do sistema), banco, .env ou .data/:
  quem recebe o executável começa zerado.
- Sem UPX: compressão de executável é um gatilho comum de falso positivo.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
WEB_DIST = ROOT / "apps" / "web" / "dist"
if not (WEB_DIST / "index.html").is_file():
    raise SystemExit("apps/web/dist/index.html não existe: rode `pnpm build` antes do PyInstaller.")

hiddenimports = (
    # uvicorn escolhe loop/protocolo/lifespan em tempo de execução, por texto
    collect_submodules("uvicorn")
    + ["anyio._backends._asyncio"]
)

a = Analysis(
    [str(ROOT / "main.py")],
    pathex=[str(ROOT)],
    binaries=[],
    datas=[(str(WEB_DIST), "web_dist")],
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    # Nada de ferramentas de dev/teste nem pacotes pesados que algum import opcional puxaria
    excludes=["tkinter", "pytest", "psycopg", "PyInstaller", "IPython", "numpy", "pandas", "matplotlib"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MelhoresValores",
    icon=str(ROOT / "packaging" / "icon.ico"),
    console=False,  # a janela é a do pywebview, não um terminal
    upx=False,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    name="MelhoresValores",
    upx=False,
)
