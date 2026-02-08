Construa um protótipo fim-a-fim: coleta, normalização, deduplicação e gravação no BigQuery, com logs e sinais mínimos de operação.

Dica opcional: Firecrawl (open source) pode ajudar na coleta/extração. Use se fizer sentido e explique
no README.

Visão geral
Você terá 72 horas para construir um protótipo funcional de um coletor de promoções do
Mercado Livre. O foco é demonstrar entrega fim-a-fim com qualidade de dados e operação
mínima (logs, rastreabilidade, dedupe).

Objetivo:
• Coletar promoções/ofertas a partir de 1 a 3 páginas/consultas definidas por você.
• Normalizar os dados para um modelo consistente.
• Persistir no BigQuery (obrigatório).
• Evitar duplicação (obrigatório).
• Ter monitoramento básico (obrigatório).
• Rodar no GCP - preferencialmente Cloud Run (VM é aceitável com justificativa).
O que vale mais pontos
• Entrega funcionando (coleta -> normaliza -> BigQuery).
• README claro e reprodutível (rodar local e deploy).
• Deduplicação defensável.
• Logs úteis e tratamento de erros.
• Código simples, legível e bem estruturado.

Escopo mínimo (MVP obrigatório)

1) Coleta - Mercado Livre
• Escolha 1 a 3 fontes/consultas (ex.: uma categoria, uma busca com filtro, uma vitrine de
ofertas).
• Colete itens suficientes para demonstrar o pipeline (não precisa cobrir o site inteiro).
• Respeite boas práticas de acesso (rate limit, reintentos com backoff, nada de
agressividade).

2) Normalização - modelo único
Para cada item/promoção, normalize pelo menos os campos abaixo (você pode adicionar
outros):
• marketplace (ex.: mercado_livre)
• item_id (identificador estável extraído da fonte)
• url
• title
• price (preço atual)
• original_price (se existir)
• discount_percent (se conseguir calcular)
• seller (se disponível)
• image_url (se disponível)
• source (qual consulta/página gerou o item)
• collected_at (timestamp)

Sugestão de schema (exemplo) para BigQuery:

" CREATE TABLE dataset.promotions ( marketplace STRING, item_id STRING, url STRING, title
STRING, price NUMERIC, original_price NUMERIC, discount_percent FLOAT64, seller STRING,
image_url STRING, source STRING, dedupe_key STRING, execution_id STRING, collected_at
TIMESTAMP, inserted_at TIMESTAMP ); "

3) Armazenamento - BigQuery (obrigatório)
• Grave os dados em uma tabela no BigQuery. O projeto/dataset pode ser fornecido; se não
houver acesso, use seu próprio projeto e documente.
• Inclua rastreabilidade mínima (ex.: execution_id, inserted_at).

4) Deduplicação (obrigatório)
• Garanta que a mesma promoção não seja inserida repetidamente.
• Estratégias aceitas: MERGE no BigQuery, staging + tabela final, ou outra abordagem
explicada no README.
• Uma sugestão é criar um dedupe_key (ex.: marketplace + item_id + price)

5) Monitoramento básico (obrigatório)
• Logs que mostrem: início/fim da execução, quantidade coletada, inserida, deduplicada e
erros.
• Um sinal mínimo de saúde: endpoint /health ou execução com retorno claro de status.

6) Execução no GCP (obrigatório)
• Rodar no Google Cloud - preferencialmente Cloud Run (container).
• Compute Engine (VM) é aceitável se você justificar no README por que escolheu essa
rota

Entregáveis:

• Repositório Git (GitHub/GitLab) com o código.
• README contendo: como rodar localmente; como fazer deploy; configuração de
credenciais/permissões; fonte(s) coletadas; estratégia de dedupe; schema/tabelas do
BigQuery; trade-offs.
• Uma query SQL de validação no BigQuery (ex.: itens coletados nas últimas 24h).
• (Opcional) diagrama simples da arquitetura (Markdown ou Mermaid).

Critérios de avaliação:

• Funciona fim-a-fim e é reprodutível.
• Qualidade e consistência dos dados normalizados.
• Deduplicação coerente e implementada.
• Observabilidade e tratamento de erros.
• Qualidade de código (organização, clareza, simplicidade).

Extensões opcionais (se sobrar tempo):

• Agendamento (ex.: Cloud Scheduler chamando o serviço).
• Pipeline staging -> final com MERGE.
• Retry com backoff para falhas transitórias.
• Pequeno relatório com métricas (via query e prints no README).
Boas práticas e regras
• Não versionar segredos (chaves, tokens, credenciais). Use variáveis de ambiente.
• Respeitar limites e termos de uso. Nada de bypass de segurança.
• Se algo não couber no prazo, explique no README. Transparência conta.
