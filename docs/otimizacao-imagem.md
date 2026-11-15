# Otimização da imagem da API — medição

> Medição da imagem `ghcr.io/ladongx/melhores-valores-api` (construída pelo `Dockerfile` da raiz),
> antes e depois da otimização. Fase 1 mede o **antes**; a fase 2 (orquestrada) mede
> **antes × depois** com o `Dockerfile` otimizado pelo agente BUILD.

## Objetivo

A imagem da API está em ~2,2 GB (`docker image ls`), o que pesa no pull/push do registry e
no disco das máquinas que rodam o compose. Este documento registra a composição real desse
peso, o método de medição e os números de comparação entre as versões "antes" e "depois".

## Como medir

### Construir a imagem de referência (igual ao CI)

O contexto de build do CI só tem arquivos versionados; para reproduzir isso localmente:

```sh
git archive origin/main -o main.tar
tar -xf main.tar -C pasta-main
docker build -t mv-api:antes pasta-main
```

> **Importante — construir de uma PASTA, não por `git archive | docker build -`:** quando o
> contexto chega como tarball pela entrada padrão, o BuildKit **não aplica o
> `Dockerfile.dockerignore`** (ele só vale para contexto de pasta). Por tarball entram
> arquivos que o CI exclui (ex.: `execution/tests`, 10 MB) e a imagem sai maior que a
> publicada. O Actions usa `context: .` (pasta), onde o ignore é aplicado. A medição "antes"
> da tarefa anterior (2,23 GB → 1,26 GB) **não foi afetada** por isso: o `Dockerfile` antigo
> não tinha `Dockerfile.dockerignore` (não havia o que não aplicar).

### Tamanhos

```sh
# tamanho listado pelo Docker
docker image ls mv-api:antes

# tamanho comprimido (o que trafega no registry), no Git Bash:
docker save mv-api:antes | gzip -c | wc -c
# (no PowerShell, sem gzip no PATH:
#  cmd /c "docker save mv-api:antes | ""C:\Program Files\Git\usr\bin\gzip.exe"" -c | wc -c")

# tamanho por camada
docker history --no-trunc --format "{{.Size}}\t{{.CreatedBy}}" mv-api:antes
```

### Peso por diretório (dentro da imagem)

```sh
docker run --rm --entrypoint sh mv-api:antes -c "du -xh --max-depth=3 / 2>/dev/null | sort -h | tail -25"
```

### Medição de runtime (`scripts/medir-imagem.ps1`)

Script de PowerShell 5.1+ (Windows + Docker Desktop), que depende só de Docker:

```sh
# básico (sem visita a sites — seguro para rodar a qualquer momento):
.\scripts\medir-imagem.ps1 -Image mv-api:antes

# com teste de pico (FASE 2 — faz uma visita REAL ao site do anúncio):
.\scripts\medir-imagem.ps1 -Image mv-api:antes -PeakUrl "https://www.amazon.com.br/dp/XXXX"
```

O que ele faz:

1. Cria uma rede própria (`mvmed-<timestamp>`) e sobe `postgres:15-alpine` e `redis:7-alpine`
   nela, **sem publicar** 5432/6379 no host;
2. Sobe a API com o comando de produção
   (`sh -c "prisma migrate deploy && uvicorn execution.web_server:app --host 0.0.0.0 --port 8000"`),
   publicando só a porta 8000, com `FIRECRAWL_API_KEY=` vazio; mede o tempo do `docker run`
   até `GET /` responder 200;
3. Sobe o worker de produção
   (`celery -A execution.worker_tasks worker -B -s /tmp/celerybeat-schedule --concurrency=2 --max-tasks-per-child=20 --loglevel=info`);
   espera o log `ready`, confere que as tarefas foram registradas (`[tasks]`) e que o Beat
   carregou (`beat: Starting`);
4. Depois de ~30 s, mede a RAM em repouso da API e do worker com `docker stats --no-stream`
   (5 amostras, mediana);
5. Com `-PeakUrl` (desligado por padrão): insere um produto com a URL direto no Postgres
   (via `psql` no container do banco, com store detectada pela URL e `updatedAt`), chama
   `POST /product/{id}/refresh` e amostra `docker stats` da API a cada ~0,5 s, registrando
   o pico de RAM e a resposta;
6. Imprime o resumo e **derruba tudo** (containers e rede) no `finally`, mesmo com erro.

> **Importante:** não usar o `docker compose` do repo para medir — ele monta `.:/app` por
> volume, o que esconderia o conteúdo real da imagem.

---

## Antes

Imagem: `mv-api:antes`, construída de `git archive origin/main` com o `Dockerfile` de
`origin/main` em 15/11/2026 (commit da época).

### Tamanho

| Métrica | Valor |
|---|---|
| `docker image ls` | **2,23 GB** |
| `du -xsm /` (dentro do container) | **1533 MB** (soma das camadas no `docker history`: ~1,6 GB) |
| Comprimido (`docker save \| gzip`), `wc -c` | **607.696.066 bytes ≈ 607,7 MB** (rebuild da fase 2; na fase 1 deu 607.699.425 B) |

> Nota sobre o `2,23 GB` do `docker image ls`: nesta máquina o Docker usa o snapshotter do
> containerd, e `docker system df -v` contabiliza `SIZE 2,23 GB = SHARED 1,615 GB + UNIQUE
> 611 MB` (conteúdo comprimido + descomprimido somados). O tamanho real do filesystem da
> imagem é ~1,6 GB (confirmado por `du` e pela soma das camadas), e o tamanho comprimido
> (o que conta para pull/push no registry) é ~608 MB. A referência "~2,2 GB" do projeto
> veio do `docker image ls`, por isso ela aparece nas tabelas, mas o ganho real é medido
> por `du` e gzip (ver "Antes × depois").

### Por camada (`docker history`)

| Tamanho | Camada |
|---|---|
| 87,7 MB | Base `python:3.11-slim` (rootfs Debian trixie) |
| 4,9 MB | `apt-get install ca-certificates netbase tzdata` |
| 48,8 MB | Compila e instala o Python 3.11 |
| 512 kB | `apt-get install libatomic1 openssl` |
| **291 MB** | `pip install -r requirements.txt` |
| **284 MB** | `apt-get install` das libs do Chromium (nss3, atk, cups, gbm, pango, cairo…) |
| **427 MB** | `playwright install --no-shell chromium` |
| 14,3 MB | `COPY . .` |
| **457 MB** | `prisma generate` |
| — | `EXPOSE`, `CMD` (0 B) |

