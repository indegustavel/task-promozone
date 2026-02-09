"""Pipeline de orquestração: coleta -> normaliza -> dedupe -> BigQuery."""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import List

from promozone.collectors.mercadolivre_scraper import MercadoLivreScraperClient
from promozone.collectors.mercadolivre_parser import parse_items
from promozone.config import Settings
from promozone.models.promotion import Promotion
from promozone.services.bigquery_repository import BigQueryRepository
from promozone.services.dedup import build_dedupe_key, deduplicate_in_memory

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Resultado de uma execução do pipeline."""

    execution_id: str
    status: str = "success"
    sources_processed: int = 0
    total_collected: int = 0
    total_after_dedup: int = 0
    total_loaded: int = 0
    errors: List[str] = field(default_factory=list)
    duration_seconds: float = 0.0


def run_pipeline(settings: Settings) -> PipelineResult:
    """Executa o pipeline completo de coleta de promoções.

    1. Para cada fonte configurada, coleta itens via API do ML.
    2. Parseia e normaliza em Promotion.
    3. Enriquece com dedupe_key e execution_id.
    4. Deduplica em memória.
    5. Grava no BigQuery via staging + MERGE.
    """
    execution_id = str(uuid.uuid4())
    start = datetime.now(timezone.utc)
    result = PipelineResult(execution_id=execution_id)

    logger.info("=== Pipeline iniciado | execution_id=%s ===", execution_id)

    sources = settings.get_sources()
    logger.info("Fontes configuradas: %d", len(sources))

    # Scraper como cliente padrão (API pública retorna 403)
    logger.info("🌐 Usando scraper (HTML) para coleta de dados reais")
    client = MercadoLivreScraperClient(
        delay_seconds=settings.ml_request_delay_seconds,
        max_items=settings.ml_max_items_per_source,
    )

    all_promotions: List[Promotion] = []

    try:
        # --- Etapa 1: Coleta e parse ---
        for source_cfg in sources:
            try:
                logger.info("Coletando fonte=%s query=%r", source_cfg.source, source_cfg.query)
                raw_items = client.search(source_cfg.query)
                promotions = parse_items(raw_items, source=source_cfg.source)

                # Enriquece com execution_id e dedupe_key
                for promo in promotions:
                    promo.execution_id = execution_id
                    promo.dedupe_key = build_dedupe_key(promo)

                all_promotions.extend(promotions)
                result.sources_processed += 1
                logger.info(
                    "Fonte %s: %d itens coletados",
                    source_cfg.source,
                    len(promotions),
                )

            except Exception as exc:
                error_msg = f"Erro na fonte {source_cfg.source}: {exc}"
                logger.exception(error_msg)
                result.errors.append(error_msg)

        result.total_collected = len(all_promotions)
        logger.info("Total coletado (todas as fontes): %d", result.total_collected)

        # --- Etapa 2: Dedup em memória ---
        unique_promotions = deduplicate_in_memory(all_promotions)
        result.total_after_dedup = len(unique_promotions)
        logger.info("Após dedup em memória: %d", result.total_after_dedup)

        # --- Etapa 3: Gravar no BigQuery ---
        bq_repo = BigQueryRepository(settings)
        bq_repo.ensure_dataset_and_tables()
        result.total_loaded = bq_repo.upsert_promotions(unique_promotions)
        logger.info("Gravados no BigQuery: %d", result.total_loaded)

    except Exception as exc:
        error_msg = f"Erro fatal no pipeline: {exc}"
        logger.exception(error_msg)
        result.errors.append(error_msg)
        result.status = "error"

    finally:
        client.close()

    end = datetime.now(timezone.utc)
    result.duration_seconds = round((end - start).total_seconds(), 2)

    if result.errors:
        result.status = "partial_error" if result.total_loaded > 0 else "error"

    logger.info(
        "=== Pipeline finalizado | execution_id=%s | status=%s | "
        "coletados=%d | dedup=%d | gravados=%d | erros=%d | duração=%.2fs ===",
        execution_id,
        result.status,
        result.total_collected,
        result.total_after_dedup,
        result.total_loaded,
        len(result.errors),
        result.duration_seconds,
    )

    return result

