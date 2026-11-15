FROM python:3.11-slim
WORKDIR /app
# PYTHONUNBUFFERED: logs do uvicorn/celery saem na hora no `docker logs` (sem buffer de stdout).
# PYTHONDONTWRITEBYTECODE: não grava __pycache__ em /app em tempo de execução (camada gravável limpa).
# PLAYWRIGHT_BROWSERS_PATH: local fixo do Chromium (independe do HOME de quem roda o container).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    libatomic1 openssl \
    libnss3 libatk1.0-0 libatk-bridge2.0-0 libcups2 \
    libdrm2 libxkbcommon0 libxcomposite1 libxdamage1 \
    libxfixes3 libxrandr2 libgbm1 libasound2 \
    libpango-1.0-0 libcairo2 libdbus-1-3 libexpat1 \
    && dpkg --purge --force-depends mesa-libgallium libllvm19 libz3-4 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Só o Chromium completo (novo headless, channel="chromium"); o chromium-headless-shell
# não é usado pelo scraper, então --no-shell mantém a imagem menor.
RUN playwright install --no-shell chromium
COPY schema.prisma .
# prisma generate baixa (uma vez, no build) o Node, o Prisma CLI e os engines. Depois sobra só o
# que a produção usa: o node do próprio Playwright (versão fixa pelo requirements.txt) no lugar do
# Node "mais recente" do nodeenv (150 MB + npm + headers), o query-engine/schema-engine e o client
# gerado. Sem rede em tempo de execução: `prisma migrate deploy` e o client funcionam offline.
RUN prisma generate \
    && ln -s /usr/local/lib/python3.11/site-packages/playwright/driver/node /usr/local/bin/node \
    && node --version \
    && rm -rf /root/.cache/prisma-python/nodeenv /root/.cache/prisma /root/.npm /root/.cache/checkpoint-nodejs \
    && rm -f /root/.cache/prisma-python/binaries/*/*/node_modules/@prisma/engines/libquery_engine-*.so.node
# Código por último: é o que muda a cada commit (as camadas acima ficam em cache)
COPY migrations ./migrations
COPY execution ./execution
EXPOSE 8000
# Comando padrão: a API. Worker e beat do Celery usam a mesma imagem trocando o comando.
CMD ["uvicorn", "execution.web_server:app", "--host", "0.0.0.0", "--port", "8000"]
