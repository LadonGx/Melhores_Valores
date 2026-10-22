"""
Caminhos e configuração do app desktop.

Os dados do usuário ficam na pasta de dados do sistema operacional, nunca ao
lado do executável (a pasta de instalação pode ser somente leitura):
  Windows: %LOCALAPPDATA%\\MelhoresValores\\
  macOS:   ~/Library/Application Support/MelhoresValores/
  Linux:   ~/.local/share/MelhoresValores/

MV_DATA_DIR sobrescreve a pasta inteira (dev e testes); MV_DB_PATH, só o banco;
MV_WEB_DIST, a pasta do frontend buildado.
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_data_dir

APP_NAME = "MelhoresValores"


def is_frozen() -> bool:
    """True quando rodando de dentro do executável gerado pelo PyInstaller."""
    return getattr(sys, "frozen", False)


def resource_path(relative: str) -> Path:
    """Caminho de um arquivo empacotado junto com o app: dentro do pacote do
    PyInstaller (sys._MEIPASS) no executável, ou a partir da raiz do repo em dev."""
    base = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent.parent))
    return base / relative


DATA_DIR = Path(os.getenv("MV_DATA_DIR") or user_data_dir(APP_NAME, appauthor=False))

# Configuração do usuário (ex: FIRECRAWL_API_KEY) tem prioridade sobre o .env do repo
load_dotenv(DATA_DIR / "config.env")
if not is_frozen():
    # Só em dev. No executável, nunca: quem recebe o .exe não pode herdar as
    # chaves do desenvolvedor — cada um usa só o próprio config.env.
    load_dotenv()

DB_PATH = Path(os.getenv("MV_DB_PATH") or DATA_DIR / "melhores_valores.db")
LOG_DIR = DATA_DIR / "logs"
# Guarda {pid, port} da instância em execução, para uma 2ª abertura reaproveitá-la
LOCK_PATH = DATA_DIR / "app.lock"
# Última porta usada. A porta precisa ser estável entre aberturas: o frontend
# guarda dados no localStorage (ex: grupos de produtos), que é separado por
# origem (host + porta) — mudar de porta faria esses dados "sumirem".
PORT_PATH = DATA_DIR / "port"

# Frontend buildado (`pnpm build`): no executável vai empacotado como web_dist/
WEB_DIST_DIR = Path(
    os.getenv("MV_WEB_DIST")
    or resource_path("web_dist" if is_frozen() else "apps/web/dist")
)
