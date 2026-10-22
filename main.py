"""Melhores Valores — app desktop. Uso: python main.py [--port N] [--browser | --no-browser]"""

import logging
import os

from execution.launcher import main

if __name__ == "__main__":
    code = main()
    # Saída imediata: uma checagem de preço em andamento (thread do pool, que o
    # Python esperaria terminar) deixaria o processo vivo e invisível por até
    # ~30 s depois de fechar a janela. O SQLite é transacional, então interromper
    # uma escrita no meio só a desfaz.
    logging.shutdown()
    os._exit(code)
