"""
Repositório BigQuery: staging + MERGE para deduplicação.

Repositório = camada que gerencia o acesso ao banco de dados.

Este arquivo é responsável por salvar as promoções no BigQuery
(banco de dados do Google Cloud) de forma inteligente, evitando duplicatas.

Estratégia de 2 camadas:
1. STAGING (temporária): Recebe os novos dados
2. FINAL: Contém todos os dados únicos

Processo:
1. Limpa a tabela staging
2. Insere os novos dados na staging
3. Faz MERGE: copia da staging para a final apenas os que não existem
4. Resultado: tabela final sem duplicatas
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from google.cloud import bigquery  # Biblioteca do Google Cloud para BigQuery

from promozone.config import Settings
from promozone.models.promotion import Promotion

logger = logging.getLogger(__name__)

# ===== SCHEMA (ESTRUTURA) DA TABELA =====
# Define quais colunas a tabela tem e qual o tipo de cada uma
# É como um "molde" que define a estrutura da tabela no BigQuery
PROMOTIONS_SCHEMA = [
    # STRING = texto, NUMERIC = número decimal, FLOAT64 = número decimal de precisão dupla
    # TIMESTAMP = data e hora
    # mode="REQUIRED" = campo obrigatório (não pode ser vazio)

    bigquery.SchemaField("marketplace", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("item_id", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("url", "STRING"),
    bigquery.SchemaField("title", "STRING"),
    bigquery.SchemaField("price", "NUMERIC"),
    bigquery.SchemaField("original_price", "NUMERIC"),
    bigquery.SchemaField("discount_percent", "FLOAT64"),
    bigquery.SchemaField("seller", "STRING"),
    bigquery.SchemaField("image_url", "STRING"),
    bigquery.SchemaField("source", "STRING"),
    bigquery.SchemaField("dedupe_key", "STRING", mode="REQUIRED"),  # Chave de deduplicação
    bigquery.SchemaField("execution_id", "STRING"),
    bigquery.SchemaField("collected_at", "TIMESTAMP"),
    bigquery.SchemaField("inserted_at", "TIMESTAMP"),
]


class BigQueryRepository:
    """
    Gerencia escrita e deduplicação no BigQuery via staging + MERGE.

    Esta classe é responsável por todas as operações com o BigQuery:
    - Criar dataset e tabelas
    - Inserir dados na staging
    - Fazer MERGE para a tabela final
    - Garantir que não haja duplicatas
    """

    def __init__(self, settings: Settings) -> None:
        """
        Inicializa o repositório.

        Args:
            settings: Objeto com as configurações (IDs do projeto, dataset, etc)
        """
        self.settings = settings
        # Cria o cliente do BigQuery (conexão com o banco de dados)
        self.client = bigquery.Client(project=settings.bq_project_id)

    def ensure_dataset_and_tables(self) -> None:
        """
        Cria dataset e tabelas se não existirem.

        Dataset = conjunto de tabelas (como um "banco de dados")

        Esta função é útil em desenvolvimento para garantir que
        a estrutura necessária existe antes de tentar inserir dados.

        Cria:
        1. Dataset (se não existir)
        2. Tabela final (se não existir)
        3. Tabela staging (se não existir)

        exists_ok=True significa que não dá erro se já existir.
        """
        # Cria referência ao dataset
        dataset_ref = bigquery.DatasetReference(
            self.settings.bq_project_id, self.settings.bq_dataset
        )

        # Cria objeto Dataset com localização US
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"

        # Cria o dataset (ou não faz nada se já existir)
        self.client.create_dataset(dataset, exists_ok=True)
        logger.info("Dataset %s garantido", self.settings.bq_dataset)

        # Cria ambas as tabelas (final e staging)
        for table_name in [self.settings.bq_table, self.settings.bq_staging_table]:
            # Cria referência à tabela
            table_ref = dataset_ref.table(table_name)

            # Cria objeto Table com o schema definido
            table = bigquery.Table(table_ref, schema=PROMOTIONS_SCHEMA)

            # Cria a tabela (ou não faz nada se já existir)
            self.client.create_table(table, exists_ok=True)
            logger.info("Tabela %s garantida", table_name)

    def _load_to_staging(self, promotions: List[Promotion]) -> int:
        """
        Carrega promoções na tabela de staging (WRITE_TRUNCATE).

        WRITE_TRUNCATE = apaga tudo que estava na tabela e insere os novos dados.
        Isso garante que a staging sempre tem apenas os dados da execução atual.

        Processo:
        1. Pega a hora atual
        2. Para cada promoção, define inserted_at e converte para dict
        3. Envia todos os dados para o BigQuery de uma vez
        4. Aguarda a conclusão

        Args:
            promotions: Lista de promoções a serem carregadas

        Retorna:
            int: Número de linhas carregadas
        """
        # Pega a hora atual em UTC (fuso horário universal)
        now = datetime.now(timezone.utc)

        # Lista para armazenar os dicionários (formato que o BigQuery aceita)
        rows = []

        # Para cada promoção:
        for p in promotions:
            # Define o timestamp de inserção
            p.inserted_at = now
            # Converte para dicionário e adiciona na lista
            rows.append(p.to_bq_row())

        # Nome completo da tabela staging
        staging_ref = self.settings.bq_full_staging_table

        # Configuração do job de carga
        job_config = bigquery.LoadJobConfig(
            schema=PROMOTIONS_SCHEMA,  # Estrutura da tabela
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,  # Apaga e reescreve
        )

        # Inicia o job de carga (envia os dados para o BigQuery)
        job = self.client.load_table_from_json(
            rows, staging_ref, job_config=job_config
        )

        # Aguarda a conclusão do job (operação síncrona)
        # Se houver erro, lança exceção aqui
        job.result()

        logger.info("Staging: %d linhas carregadas em %s", len(rows), staging_ref)
        return len(rows)

    def _merge_staging_into_final(self) -> None:
        """
        Executa MERGE da staging para a tabela final com base em dedupe_key.

        MERGE = operação SQL que combina INSERT e UPDATE de forma inteligente.

        Como funciona:
        1. Compara cada linha da staging com a tabela final usando dedupe_key
        2. Se a dedupe_key NÃO existe na final: insere (INSERT)
        3. Se a dedupe_key JÁ existe na final: não faz nada (evita duplicata)

        Resultado: apenas promoções novas são inseridas na tabela final.

        Exemplo:
            Staging tem: [A, B, C]
            Final tem: [A, D]
            Após MERGE, Final tem: [A, D, B, C]
            (A não foi duplicado, B e C foram inseridos)
        """
        # Query SQL do MERGE
        # target = tabela final (destino)
        # source = tabela staging (origem)
        merge_sql = f"""
        MERGE `{self.settings.bq_full_table}` AS target
        USING `{self.settings.bq_full_staging_table}` AS source
        ON target.dedupe_key = source.dedupe_key
        WHEN NOT MATCHED THEN
            INSERT (
                marketplace, item_id, url, title, price, original_price,
                discount_percent, seller, image_url, source,
                dedupe_key, execution_id, collected_at, inserted_at
            )
            VALUES (
                source.marketplace, source.item_id, source.url, source.title,
                source.price, source.original_price, source.discount_percent,
                source.seller, source.image_url, source.source,
                source.dedupe_key, source.execution_id,
                source.collected_at, source.inserted_at
            )
        """

        # Executa a query
        query_job = self.client.query(merge_sql)

        # Aguarda conclusão
        result = query_job.result()

        # Registra quantas linhas foram afetadas (inseridas)
        logger.info(
            "MERGE concluído: %d linhas afetadas",
            query_job.num_dml_affected_rows or 0,
        )

    def upsert_promotions(self, promotions: List[Promotion]) -> int:
        """
        Pipeline completo: staging -> MERGE -> tabela final.

        UPSERT = UPDATE + INSERT (atualiza se existe, insere se não existe)
        No nosso caso, apenas inserimos novos (não atualizamos existentes).

        Esta é a função principal que deve ser chamada para salvar promoções.
        Ela coordena todo o processo de 2 camadas.

        Processo:
        1. Verifica se há promoções para salvar
        2. Carrega na staging (apagando o que tinha antes)
        3. Faz MERGE para a tabela final (apenas novos)
        4. Retorna quantas foram carregadas

        Args:
            promotions: Lista de promoções a serem salvas

        Retorna:
            int: Número de linhas carregadas no staging

        Exemplo:
            repo = BigQueryRepository(settings)
            count = repo.upsert_promotions(promotions)
            print(f"{count} promoções salvas")
        """
        # Se a lista está vazia, não faz nada
        if not promotions:
            logger.warning("Nenhuma promoção para gravar no BigQuery")
            return 0

        # Carrega na staging
        loaded = self._load_to_staging(promotions)

        # Faz MERGE para a final
        self._merge_staging_into_final()

        return loaded

