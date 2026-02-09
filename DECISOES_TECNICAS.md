# Decisões Técnicas — PromoZone

Documento que explica a stack escolhida, as decisões de arquitetura e o porquê de cada uma delas no contexto do desafio: construir um coletor de promoções do Mercado Livre com pipeline completo até o BigQuery, rodando no Google Cloud Run, em 72 horas.

---

## Stack

| Camada | Tecnologia | Versão |
|--------|-----------|--------|
| Linguagem | Python | 3.11 |
| API | FastAPI + Uvicorn | 0.115 / 0.34 |
| Validação / Config | Pydantic v2 + pydantic-settings | 2.10 / 2.7 |
| HTTP Client | httpx | 0.28 |
| Retry | tenacity | 9.0 |
| Data Warehouse | Google BigQuery | SDK 3.27 |
| Container | Docker (python:3.11-slim) | — |
| Runtime | Google Cloud Run | — |
| Testes | pytest | 9.0 |

---

## 1. Por que Python 3.11?

- É a versão estável mais recente com suporte LTS amplamente adotada em produção.
- Tem melhorias significativas de performance (10-60% mais rápido que 3.10 em vários benchmarks).
- Mensagens de erro mais claras (tracebacks aprimorados), o que acelera debug durante o prazo curto.
- Compatibilidade total com todas as bibliotecas usadas (FastAPI, Pydantic v2, google-cloud-bigquery).

## 2. Por que FastAPI (e não Flask)?

- **Pydantic nativo**: validação de dados e configuração via `pydantic-settings` se integram naturalmente. O modelo `Promotion` e o `Settings` usam Pydantic, então a stack fica coesa.
- **Documentação automática**: `/docs` (Swagger UI) é gerado sem esforço — útil para demonstrar o projeto.
- **Tipagem forte**: type hints são obrigatórios, o que reduz bugs em um prazo apertado.
- **Async-ready**: embora o pipeline atual seja síncrono, a migração para async é trivial se necessário.
- **Performance**: Uvicorn + FastAPI é significativamente mais rápido que Flask + Gunicorn para I/O bound.

## 3. Por que httpx (e não requests)?

- **Interface moderna**: API similar ao `requests`, mas com suporte nativo a async (futuro).
- **HTTP/2**: suporte embutido, útil para conexões com o Mercado Livre.
- **Timeout granular**: controle fino de connect/read/write timeouts.
- **Integração com tenacity**: o decorator `@retry` funciona perfeitamente com httpx.
- **Menos dependências**: httpx é mais leve que requests + urllib3.

## 4. Por que tenacity para retry?

- **Backoff exponencial configurável**: `wait_exponential(multiplier=1, min=2, max=10)` evita sobrecarregar o servidor alvo.
- **Retry seletivo**: só retenta em `TransportError` (rede) e `HTTPStatusError` (5xx), não em 4xx.
- **Decorador simples**: `@retry(...)` sobre o método, sem poluir a lógica de negócio.
- **Alternativa considerada**: retry manual com `time.sleep` — descartado por ser mais verboso e propenso a erros.

## 5. Por que Pydantic v2 + pydantic-settings?

- **Modelo `Promotion`**: validação automática de tipos, valores default, serialização para BigQuery (`to_bq_row()`).
- **`Settings(BaseSettings)`**: lê `.env` e variáveis de ambiente automaticamente, com validação de tipos.
- **`extra="ignore"`**: ignora variáveis de ambiente não mapeadas, evitando erros em ambientes com muitas env vars (Cloud Run).
- **`field_validator`**: validação customizada do `ml_sources` (JSON array) no momento do carregamento.

## 6. Por que Web Scraping ao invés da API REST?

Esta foi a decisão mais importante e não-óbvia do projeto.

**Tentativa inicial**: usar a API pública do Mercado Livre (`api.mercadolibre.com/sites/MLB/search`), que não requer autenticação.

**Problema encontrado**: a API retorna **403 Forbidden** para todas as queries, mesmo com headers de navegador, diferentes User-Agents e delays entre requests. O bloqueio é por IP/região e não há como contornar sem um access token OAuth2 (que exige registro de aplicação no ML Developers).

**Solução implementada**: `MercadoLivreScraperClient` — scraper que extrai dados do HTML renderizado pelo servidor (SSR) do Mercado Livre.

**Como funciona**:
1. Faz GET em `https://lista.mercadolivre.com.br/{query}` (mesma URL que o navegador acessa).
2. O HTML contém um objeto JSON embutido em `<script>` tags: `_n.ctx.r = {...}`.
3. Esse JSON contém todos os dados dos produtos em estrutura "polycard" (título, preço, vendedor, imagem).
4. O scraper extrai esse JSON via regex, parseia os polycards e converte para o mesmo formato que a API retornaria.

