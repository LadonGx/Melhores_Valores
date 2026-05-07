# Resumo do Projeto: Melhores Valores

Este documento fornece uma visão geral completa do projeto **Melhores Valores** para facilitar o entendimento por outras IAs ou desenvolvedores.

## 📌 Visão Geral
O **Melhores Valores** é um rastreador de preços e API de busca para plataformas de e-commerce brasileiras (Amazon BR, Mercado Livre, AliExpress). O sistema monitora preços automaticamente, mantém um histórico e permite buscas em tempo real, utilizando uma arquitetura resiliente de web scraping.

---

## 🛠️ Stack Tecnológica
- **Linguagem Principal**: Python 3.11+
- **Framework Web**: FastAPI (API REST)
- **Banco de Dados**: PostgreSQL 15 (via Prisma ORM - Interface Síncrona)
- **Cache e Mensageria**: Redis 7
- **Fila de Tarefas e Agendamento**: Celery + Celery Beat
- **Web Scraping**: 
    - `httpx` (requisições rápidas)
    - `Playwright/Chromium` (renderização de JS)
    - `Firecrawl API` (IA-powered scraping, como último recurso)
- **Infraestrutura**: Docker & Docker Compose

---

## 🏗️ Arquitetura do Projeto (3 Camadas)
O projeto segue uma arquitetura rigorosa de 3 camadas para separar regras de negócio, coordenação e execução técnica:

### 1. Camada de Diretivas (`/directives`)
Contém Procedimentos Operacionais Padrão (SOPs) em Markdown que definem o comportamento esperado do sistema:
- Regras de cache, padrões de adapters, estratégias de scraping e esquemas de banco de dados.

### 2. Camada de Orquestração (`execution/*_orchestrator.py`)
Lógica de tomada de decisão que coordena o fluxo entre as ferramentas:
- Decide qual nível do "Cascading Scraping" usar.
- Agrega resultados de buscas multi-loja.

### 3. Camada de Execução (`/execution`)
Módulos determinísticos e focados que realizam o trabalho pesado:
- **Adapters**: Parsers específicos por loja (`amazon.py`, `mercadolivre.py`, etc.).
- **Scrapers**: Implementações de busca de HTML (httpx, Playwright).
- **Client DB**: Interface única de acesso ao banco (Prisma) (`db_client.py`).
- **Cache**: Gerenciamento de TTL e chaves no Redis (`cache_manager.py`).

---

## 📂 Estrutura de Pastas
```text
/
├── .agents/workflows/      # Fluxos de trabalho e arquitetura detalhada
├── directives/             # Regras de negócio e SOPs (Markdown)
├── execution/              # Código fonte Python
│   ├── adapters/           # Parsers de HTML por loja
│   ├── scrapers/           # Ferramentas de requisição (httpx, playwright)
│   ├── search_scrapers/    # Scrapers específicos para páginas de busca
│   ├── web_server.py       # Endpoints FastAPI
│   ├── worker_tasks.py     # Definições de tarefas Celery
│   ├── db_client.py        # Único ponto de acesso ao banco (Prisma)
│   ├── cache_manager.py    # Lógica de cache Redis
│   ├── *_orchestrator.py   # Lógica de coordenação (Search/Scraping)
├── schema.prisma           # Definição do esquema do banco de dados
├── docker-compose.yml      # Orquestração de serviços (API, Worker, Beat, DB, Redis)
├── Dockerfile              # Configuração da imagem Python
└── requirements.txt        # Dependências do projeto
```

---

## 🚀 Principais Funcionalidades

### 1. Monitoramento de Preços (Cascading Scraping)
Ao adicionar uma URL, o sistema tenta extrair o preço seguindo esta ordem de resiliência:
1. **Cache**: Verifica no Redis se o preço foi obtido nas últimas 2 horas.
2. **Nível 1 (httpx)**: Rápido e gratuito.
3. **Nível 2 (Playwright)**: Lida com sites que exigem JavaScript.
4. **Nível 3 (Firecrawl)**: API paga, usada apenas se os anteriores falharem.

### 2. Busca de Produtos Multi-Loja
Permite buscar um termo (ex: "iPhone 15") e retorna resultados agregados da Amazon e Mercado Livre, ordenados pelo menor preço.

### 3. Agendamento Automático
O **Celery Beat** dispara uma tarefa a cada 6 horas (`schedule_all_products`) para atualizar os preços de todos os produtos cadastrados no banco de dados, garantindo que o histórico de preços esteja sempre atualizado.

---

## 🔐 Modelos de Dados (Prisma)
- **Product**: Armazena informações básicas do produto (nome, loja, URL, imagem).
- **PriceHistory**: Registra cada variação de preço capturada com timestamp.
- **SearchResult**: Cache temporário de buscas realizadas pelos usuários.

---

## 🚦 Regras Críticas de Desenvolvimento
- **Acesso ao Banco**: APENAS via `db_client.py`. Nunca chame o Prisma Client em outros arquivos.
- **Sincronicidade**: O Prisma está configurado como síncrono; não use `async/await` em chamadas de banco.
- **Resiliência**: Sempre priorize o cache e os scrapers gratuitos antes de escalar para o Firecrawl.
- **Isolamento**: Cada loja deve ter seu próprio Adapter para facilitar a manutenção em caso de mudança de layout no site.
