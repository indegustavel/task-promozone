"""
Modelo normalizado de promoção.

Este arquivo define a estrutura de dados de uma promoção.
É como um "molde" ou "formulário" que define quais informações
cada promoção deve ter e qual o tipo de cada informação.
"""

from __future__ import annotations

from datetime import datetime, timezone  # Para trabalhar com datas e horas
from typing import Optional  # Para campos que podem ser None (vazios)

from pydantic import BaseModel, Field  # Para validação automática de dados


class Promotion(BaseModel):
    """
    Representa um item/promoção normalizado, pronto para gravar no BigQuery.

    Esta classe define todos os campos que uma promoção possui.
    Pydantic (BaseModel) garante que:
    - Todos os campos obrigatórios estejam presentes
    - Os tipos de dados estejam corretos (string, número, etc)
    - Valores padrão sejam aplicados quando necessário

    Exemplo de uso:
        promo = Promotion(
            item_id="MLB123456",
            url="https://...",
            title="Smartphone X",
            price=999.90,
            source="busca_smartphone"
        )
    """

    # ===== CAMPOS PRINCIPAIS DO ITEM =====

    # De qual marketplace veio (sempre "mercado_livre" neste projeto)
    marketplace: str = Field(
        default="mercado_livre",
        description="Identificador do marketplace de origem",
    )

    # ID único do item no Mercado Livre (ex: "MLB123456789")
    # O "..." significa que é obrigatório (não tem valor padrão)
    item_id: str = Field(
        ..., description="Identificador estável do item na fonte"
    )

    # Link para a página do produto
    url: str = Field(..., description="URL do item")

    # Nome/título do produto
    title: str = Field(..., description="Título do item")

    # Preço atual do produto (número decimal)
    price: float = Field(..., description="Preço atual")

    # Preço original (antes do desconto), se houver
    # Optional[float] significa que pode ser None (vazio)
    original_price: Optional[float] = Field(
        default=None, description="Preço original (antes do desconto)"
    )

    # Percentual de desconto calculado (ex: 15.5 para 15,5%)
    discount_percent: Optional[float] = Field(
        default=None, description="Percentual de desconto calculado"
    )

    # Nome do vendedor
    seller: Optional[str] = Field(
        default=None, description="Nome do vendedor"
    )

    # URL da imagem do produto
    image_url: Optional[str] = Field(
        default=None, description="URL da imagem principal"
    )

    # Identificador de qual busca gerou este item
    # (ex: "busca_smartphone", "busca_notebook")
    source: str = Field(
        ..., description="Identificador da consulta/fonte que gerou o item"
    )

    # ===== CAMPOS DE RASTREABILIDADE =====
    # Estes campos ajudam a rastrear e controlar os dados

    # Chave única para identificar duplicatas
    # Formato: hash SHA256 de "marketplace:item_id:price"
    # Exemplo: se o mesmo produto com o mesmo preço for coletado duas vezes,
    # terá a mesma dedupe_key e será considerado duplicata
    dedupe_key: str = Field(
        default="", description="Chave de deduplicação (marketplace:item_id:price)"
    )

    # ID único da execução do pipeline que coletou este item
    # Permite saber em qual "rodada" de coleta o item foi encontrado
    # Formato: UUID (ex: "550e8400-e29b-41d4-a716-446655440000")
    execution_id: str = Field(
        default="", description="UUID da execução que coletou o item"
    )

    # Data e hora em que o item foi coletado
    # default_factory=lambda: ... significa que o valor padrão é gerado
    # automaticamente quando o objeto é criado (hora atual em UTC)
    collected_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        description="Timestamp da coleta",
    )

    # Data e hora em que o item foi inserido no BigQuery
    # Começa como None e é preenchido no momento da gravação
    inserted_at: Optional[datetime] = Field(
        default=None,
        description="Timestamp de inserção no BigQuery (preenchido na gravação)",
    )

    def to_bq_row(self) -> dict:
        """
        Converte o objeto Promotion para um dicionário compatível com BigQuery.

        O BigQuery precisa receber os dados em formato de dicionário (dict),
        e as datas precisam estar em formato ISO string (ex: "2024-01-15T10:30:45").

        Retorna:
            dict: Dicionário com todos os campos da promoção, pronto para
                  ser enviado ao BigQuery

        Exemplo:
            promo = Promotion(...)
            row = promo.to_bq_row()
            # row = {"item_id": "MLB123", "price": 999.90, ...}
        """
        # model_dump() converte o objeto Pydantic em dicionário
        data = self.model_dump()

        # BigQuery espera datas em formato string ISO
        # isoformat() converte datetime para string no formato ISO 8601
        # Exemplo: datetime(2024, 1, 15, 10, 30) -> "2024-01-15T10:30:45"
        data["collected_at"] = self.collected_at.isoformat()

        # Se inserted_at não for None, converte para string
        # Caso contrário, mantém None
        data["inserted_at"] = (
            self.inserted_at.isoformat() if self.inserted_at else None
        )

        return data

