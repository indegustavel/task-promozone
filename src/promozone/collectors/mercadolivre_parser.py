"""
Parser que transforma resultados crus da API do ML em Promotion.

Parser = analisador/conversor de dados.

Este arquivo pega os dados "crus" (brutos) que vêm do Mercado Livre
e os transforma em objetos Promotion padronizados que nosso sistema entende.

Por que precisamos disso?
- A API do Mercado Livre retorna dados em um formato específico (JSON)
- Nosso sistema trabalha com objetos Promotion
- Este parser faz a "tradução" entre os dois formatos
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from promozone.models.promotion import Promotion

logger = logging.getLogger(__name__)


def _safe_float(value: Any) -> Optional[float]:
    """
    Converte um valor para float de forma segura.

    Às vezes os dados vêm em formatos inesperados (string, None, etc).
    Esta função tenta converter para float, e se não conseguir,
    retorna None ao invés de causar um erro.

    Args:
        value: Valor a ser convertido (pode ser qualquer tipo)

    Retorna:
        float ou None: O valor convertido, ou None se não for possível

    Exemplos:
        _safe_float(100)      -> 100.0
        _safe_float("99.90")  -> 99.9
        _safe_float(None)     -> None
        _safe_float("abc")    -> None
    """
    # Se já é None, retorna None
    if value is None:
        return None

    try:
        # Tenta converter para float
        return float(value)
    except (TypeError, ValueError):
        # Se der erro, retorna None
        return None


def _calc_discount(price: float, original_price: Optional[float]) -> Optional[float]:
    """
    Calcula o percentual de desconto.

    Fórmula: desconto = (1 - preço_atual / preço_original) * 100

    Args:
        price: Preço atual do produto
        original_price: Preço original (antes do desconto), pode ser None

    Retorna:
        float ou None: Percentual de desconto (ex: 15.5 para 15,5%),
                       ou None se não houver desconto

    Exemplos:
        _calc_discount(85.0, 100.0)  -> 15.0  (15% de desconto)
        _calc_discount(100.0, 100.0) -> None  (sem desconto)
        _calc_discount(100.0, None)  -> None  (sem preço original)
    """
    # Verifica se:
    # 1. original_price existe (não é None)
    # 2. original_price é maior que zero
    # 3. original_price é maior que o preço atual (há desconto)
    if original_price and original_price > 0 and original_price > price:
        # Calcula o percentual e arredonda para 2 casas decimais
        return round((1 - price / original_price) * 100, 2)

    # Se não há desconto, retorna None
    return None


def _extract_seller(item: Dict[str, Any]) -> Optional[str]:
    """
    Extrai o nome do vendedor do item, se disponível.

    O Mercado Livre pode fornecer o nome do vendedor de várias formas:
    - seller.nickname (vendedor comum)
    - official_store_name (loja oficial)

    Esta função tenta extrair de todas as formas possíveis.

    Args:
        item: Dicionário com dados do item do Mercado Livre

    Retorna:
        str ou None: Nome do vendedor, ou None se não encontrado
    """
    # Tenta pegar o objeto "seller" do item
    seller = item.get("seller", {})

    # Se seller é um dicionário, tenta pegar o nickname
    if isinstance(seller, dict):
        nickname = seller.get("nickname")
        if nickname:
            return str(nickname)

    # Fallback (plano B): tenta pegar o nome da loja oficial
    official = item.get("official_store_name")
    if official:
        return str(official)

    # Se não encontrou nada, retorna None
    return None


def parse_items(raw_items: List[Dict[str, Any]], source: str) -> List[Promotion]:
    """
    Converte lista de itens crus da API do ML em lista de Promotion.

    Esta é a função principal do parser. Ela recebe uma lista de
    dicionários (dados brutos do Mercado Livre) e converte cada um
    em um objeto Promotion padronizado.

    Processo:
        1. Para cada item da lista:
           a. Extrai o ID do item (obrigatório)
           b. Extrai o preço (obrigatório)
           c. Extrai outros campos (título, URL, vendedor, etc)
           d. Calcula o desconto se houver preço original
           e. Cria um objeto Promotion
        2. Retorna a lista de Promotions criadas

    Args:
        raw_items: Lista de dicionários vindos da API do Mercado Livre.
                   Cada dicionário representa um produto.
        source: Identificador da fonte/consulta (ex: "busca_smartphone")

    Retorna:
        List[Promotion]: Lista de objetos Promotion prontos para uso.
                         Nota: dedupe_key e execution_id ainda não estão
                         preenchidos (serão preenchidos depois)

    Exemplo:
        raw = [{"id": "MLB123", "price": 100, "title": "Produto X"}, ...]
        promos = parse_items(raw, "busca_smartphone")
        # promos = [Promotion(...), Promotion(...), ...]
    """
    # Lista para armazenar as promoções convertidas
    promotions: List[Promotion] = []

    # Percorre cada item da lista de dados brutos
    for item in raw_items:
        try:
            # ===== EXTRAÇÃO DO ID (OBRIGATÓRIO) =====
            # Pega o ID do item e converte para string
            item_id = str(item.get("id", ""))

            # Se não tem ID, não podemos processar este item
            if not item_id:
                logger.warning("Item sem ID, pulando: %s", item)
                continue  # Pula para o próximo item

            # ===== EXTRAÇÃO DO PREÇO (OBRIGATÓRIO) =====
            # Tenta converter o preço para float de forma segura
            price = _safe_float(item.get("price"))

            # Se não tem preço válido, não podemos processar
            if price is None:
                logger.warning("Item %s sem preço válido, pulando", item_id)
                continue  # Pula para o próximo item

            # ===== EXTRAÇÃO DE CAMPOS OPCIONAIS =====
            # Preço original (pode ser None se não houver desconto)
            original_price = _safe_float(item.get("original_price"))

            # Calcula o percentual de desconto
            discount = _calc_discount(price, original_price)

            # ===== CRIAÇÃO DO OBJETO PROMOTION =====
            # Cria um objeto Promotion com todos os dados extraídos
            promo = Promotion(
                item_id=item_id,
                url=item.get("permalink", ""),  # Link do produto
                title=item.get("title", ""),    # Título do produto
                price=price,
                original_price=original_price,
                discount_percent=discount,
                seller=_extract_seller(item),   # Extrai nome do vendedor
                image_url=item.get("thumbnail", ""),  # URL da imagem
                source=source,  # Identificador da busca
            )

            # Adiciona a promoção na lista
            promotions.append(promo)

        except Exception:
            # Se der qualquer erro ao processar este item,
            # registra no log e continua com o próximo
            # (não queremos que um item com problema pare todo o processo)
            logger.exception("Erro ao parsear item %s", item.get("id", "?"))

    # Registra no log quantos itens foram processados com sucesso
    logger.info(
        "Parseados %d/%d itens da fonte=%s",
        len(promotions),  # Quantos foram convertidos com sucesso
        len(raw_items),   # Quantos vieram da API
        source,
    )

    return promotions

