"""Configuração de logging estruturado para Cloud Run e local."""

from __future__ import annotations

import logging
import sys


def setup_logging(level: str = "INFO") -> None:
    """Configura logging com formato amigável a Cloud Logging.

    Em produção o Cloud Run captura stdout/stderr automaticamente.
    Usamos formato com timestamp, nível, logger e mensagem.
    """
    log_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    # Remove handlers existentes para evitar duplicação
    root_logger.handlers.clear()
    root_logger.addHandler(handler)

    # Reduz verbosidade de libs externas
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("google").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

