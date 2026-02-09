"""Cliente HTTP para a API pública do Mercado Livre."""

from __future__ import annotations

import logging
import time
from typing import Any, Dict, List, Optional

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# API pública de busca do Mercado Livre (Brasil)
ML_SEARCH_URL = "https://api.mercadolibre.com/sites/MLB/search"


class MercadoLivreClient:
    """Faz requisições à API pública do Mercado Livre com rate limiting e retries."""

    def __init__(
        self,
        delay_seconds: float = 1.0,
        max_items: int = 50,
        timeout: float = 30.0,
    ) -> None:
        self.delay_seconds = delay_seconds
        self.max_items = max_items
        self.timeout = timeout

        # Headers para evitar 403 (simula navegador real)
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.mercadolivre.com.br/",
            "Origin": "https://www.mercadolivre.com.br",
        }
        self._client = httpx.Client(timeout=self.timeout, headers=headers, follow_redirects=True)

    def close(self) -> None:
        self._client.close()

    @retry(
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.TransportError)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _get(self, url: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """GET com retry e backoff exponencial."""
        logger.debug("GET %s params=%s", url, params)
        response = self._client.get(url, params=params)
        response.raise_for_status()
        return response.json()

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Busca itens no Mercado Livre, paginando até max_items.

        Retorna lista de dicts crus da API (campo 'results').
        """
        all_results: List[Dict[str, Any]] = []
        offset = 0
        limit = min(50, self.max_items)  # API aceita no máximo 50 por página

        while len(all_results) < self.max_items:
            params = {"q": query, "offset": offset, "limit": limit}
            logger.info(
                "Buscando query=%r offset=%d limit=%d", query, offset, limit
            )

            data = self._get(ML_SEARCH_URL, params=params)
            results = data.get("results", [])

            if not results:
                logger.info("Sem mais resultados para query=%r", query)
                break

            all_results.extend(results)
            offset += len(results)

            # Respeita rate limiting
            time.sleep(self.delay_seconds)

        # Trunca ao máximo configurado
        return all_results[: self.max_items]