**Por que essa abordagem**:
- ✅ Retorna dados reais e completos (50 itens por página).
- ✅ Mantém a mesma interface (`search(query) -> List[Dict]`) — o parser existente funciona sem alteração.
- ✅ Respeita rate limiting (delay configurável entre requests).
- ✅ O cliente original da API (`mercadolivre_client.py`) foi mantido no código para uso futuro caso a API volte a funcionar.
- ❌ Mais frágil que a API (mudanças no HTML podem quebrar o scraper).

## 7. Por que BigQuery com Staging + MERGE?

**Alternativas consideradas**:
- **INSERT direto**: simples, mas não garante deduplicação entre execuções.
- **DELETE + INSERT**: funciona, mas não é atômico e pode perder dados em caso de falha.
- **MERGE (escolhido)**: atômico, insere apenas registros novos baseado na `dedupe_key`.

**Fluxo**:
1. Carrega dados na tabela `promotions_staging` com `WRITE_TRUNCATE` (limpa staging a cada execução).
2. Executa `MERGE` da staging para a tabela final usando `dedupe_key` como chave.
3. Apenas registros com `dedupe_key` inexistente na tabela final são inseridos.

**Por que duas camadas de dedup**:
- **Memória** (antes do BigQuery): remove duplicatas óbvias dentro da mesma execução (ex: mesmo item aparece em duas queries). Economiza custo de escrita no BigQuery.
- **MERGE** (no BigQuery): garante deduplicação entre execuções diferentes. Mesmo item coletado ontem e hoje não é duplicado.

## 8. Por que `dedupe_key = SHA256(marketplace:item_id:price)`?

- **Incluir `price`**: permite rastrear mudanças de preço. Se um smartphone custa R$1.999 hoje e R$1.799 amanhã, são dois registros distintos — útil para análise de histórico de preços.
- **SHA256**: gera chave de tamanho fixo (64 chars), determinística e sem colisões práticas.
- **Alternativa descartada**: `marketplace:item_id` (sem price) — ignoraria mudanças de preço, perdendo informação valiosa.

## 9. Por que Cloud Run (e não Compute Engine)?

- **Serverless**: não precisa gerenciar VMs, patches, ou escala.
- **Pay-per-use**: cobra apenas pelo tempo de execução. Para um coletor que roda 1x/dia por ~15 segundos, o custo é praticamente zero.
- **Deploy simples**: `docker build` + `gcloud run deploy`. Sem SSH, sem systemd, sem cron.
- **Integração com Cloud Scheduler**: um job HTTP que faz `POST /run` no horário configurado.
- **Alternativa (Compute Engine)**: faria sentido se o pipeline fosse contínuo (streaming) ou precisasse de estado persistente. Para batch periódico, Cloud Run é mais adequado.

## 10. Por que a estrutura de diretórios `src/promozone/`?

Segue o padrão `src layout` recomendado pela comunidade Python:
- **Isolamento**: código-fonte em `src/` evita imports acidentais do diretório raiz.
- **Separação clara**: `collectors/` (coleta), `models/` (domínio), `services/` (orquestração), `api/` (interface).
- **Testabilidade**: testes em `tests/` separados do código, com `PYTHONPATH=src`.

## 11. Por que 16 testes unitários?

Cobertura focada nos componentes críticos:
- **`test_promotion_model.py`** (3): garante que o modelo Pydantic serializa corretamente para BigQuery.
- **`test_mercadolivre_parser.py`** (6): garante que o parser trata edge cases (sem preço, sem ID, loja oficial).
- **`test_dedup.py`** (5): garante que a deduplicação é determinística e correta.
- **`test_pipeline.py`** (2): garante que o orquestrador integra todas as peças (com mocks de I/O).

**Não foram escritos testes de integração** com BigQuery real ou com o Mercado Livre — seriam frágeis e lentos para o prazo de 72h. Os testes unitários com mocks cobrem a lógica de negócio.

## 12. Logging estruturado

- Formato: `timestamp | level | logger | message` — compatível com Cloud Logging.
- Cada etapa do pipeline loga: início, quantidade coletada, parseada, deduplicada, gravada, erros.
- Libs externas (httpx, google, uvicorn) têm nível reduzido para WARNING — evita poluição.
- O `execution_id` (UUID) aparece nos logs e nos dados, permitindo rastrear uma execução de ponta a ponta.

---

## Resumo visual

```
[Cloud Scheduler] --POST /run--> [Cloud Run / FastAPI]
                                        |
                                   run_pipeline()
                                        |
                        +---------------+---------------+
                        |               |               |
                   Scraper HTML    Parser JSON     Dedup SHA256
                   (httpx+retry)   (Pydantic)      (memória)
                        |               |               |
                        +-------+-------+-------+-------+
                                |
                         BigQuery Repository
                         (staging + MERGE)
                                |
                    +-----------+-----------+
                    |                       |
              promotions_staging       promotions
              (WRITE_TRUNCATE)         (tabela final)
```