Soma: ~1,615 GB.

### Por diretório (`du` dentro da imagem)

| Categoria | Diretório(s) | Tamanho |
|---|---|---|
| **Cache do Playwright (navegador)** | `/root/.cache/ms-playwright` | **408 MB** |
| **Cache do Prisma (Python)** | `/root/.cache/prisma-python` | **314 MB** |
| **Site-packages (Python)** | `/usr/local/lib/python3.11/site-packages` | **222 MB** |
| Sistema Debian | `/usr` (menos `/usr/local`) + `/var` + `/etc` | ~377 MB |
| Cache do npm | `/root/.npm` | 69 MB |
| Cache do pip | `/root/.cache/pip` | 65 MB |
| Cache do Prisma CLI | `/root/.cache/prisma` | 51 MB |
| `/app` (código copiado) | `/app` | 14 MB |
| `/tmp` | `/tmp` | 2,6 MB |

Detalhes que ajudam a planejar o corte:

- `site-packages` (222 MB) inclui **122 MB só do `node` embutido no driver do Playwright**
  (`site-packages/playwright/driver/node`);
- `/usr/lib/x86_64-linux-gnu` tem 276 MB, puxados por `libLLVM.so.19.1` (124 MB) e
  `libgallium` (41 MB) — dependências das libs gráficas (mesa/gbm) instaladas para o Chromium;
- `/root/.cache` soma 836 MB (Playwright 408 + prisma-python 314 + prisma 51 + pip 65) —
  **mais da metade do conteúdo da imagem é cache de build/instaladores**;
- `/root/.cache/prisma-python` inclui um **`node` inteiro (144 MB)** em `nodeenv/bin/node`
  (o `prisma generate` baixa o próprio Node);
- Em `/app` (14 MB): `execution` 9,9 MB (dos quais `execution/tests` **9,7 MB** — fixtures de
  teste), `docs` 2,6 MB, `apps` 0,76 MB — tudo que não é necessário para produção;
- `/tmp` tem 2,6 MB de sobra do `prisma generate`.

### Tempo de build (sem cache)

| Métrica | Valor |
|---|---|
| `git archive origin/main \| docker build --no-cache` | **111,4 s** (cronômetro no comando completo, sem nenhum outro build em paralelo — medido na fase 2) |

A prévia de ~137 s da fase 1 foi feita com o build do agente BUILD rodando em paralelo
(concorrência de I/O e rede) e vale só como ordem de grandeza.

### Build local com arquivos fora do git (informativo)

O `.dockerignore` atual **não exclui** os arquivos fora do git da raiz; o único relevante
hoje é `backup-melhores-valores.sql` (**0,4 MB**), que entraria no contexto e na camada
`COPY . .` de um `docker build .` local. Impacto pequeno (não reconstruído localmente —
medição dispensada por ser opcional e baixo impacto).

### Runtime

Medição oficial (script, **com** `-PeakUrl` do ML — ver "Antes × depois"): tempo até `GET /`
**2,5 s**, RAM repouso API **68,2 MiB** / worker **127,2 MiB**, pico da API no refresh
**497,9 MiB**, resposta do ML `{"status":"error","reason":"unavailable"}`. Worker subiu com
`ready`/tarefas registradas/Beat carregado. (A prévia da fase 1, sem `-PeakUrl`, deu
3 s / 68 / 127 MiB — consistente.)

Limpeza confirmada: `docker ps -a` e `docker network ls` sem nenhum container/rede
`mvmed-*` restante.

---

## Mudanças aplicadas (ganho de cada uma)

Tabela passo a passo do BUILD (mesma máquina, mesmas réguas: `du -xsm /` dentro do container
e `docker save | gzip | wc -c`):

| Passo | Mudança | du (MB) | gz (MB) | Ganho do passo (du / gz) |
|---|---|---|---|---|
| 0 | Dockerfile original (`git archive HEAD`) | 1533 | 607,7 | — (baseline) |
| 1 | `Dockerfile.dockerignore` allowlist | 1520 | 603,0 | −13 / −4,7 |
| 2 | apt num único RUN com `--no-install-recommends` | 1487 | 594,7 | −33 / −8,3 |
| 3 | `dpkg --purge --force-depends mesa-libgallium libllvm19 libz3-4` | 1297 | 528,2 | **−190 / −66,5** |
| 4 | `pip install --no-cache-dir` | 1232 | 464,2 | −65 / −64,0 |
| 5 | Prisma enxuto (sem caches duplicados) | 1013 | 405,6 | −219 / −58,6 |
| 6 = `mv-api:depois` | Node do Playwright no lugar do nodeenv + ENVs + ordem das camadas | 858 | 350,8 | −155 / −54,8 |

Explicação de cada passo:

- **Passo 1 — `Dockerfile.dockerignore` (allowlist):** o contexto de build passa a só incluir
  o que produção usa (`execution`, `migrations`, `requirements.txt`, `schema.prisma`) —
  contexto caiu para 142 kB: sem `docs/`, `apps/`, `execution/tests`, `.github`, `.env`,
  `backup-*.sql`, que antes entravam na camada `COPY . .` da imagem.
- **Passo 2 — apt enxuto:** um único `RUN` com `--no-install-recommends` não puxa os
  recommends que o Chromium não usa: systemd (daemon/sysv/timesyncd/cryptsetup), dbus
  (daemon/bin/session), procps, psmisc, shared-mime-info, gsettings-desktop-schemas, dconf,
  glib2.0-data, at-spi2-core, alsa-ucm/topology-conf, libpam/nss-systemd, xdg-user-dirs,
  x11-common, krb5-locales… O cliente `libdbus-1-3` fica; sem daemon o Chromium se comporta
  igual (já não havia daemon rodando).
