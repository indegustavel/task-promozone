"""Configuração centralizada via variáveis de ambiente."""

from __future__ import annotations

import json
from typing import List

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class SourceConfig:
    """Representa uma fonte/consulta de coleta do Mercado Livre."""

    def __init__(self, query: str, source: str) -> None:
        self.query = query
        self.source = source

    def __repr__(self) -> str:
        return f"SourceConfig(query={self.query!r}, source={self.source!r})"


class Settings(BaseSettings):
    """Configurações lidas de variáveis de ambiente (ou .env)."""

    # Google Cloud (credenciais são lidas automaticamente pelo cliente BigQuery)
    google_application_credentials: str = Field(
        default="", description="Caminho para chave de serviço (apenas local)"
    )

    # BigQuery
    bq_project_id: str = Field(..., description="GCP project ID")
    bq_dataset: str = Field(default="promozone", description="BigQuery dataset")
    bq_table: str = Field(default="promotions", description="Tabela final")
    bq_staging_table: str = Field(
        default="promotions_staging", description="Tabela de staging"
    )

    # Mercado Livre
    ml_sources: str = Field(
        default='[{"query": "smartphone", "source": "busca_smartphone"}]',
        description="JSON array com as fontes de coleta",
    )
    ml_max_items_per_source: int = Field(
        default=50, description="Máximo de itens por fonte"
    )
    ml_request_delay_seconds: float = Field(
        default=1.0, description="Delay entre requests (rate limiting)"
    )

    # Geral
    log_level: str = Field(default="INFO")
    environment: str = Field(default="local")
    port: int = Field(default=8080)

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",  # Ignora variáveis de ambiente não mapeadas
    }

    @field_validator("ml_sources", mode="before")
    @classmethod
    def _validate_ml_sources(cls, v: str) -> str:
        """Valida que ml_sources é um JSON array válido."""
        try:
            parsed = json.loads(v)
            if not isinstance(parsed, list):
                raise ValueError("ml_sources deve ser um JSON array")
        except json.JSONDecodeError as exc:
            raise ValueError(f"ml_sources não é JSON válido: {exc}") from exc
        return v

    def get_sources(self) -> List[SourceConfig]:
        """Retorna lista de SourceConfig a partir do JSON."""
        raw = json.loads(self.ml_sources)
        return [SourceConfig(query=s["query"], source=s["source"]) for s in raw]

    @property
    def bq_full_table(self) -> str:
        return f"{self.bq_project_id}.{self.bq_dataset}.{self.bq_table}"

    @property
    def bq_full_staging_table(self) -> str:
        return f"{self.bq_project_id}.{self.bq_dataset}.{self.bq_staging_table}"


def get_settings() -> Settings:
    """Factory para obter as configurações (facilita testes com override)."""
    return Settings()

