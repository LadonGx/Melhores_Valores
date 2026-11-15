FROM python:3.11-slim
WORKDIR /app
# PYTHONUNBUFFERED: logs do uvicorn/celery saem na hora no `docker logs` (sem buffer de stdout).
# PYTHONDONTWRITEBYTECODE: não grava __pycache__ em /app em tempo de execução (camada gravável limpa).
# PLAYWRIGHT_BROWSERS_PATH: local fixo do Chromium (independe do HOME de quem roda o container).
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PLAYWRIGHT_BROWSERS_PATH=/ms-playwright
# O `dpkg --purge` no fim tira os drivers de vídeo do Mesa e o compilador LLVM/Z3 que eles usam
# (~195 MB): o libgbm1 os puxa, mas o Chromium sem tela desenha o WebGL com o SwiftShader embutido
# e o container não tem GPU. O dpkg fica com a dependência do libgbm1 marcada como quebrada, então
# qualquer `apt-get install` novo tem de vir ANTES dessa linha (depois dela o apt reclama).
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
# Traduções da interface do Chromium: só en-US e pt-BR ficam (o idioma das páginas vem do
# locale="pt-BR" do contexto). O build falha se a pasta não existir/for ambígua ou faltar um dos 2.
RUN playwright install --no-shell chromium \
    && LOCALES="$(find "$PLAYWRIGHT_BROWSERS_PATH" -type d -name locales -path '*chrom*')" \
    && test -n "$LOCALES" && test "$(echo "$LOCALES" | wc -l)" -eq 1 \
    && echo "locales antes: $(du -sm "$LOCALES") MB, $(ls "$LOCALES" | wc -l) arquivos" \
    && find "$LOCALES" -name '*.pak' ! -name en-US.pak ! -name pt-BR.pak -delete \
    && test -f "$LOCALES/en-US.pak" && test -f "$LOCALES/pt-BR.pak" \
    && echo "locales depois: $(du -sm "$LOCALES") MB, $(ls "$LOCALES" | wc -l) arquivos"
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
