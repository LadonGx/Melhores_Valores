# Melhores Valores: guia para transformar em executável

Resumo da análise do repositório LadonGx/Melhores\_Valores (baseada no README, sem acesso ao código-fonte), com problema, soluções, estratégias, conselhos e o que será perdido.

## 1. Contexto e objetivo

**Projeto:** rastreador de preços e API de busca para Amazon BR e Mercado Livre.

**Stack atual:**

- Backend: Python 3.11+, FastAPI, Celery + Celery Beat, PostgreSQL 15 (via Prisma), Redis 7.
- Scraping em cascata: `httpx`, depois Playwright/Chromium, depois Firecrawl API (paga, último recurso).
- Frontend: React + Vite + TypeScript em monorepo pnpm (`apps/web`, `packages/types`, `packages/utils`).
- Infraestrutura: Docker e Docker Compose (db, redis, api, worker, beat).

**Objetivo do autor:** transformar o programa em um executável que as pessoas possam baixar, para:

- não precisar fazer deploy do backend para todos usarem;
- não precisar criar CRUD de usuários com autenticação.

## 2. O problema

A arquitetura atual foi pensada para **servidor**: vários serviços separados que dependem uns dos outros (banco, Redis, worker, agendador, API). Um usuário comum não consegue instalar e configurar tudo isso. Além disso, hospedar para todos exigiria infraestrutura paga, autenticação e controle de dados por usuário.

## 3. Veredito

**É viável e faz sentido para o objetivo, mas não com a arquitetura atual.** É preciso simplificar o backend para rodar em **um único processo**, com banco em arquivo local. Só depois disso o empacotamento funciona.

## 4. Por que a ideia faz sentido

1. **Sem deploy e sem custo de servidor.** Cada usuário roda no próprio computador.
2. **Sem Auth e sem CRUD de usuários.** Cada pessoa tem seu banco local e só vê os próprios produtos, então o problema de "quem vê o quê" desaparece.
3. **Menos bloqueios nos scrapers.** Amazon e Mercado Livre costumam bloquear IPs de datacenter. Num servidor todas as requisições saem do mesmo IP e o bloqueio é quase certo. Na casa de cada usuário o tráfego sai de IP residencial e parece normal. É o maior ponto a favor.

## 5. Por que o projeto atual não vira um .exe direto

| Componente atual | Problema | Solução |
| --- | --- | --- |
| PostgreSQL | O usuário teria que instalar e configurar um servidor de banco | Trocar por SQLite (um arquivo local) |
| Redis (cache + broker) | Mesmo problema, e no Windows nem roda nativamente | Cache em memória ou tabela no SQLite |
| Celery worker + Beat | São 2 processos extras que dependem do Redis | APScheduler dentro do próprio app |
| Prisma (Python) | Depende de binários e CLI em Node, muito difícil de empacotar com PyInstaller | Trocar por `sqlite3` ou SQLAlchemy |
| Firecrawl API (paga) | Chave embutida no executável pode ser extraída e você pagaria pelo uso de todos | Remover ou deixar opcional, com o usuário usando a própria chave |
| Docker Compose | Não faz sentido para usuário final | Deixa de ser necessário |

**Vantagem do projeto:** o README diz que todo acesso ao banco passa por `execution/db_client.py`. Trocar o banco fica concentrado em um arquivo e o resto do código não precisa perceber a mudança.

## 6. Solução passo a passo

### Passo 1: Banco, de PostgreSQL para SQLite

- Reescreva o `db_client.py` mantendo as mesmas funções públicas.
- O schema tem só 3 tabelas (`Product`, `PriceHistory`, `SearchResult`), então a migração é simples.
- Salve o arquivo na pasta de dados do usuário (por exemplo `%APPDATA%/MelhoresValores/` no Windows), nunca ao lado do executável, porque a pasta de instalação pode ser somente leitura.

### Passo 2: Fila e agendamento, de Celery para threads e APScheduler

- O `POST /search` hoje enfileira uma task e devolve um `search_id`. Mantenha esse contrato para o frontend não mudar, usando `BackgroundTasks` do FastAPI ou uma thread.
- O Celery Beat vira:

```python
from apscheduler.schedulers.background import BackgroundScheduler

scheduler = BackgroundScheduler()
scheduler.add_job(schedule_all_products, "interval", hours=6)
scheduler.start()
```

### Passo 3: Cache, de Redis para memória

- Um dicionário com TTL de 2h (ou a biblioteca `cachetools`) substitui o `cache_manager.py`.
- Perder o cache ao fechar o app não é problema, pois é apenas otimização.

### Passo 4: Servir o frontend pelo próprio backend

- Rode `pnpm build` e deixe o FastAPI entregar os arquivos estáticos. Assim há uma única porta e nenhum problema de CORS.
- No frontend, use URL relativa em vez de `http://localhost:8000` (ajuste o `VITE_API_URL`).

```python
from fastapi.staticfiles import StaticFiles

# montar DEPOIS das rotas da API
app.mount("/", StaticFiles(directory="web_dist", html=True), name="web")
```

### Passo 5: Ponto de entrada único (`main.py`)

```python
import threading, webbrowser, uvicorn

threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
uvicorn.run(app, host="127.0.0.1", port=8000)
```

- Use `127.0.0.1` e não `0.0.0.0`, para que só o próprio computador acesse o programa.
- Alternativa: abrir uma janela nativa com `pywebview`.

### Passo 6: Empacotar com PyInstaller

```bash
pyinstaller --onedir --name MelhoresValores \
  --add-data "apps/web/dist:web_dist" main.py
```

