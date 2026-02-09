# PromoZone 🛒

Coletor de promoções do Mercado Livre com pipeline completo: coleta → normalização → deduplicação → BigQuery.

Desenvolvido como protótipo funcional para demonstrar entrega fim-a-fim com qualidade de dados, rastreabilidade e operação mínima.

---

## 📋 Índice

- [Visão Geral](#visão-geral)
- [Arquitetura](#arquitetura)
- [Tecnologias](#tecnologias)
- [Estrutura do Projeto](#estrutura-do-projeto)
- [Configuração](#configuração)
- [Como Rodar Localmente](#como-rodar-localmente)
- [Como Fazer Deploy no Cloud Run](#como-fazer-deploy-no-cloud-run)
- [Endpoints da API](#endpoints-da-api)
- [Estratégia de Deduplicação](#estratégia-de-deduplicação)
- [Schema do BigQuery](#schema-do-bigquery)
- [Validação e Queries](#validação-e-queries)
- [Testes](#testes)
- [Trade-offs e Decisões](#trade-offs-e-decisões)

---

## 🎯 Visão Geral

O **PromoZone** coleta promoções do Mercado Livre através da API pública de busca, normaliza os dados para um modelo consistente, aplica deduplicação em duas camadas (memória + BigQuery) e persiste no BigQuery com rastreabilidade completa.

### Funcionalidades

- ✅ Coleta de 1-3 fontes configuráveis (queries de busca)
- ✅ Normalização para modelo único (`Promotion`)
- ✅ Deduplicação defensável (staging + MERGE no BigQuery)
- ✅ Logs estruturados e tratamento de erros
- ✅ Rastreabilidade (`execution_id`, `dedupe_key`, timestamps)
- ✅ API REST com `/health` e `/run`
- ✅ Pronto para Cloud Run (containerizado)
- ✅ Testes automatizados (16 testes unitários)

---

## 🏗️ Arquitetura

```
┌─────────────┐
│ Cloud       │
│ Scheduler   │ (opcional)
└──────┬──────┘
       │ POST /run
       ▼
┌─────────────────────────────────────────┐
│         Cloud Run (FastAPI)             │
│  ┌───────────────────────────────────┐  │
│  │  Pipeline Orchestrator            │  │
│  │  1. Coleta (ML API)               │  │
│  │  2. Parse & Normalização          │  │
│  │  3. Dedup em memória              │  │
│  │  4. Staging → MERGE → BigQuery    │  │
│  └───────────────────────────────────┘  │
└─────────────────┬───────────────────────┘
                  │
                  ▼
         ┌────────────────┐
         │   BigQuery     │
         │  - staging     │
         │  - promotions  │
         └────────────────┘
```

### Fluxo de Dados

1. **Coleta**: `MercadoLivreClient` faz requests à API pública com rate limiting e retry/backoff
2. **Parse**: `mercadolivre_parser` transforma JSON cru em objetos `Promotion`
3. **Enriquecimento**: adiciona `execution_id`, `dedupe_key`, `collected_at`
4. **Dedup em memória**: remove duplicatas óbvias na mesma execução
5. **Staging**: carrega dados na tabela `promotions_staging` (WRITE_TRUNCATE)
6. **MERGE**: insere apenas registros novos (baseado em `dedupe_key`) na tabela final

---

## 🛠️ Tecnologias

- **Python 3.11**
- **FastAPI** — API REST
- **Uvicorn** — ASGI server
- **Pydantic** — validação e settings
- **httpx** — HTTP client assíncrono
- **tenacity** — retry com backoff exponencial
- **google-cloud-bigquery** — cliente BigQuery
- **pytest** — testes automatizados
- **Docker** — containerização para Cloud Run

---

## 📁 Estrutura do Projeto

```
task-promozone/
├── .env.example              # Template de variáveis de ambiente
├── .gitignore
├── Dockerfile                # Imagem para Cloud Run
├── requirements.txt
├── README.md
├── context.md                # Especificação do desafio
├── queries/
│   └── validation.sql        # Query de validação (últimas 24h)
├── src/
│   └── promozone/
│       ├── config.py         # Configuração via env vars
│       ├── logging_config.py # Setup de logging
│       ├── api/
│       │   └── main.py       # FastAPI app (/health, /run)
│       ├── collectors/
│       │   ├── mercadolivre_client.py   # HTTP client + retry
│       │   └── mercadolivre_parser.py   # Parser JSON → Promotion
│       ├── models/
│       │   └── promotion.py  # Modelo Pydantic normalizado
│       └── services/
│           ├── dedup.py                 # Lógica de deduplicação
│           ├── bigquery_repository.py   # Staging + MERGE
│           └── pipeline.py              # Orquestrador
└── tests/
    ├── test_dedup.py
    ├── test_mercadolivre_parser.py
    ├── test_pipeline.py
    └── test_promotion_model.py
```

---

## ⚙️ Configuração

### 1. Pré-requisitos

- Python 3.11+
- Conta GCP com BigQuery habilitado
- Service Account com permissões:
  - `BigQuery Data Editor`
  - `BigQuery Job User`

### 2. Variáveis de Ambiente

Copie `.env.example` para `.env` e preencha:

```bash
cp .env.example .env
```

**Variáveis obrigatórias:**

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `GOOGLE_APPLICATION_CREDENTIALS` | Caminho para chave JSON (local) | `./sua-chave.json` |
| `BQ_PROJECT_ID` | ID do projeto GCP | `tensile-impact-486818-g9` |
| `BQ_DATASET` | Dataset do BigQuery | `promozone` |
| `BQ_TABLE` | Tabela final | `promotions` |
| `BQ_STAGING_TABLE` | Tabela de staging | `promotions_staging` |
| `ML_SOURCES` | JSON array com fontes | Ver exemplo abaixo |

**Exemplo de `ML_SOURCES`:**

```json
[
  {"query": "smartphone", "source": "busca_smartphone"},
  {"query": "notebook", "source": "busca_notebook"},
  {"query": "fone de ouvido", "source": "busca_fone"}
]
```

**Variáveis opcionais:**

- `ML_MAX_ITEMS_PER_SOURCE` (padrão: 50)
- `ML_REQUEST_DELAY_SECONDS` (padrão: 1.0)
- `LOG_LEVEL` (padrão: INFO)
- `ENVIRONMENT` (padrão: local)
- `PORT` (padrão: 8080)

---

## 🚀 Como Rodar Localmente

### 1. Clonar o repositório

```bash
git clone <seu-repo>
cd task-promozone
```

### 2. Criar ambiente virtual e instalar dependências

```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# ou
.\.venv\Scripts\activate   # Windows

pip install -r requirements.txt
```

### 3. Configurar credenciais

- Coloque sua chave de serviço GCP no diretório raiz (ex: `chave.json`)
- Configure o `.env` com `GOOGLE_APPLICATION_CREDENTIALS=./chave.json`

### 4. Rodar o servidor

**Opção 1: Script helper (recomendado)**
```bash
python run_local.py
```

**Opção 2: Uvicorn direto**
```bash
# Linux/Mac
export PYTHONPATH=src
uvicorn promozone.api.main:app --reload --port 8080

# Windows PowerShell
cd src
python -m uvicorn promozone.api.main:app --reload --port 8080
```

### 5. Testar os endpoints

**Health check:**
```bash
# Linux/Mac
curl http://localhost:8080/health

# Windows PowerShell
Invoke-WebRequest -Uri http://localhost:8080/health -UseBasicParsing | Select-Object -ExpandProperty Content
```

**Executar pipeline:**
```bash
# Linux/Mac
curl -X POST http://localhost:8080/run

# Windows PowerShell
Invoke-WebRequest -Uri http://localhost:8080/run -Method POST -UseBasicParsing | Select-Object -ExpandProperty Content
```

Resposta esperada:
```json
{
  "execution_id": "uuid-aqui",
  "status": "success",
  "sources_processed": 3,
  "total_collected": 150,
  "total_after_dedup": 145,
  "total_loaded": 145,
  "errors": [],
  "duration_seconds": 12.34
}
```

---

## ☁️ Como Fazer Deploy no Cloud Run

### 1. Configurar projeto GCP

```bash
gcloud config set project tensile-impact-486818-g9
gcloud auth configure-docker
```

### 2. Build da imagem Docker

```bash
docker build -t gcr.io/tensile-impact-486818-g9/promozone:latest .
docker push gcr.io/tensile-impact-486818-g9/promozone:latest
```

### 3. Deploy no Cloud Run

```bash
gcloud run deploy promozone \
  --image gcr.io/tensile-impact-486818-g9/promozone:latest \
  --platform managed \
  --region us-central1 \
  --allow-unauthenticated \
  --set-env-vars "BQ_PROJECT_ID=tensile-impact-486818-g9,BQ_DATASET=promozone,BQ_TABLE=promotions,BQ_STAGING_TABLE=promotions_staging,ML_SOURCES=[{\"query\":\"smartphone\",\"source\":\"busca_smartphone\"}],LOG_LEVEL=INFO"
```

**Nota:** No Cloud Run, **não** use `GOOGLE_APPLICATION_CREDENTIALS`. O serviço usa automaticamente a Service Account associada ao Cloud Run.

### 4. (Opcional) Agendar com Cloud Scheduler

```bash
gcloud scheduler jobs create http promozone-daily \
  --schedule="0 9 * * *" \
  --uri="https://promozone-xxx.run.app/run" \
  --http-method=POST \
  --location=us-central1
```

---

## 🔌 Endpoints da API

### `GET /health`

Health check simples.

**Resposta:**
```json
{"status": "ok"}
```

### `POST /run`

Dispara execução completa do pipeline.

**Resposta (sucesso):**
```json
{
  "execution_id": "abc-123",
  "status": "success",
  "sources_processed": 3,
  "total_collected": 150,
  "total_after_dedup": 145,
  "total_loaded": 145,
  "errors": [],
  "duration_seconds": 12.34
}
```

**Resposta (erro parcial):**
```json
{
  "execution_id": "abc-123",
  "status": "partial_error",
  "sources_processed": 2,
  "total_collected": 100,
  "total_after_dedup": 95,
  "total_loaded": 95,
  "errors": ["Erro na fonte busca_fone: timeout"],
  "duration_seconds": 15.67
}
```

---

## 🔄 Estratégia de Deduplicação

### Camada 1: Deduplicação em Memória

Remove duplicatas óbvias **dentro da mesma execução** antes de gravar no BigQuery.

**Chave:** `dedupe_key = SHA256(marketplace:item_id:price)`

### Camada 2: MERGE no BigQuery

Pipeline de staging → final:

1. Carrega dados na tabela `promotions_staging` (WRITE_TRUNCATE)
2. Executa `MERGE` na tabela final usando `dedupe_key` como chave
3. Insere apenas registros que **não existem** na tabela final

**SQL do MERGE:**
```sql
MERGE `project.dataset.promotions` AS target
USING `project.dataset.promotions_staging` AS source
ON target.dedupe_key = source.dedupe_key
WHEN NOT MATCHED THEN INSERT (...)
```

### Por que `marketplace:item_id:price`?

- **Permite rastrear mudanças de preço** — mesmo item com preço diferente gera novo registro
- **Evita duplicatas exatas** — mesmo item + mesmo preço = mesma chave
- **Determinístico** — sempre gera a mesma chave para os mesmos dados

---

## 📊 Schema do BigQuery

```sql
CREATE TABLE `project.dataset.promotions` (
  marketplace STRING NOT NULL,
  item_id STRING NOT NULL,
  url STRING,
  title STRING,
  price NUMERIC,
  original_price NUMERIC,
  discount_percent FLOAT64,
  seller STRING,
  image_url STRING,
  source STRING,
  dedupe_key STRING NOT NULL,
  execution_id STRING,
  collected_at TIMESTAMP,
  inserted_at TIMESTAMP
);
```

**Campos de rastreabilidade:**

- `dedupe_key` — chave de deduplicação (SHA256)
- `execution_id` — UUID da execução que coletou o item
- `collected_at` — timestamp da coleta
- `inserted_at` — timestamp de inserção no BigQuery

---

## 🔍 Validação e Queries

### Query de Validação (últimas 24h)

Arquivo: `queries/validation.sql`

```sql
SELECT
    source,
    COUNT(*) AS total_items,
    COUNT(DISTINCT item_id) AS unique_items,
    ROUND(AVG(price), 2) AS avg_price,
    ROUND(MIN(price), 2) AS min_price,
    ROUND(MAX(price), 2) AS max_price,
    COUNTIF(discount_percent IS NOT NULL) AS items_with_discount,
    ROUND(AVG(discount_percent), 2) AS avg_discount_percent,
    MIN(collected_at) AS first_collected,
    MAX(collected_at) AS last_collected
FROM
    `{project_id}.promozone.promotions`
WHERE
    collected_at >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 24 HOUR)
GROUP BY
    source
ORDER BY
    total_items DESC;
```

**Como executar:**

```bash
bq query --use_legacy_sql=false < queries/validation.sql
```

---

## 🧪 Testes

### Rodar todos os testes

```bash
export PYTHONPATH=src  # Linux/Mac
$env:PYTHONPATH="src"  # Windows

pytest tests/ -v
```

### Cobertura

- ✅ `test_promotion_model.py` — modelo Pydantic (3 testes)
- ✅ `test_mercadolivre_parser.py` — parser (6 testes)
- ✅ `test_dedup.py` — deduplicação (5 testes)
- ✅ `test_pipeline.py` — pipeline com mocks (2 testes)

**Total: 16 testes passando**

---

## ⚖️ Trade-offs e Decisões

### 1. API Pública vs Scraping

**Escolha:** API pública do Mercado Livre (`/sites/MLB/search`)

**Motivo:**
- ✅ Mais estável e confiável
- ✅ Respeita termos de uso
- ✅ Não requer parsing de HTML
- ❌ Limitado a 50 itens por página (paginação necessária)

### 2. Staging + MERGE vs INSERT direto

**Escolha:** Staging table + MERGE

**Motivo:**
- ✅ Deduplicação atômica no BigQuery
- ✅ Permite validação antes do MERGE
- ✅ Facilita rollback (staging é truncada a cada execução)
- ❌ Mais complexo que INSERT direto

### 3. FastAPI vs Flask

**Escolha:** FastAPI

**Motivo:**
- ✅ Validação automática com Pydantic
- ✅ Documentação OpenAPI automática (`/docs`)
- ✅ Async-ready (futuro)
- ✅ Mais moderno e performático

### 4. Dedupe key: `marketplace:item_id:price`

**Escolha:** Incluir `price` na chave

**Motivo:**
- ✅ Permite rastrear histórico de preços
- ✅ Detecta mudanças de promoção
- ❌ Gera mais registros (trade-off aceitável para análise)

**Alternativa considerada:** `marketplace:item_id` (ignoraria mudanças de preço)

### 5. Cloud Run vs Compute Engine

**Escolha:** Cloud Run

**Motivo:**
- ✅ Serverless (escala automático, paga por uso)
- ✅ Deploy simplificado (container)
- ✅ Integração nativa com Cloud Scheduler
- ✅ Não requer gerenciamento de VMs

### 6. Retry com Tenacity

**Escolha:** Retry automático com backoff exponencial

**Motivo:**
- ✅ Resiliência a falhas transitórias (timeouts, 5xx)
- ✅ Backoff exponencial evita sobrecarga
- ✅ Configurável (3 tentativas, 2-10s)

---

## 📝 Logs

Exemplo de log estruturado:

```
2026-02-08T18:30:00 | INFO     | promozone.api.main | PromoZone iniciado | env=local
2026-02-08T18:30:05 | INFO     | promozone.services.pipeline | === Pipeline iniciado | execution_id=abc-123 ===
2026-02-08T18:30:06 | INFO     | promozone.collectors.mercadolivre_client | Buscando query='smartphone' offset=0 limit=50
2026-02-08T18:30:08 | INFO     | promozone.collectors.mercadolivre_parser | Parseados 50/50 itens da fonte=busca_smartphone
2026-02-08T18:30:09 | INFO     | promozone.services.dedup | Dedup em memória: 2 duplicatas removidas de 150 itens
2026-02-08T18:30:12 | INFO     | promozone.services.bigquery_repository | Staging: 148 linhas carregadas
2026-02-08T18:30:14 | INFO     | promozone.services.bigquery_repository | MERGE concluído: 145 linhas afetadas
2026-02-08T18:30:14 | INFO     | promozone.services.pipeline | === Pipeline finalizado | status=success | coletados=150 | dedup=148 | gravados=148 | duração=9.2s ===
```

---

## 🔒 Segurança

- ✅ Chaves de serviço **não versionadas** (`.gitignore`)
- ✅ Variáveis de ambiente para configuração sensível
- ✅ No Cloud Run: usa Service Account do serviço (sem chave JSON)
- ✅ Rate limiting para respeitar limites da API

---

## 🚧 Melhorias Futuras

- [ ] Cache de resultados (Redis/Memorystore)
- [ ] Métricas com Cloud Monitoring
- [ ] Alertas para falhas (Cloud Alerting)
- [ ] Dashboard com Looker Studio
- [ ] Suporte a múltiplos marketplaces
- [ ] Webhook para notificações de novas promoções
- [ ] Testes de integração com BigQuery real

---

## 📄 Licença

MIT

---

## 👤 Autor

Desenvolvido como desafio técnico para demonstrar habilidades em:
- Engenharia de dados (coleta, normalização, deduplicação)
- Cloud GCP (BigQuery, Cloud Run)
- Python (FastAPI, Pydantic, pytest)
- DevOps (Docker, CI/CD ready)

