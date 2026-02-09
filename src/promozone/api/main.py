"""FastAPI app — endpoints /health e /run."""

from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException

from promozone.config import get_settings
from promozone.logging_config import setup_logging
from promozone.services.pipeline import run_pipeline

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown do app."""
    settings = get_settings()
    setup_logging(level=settings.log_level)

    # Configura GOOGLE_APPLICATION_CREDENTIALS como env var do sistema
    # (necessário para o cliente BigQuery encontrar as credenciais)
    if settings.google_application_credentials:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.google_application_credentials
        logger.info("Credenciais GCP configuradas: %s", settings.google_application_credentials)

    logger.info(
        "PromoZone iniciado | env=%s | fontes=%s",
        settings.environment,
        settings.ml_sources,
    )
    yield
    logger.info("PromoZone encerrado")


app = FastAPI(
    title="PromoZone",
    description="Coletor de promoções do Mercado Livre",
    version="0.1.0",
    lifespan=lifespan,
)


@app.get("/health")
def health():
    """Health check simples."""
    return {"status": "ok"}


@app.post("/run")
def run_collector():
    """Dispara uma execução completa do pipeline de coleta.

    Retorna estatísticas da execução (itens coletados, deduplicados, gravados, erros).
    """
    try:
        settings = get_settings()
        result = run_pipeline(settings)

        status_code = 200 if result.status == "success" else 207

        return {
            "execution_id": result.execution_id,
            "status": result.status,
            "sources_processed": result.sources_processed,
            "total_collected": result.total_collected,
            "total_after_dedup": result.total_after_dedup,
            "total_loaded": result.total_loaded,
            "errors": result.errors,
            "duration_seconds": result.duration_seconds,
        }

    except Exception as exc:
        logger.exception("Erro ao executar pipeline")
        raise HTTPException(status_code=500, detail=str(exc)) from exc