- **Passo 3 — purge forçado de mesa/llvm/z3 (maior ganho individual, −190 MB du):**
  `libgbm1` puxa como dependência dura `mesa-libgallium` (41,6 MB), `libllvm19` (126,7 MB) e
  `libz3-4` (27,1 MB); o Chromium headless renderiza por SwiftShader, não usa GPU/DRM real,
  então os purgamos à força. **Efeito colateral no dpkg:** `libgbm1` fica com dependência
  quebrada marcada — só afetaria um `apt-get install` futuro *dentro* da imagem (que ninguém
  faz). Se um dia precisar de GPU/DRM real, remover essa linha do `Dockerfile`.
- **Passo 4 — `pip --no-cache-dir`:** não grava `/root/.cache/pip` (65 MB) durante a
  instalação das dependências.
- **Passo 5 — Prisma enxuto:** sem `/root/.cache/prisma` (51 MB, duplicado do CLI), sem
  `/root/.npm` (69 MB), nodeenv sem `include/share/npm`, e sem os
  `libquery_engine*.so.node` (sobra só o query-engine binário que a produção usa).
- **Passo 6 — node único + ENVs + ordem:** o `prisma generate` passa a usar o **node do
  próprio Playwright** (v24.22.1, versão fixa pelo `requirements.txt`, via symlink
  `/usr/local/bin/node`) e o nodeenv (Node 26 "latest", 150 MB + npm + headers) é apagado;
  adiciona as 3 ENVs abaixo e reordena as camadas (código por último).

**Sobre o apt — o que ficou:** todas as libs exigidas pelo `ldd` do binário do Chromium
(`libnss3`, `libatk*`, `libcups2`, `libdrm2`, `libxkbcommon0`, `libxcomposite1`,
`libxdamage1`, `libxfixes3`, `libxrandr2`, `libgbm1`, `libasound2`, `libpango-1.0-0`,
`libcairo2`, `libdbus-1-3`, `libexpat1`), além de `libatomic1` (pedida pelo `ldd`) e
`openssl` (o Prisma detecta `debian-openssl-3.0.x` por `openssl version`; só 2,5 MB).
Fontes `fonts-dejavu-core/-mono` (3,5 MB) continuam (dependência do fontconfig — o
layout/medida de texto usa as fontes do sistema). Nada dos 31 pacotes que o
`playwright install-deps --dry-run` pede (xvfb, fontes extras, libgl1, mesa-dri,
libvulkan1…) — nenhum é exigido pelo binário: `ldd` sem "not found" e o Chromium sobe,
renderiza, faz screenshot e WebGL (SwiftShader) normalmente.

**As 3 variáveis de ambiente adicionadas:**

| ENV | Efeito |
|---|---|
| `PYTHONUNBUFFERED=1` | logs do uvicorn/celery saem imediatamente no `docker logs` |
| `PYTHONDONTWRITEBYTECODE=1` | sem `__pycache__` novo em `/app` em tempo de execução (camada gravável limpa; também evita lixo no bind mount do compose de dev). Custo: ~centenas de ms de compilação no start |
| `PLAYWRIGHT_BROWSERS_PATH=/ms-playwright` | local fixo do Chromium (antes dependia de `$HOME`/root). Não muda comportamento |

## Depois

Imagem: `mv-api:depois`, construída de `docker build --no-cache -t mv-api:depois .` na raiz
da worktree (`Dockerfile` novo, BuildKit usa o `Dockerfile.dockerignore`), 15/11/2026.

### Tamanho

| Métrica | Valor |
|---|---|
| `docker image ls` | **1,26 GB** |
| `du -xsm /` (dentro do container) | **858 MB** |
| Comprimido (`docker save \| gzip`), `wc -c` | **350.806.993 bytes ≈ 350,8 MB** |

### Por camada (`docker history`)

| Tamanho | Camada |
|---|---|
| 87,7 MB | Base `python:3.11-slim` |
| 4,9 MB | `ca-certificates`/`netbase`/`tzdata` |
| 48,8 MB | Compila e instala o Python 3.11 |
| **49,4 MB** | `apt-get` (era 284 MB + 0,5 MB): libs do Chromium com `--no-install-recommends` + purge mesa/llvm/z3 |
| **211 MB** | `pip install --no-cache-dir -r requirements.txt` |
| **427 MB** | `playwright install --no-shell chromium` (Chromium ~403 + ffmpeg ~6 + metadados) |
| 12,3 kB | `COPY schema.prisma` |
| **76,5 MB** | `prisma generate` + symlink do node + limpeza dos caches |
| 82 kB | `COPY migrations` |
| 246 kB | `COPY execution` |

Ordem das camadas: apt → requirements+pip → playwright → schema+prisma → migrations →
execution (só as 2 últimas mudam a cada commit).

### Por diretório (`du -sm` dentro da imagem)

| Categoria | Diretório(s) | Antes | Depois |
|---|---|---|---|
| Navegador (Playwright) | `/ms-playwright` (antes `/root/.cache/ms-playwright`) | 408 MB | 408 MB |
| Site-packages (Python) | `/usr/local/lib/python3.11/site-packages` | 222 MB | 216 MB |
| Sistema Debian | `/usr` (menos `/usr/local`) + `/var` + `/etc` | ~377 MB | ~155 MB |
| Cache do Prisma | `/root/.cache/prisma-python` | 314 MB | **70 MB** |
| Cache do npm/pip/Prisma CLI | `/root/.npm` + `/root/.cache/pip` + `/root/.cache/prisma` | 185 MB | **0** |
| `/app` | código | 14 MB | **1 MB** (só `execution`, `migrations`, `requirements.txt`, `schema.prisma`) |
| `/tmp` | sobra do prisma generate | 2,6 MB | 2,6 MB |

Dentro de `/usr` no "depois": `/usr/lib/x86_64-linux-gnu` caiu de 276 MB para **76 MB**
(saíram `libLLVM.so.19.1` 124 MB, `libgallium` 41 MB e `libz3` 27 MB); `site-packages`
continua com os 122 MB do node do driver do Playwright (que agora também serve o Prisma).

## Antes × depois

> **Régua confiável:** `du -xsm /` (dentro do container) e `docker save | gzip | wc -c`.
> O `docker image ls` do Docker Desktop com o snapshotter containerd soma de outro jeito
> (comprimido + descomprimido — `docker system df -v` mostra `SHARED + UNIQUE` ≈ 2× o du),
> então use-o só como referência do que o Docker exibe, nunca para comparar ganho real.

Mesma máquina, builds sem cache um depois do outro (sem concorrência), 15/11/2026:

