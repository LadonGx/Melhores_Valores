"""
Caminhos e configuração do app desktop.

Os dados do usuário ficam na pasta de dados do sistema operacional, nunca ao
lado do executável (a pasta de instalação pode ser somente leitura):
  Windows: %LOCALAPPDATA%\\MelhoresValores\\
  macOS:   ~/Library/Application Support/MelhoresValores/
  Linux:   ~/.local/share/MelhoresValores/

MV_DATA_DIR sobrescreve a pasta inteira (dev e testes); MV_DB_PATH, só o banco.
"""

import os
from pathlib import Path

from dotenv import load_dotenv
from platformdirs import user_data_dir

APP_NAME = "MelhoresValores"

DATA_DIR = Path(os.getenv("MV_DATA_DIR") or user_data_dir(APP_NAME, appauthor=False))

# Configuração do usuário (ex: FIRECRAWL_API_KEY) tem prioridade sobre o .env do repo
load_dotenv(DATA_DIR / "config.env")
load_dotenv()

DB_PATH = Path(os.getenv("MV_DB_PATH") or DATA_DIR / "melhores_valores.db")
