"""Modelo normalizado de promoção."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from pydantic import BaseModel, Field


class Promotion(BaseModel):
    """Representa um item/promoção normalizado, pronto para gravar no BigQuery."""

    marketplace: str = Field(
        default="mercado_livre",
        description="Identificador do marketplace de origem",
    )
    item_id: str = Field(
        ..., description="Identificador estável do item na fonte"
    )
    url: str = Field(..., description="URL do item")
    title: str = Field(..., description="Título do item")
    price: float = Field(..., description="Preço atual")
    original_price: Optional[float] = Field(
        default=None, description="Preço original (antes do desconto)"
    )
    discount_percent: Optional[float] = Field(
        default=None, description="Percentual de desconto calculado"
    )
    seller: Optional[str] = Field(
        default=None, description="Nome do vendedor"
    )
    image_url: Optional[str] = Field(
        default=None, description="URL da imagem principal"
    )
    source: str = Field(
        ..., description="Identificador da consulta/fonte que gerou o item"
    )

    # Campos de rastreabilidade
    dedupe_key: str = Field(
        default="", description="Chave de deduplicação (marketplace:item_id:price)"
    )
    execution_id: str = Field(
        default="", description="UUID da execução que coletou o item"
    )
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp da coleta",
    )
    inserted_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp de inserção no BigQuery (preenchido na gravação)",
    )

    def to_bq_row(self) -> dict:
        """Converte para dict compatível com BigQuery load."""
        data = self.model_dump()
        # BigQuery espera strings ISO para timestamps
        data["collected_at"] = self.collected_at.isoformat()
        data["inserted_at"] = (
            self.inserted_at.isoformat() if self.inserted_at else None
        )
        return data

