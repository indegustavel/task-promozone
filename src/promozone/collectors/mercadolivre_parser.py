"""Parser que transforma resultados crus da API do ML em Promotion."""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from promozone.models.promotion import Promotion

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> Optional[float]:
    """Converte para float de forma segura, retornando None se inválido."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _calc_discount(price: float, original_price: Optional[float]) -> Optional[float]:
    """Calcula percentual de desconto."""
    if original_price and original_price > 0 and original_price > price:
        return round((1 - price / original_price) * 100, 2)
    return None


def _extract_seller(item: Dict[str, Any]) -> Optional[str]:
    """Extrai nome do vendedor do item, se disponível."""
    seller = item.get("seller", {})
    if isinstance(seller, dict):
        nickname = seller.get("nickname")
        if nickname:
            return str(nickname)
    # Fallback: seller_address ou official_store_name
    official = item.get("official_store_name")
    if official:
        return str(official)
    return None


def parse_items(raw_items: List[Dict[str, Any]], source: str) -> List[Promotion]:
    """Converte lista de itens crus da API do ML em lista de Promotion.

    Args:
        raw_items: Lista de dicts vindos de data['results'] da API.
        source: Identificador da fonte/consulta.

    Returns:
        Lista de Promotion (sem dedupe_key e execution_id preenchidos).
    """
    promotions: List[Promotion] = []

    for item in raw_items:
        try:
            item_id = str(item.get("id", ""))
            if not item_id:
                logger.warning("Item sem ID, pulando: %s", item)
                continue

            price = _safe_float(item.get("price"))
            if price is None:
                logger.warning("Item %s sem preço válido, pulando", item_id)
                continue

            original_price = _safe_float(item.get("original_price"))
            discount = _calc_discount(price, original_price)

            promo = Promotion(
                item_id=item_id,
                url=item.get("permalink", ""),
                title=item.get("title", ""),
                price=price,
                original_price=original_price,
                discount_percent=discount,
                seller=_extract_seller(item),
                image_url=item.get("thumbnail", ""),
                source=source,
            )
            promotions.append(promo)

        except Exception:
            logger.exception("Erro ao parsear item %s", item.get("id", "?"))

    logger.info(
        "Parseados %d/%d itens da fonte=%s",
        len(promotions),
        len(raw_items),
        source,
    )
    return promotions

