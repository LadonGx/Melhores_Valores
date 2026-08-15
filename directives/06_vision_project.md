# 🎯 Visão do Projeto: Rastreador de Preços Inteligente (Price Tracker)

_Status:_ Fase 1 (MVP) - Desenvolvimento Ativo
_Ambiente de Desenvolvimento:_ Google Antigravity (Agent-First IDE)

---

## Parte 1: Objetivo e Visão de Negócio 📊

### 💡 A Ideia Central

O projeto é uma plataforma automatizada de rastreamento de preços de e-commerce (Amazon, Mercado Livre). O objetivo é permitir que o usuário insira o link de um produto e o sistema, de forma autônoma e em segundo plano, monitore o preço desse item ao longo do tempo.

### 🎯 O Problema que Resolvemos

Consumidores frequentemente sofrem com falsas promoções (a famosa "metade do dobro") ou perdem quedas de preços relâmpago. Acompanhar preços manualmente em diferentes marketplaces é inviável e frustrante.

### 🚀 Proposta de Valor (Core Features)

1. _Cadastro Simples:_ O usuário apenas cola a URL do produto. O sistema deduz a loja e extrai os metadados (nome, imagem).
2. _Histórico Transparente:_ Exibição clara do preço atual, do menor preço histórico e da média de valores.
3. _Monitoramento Invisível:_ O sistema checa os preços periodicamente sem que o usuário precise estar com o site aberto.
4. _Resiliência Anti-Bot:_ O rastreador utiliza inteligência e infraestrutura em nuvem para contornar proteções complexas de sites como Amazon e Mercado Livre, garantindo dados precisos.

### 🔮 Visão de Futuro e Monetização (Roadmap)

- _Alertas Inteligentes:_ Notificações automáticas via E-mail, Push ou WhatsApp quando um produto atingir o "Preço Alvo" definido pelo usuário.
- _Normalização com IA (Semantic Matching):_ Identificar que "iPhone 15 128GB" na Amazon é o mesmo produto que "Apple iPhone 15 128 GB Preto" no Mercado Livre, unificando o gráfico de preços.
- _Monetização:_ Geração de receita primária através de links de afiliados embutidos no redirecionamento da compra e, secundariamente, planos premium para rastreamento em tempo real de produtos de altíssima demanda.

---

## Parte 2: Arquitetura e Visão Técnica 🛠️

Este projeto foi desenhado para ser resiliente, altamente escalável e otimizado para não desperdiçar recursos (computacionais e financeiros).

### 🏗️ Arquitetura Orientada a Agentes (3-Layer Architecture)

Para garantir que a IA gere código confiável, separamos as responsabilidades:

1. _Camada de Diretivas (/directives):_ Regras de negócio em Markdown. Os LLMs leem isso antes de agir.
2. _Camada de Orquestração:_ A IA atua apenas roteando intenções e chamando os scripts corretos, sem tentar processar a lógica complexa diretamente.
3. _Camada de Execução (/execution):_ Scripts Python determinísticos, estritos e testáveis.

### 💻 Stack Tecnológico

- _Linguagem:_ Python 3.12+ (Otimizado para manipulação de dados e automação).
- _Web Server / API:_ FastAPI (Alta performance, tipagem estrita e chamadas assíncronas).
- _Banco de Dados:_ PostgreSQL, gerenciado de forma segura e moderna através do Prisma ORM (prisma-client-python).
- _Fila de Tarefas & Agendamento:_ Celery (Workers para scraping em background) e Celery Beat (Scheduler para varreduras periódicas).
- _Message Broker & Cache:_ Redis (Gerencia a fila do Celery e atua como cache temporário para evitar requests duplicados na mesma URL).
- _Extração de Dados (Scraping):_ Firecrawl API (Delega o custo computacional de renderizar JavaScript, rotacionar proxies e burlar anti-bots para um serviço externo via LLM Extraction).
- _Infraestrutura Local:_ Docker Compose (PostgreSQL e Redis rodando em containers para isolamento perfeito).

### 🔄 Fluxo de Dados (Data Flow)

1. _Input:_ FastAPI recebe a requisição POST com a URL do produto.
2. _Cache Check:_ O sistema verifica o Redis (cache_manager.py). Se o preço foi atualizado nas últimas 2 horas, retorna do cache e encerra.
3. _Task Queue:_ Se não houver cache, o FastAPI despacha uma tarefa assíncrona para o Celery (worker_tasks.py) e responde ao usuário instantaneamente ("Processando").
4. _Scraping:_ O Worker envia a URL para a API do Firecrawl (firecrawl_api.py), que lida com a navegação pesada.
5. _Adapters Pattern:_ O JSON sujo retornado pelo Firecrawl passa pelo Adapter específico da loja (ex: /adapters/amazon.py) para higienização rigorosa dos tipos de dados.
6. _Persistência:_ O preço limpo é salvo no PostgreSQL via Prisma (db_client.py) e uma cópia atualizada é gravada no Redis Cache.

### 🛡️ Princípios de Design e Riscos Mitigados

- _Defesa contra Over-Scraping (Custos):_ A regra "Cache-First" é absoluta. O Firecrawl consome créditos; portanto, o Redis atua como nosso escudo financeiro.
- _Design Pattern de Adapters:_ Sites mudam o HTML constantemente. Se a Amazon mudar amanhã, apenas o arquivo amazon.py quebra, o resto do ecossistema permanece intacto.
- _Desacoplamento:_ O Web Server nunca espera o Scraping terminar. Isso previne timeouts e garante que a interface do usuário seja sempre fluida
