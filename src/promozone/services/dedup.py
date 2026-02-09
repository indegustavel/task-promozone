"""
Lógica de deduplicação em memória.

Deduplicação = processo de remover itens duplicados.

Este arquivo contém funções para identificar e remover promoções
duplicadas dentro de uma mesma execução do programa.

Por que precisamos disso?
- Ao buscar "smartphone" e "notebook", alguns produtos podem aparecer
  em ambas as buscas
- Queremos salvar cada produto apenas uma vez no banco de dados
"""

from __future__ import annotations

import hashlib  # Para criar hashes (identificadores únicos)
import logging  # Para registrar mensagens de log
from typing import List  # Para indicar que trabalhamos com listas

from promozone.models.promotion import Promotion

# Cria um logger específico para este módulo
logger = logging.getLogger(__name__)


def build_dedupe_key(promo: Promotion) -> str:
    """
    Gera uma chave única de deduplicação para uma promoção.

    A chave é um hash SHA256 (sequência de 64 caracteres hexadecimais)
    gerado a partir de: marketplace + item_id + price

    Por que incluir o preço?
    - Se o mesmo produto mudar de preço, queremos registrar como
      uma nova entrada (para rastrear histórico de preços)
    - Se o preço for igual, é considerado duplicata

    Estratégia:
        1. Cria uma string: "mercado_livre:MLB123456:999.90"
        2. Gera um hash SHA256 desta string
        3. O hash é sempre o mesmo para a mesma combinação

    Args:
        promo: Objeto Promotion para gerar a chave

    Retorna:
        str: Hash SHA256 de 64 caracteres (ex: "a3f5b2c...")

    Exemplo:
        promo = Promotion(item_id="MLB123", price=100.0, ...)
        key = build_dedupe_key(promo)
        # key = "a3f5b2c1d4e6f7a8b9c0d1e2f3a4b5c6..."
    """
    # Cria uma string combinando marketplace, item_id e price
    raw = f"{promo.marketplace}:{promo.item_id}:{promo.price}"

    # Gera o hash SHA256:
    # 1. raw.encode() converte a string para bytes
    # 2. hashlib.sha256() calcula o hash
    # 3. .hexdigest() converte o hash para string hexadecimal
    return hashlib.sha256(raw.encode()).hexdigest()


def deduplicate_in_memory(promotions: List[Promotion]) -> List[Promotion]:
    """
    Remove duplicatas dentro da mesma execução com base no dedupe_key.

    Esta função percorre a lista de promoções e mantém apenas a
    primeira ocorrência de cada dedupe_key única.

    Como funciona:
        1. Cria um conjunto (set) vazio para guardar as chaves já vistas
        2. Para cada promoção:
           - Se a chave já foi vista, pula (não adiciona na lista final)
           - Se é nova, adiciona na lista final e marca como vista
        3. Retorna a lista sem duplicatas

    Args:
        promotions: Lista de promoções que pode conter duplicatas

    Retorna:
        List[Promotion]: Lista sem duplicatas, preservando a primeira ocorrência

    Exemplo:
        promos = [promo1, promo2, promo1]  # promo1 aparece 2x
        unique = deduplicate_in_memory(promos)
        # unique = [promo1, promo2]  # apenas 2 itens
    """
    # Set (conjunto) para guardar as chaves já vistas
    # Set é eficiente para verificar se um item já existe
    seen: set[str] = set()

    # Lista para guardar as promoções únicas
    unique: List[Promotion] = []

    # Percorre cada promoção
    for promo in promotions:
        # Se a chave já foi vista, pula para a próxima
        if promo.dedupe_key in seen:
            continue

        # Se é nova, adiciona no conjunto de vistas
        seen.add(promo.dedupe_key)

        # E adiciona na lista de únicas
        unique.append(promo)

    # Calcula quantas duplicatas foram removidas
    removed = len(promotions) - len(unique)

    # Se removeu alguma, registra no log
    if removed > 0:
        logger.info(
            "Dedup em memória: %d duplicatas removidas de %d itens",
            removed,
            len(promotions),
        )

    return unique

