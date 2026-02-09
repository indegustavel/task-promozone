"""Repositório BigQuery: staging + MERGE para deduplicação."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List

from google.cloud import bigquery

from promozone.config import Settings
from promozone.models.promotion import Promotion

logger = logging.getLogger(__name__)

# Schema da tabela de promoções
PROMOTIONS_SCHEMA = [
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
    bigquery.SchemaField("dedupe_key", "STRING", mode="REQUIRED"),
    bigquery.SchemaField("execution_id", "STRING"),
    bigquery.SchemaField("collected_at", "TIMESTAMP"),
    bigquery.SchemaField("inserted_at", "TIMESTAMP"),
]


class BigQueryRepository:
    """Gerencia escrita e deduplicação no BigQuery via staging + MERGE."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.client = bigquery.Client(project=settings.bq_project_id)

    def ensure_dataset_and_tables(self) -> None:
        """Cria dataset e tabelas se não existirem (útil em dev)."""
        dataset_ref = bigquery.DatasetReference(
            self.settings.bq_project_id, self.settings.bq_dataset
        )
        dataset = bigquery.Dataset(dataset_ref)
        dataset.location = "US"
        self.client.create_dataset(dataset, exists_ok=True)
        logger.info("Dataset %s garantido", self.settings.bq_dataset)

        for table_name in [self.settings.bq_table, self.settings.bq_staging_table]:
            table_ref = dataset_ref.table(table_name)
            table = bigquery.Table(table_ref, schema=PROMOTIONS_SCHEMA)
            self.client.create_table(table, exists_ok=True)
            logger.info("Tabela %s garantida", table_name)

    def _load_to_staging(self, promotions: List[Promotion]) -> int:
        """Carrega promoções na tabela de staging (WRITE_TRUNCATE)."""
        now = datetime.now(timezone.utc)
        rows = []
        for p in promotions:
            p.inserted_at = now
            rows.append(p.to_bq_row())

        staging_ref = self.settings.bq_full_staging_table
        job_config = bigquery.LoadJobConfig(
            schema=PROMOTIONS_SCHEMA,
            write_disposition=bigquery.WriteDisposition.WRITE_TRUNCATE,
        )

        job = self.client.load_table_from_json(
            rows, staging_ref, job_config=job_config
        )
        job.result()  # Aguarda conclusão

        logger.info("Staging: %d linhas carregadas em %s", len(rows), staging_ref)
        return len(rows)

    def _merge_staging_into_final(self) -> None:
        """Executa MERGE da staging para a tabela final com base em dedupe_key."""
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
        query_job = self.client.query(merge_sql)
        result = query_job.result()
        logger.info(
            "MERGE concluído: %d linhas afetadas",
            query_job.num_dml_affected_rows or 0,
        )

    def upsert_promotions(self, promotions: List[Promotion]) -> int:
        """Pipeline completo: staging -> MERGE -> tabela final.

        Returns:
            Número de linhas carregadas no staging.
        """
        if not promotions:
            logger.warning("Nenhuma promoção para gravar no BigQuery")
            return 0

        loaded = self._load_to_staging(promotions)
        self._merge_staging_into_final()
        return loaded

