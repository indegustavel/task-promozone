"""Lógica de deduplicação em memória."""

from __future__ import annotations

import hashlib
import logging
from typing import List

from promozone.models.promotion import Promotion

logger = logging.getLogger(__name__)


def build_dedupe_key(promo: Promotion) -> str:
    """Gera chave de deduplicação determinística.

    Estratégia: hash de marketplace + item_id + price.
    Isso garante que o mesmo item com o mesmo preço não seja duplicado,
    mas permite registrar mudanças de preço como entradas distintas.
    """
    raw = f"{promo.marketplace}:{promo.item_id}:{promo.price}"
    return hashlib.sha256(raw.encode()).hexdigest()


def deduplicate_in_memory(promotions: List[Promotion]) -> List[Promotion]:
    """Remove duplicatas dentro da mesma execução com base no dedupe_key.

    Retorna lista sem duplicatas, preservando a primeira ocorrência.
    """
    seen: set[str] = set()
    unique: List[Promotion] = []

    for promo in promotions:
        if promo.dedupe_key in seen:
            continue
        seen.add(promo.dedupe_key)
        unique.append(promo)

    removed = len(promotions) - len(unique)
    if removed > 0:
        logger.info(
            "Dedup em memória: %d duplicatas removidas de %d itens",
            removed,
            len(promotions),
        )

    return unique

