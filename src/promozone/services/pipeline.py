"""
Pipeline de orquestração: coleta -> normaliza -> dedupe -> BigQuery.

Pipeline = sequência de etapas que processam dados.
Orquestração = coordenação de várias etapas em ordem.

Este arquivo é o "maestro" que coordena todo o processo:
1. Coleta dados do Mercado Livre
2. Normaliza (converte para formato padrão)
3. Deduplica (remove repetidos)
4. Salva no BigQuery

É como uma linha de produção onde cada etapa processa os dados
e passa para a próxima etapa.
"""

from __future__ import annotations

import logging
import uuid  # Para gerar IDs únicos
from dataclasses import dataclass, field  # Para criar classes de dados simples
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
    """
    Resultado de uma execução do pipeline.

    Esta classe armazena estatísticas e informações sobre
    uma execução do pipeline. É como um "relatório" do que aconteceu.

    @dataclass = decorador que cria automaticamente __init__, __repr__, etc.
    """

    # ID único desta execução (UUID)
    execution_id: str

    # Status da execução: "success", "partial_error" ou "error"
    status: str = "success"

    # Quantas fontes (buscas) foram processadas com sucesso
    sources_processed: int = 0

    # Total de itens coletados (antes de remover duplicatas)
    total_collected: int = 0

    # Total após remover duplicatas em memória
    total_after_dedup: int = 0

    # Total efetivamente gravado no BigQuery
    total_loaded: int = 0

    # Lista de mensagens de erro (se houver)
    # field(default_factory=list) cria uma lista vazia para cada instância
    errors: List[str] = field(default_factory=list)

    # Duração total da execução em segundos
    duration_seconds: float = 0.0


def run_pipeline(settings: Settings) -> PipelineResult:
    """
    Executa o pipeline completo de coleta de promoções.

    Esta é a função principal que coordena todo o processo.
    Ela é chamada quando alguém acessa o endpoint /run da API.

    Etapas do pipeline:
    1. Para cada fonte configurada (ex: "smartphone", "notebook"):
       a. Coleta itens via scraping do Mercado Livre
       b. Parseia (converte) para objetos Promotion
       c. Enriquece com execution_id e dedupe_key
    2. Deduplica em memória (remove repetidos dentro desta execução)
    3. Grava no BigQuery via staging + MERGE (remove repetidos globais)
    4. Retorna estatísticas da execução

    Args:
        settings: Objeto com todas as configurações

    Retorna:
        PipelineResult: Objeto com estatísticas e status da execução

    Exemplo:
        settings = get_settings()
        result = run_pipeline(settings)
        print(f"Coletados: {result.total_collected}")
        print(f"Gravados: {result.total_loaded}")
    """
    # ===== INICIALIZAÇÃO =====
    # Gera um ID único para esta execução (UUID v4)
    # Exemplo: "550e8400-e29b-41d4-a716-446655440000"
    execution_id = str(uuid.uuid4())

    # Marca o início da execução (para calcular duração depois)
    start = datetime.now(timezone.utc)

    # Cria objeto para armazenar o resultado
    result = PipelineResult(execution_id=execution_id)

    logger.info("=== Pipeline iniciado | execution_id=%s ===", execution_id)

    # Obtém a lista de fontes (buscas) configuradas
    sources = settings.get_sources()
    logger.info("Fontes configuradas: %d", len(sources))

    # ===== CRIAÇÃO DO CLIENTE DE SCRAPING =====
    # Usamos scraper porque a API pública do ML retorna erro 403
    logger.info("🌐 Usando scraper (HTML) para coleta de dados reais")
    client = MercadoLivreScraperClient(
        delay_seconds=settings.ml_request_delay_seconds,
        max_items=settings.ml_max_items_per_source,
    )

    # Lista para acumular todas as promoções de todas as fontes
    all_promotions: List[Promotion] = []

    try:
        # ===== ETAPA 1: COLETA E PARSE =====
        # Processa cada fonte (busca) configurada
        for source_cfg in sources:
            try:
                logger.info("Coletando fonte=%s query=%r", source_cfg.source, source_cfg.query)

                # Faz a busca no Mercado Livre via scraping
                # Retorna lista de dicionários com dados brutos
                raw_items = client.search(source_cfg.query)

                # Converte os dados brutos em objetos Promotion
                promotions = parse_items(raw_items, source=source_cfg.source)

                # ===== ENRIQUECIMENTO =====
                # Adiciona informações extras em cada promoção
                for promo in promotions:
                    # Define o ID da execução (para rastreabilidade)
                    promo.execution_id = execution_id

                    # Gera a chave de deduplicação (hash único)
                    promo.dedupe_key = build_dedupe_key(promo)

                # Adiciona as promoções desta fonte na lista geral
                all_promotions.extend(promotions)

                # Incrementa contador de fontes processadas com sucesso
                result.sources_processed += 1

                logger.info(
                    "Fonte %s: %d itens coletados",
                    source_cfg.source,
                    len(promotions),
                )

            except Exception as exc:
                # Se der erro em uma fonte, registra mas continua com as outras
                error_msg = f"Erro na fonte {source_cfg.source}: {exc}"
                logger.exception(error_msg)
                result.errors.append(error_msg)

        # Atualiza estatística total
        result.total_collected = len(all_promotions)
        logger.info("Total coletado (todas as fontes): %d", result.total_collected)

        # ===== ETAPA 2: DEDUPLICAÇÃO EM MEMÓRIA =====
        # Remove duplicatas dentro desta execução
        # (ex: mesmo produto apareceu em "smartphone" e "celular")
        unique_promotions = deduplicate_in_memory(all_promotions)
        result.total_after_dedup = len(unique_promotions)
        logger.info("Após dedup em memória: %d", result.total_after_dedup)

        # ===== ETAPA 3: GRAVAÇÃO NO BIGQUERY =====
        # Cria repositório do BigQuery
        bq_repo = BigQueryRepository(settings)

        # Garante que dataset e tabelas existem
        bq_repo.ensure_dataset_and_tables()

        # Salva as promoções (staging + MERGE)
        # O MERGE garante que não haverá duplicatas globais
        # (ex: mesmo produto já foi coletado em execução anterior)
        result.total_loaded = bq_repo.upsert_promotions(unique_promotions)
        logger.info("Gravados no BigQuery: %d", result.total_loaded)

    except Exception as exc:
        # Se der erro fatal (não relacionado a uma fonte específica),
        # registra e marca o status como erro
        error_msg = f"Erro fatal no pipeline: {exc}"
        logger.exception(error_msg)
        result.errors.append(error_msg)
        result.status = "error"

    finally:
        # SEMPRE fecha o cliente, mesmo se houver erro
        # Isso libera recursos (conexões HTTP)
        client.close()

    # ===== FINALIZAÇÃO =====
    # Marca o fim da execução
    end = datetime.now(timezone.utc)

    # Calcula a duração total em segundos
    # (end - start) retorna um timedelta
    # .total_seconds() converte para float
    # round(..., 2) arredonda para 2 casas decimais
    result.duration_seconds = round((end - start).total_seconds(), 2)

    # ===== DETERMINAÇÃO DO STATUS FINAL =====
    # Se houve erros, ajusta o status
    if result.errors:
        # Se gravou algo, é erro parcial
        # Se não gravou nada, é erro total
        result.status = "partial_error" if result.total_loaded > 0 else "error"

    # ===== LOG FINAL COM RESUMO =====
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

    # Retorna o objeto com todas as estatísticas
    return result