- Prefira `--onedir` a `--onefile`: o `onefile` descompacta tudo a cada execução (abertura lenta) e gera mais falsos positivos de antivírus.
- No Windows, o separador do `--add-data` é `;` em vez de `:`.

### Passo 7: Playwright/Chromium (ponto mais delicado)

O Chromium tem cerca de 150 a 300 MB. Duas opções:

- **Embutir** no pacote: instalação maior, mas funciona offline.
- **Baixar na primeira execução** (`playwright install chromium`): instalador menor.

Como os scrapers já tentam `httpx` primeiro e usam Playwright só como fallback, o Chromium pode ser opcional e baixado apenas quando necessário.

### Passo 8: Distribuição

- O repositório já tem `.github/workflows`. Crie um workflow que gere o build em **Windows, macOS e Linux**. O PyInstaller não faz cross-compile, então cada sistema precisa ser compilado no próprio sistema.
- Publique em **GitHub Releases**: os usuários baixam por lá, de graça e sem infraestrutura sua.

## 7. Estratégia recomendada

1. Fazer os passos 1 a 5 e validar que o app roda com `python main.py`, **sem Docker, Postgres ou Redis**.
2. Só então empacotar com PyInstaller. Se algo falhar, é bem mais fácil depurar fora do executável.
3. Testar o executável em uma **máquina limpa** (sem Python, Node ou Docker instalados).
4. Automatizar o build multiplataforma com GitHub Actions.
5. Publicar a primeira versão em GitHub Releases com instruções de download.

## 8. Pontos que serão perdidos

Ao sair da arquitetura de servidor para o modelo local, o projeto abre mão de:

| O que se perde | Impacto |
| --- | --- |
| **Histórico compartilhado** | Cada usuário constrói só o próprio histórico de preços; não há base única |
| **Controle central de atualizações** | Se Amazon ou Mercado Livre mudarem o HTML, os adapters quebram e todos ficam com a versão quebrada até baixarem outra |
| **Firecrawl embutido** | O fallback pago some ou depende da chave de cada usuário |
| **Persistência do cache Redis** | O cache vira em memória e se perde ao fechar o app |
| **Robustez do Celery** | Perde-se retentativas, filas persistentes e escalabilidade de workers |
| **Concorrência do PostgreSQL** | SQLite é mais simples e adequado para um usuário, mas não para muitos acessos simultâneos |
| **Reprodutibilidade do Docker** | O ambiente deixa de ser idêntico em todo lugar e passa a depender de cada sistema operacional |
| **Agendamento 24h** | A checagem a cada 6h só roda com o app aberto |
| **Visibilidade de uso** | Sem servidor, você não tem logs nem métricas centrais do que os usuários fazem |
| **Prisma ORM** | Perde-se o ORM tipado e as migrations dele; o acesso passa a ser SQL ou SQLAlchemy |

## 9. Riscos e desvantagens a considerar

- **Atualizações:** implemente uma checagem de versão via API do GitHub Releases ao abrir o app.
- **Antivírus e SmartScreen:** executáveis não assinados costumam receber alertas no Windows. Certificado de assinatura é pago; a alternativa é avisar os usuários na página de download.
- **Agendamento só com o app aberto:** para checagens em segundo plano, use ícone na bandeja do sistema ou inicialização junto com o sistema.
- **Tamanho do instalador:** o Chromium pesa centenas de MB.
- **Termos de uso das lojas:** scraping costuma ir contra os termos de Amazon e Mercado Livre. Distribuir para muitas pessoas aumenta a exposição, o que vale pesar se o projeto crescer.
- **Segredos:** nunca embuta chaves de API no executável, pois qualquer pessoa consegue extraí-las.

## 10. Conselhos

- Mantenha o contrato da API (`/monitor/add`, `/history/{id}`, `/search`, `/search/{id}`) para o frontend não precisar mudar.
- Aproveite que o `db_client.py` é o único ponto de acesso ao banco para fazer a troca ali.
- Deixe o Playwright e o Firecrawl como recursos opcionais.
- Use pasta de dados do usuário, não a pasta do executável.
- Faça o app escutar apenas em `127.0.0.1`.
- Não tente fazer tudo de uma vez: valide cada passo antes do próximo.

## 11. Alternativas

| Alternativa | Quando vale | Observação |
| --- | --- | --- |
| **Docker Compose com instruções** | Público técnico | Não serve para usuário comum |
| **Tauri ou Electron com Python como sidecar** | Experiência mais polida (janela própria, instalador `.msi`) | Bem mais trabalhoso; deixar para depois da versão simples |
| **Hospedar de verdade** | Se quiser histórico compartilhado ou contas | Autenticação e hospedagem voltam a ser necessárias |

## 12. Checklist de execução

- [ ] Reescrever `db_client.py` para SQLite
- [ ] Trocar Celery por threads/BackgroundTasks e APScheduler
- [ ] Trocar Redis por cache em memória
- [ ] Servir o frontend buildado pelo FastAPI
- [ ] Ajustar o frontend para URL relativa
- [ ] Criar `main.py` como ponto de entrada único
- [ ] Tornar Firecrawl e Playwright opcionais
- [ ] Validar com `python main.py` sem Docker
- [ ] Empacotar com PyInstaller (`--onedir`)
- [ ] Testar em máquina limpa
- [ ] Criar workflow de build multiplataforma no GitHub Actions
- [ ] Publicar em GitHub Releases
- [ ] Implementar checagem de nova versão

## 13. Próximo passo sugerido

Para ajudar na reescrita, envie o conteúdo de `execution/db_client.py` e `execution/worker_tasks.py`. A partir deles dá para montar o novo `db_client.py` em SQLite, o `main.py` e o workflow do GitHub Actions.