| Métrica | Antes | Depois | Variação |
|---|---|---|---|
| `docker image ls` | 2,23 GB | 1,26 GB | **−43,5%** |
| `du -xsm /` | 1533 MB | 858 MB | **−44,0%** |
| Comprimido (`save \| gzip`) | 607,7 MB (607.696.066 B) | 350,8 MB (350.806.993 B) | **−42,3%** |
| Build sem cache | 111,4 s | 99,8 s | **−10,4%** |
| Tempo até `GET /` (200) | 2,5 s | 2,9 s | +0,4 s (ruído) |
| RAM repouso API (mediana de 5) | 68,2 MiB | 67,7 MiB | −0,7% ✅ dentro de ±5% |
| RAM repouso worker (mediana de 5) | 127,2 MiB | 130,5 MiB | +2,6% ✅ dentro de ±5% |
| Pico RAM API no refresh | 497,9 MiB | 494,7 MiB | −0,6% ✅ dentro de ±5% |
| Worker: ready / tasks / beat | sim / sim / sim | sim / sim / sim | idêntico |
| Resposta do ML no refresh | `{"status":"error","reason":"unavailable"}` | `{"status":"error","reason":"unavailable"}` | idêntica |

Nota sobre a resposta do ML: nas duas execuções o refresh devolveu HTTP 200 com
`reason: "unavailable"` ("Não foi possível obter os dados do anúncio…"). A página
`ritmo-da-guerra/p/MLB60505498` não entregou dados na hora da visita — **comportamento
idêntico nas duas imagens**, então a comparação (inclusive o pico de RAM, com o Playwright
aberto na visita) continua válida. No teste real da branch `feat/ml-sem-login-e-formato`, o
Mercado Livre também não entregou a página para esta máquina, nem com o scraper novo nem com o
antigo, enquanto o homelab checava normalmente. Então não é efeito da imagem.

## Verificação de funções

Feitas pelo orquestrador na `mv-api:depois` em 15/11/2026, sempre com `FIRECRAWL_API_KEY=`
vazio, numa rede Docker própria (`mvver`) com `postgres:15-alpine` e `redis:7-alpine`, sem o
`docker compose` do repo (que montaria `.:/app` por cima da imagem).

| # | Verificação | Resultado |
|---|---|---|
| 1 | pytest na imagem, testes montados por volume | ✅ `340 passed` na `depois` (7,3 s) e na `antes` (7,5 s), Python 3.11.18 |
| 2 | `prisma migrate deploy` em banco vazio e com dados | ✅ vazio: 8 migrações aplicadas; com dados: 5 pendentes aplicadas sobre o dump real, sem perder linhas; 2ª execução: `No pending migrations` |
| 3 | API com o comando de produção | ✅ `GET /` 200 em 3,0 s; `/products`, `/groups`, `/stores/stats?days=1` → 200 |
| 4 | Worker com o comando de produção | ✅ `ready`, as 2 tarefas registradas (iguais às da `antes`), Beat com `crontab 0 */6 * * *` |
| 5 | Chromium | ✅ impressão digital idêntica à da `antes` (`Compare-Object` vazio), perfil persistente criado e reaberto |
| 6 | Scraping real curto | ✅ Amazon pelo httpx e pelo Playwright com o preço igual ao da página; ML com a mesma resposta da `antes` |
| 7 | `POST /product/{id}/refresh` (Amazon) | ✅ `ok`, nível 1, R$ 59,18, vendido pela Amazon, `trigger=manual` gravado |
| 8 | Front (`apps/web/Dockerfile`) | ✅ arquivo não mudou; build sem cache OK com o `.dockerignore` novo |
| 9 | `pnpm lint` / `typecheck` / `test` | — não se aplica: nenhum arquivo do monorepo (`apps/`, `packages/`, `package.json`, lock) foi tocado |

### 1. pytest

```powershell
docker run --rm -e FIRECRAWL_API_KEY= -v "D:\Estudos\Melhores_Valores\execution\tests:/app/execution/tests:ro" mv-api:depois `
  sh -c "python --version && pip install -q --no-cache-dir pytest && python -m pytest execution/tests -q -p no:cacheprovider"
```

```
=== mv-api:antes
Python 3.11.18
340 passed in 7.45s
=== mv-api:depois
Python 3.11.18
340 passed in 7.26s
```

O `pytest` é instalado só no container descartável; a imagem não leva os testes nem o pytest.

### 2. Migrações

**Banco vazio** (`prisma migrate deploy` da imagem nova):

```
8 migrations found in prisma/migrations
Applying migration `20260304233713_add_search_results`
...
Applying migration `20261115000000_add_check_attempt_and_format`
All migrations have been successfully applied.
8 migracoes aplicadas          (_prisma_migrations com finished_at)
```

**Banco com dados:** o `backup-melhores-valores.sql` (dump só de dados, tirado do homelab)
está na estrutura das 3 primeiras migrações. Então:

1. as 3 primeiras migrações foram aplicadas com uma pasta `migrations` parcial montada por volume;
2. o dump foi carregado (`psql -v ON_ERROR_STOP=1`);
3. o `prisma migrate deploy` da imagem nova aplicou as outras 5 por cima dos dados.

```
8 migrations found in prisma/migrations
Applying migration `20261108230000_add_product_groups`
Applying migration `20261109000000_one_group_per_product`
Applying migration `20261111120000_add_product_last_check`
Applying migration `20261112000000_add_price_history_seller`
Applying migration `20261115000000_add_check_attempt_and_format`
All migrations have been successfully applied.

 produtos | historico | buscas | com_status | tentativas
       25 |       946 |    409 |         25 |          0     (dump: 25 / 946 / 409 linhas)
