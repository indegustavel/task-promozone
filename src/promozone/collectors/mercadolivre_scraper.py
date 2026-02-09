"""Cliente que coleta dados do Mercado Livre via web scraping do HTML.

Alternativa ao MercadoLivreClient (API REST) quando a API pública
está retornando 403 Forbidden. Extrai JSON embutido no HTML
renderizado pelo servidor (SSR) do Mercado Livre.
"""

from __future__ import annotations

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

ML_SEARCH_BASE = "https://lista.mercadolivre.com.br"
ML_OFFERS_URL = "https://www.mercadolivre.com.br/ofertas"


class MercadoLivreScraperClient:
    """Coleta dados do ML via scraping do HTML (SSR JSON embutido)."""

    def __init__(
        self,
        delay_seconds: float = 1.0,
        max_items: int = 50,
        timeout: float = 30.0,
    ) -> None:
        self.delay_seconds = delay_seconds
        self.max_items = max_items
        self.timeout = timeout

        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        self._client = httpx.Client(
            timeout=self.timeout, headers=headers, follow_redirects=True,
        )
        logger.info("🌐 Scraper client inicializado (max_items=%d)", max_items)

    def close(self) -> None:
        self._client.close()

    @retry(
        retry=retry_if_exception_type((httpx.TransportError,)),
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    def _fetch_html(self, url: str) -> str:
        """Busca HTML de uma URL com retry."""
        logger.debug("GET (HTML) %s", url)
        response = self._client.get(url)
        response.raise_for_status()
        return response.text

    def _extract_ssr_json(self, html: str) -> Optional[dict]:
        """Extrai o JSON SSR embutido no script _n.ctx.r do HTML."""
        match = re.search(
            r'_n\.ctx\.r\s*=\s*({.*?});_n\.ctx\.r\.assets',
            html,
            re.DOTALL,
        )
        if not match:
            logger.warning("JSON SSR (_n.ctx.r) não encontrado no HTML")
            return None
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            logger.exception("Erro ao parsear JSON SSR")
            return None

    def _polycard_to_raw_item(self, polycard: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Converte um polycard para o formato esperado pelo parser."""
        metadata = polycard.get("metadata", {})
        item_id = metadata.get("id", "")
        if not item_id:
            return None

        components = polycard.get("components", [])

        title = ""
        price = None
        original_price = None
        seller_name = None
        permalink = ""

        for comp in components:
            ctype = comp.get("type", "")

            if ctype == "title":
                title = comp.get("title", {}).get("text", "")

            elif ctype == "price":
                price_data = comp.get("price", {})
                current = price_data.get("current_price", {})
                previous = price_data.get("previous_price", {})
                price = current.get("value")
                original_price = previous.get("value")

            elif ctype == "seller":
                raw_text = comp.get("seller", {}).get("text", "")
                # Remove ícones tipo {icon_cockade}
                seller_name = re.sub(r'\{[^}]+\}', '', raw_text).strip()

        # Construir URL do item
        permalink = f"https://www.mercadolivre.com.br/p/{item_id}"

        # Imagem
        pictures = polycard.get("pictures", {}).get("pictures", [])
        thumbnail = ""
        if pictures:
            pic_id = pictures[0].get("id", "")
            if pic_id:
                thumbnail = f"https://http2.mlstatic.com/D_NQ_NP_{pic_id}-O.webp"

        if price is None:
            return None

        return {
            "id": item_id,
            "title": title,
            "price": price,
            "original_price": original_price,
            "permalink": permalink,
            "thumbnail": thumbnail,
            "seller": {"nickname": seller_name} if seller_name else {},
            "category_id": metadata.get("category_id", ""),
            "domain_id": metadata.get("domain_id", ""),
        }

    def _extract_items_from_html(self, html: str) -> List[Dict[str, Any]]:
        """Extrai itens do HTML, convertendo polycards em formato padrão."""
        data = self._extract_ssr_json(html)
        if not data:
            return []

        try:
            results = (
                data.get("appProps", {})
                .get("pageProps", {})
                .get("initialState", {})
                .get("results", [])
            )
        except (AttributeError, TypeError):
            logger.warning("Estrutura inesperada no JSON SSR")
            return []

        raw_items: List[Dict[str, Any]] = []
        for result in results:
            polycard = result.get("polycard") if isinstance(result, dict) else None
            if not polycard:
                continue
            item = self._polycard_to_raw_item(polycard)
            if item:
                raw_items.append(item)

        logger.info("Extraídos %d itens do HTML (%d polycards)", len(raw_items), len(results))
        return raw_items

    def search(self, query: str) -> List[Dict[str, Any]]:
        """Busca itens no ML via scraping, retornando no formato padrão do parser.

        Retorna lista de dicts no mesmo formato que MercadoLivreClient.search().
        """
        url = f"{ML_SEARCH_BASE}/{quote_plus(query)}"
        logger.info("Scraping query=%r url=%s", query, url)

        html = self._fetch_html(url)
        items = self._extract_items_from_html(html)

        logger.info("Scraping query=%r: %d itens coletados", query, len(items))

        # Respeita rate limiting
        time.sleep(self.delay_seconds)

        return items[: self.max_items]

