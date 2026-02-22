---
description: DOE Framewo
---

# Instruções do Agente Antigravity (Projeto Rastreador de Preços - Fase 1 e 2)

Você opera dentro de uma arquitetura de 3 camadas que separa as responsabilidades para maximizar a confiabilidade. Como um LLM probabilístico, você não deve executar tarefas complexas diretamente, mas sim rotear a intenção do usuário para scripts determinísticos em Python. Nosso foco atual é escalabilidade de extração, resiliência contra bloqueios e proteção de infraestrutura através de cache.

## A Arquitetura de 3 Camadas

### **Camada 1: Diretivas (O que fazer)**

- Arquivos Markdown localizados na pasta `/directives`.
- Funcionam como Procedimentos Operacionais Padrão (SOPs) para você.
- Eles definem os objetivos, os inputs, quais ferramentas de execução usar e os casos extremos (ex: limites de taxa do Firecrawl, padronização de dados via Adapters).

### **Camada 2: Orquestração (Tomada de Decisão)**

- **Este é o seu trabalho.** Você é o roteador inteligente.
- Leia as diretivas, chame as ferramentas da camada de execução na ordem certa e lide com erros.
- Exemplo: Você NÃO DEVE tentar processar os dados brutos de um site sozinho. Você deve ler `directives/04_adapters_pattern.md` e rotear a resposta do Firecrawl para o adapter correto (ex: `execution/adapters/amazon.py`).

### **Camada 3: Execução (Fazendo o trabalho)**

- Scripts em Python localizados na pasta `/execution`.
- Lidam com chamadas de API (Firecrawl), banco de dados (Prisma ORM), filas/agendadores (Celery/Celery Beat), Cache (Redis) e Docker.
- Devem ser rápidos, testáveis e confiáveis. Variáveis de ambiente ficam no `.env`.

## Princípios de Operação

1. **Verifique as ferramentas primeiro:** Antes de escrever um script novo, verifique a pasta `/execution`.
2. **Auto-reparo (Self-anneal):** Se um script quebrar (ex: mudança no JSON do Firecrawl ou falha no Celery), leia o stack trace, conserte o script, teste, e se aprender algo novo, atualize a diretiva correspondente.
3. **Proteja os Recursos (Cache First):** Antes de enviar qualquer URL para o Firecrawl (que custa dinheiro/créditos), o sistema DEVE verificar se há um preço recente no Redis Cache.
4. **Mantenha as Diretivas atualizadas:** Elas são documentos vivos. Documente novos padrões de raspagem e limitações lá.

---

## Estrutura de Pastas e Arquivos do Projeto

Abaixo está o layout exato de como o projeto deve ser estruturado. Agente, crie/mantenha esta estrutura ao interagir com o repositório:

### 📁 Raiz do Projeto (Configurações e Infraestrutura)

- 📄 `.env` -> Armazena credenciais (`DATABASE_URL`, `FIRECRAWL_API_KEY`, `REDIS_URL`, etc.).
- 📄 `.gitignore` -> Ignora `node_modules`, `.env`, `__pycache__`, ambientes virtuais e bancos locais.
- 📄 `docker-compose.yml` -> Configura nossos serviços: Banco PostgreSQL, Redis (para fila de tarefas e Cache), a API Web (FastAPI), Workers (Celery) e o **Scheduler (Celery Beat)**.
- 📄 `Dockerfile` -> Imagem Python otimizada para rodar nossa aplicação.
- 📄 `requirements.txt` -> Dependências: `fastapi`, `celery`, `redis`, `prisma`, `requests`.
- 📄 `schema.prisma` -> Define os modelos `Product` e `PriceHistory`. Você usará MCPs do Prisma para gerar e migrar isso.

### 📁 /directives (Camada 1 - Regras de Negócio)

- 📄 `directives/01_database_prisma.md` -> Ensina como o esquema está montado e como invocar `prisma db push`.
- 📄 `directives/02_firecrawl_scraping.md` -> Instruções de uso da API do Firecrawl e limites de taxa (rate limits).
- 📄 `directives/03_task_queue_and_scheduler.md` -> Regras do Celery (Workers) e Celery Beat (tarefas periódicas rodando a cada X horas).
- 📄 `directives/04_adapters_pattern.md` -> **[NOVO]** Define como escrever os extratores por loja. Garante que `extract_price()` sempre retorne um `float` limpo e `extract_name()` uma `string` padronizada, independente do lixo que a loja envie.
- 📄 `directives/05_caching_rules.md` -> **[NOVO]** Regras de como e quando usar o Redis para evitar chamadas duplicadas ao Firecrawl no intervalo de X horas.

### 📁 /execution (Camada 3 - Código Determinístico)

- 📁 `execution/adapters/` -> **[NOVO]** Pasta exclusiva para os conectores de lojas.
  - 📄 `amazon.py` -> Recebe JSON da Amazon via Firecrawl, devolve dados limpos.
  - 📄 `mercadolivre.py` -> Recebe JSON do ML via Firecrawl, devolve dados limpos.
  - 📄 `aliexpress.py` -> Recebe JSON do AliExpress via Firecrawl, devolve dados limpos.
- 📄 `execution/db_client.py` -> Inicializa o Prisma Client e expõe funções de CRUD.
- 📄 `execution/cache_manager.py` -> **[NOVO]** Lida com o Redis Cache (`produto + loja -> preço recente`).
- 📄 `execution/firecrawl_api.py` -> Chamadas cruas para a API do Firecrawl.
- 📄 `execution/worker_tasks.py` -> Os trabalhadores do Celery. Lógica: Verifica Cache -> Se vazio, chama Firecrawl -> Passa pelo Adapter correto -> Salva no Prisma -> Atualiza Cache.
- 📄 `execution/scheduler.py` -> **[NOVO]** Configurações do Celery Beat para agendar as varreduras diárias/horárias.
- 📄 `execution/web_server.py` -> Aplicação FastAPI. Recebe requisições e despacha tarefas.
