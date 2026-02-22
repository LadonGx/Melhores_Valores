import os
from prisma import Prisma
from dotenv import load_dotenv

load_dotenv()

db = Prisma()

async def connect_db():
    """Inicializa a conexão com o banco de dados via Prisma."""
    if not db.is_connected():
        await db.connect()

async def disconnect_db():
    """Fecha a conexão com o banco de dados."""
    if db.is_connected():
        await db.disconnect()