8 migracoes aplicadas
--- 2ª execução: No pending migrations to apply.
```

Tudo offline em relação ao Prisma: o CLI usa o node e os engines que já estão na imagem.

### 3. API (comando de produção, sobre o banco com dados)

`sh -c "prisma migrate deploy && uvicorn execution.web_server:app --host 0.0.0.0 --port 8000"`:

```
GET / em 3,0 s
GET /                    -> 200 {"status":"ok","message":"Price Tracker API is running"}
GET /products            -> 200, 21744 bytes {"total":25,"products":[...]}
GET /groups              -> 200 {"groups":[]}
GET /stores/stats?days=1 -> 200, 3083 bytes {"days":1,...,"stores":[{"store":"amazon",...
```

Log da API sem `ERROR`/`Traceback`.

### 4. Worker + Beat (comando de produção)

`celery -A execution.worker_tasks worker -B -s /tmp/celerybeat-schedule --concurrency=2 --max-tasks-per-child=20 --loglevel=info`:

```
[INFO/Beat] beat: Starting...
[tasks]
. execution.worker_tasks.process_price_check
. execution.worker_tasks.schedule_all_products
[INFO/MainProcess] Connected to redis://mvver-redis:6379/0
[INFO/MainProcess] celery@9044d40273ca ready.

schedule-all-products-every-6-hours execution.worker_tasks.schedule_all_products <crontab: 0 */6 * * *>
/tmp/celerybeat-schedule criado (16 kB)
tarefas na antes:  ['execution.worker_tasks.process_price_check', 'execution.worker_tasks.schedule_all_products']
tarefas na depois: ['execution.worker_tasks.process_price_check', 'execution.worker_tasks.schedule_all_products']
```

O worker também processou de verdade uma tarefa `process_price_check` (`POST /monitor/add`,
item 6).

### 5. Chromium — impressão digital antes × depois

O mesmo script roda nas duas imagens com `--network none`. Ele abre o navegador como o scraper
(`_open_disposable_context` e `_open_persistent_context(p, "mercadolivre")`, com
`BROWSER_PROFILE_DIR=/tmp/perfis`) e lê a impressão digital do navegador.

Como o purge de mesa/llvm mexe na pilha gráfica, a verificação incluiu:

- o WebGL (vendor/renderer reais via `WEBGL_debug_renderer_info`, número de extensões, textura máxima, WebGL2);
- o hash de um canvas 2D com texto acentuado;
- a medida de fontes.

Saída da `depois` (a da `antes` é **idêntica linha a linha**: `Compare-Object` vazio):

```
browser.version = 156.0.8078.4
[descartavel] ua = Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36
[descartavel] webdriver = False
[descartavel] plugins = 5
[descartavel] languages = pt-BR
[descartavel] tz = America/Sao_Paulo
[descartavel] screen = 1280x800x24
[descartavel] webglVendor = Google Inc. (Google)
[descartavel] webglRenderer = ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)
[descartavel] webglExt = 35
[descartavel] webglMaxTex = 8192
[descartavel] webgl2 = True
[descartavel] canvasHash = 779721659
[descartavel] textWidth = 165
[descartavel] fonts = sans-serif=114,serif=114,monospace=96,Arial=114,DejaVu Sans=114
perfil novo = True
[persistente] ... (mesmos valores do descartável)
perfil reaberto novo = False
perfil em disco = ['mercadolivre', 'mercadolivre.lock']
```

O WebGL continua saindo pelo SwiftShader, que vem dentro do Chromium e não usa o
mesa/llvm do sistema. Por isso o purge não muda nada do que o site enxerga.

### 6 e 7. Scraping real (poucas visitas, sem loop)

Visitas feitas nesta verificação, sobre a stack de teste com a imagem nova:

| Visita | Caminho | Resultado | Página no Chrome |
|---|---|---|---|
| `POST /product/{id}/refresh` de `dp/6525948150` | API → cascata, nível 1 (httpx), 2,3 s | `ok`, **R$ 59,18**, `amazon`, `physical`, `trigger=manual` | R$ 59,18, Capa Comum, Enviado/Vendido Amazon.com.br |
| `POST /monitor/add` de `dp/6581339210` | API → fila → worker, nível 1 (httpx), 2,5 s | `ok`, **R$ 121,01**, `amazon`, `physical`, `trigger=added` | R$ 121,01, Capa Comum, Enviado/Vendido Amazon.com.br |
| Nível 2 forçado de `dp/6581339210` | `scrape_product_with_meta` com o httpx desligado só no teste (Firecrawl bloqueado) | nível 2 (Playwright), 11,8 s, **R$ 121,01**, `amazon`, `physical` | idem |
| Mercado Livre `ritmo-da-guerra/p/MLB60505498` | refresh da medição (uma visita por imagem, na mesma hora) | `unavailable` nas duas imagens | — |

Linha do `CheckAttempt` gravada pelo refresh e pela tarefa:

```
 trigger | status | level | durationMs |    asin    |  format  |      ultimo
 manual  | ok     |     1 |       2306 | 6525948150 | physical | 59.18 amazon true
 added   | ok     |     1 |       2481 | 6581339210 | physical | 121.01 amazon true
```

### 8. Front

`git diff origin/main --stat -- apps packages package.json pnpm-lock.yaml .github` → vazio:
o `apps/web/Dockerfile` não mudou. O front usa o mesmo contexto `.` e o `.dockerignore` da
raiz, que ganhou as exclusões de segredos e dumps. Com isso:

- `docker build --no-cache -f apps/web/Dockerfile .` passou (exit 0);
- a imagem tem `50x.html`, `assets`, `favicon.svg` e `index.html`;
- nenhum `.env`, `.sql` ou `.patch` entrou na imagem.

### Conteúdo da imagem (nada fora do git, nenhum segredo)

```
/app: execution  migrations  requirements.txt  schema.prisma
/app/execution: __init__.py adapters cache_manager.py db_client.py firecrawl_api.py scrapers
  scraping_orchestrator.py search_orchestrator.py search_scrapers search_status.py
  store_detection.py store_health.py store_lock.py web_server.py worker_tasks.py
find / -xdev ( -name '.env*' -o -name 'backup-*.sql' -o -name '*.dump' -o -name '*.patch' -o -name '.git' ) → vazio
```

A imagem foi construída com `.env`, `backup-melhores-valores.sql` e um `teste.patch` presentes
na raiz, e nenhum deles entrou, porque o `Dockerfile.dockerignore` é uma lista do que entra.

## Propostas não aplicadas

Números medidos pelo BUILD (mesma máquina):

- **(a) `chromium-headless-shell` no lugar do Chromium completo:** −130 MB descomprimido
  (273 MB vs 403 MB; imagem ficaria ~1,13 GB, du ~730 MB). **Não recomendado:** perde o
  "novo headless" — UA `HeadlessChrome`, `sec-ch-ua` com "HeadlessChrome", 0 plugins —
  justamente o que o scraper evita contra o login_wall do ML (ver
  `execution/scrapers/README.md`).
- **(a') Aparar o Chromium completo (≈ −68 MB, não aplicado):** `locales/` 50 MB (manter só
  en-US e pt-BR → ≈ −47 MB) e `WidevineCdm` 21 MB (DRM, sem uso). Risco baixo, mas mexe
  dentro do bundle do Playwright (que se atualiza sozinho a cada `playwright install`).
  **Atualização (branch `perf/imagem-api-ajustes`):** o corte de `locales/` foi **aplicado**
  (ver "Ajustes finais" abaixo); o `WidevineCdm` continua **como proposta** — o teste de DRM
  mostrou diferença detectável na API do navegador (ver seção "DRM (WidevineCdm)").
- **(b) Duas imagens (API sem Chromium / worker com Chromium):** API = **574 MB**
  (du 406 MB, gz 143,7 MB) vs 1,26 GB do "depois"; worker ficaria a imagem atual. Como
  compartilham base+pip+Prisma, o registry guarda pouco mais que uma delas. **Impedimento:**
  o botão "Atualizar preço" (`POST /product/{id}/refresh`) roda `run_price_pipeline` na
  própria API, e o ML só funciona via Playwright — sem mover o refresh para uma task do
  worker (mudança de código/contrato, fora do escopo de imagem), o refresh do ML quebraria.
  **Conclusão em "Ajustes finais" → "Duas imagens — fora do escopo"** (no homelab o total
  baixado até aumentaria).

## Ajustes finais (branch perf/imagem-api-ajustes)

Régua igual ao ciclo anterior: `du -xsm /` (dentro do container) e
`docker save | gzip | wc -c` (a régua confiável; o `docker image ls` do Docker Desktop com
containerd soma comprimido + descomprimido, então não serve para comparar ganho real).

### Baseline desta tarefa: `mv-aj:antes`

`git archive origin/main` (origin/main = `69c0e52`) extraído numa pasta e
`docker build -t mv-aj:antes <pasta>` — construído **de pasta**, como o CI (receita em
"Como medir"; o primeiro build por `git archive | docker build -` ignorava o
`Dockerfile.dockerignore` e entrava com `execution/tests`, 10 MB a mais — correção aplicada):

| Métrica | Valor |
|---|---|
| `docker image ls` | 1,26 GB |
| `du -xsm /` | **858 MB** ✓ (bate com o "depois" do ciclo anterior) |
| Comprimido (`save \| gzip`) | **350.806.386 B ≈ 350,8 MB** ✓ |
| `/app/execution` | sem `tests` ✓ (igual à `mv-aj:depois`) |

Runtime da `mv-aj:antes` (sem `-PeakUrl`): `GET /` 3,5 s, RAM API **67,7 MiB**, RAM worker
**130,5 MiB** (mediana de 5 amostras; uma primeira rodada deu 157,9 MiB — filho do prefork do
Celery pego no meio de ciclo, uma segunda rodada confirmou 130,5; worker ready/tasks/beat OK).
O teste de DRM não foi repetido: o Chromium da imagem reconstruída é idêntico (mesmas camadas
em cache).

### Traduções do Chromium (aplicado)

Em `/ms-playwright/chromium-1248/chrome-linux64/locales/`. O `Dockerfile` não fixa a versão:
acha a pasta com `find "$PLAYWRIGHT_BROWSERS_PATH" -type d -name locales -path '*chrom*'` e
o build falha se não achar exatamente uma pasta ou se `en-US.pak`/`pt-BR.pak` não sobrarem.

| Item | Antes | Depois |
|---|---|---|
| `locales/` | 50 MB, 220 arquivos `.pak` | **2 MB, 2 arquivos** (`en-US.pak` + `pt-BR.pak`) |
| Pasta `chrome-linux64/` do Chromium | 403 MB | 355 MB |
| Ganho no `du` da imagem | — | **−48 MB** (858 → 810 MB) |
| Ganho no comprimido | — | **−13,0 MB** (350.806.386 → 337.791.730 B; camada do Playwright 427 → 377 MB) |

Por que é seguro: o Chromium usa os `.pak` para textos da própria interface do navegador
(páginas internas, diálogos, mensagens de erro de rede). As páginas de produto que o scraper
lê são traduzidas pelo site, não pelo navegador. A linguagem que o site enxerga vem de
`Accept-Language`/`navigator.languages` do contexto do Playwright (pt-BR), que não depende
dos `.pak`. **Verificação da impressão digital (feita):** a página renderizada pelo Chromium
saiu com as 91 linhas do fingerprint idênticas linha por linha antes × depois; mensagens de
validação de formulário vieram em **inglês nas duas imagens** (o Chromium já usava
`en-US.pak` para isso, que continua na imagem; `pt-BR.pak` fica por segurança).

### DRM (WidevineCdm) — proposta, não aplicado

`WidevineCdm/` em `/ms-playwright/chromium-1248/chrome-linux64/`: **21 MB**, com
`LICENSE`, `manifest.json` (Widevine Content Decryption Module 4.10.3112.0, codecs
`vp8,vp09,avc1,av01`, esquemas `cenc`/`cbcs`) e `_platform_specific/linux_x64/libwidevinecdm.so`.

Teste feito na `mv-aj:antes`, navegador aberto **exatamente como o scraper abre**
(`ps._open_disposable_context(p)` dentro de `sync_playwright()`), página **https**
(`context.route("https://probe.test/**", ...)` com `route.fulfill` — o EME exige contexto
seguro; `data:` não serve), chamando
`navigator.requestMediaKeySystemAccess('com.widevine.alpha', ...)` (com
`robustness: 'SW_SECURE_CRYPTO'`), `org.w3.clearkey` como controle, e `navigator.plugins`/
`mimeTypes`. Segunda execução no mesmo container após `rm -rf` da pasta (a imagem não muda):

| Teste | Com WidevineCdm | Sem WidevineCdm |
|---|---|---|
| `com.widevine.alpha` | **ok** — resolve com a config pedida (`initDataTypes cenc`, vídeo avc1 com `robustness SW_SECURE_CRYPTO`, áudio mp4a.40.2) | **erro `NotSupportedError: Unsupported keySystem or supportedConfigurations.`** |
| `org.w3.clearkey` | ok | ok (idêntico) |
| `navigator.plugins` | 5 (PDF Viewer…) | idênticos |
| `navigator.mimeTypes` | `application/pdf`, `text/pdf` | idênticos |

**As saídas NÃO são iguais.** Sem a pasta, o Chromium rejeita o key system Widevine na API
do navegador — e isso é **detectável por qualquer site com uma linha de JS**
(`requestMediaKeySystemAccess('com.widevine.alpha')` resolve ou rejeita), sem precisar tocar
em conteúdo DRM de verdade. É o que significa a diferença: o Chromium completo do Playwright
traz o módulo Widevine como o Chrome de um usuário comum de Linux; sem ele, o navegador do
scraper fica "sem DRM", um sinal a menos de navegador real.

**Por que não removemos:** o ganho é pequeno (21 MB de conteúdo, ~1,6% da imagem) e a
mudança aparece justamente para o site, numa checagem de uma linha. Não sabemos se o Mercado
Livre olha esse sinal, mas ele já barra o navegador do scraper com `login_wall` em parte das
visitas, e um sinal a menos de "Chrome de verdade" pode piorar isso sem que dê para medir
antes. Clearkey, plugins e mimeTypes continuarem iguais não muda a conclusão. Fica como
proposta, não aplicada: só valeria tentar se o ML um dia deixar de importar.

### Bibliotecas de GPU (decisão: ficam fora)

O `libgbm1` (necessário ao Chromium) puxa como dependência dura `mesa-libgallium` (41,6 MB),
`libllvm19` (126,7 MB) e `libz3-4` (27,1 MB) — a pilha gráfica/compilador do mesa. O
Chromium headless do scraper não usa GPU do sistema: o WebGL sai pelo **SwiftShader**
(que vem dentro do próprio bundle do Playwright) com vendor/renderer idêntico antes × depois
da otimização (ver "Verificação de funções", item 5). Por isso as três ficam fora, via
`dpkg --purge --force-depends mesa-libgallium libllvm19 libz3-4` no `RUN` do apt.

- **Efeito colateral no dpkg:** o purge forçado deixa `libgbm1` marcado com dependência
  quebrada. Só afeta um `apt-get install` futuro **dentro** da imagem (que ninguém faz em
  produção); se um dia precisar de aceleração de GPU real, remover a linha do purge.
- **Regra para o Dockerfile:** qualquer `apt-get install` novo deve vir **antes** da linha
  do purge (o comentário acima do `RUN` do apt diz isso). Depois dela o apt recusa instalar
  por causa da dependência quebrada do `libgbm1` e pede `apt --fix-broken install`, que
  traria mesa/llvm/z3 de volta.
- **Teste de fumaça no Actions (BUILD, aplicado no workflow):** o diff de
  `.github/workflows/docker-publish.yml` adiciona dois passos no job da API (com
  `if: matrix.image == 'melhores-valores-api'`), **antes** do passo que publica:
  1. *Construir a imagem para o teste* — `docker/build-push-action@v6` com `load: true`,
     `push: false`, `tags: mv-api:smoke` e `cache-from: type=gha` (sem `cache-to`: quem grava
     o cache é o passo de publicar, que reutiliza este build);
  2. *Teste em si* — `set -euo pipefail` + `docker run --rm --network none` (imagem isolada
     de rede) rodando `node --version && prisma --version` e um `python -c` que abre o
     Chromium **como o scraper** (`ps._open_disposable_context(p)`), carrega
     `data:text/html,<title>ok</title>`, confere o título e confere que
     `ps._browser_version_cache` ficou preenchido.
  Se o Node, o Prisma ou o Chromium (dependências das libs de sistema) não funcionarem, o
  job falha **antes de publicar**. Evidência do BUILD: na `mv-aj:depois` o passo passa
  (exit 0, `browser.version = 156.0.8078.4`); com `PLAYWRIGHT_BROWSERS_PATH` quebrado falha
  (exit 1). Ressalva: validado só na execução local do passo extraído — ainda não rodou num
  GitHub Actions de verdade.

### Duas imagens — fora do escopo

**Conclusão: não faz para este projeto.** No homelab, API e worker usam a **mesma** imagem
(`ghcr.io/ladongx/melhores-valores-api`), baixada uma vez: 1,26 GB (gz 350,8 MB) e pronto.
Com duas imagens (API sem Chromium **574 MB** / du 406 MB / gz 143,7 MB + worker 1,26 GB,
com a base compartilhada só parcialmente), **o total baixado aumentaria** — a economia de
574 MB só apareceria se o worker fosse dispensado, e ele não é. E ainda exigiria mover o
botão "Atualizar preço" (`POST /product/{id}/refresh`, que roda `run_price_pipeline` na
própria API — e o ML só funciona via Playwright) para uma tarefa do worker: mudança de
código/contrato, fora do escopo de imagem. Precondição, se um dia o total baixado importar
mais que a simplicidade: primeiro o refresh vira task do worker; só depois vale discutir
duas imagens.

### Antes × depois (ajustes finais)

`mv-aj:antes` vs `mv-aj:depois`, ambas construídas de pasta (igual ao CI). Os itens
"comentário" e "teste de fumaça" não mudam a imagem (o teste é um passo do workflow); o
Widevine foi mantido.

| Item | Ganho em conteúdo (`du`) | Ganho comprimido |
|---|---|---|
| Traduções do Chromium (220 → 2 `.pak`) | **−48 MB** (858 → 810 MB) | **−13,0 MB** (350.806.386 → 337.791.730 B) |
| Comentário no Dockerfile / purge de GPU libs | 0 (já estavam no ciclo anterior) | 0 |
| Teste de fumaça no workflow | 0 (não muda a imagem) | 0 |
| WidevineCdm | mantido (21 MB) — ver seção DRM | — |

| Runtime (sem `-PeakUrl`) | Antes | Depois | Δ |
|---|---|---|---|
| Tempo até `GET /` (200) | 3,5 s | 3,0 s | dentro do ruído |
| RAM repouso API | 67,7 MiB | 67,7 MiB | 0% ✓ |
| RAM repouso worker | 130,5 MiB | 130,4 MiB | −0,1% ✓ (dentro de ±5%) |
| Worker ready/tasks/beat | OK | OK | — |

### Verificação de funções (ajustes)

Feitas pelo orquestrador na `mv-aj:depois` em 15/11/2026, com `FIRECRAWL_API_KEY=` vazio,
numa rede Docker própria (`mvaj`, Postgres 15 e Redis 7, sem o compose do repo; a API
publicada só em `127.0.0.1:8010` para não disputar a 8000 com a medição).

| # | Verificação | Resultado |
|---|---|---|
| 1 | pytest com os testes montados por volume | ✅ `340 passed in 8.20s` (Python 3.11.18) |
| 2 | `prisma migrate deploy` | ✅ banco vazio: as 8 aplicadas; banco com o dump do homelab (3 primeiras + dump + as outras 5): 25 produtos / 946 preços / 409 buscas preservados, 8 migrações registradas; 2ª execução `No pending migrations to apply.` |
| 3 | API com o comando de produção | ✅ `GET /` 200 (5,1 s nesta rodada, com a medição rodando ao lado; o número limpo é o do script, 3,0 s); `/products` (25), `/groups`, `/stores/stats?days=1` → 200; log sem `ERROR`/`Traceback` |
| 4 | Worker com o comando de produção | ✅ `ready`, `process_price_check` e `schedule_all_products` registradas, `beat: Starting...`, agenda `schedule-all-products-every-6-hours` com `crontab 0 */6 * * *` |
| 5 | Chromium | ✅ impressão digital ampliada **idêntica nas 91 linhas** entre `mv-aj:antes` e `mv-aj:depois` (abaixo); `browser.version = 156.0.8078.4`; perfil persistente criado e reaberto (`perfil reaberto novo = False`) |
| 6 | Scraping real curto | ✅ Amazon pelo httpx e pelo Playwright com o preço da página; Playwright com o **mesmo preço nas duas imagens**; ML com a **mesma resposta nas duas imagens**, na mesma hora |
| 7 | `POST /product/{id}/refresh` (Amazon) | ✅ `{"status":"ok","price":59.18,"in_stock":true,...}`, `CheckAttempt` com `trigger=manual`, nível 1 |
| 8 | Front | ✅ `apps/web/Dockerfile` e o `.dockerignore` da raiz não mudaram nesta branch; o workflow só ganhou passos com `if:` da API, e o passo do front ficou igual |
| 9 | pnpm lint/typecheck/test | — não se aplica: nenhum arquivo do monorepo foi tocado |

**Impressão digital (item 5).** Script do orquestrador, rodado com `--network none` nas duas
imagens. Ele abre o navegador como o scraper (`_open_disposable_context` e
`_open_persistent_context(p, "mercadolivre")`) numa página `https://probe.test/` servida por
`context.route` (contexto seguro, sem rede) e registra:

- os **cabeçalhos HTTP reais** da navegação;
- o `navigator`, o `Intl` e a formatação local;
- WebGL, canvas, fontes e o perfil persistente.

`Compare-Object` entre as duas saídas: vazio. Trechos da `mv-aj:depois`:

```
browser.version = 156.0.8078.4
[descartavel] header accept-language = pt-BR
[descartavel] header user-agent = Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/156.0.0.0 Safari/537.36
[descartavel] header sec-ch-ua = "Not:A-Brand";v="8", "Chromium";v="156"
[descartavel] header sec-ch-ua-platform = "Linux"
[descartavel] language = pt-BR
[descartavel] languages = pt-BR
[descartavel] dtf = {"locale":"pt-BR","calendar":"gregory","numberingSystem":"latn","timeZone":"America/Sao_Paulo","year":"numeric","month":"2-digit","day":"2-digit"}
[descartavel] collator = pt-BR
[descartavel] dateStr = 15/11/2026, 12:00:00
[descartavel] numStr = 1.234.567,891
[descartavel] currency = R$ 1.234,50
[descartavel] plugins = PDF Viewer|Chrome PDF Viewer|Chromium PDF Viewer|Microsoft Edge PDF Viewer|WebKit built-in PDF
[descartavel] webglRenderer = ANGLE (Google, Vulkan 1.3.0 (SwiftShader Device (Subzero) (0x0000C0DE)), SwiftShader driver)
[descartavel] canvasHash = 779721659
[descartavel] fonts = sans-serif=114,serif=114,monospace=96,Arial=114,DejaVu Sans=114
[descartavel] validationMsg = Please fill out this field.
perfil reaberto novo = False
```

**Scraping real (itens 6 e 7).** Poucas visitas, sem loop:

| Visita | Imagem | Resultado | Página no Chrome |
|---|---|---|---|
| `POST /product/{id}/refresh` de `dp/6525948150` | depois | nível 1 (httpx), `ok`, **R$ 59,18**, `amazon`, `physical` | R$ 59,18, Capa Comum, Enviado/Vendido Amazon.com.br |
| `POST /monitor/add` de `dp/6581339210` (fila → worker) | depois | nível 1 (httpx), `ok`, **R$ 121,01**, `amazon`, `physical`, `trigger=added` | R$ 121,01, Capa Comum, Enviado/Vendido Amazon.com.br |
| Nível 2 forçado de `dp/6581339210` (httpx desligado só no teste) | antes | Playwright, 11,7 s, **R$ 121,01**, `amazon`, `physical` | idem |
| idem | depois | Playwright, 12,0 s, **R$ 121,01**, `amazon`, `physical` | idem |
| ML `ritmo-da-guerra/p/MLB60505498`, cascata real | antes (17:44) | nível 2, `login_wall`, 33,5 s, Firecrawl pulado | — |
| idem | depois (17:45) | nível 2, `login_wall`, 33,7 s, Firecrawl pulado | — |

O ML deu `login_wall` nas duas imagens, com um minuto de diferença. Desta máquina ele já
barrava o scraper antes destes ajustes; o resultado igual é o que importa aqui.

**Regra do apt (item 3 da tarefa).** Teste num container descartável da `mv-aj:depois`:
`apt-get update && apt-get install -y xz-utils` →
`libgbm1 : Depends: mesa-libgallium (= 25.0.7-2+deb13u1) but it is not going to be installed`
e `E: Unmet dependencies. Try 'apt --fix-broken install'`. É exatamente o que o comentário
do `Dockerfile` avisa: instalação nova só antes da linha do purge.
