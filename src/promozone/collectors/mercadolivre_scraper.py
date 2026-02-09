"""
Cliente que coleta dados do Mercado Livre via web scraping do HTML.

Web Scraping = técnica de extrair dados de páginas web.

Por que usar scraping ao invés da API?
- A API pública do Mercado Livre às vezes retorna erro 403 (Forbidden)
- O scraping acessa a página como um navegador normal faria
- Extrai os dados do HTML da página

Como funciona?
1. Acessa a página de busca do Mercado Livre (como um navegador)
2. Baixa o HTML da página
3. Extrai o JSON embutido no HTML (SSR = Server-Side Rendering)
4. Converte os dados para o formato que nosso sistema entende

SSR (Server-Side Rendering):
- O Mercado Livre gera a página no servidor e inclui os dados em JSON
- Esse JSON fica embutido no HTML dentro de tags <script>
- Podemos extrair esse JSON sem precisar da API
"""

from __future__ import annotations

import json  # Para trabalhar com dados JSON
import logging  # Para registrar mensagens
import re  # Para expressões regulares (buscar padrões no texto)
import time  # Para adicionar delays entre requisições
from typing import Any, Dict, List, Optional
from urllib.parse import quote_plus  # Para codificar URLs (ex: "fone de ouvido" -> "fone+de+ouvido")

import httpx  # Biblioteca para fazer requisições HTTP
from tenacity import (  # Biblioteca para retry (tentar novamente em caso de erro)
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

logger = logging.getLogger(__name__)

# URLs base do Mercado Livre
ML_SEARCH_BASE = "https://lista.mercadolivre.com.br"
ML_OFFERS_URL = "https://www.mercadolivre.com.br/ofertas"


class MercadoLivreScraperClient:
    """
    Coleta dados do ML via scraping do HTML (SSR JSON embutido).

    Esta classe é responsável por:
    1. Fazer requisições HTTP para o Mercado Livre
    2. Baixar o HTML das páginas
    3. Extrair os dados JSON embutidos no HTML
    4. Converter para o formato que nosso sistema entende
    """

    def __init__(
        self,
        delay_seconds: float = 1.0,
        max_items: int = 50,
        timeout: float = 30.0,
    ) -> None:
        """
        Inicializa o cliente de scraping.

        Args:
            delay_seconds: Tempo de espera entre requisições (rate limiting)
            max_items: Número máximo de itens a coletar por busca
            timeout: Tempo máximo de espera por uma resposta (em segundos)
        """
        self.delay_seconds = delay_seconds
        self.max_items = max_items
        self.timeout = timeout

        # Headers HTTP que simulam um navegador real
        # Isso é importante para o servidor não bloquear nossa requisição
        headers = {
            # User-Agent: identifica o navegador
            # Usamos o do Chrome para parecer uma requisição normal
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            # Accept: tipos de conteúdo que aceitamos
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            # Accept-Language: idiomas preferidos
            "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
        }

        # Cria o cliente HTTP com as configurações
        # follow_redirects=True: segue redirecionamentos automaticamente
        self._client = httpx.Client(
            timeout=self.timeout,
            headers=headers,
            follow_redirects=True,
        )

        logger.info("🌐 Scraper client inicializado (max_items=%d)", max_items)

    def close(self) -> None:
        """
        Fecha o cliente HTTP e libera recursos.

        Importante chamar este método quando terminar de usar o scraper
        para evitar vazamento de recursos (conexões abertas).
        """
        self._client.close()

    @retry(
        # Configuração do retry (tentar novamente em caso de erro)
        retry=retry_if_exception_type((httpx.TransportError,)),  # Tenta novamente apenas para erros de rede
        stop=stop_after_attempt(3),  # Tenta no máximo 3 vezes
        wait=wait_exponential(multiplier=1, min=2, max=10),  # Espera exponencial: 2s, 4s, 8s (máx 10s)
        reraise=True,  # Se falhar 3 vezes, lança o erro
    )
    def _fetch_html(self, url: str) -> str:
        """
        Busca o HTML de uma URL com retry automático.

        Se houver erro de rede (conexão perdida, timeout, etc),
        tenta novamente até 3 vezes com espera crescente entre tentativas.

        Args:
            url: URL da página a ser baixada

        Retorna:
            str: Conteúdo HTML da página

        Raises:
            httpx.HTTPStatusError: Se o servidor retornar erro (404, 500, etc)
            httpx.TransportError: Se houver erro de rede após 3 tentativas
        """
        logger.debug("GET (HTML) %s", url)

        # Faz a requisição HTTP GET
        response = self._client.get(url)

        # Verifica se houve erro (status 4xx ou 5xx)
        # Se sim, lança uma exceção
        response.raise_for_status()

        # Retorna o conteúdo HTML como string
        return response.text

    def _extract_ssr_json(self, html: str) -> Optional[dict]:
        """
        Extrai o JSON SSR embutido no HTML.

        O Mercado Livre inclui os dados dos produtos em um JSON
        dentro de uma tag <script> no HTML. Este JSON está na variável
        JavaScript "_n.ctx.r".

        Exemplo do que procuramos no HTML:
            <script>
                _n.ctx.r = {"appProps": {...}, "pageProps": {...}};
                _n.ctx.r.assets = ...
            </script>

        Args:
            html: Conteúdo HTML da página

        Retorna:
            dict ou None: Dicionário com os dados, ou None se não encontrar
        """
        # Usa expressão regular para encontrar o padrão no HTML
        # r'...' = raw string (não interpreta \n, \t, etc)
        # _n\.ctx\.r\s*=\s* = procura "_n.ctx.r = "
        # ({.*?}) = captura tudo entre { e } (o JSON)
        # re.DOTALL = permite que . capture quebras de linha
        match = re.search(
            r'_n\.ctx\.r\s*=\s*({.*?});_n\.ctx\.r\.assets',
            html,
            re.DOTALL,
        )

        # Se não encontrou o padrão, retorna None
        if not match:
            logger.warning("JSON SSR (_n.ctx.r) não encontrado no HTML")
            return None

        try:
            # match.group(1) = o conteúdo capturado entre parênteses (o JSON)
            # json.loads() converte a string JSON em dicionário Python
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            # Se o JSON estiver malformado, registra o erro e retorna None
            logger.exception("Erro ao parsear JSON SSR")
            return None

    def _polycard_to_raw_item(self, polycard: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """
        Converte um "polycard" para o formato esperado pelo parser.

        Polycard é o formato que o Mercado Livre usa internamente para
        representar um produto no JSON SSR. Cada polycard tem:
        - metadata: informações básicas (ID, categoria)
        - components: lista de componentes (título, preço, vendedor, etc)
        - pictures: imagens do produto

        Esta função extrai essas informações e converte para o formato
        padrão que nosso parser entende (mesmo formato da API REST).

        Args:
            polycard: Dicionário com dados do produto no formato polycard

        Retorna:
            dict ou None: Dicionário no formato padrão, ou None se inválido
        """
        # ===== EXTRAÇÃO DE METADADOS =====
        metadata = polycard.get("metadata", {})
        item_id = metadata.get("id", "")

        # Se não tem ID, não podemos processar
        if not item_id:
            return None

        # ===== EXTRAÇÃO DE COMPONENTES =====
        # Components é uma lista de objetos, cada um com um tipo
        # (title, price, seller, etc)
        components = polycard.get("components", [])

        # Variáveis para armazenar os dados extraídos
        title = ""
        price = None
        original_price = None
        seller_name = None
        permalink = ""

        # Percorre cada componente procurando os dados que precisamos
        for comp in components:
            ctype = comp.get("type", "")

            # Componente de título
            if ctype == "title":
                title = comp.get("title", {}).get("text", "")

            # Componente de preço
            elif ctype == "price":
                price_data = comp.get("price", {})
                current = price_data.get("current_price", {})
                previous = price_data.get("previous_price", {})
                price = current.get("value")
                original_price = previous.get("value")

            # Componente de vendedor
            elif ctype == "seller":
                raw_text = comp.get("seller", {}).get("text", "")
                # Remove ícones que vêm no formato {icon_cockade}
                # re.sub substitui o padrão por string vazia
                seller_name = re.sub(r'\{[^}]+\}', '', raw_text).strip()

        # ===== CONSTRUÇÃO DA URL DO PRODUTO =====
        permalink = f"https://www.mercadolivre.com.br/p/{item_id}"

        # ===== EXTRAÇÃO DA IMAGEM =====
        pictures = polycard.get("pictures", {}).get("pictures", [])
        thumbnail = ""
        if pictures:
            # Pega o ID da primeira imagem
            pic_id = pictures[0].get("id", "")
            if pic_id:
                # Constrói a URL da imagem no CDN do Mercado Livre
                thumbnail = f"https://http2.mlstatic.com/D_NQ_NP_{pic_id}-O.webp"

        # ===== VALIDAÇÃO =====
        # Se não tem preço, não podemos usar este item
        if price is None:
            return None

        # ===== RETORNO NO FORMATO PADRÃO =====
        # Retorna um dicionário no mesmo formato que a API REST retornaria
        # Isso permite que o parser funcione com ambas as fontes de dados
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
        """
        Extrai itens do HTML, convertendo polycards em formato padrão.

        Processo:
        1. Extrai o JSON SSR do HTML
        2. Navega pela estrutura do JSON até encontrar os resultados
        3. Para cada resultado (polycard), converte para formato padrão
        4. Retorna lista de itens no formato padrão

        Args:
            html: Conteúdo HTML da página

        Retorna:
            List[Dict]: Lista de itens no formato padrão (compatível com parser)
        """
        # Extrai o JSON embutido no HTML
        data = self._extract_ssr_json(html)
        if not data:
            return []

        # Navega pela estrutura do JSON para encontrar os resultados
        # A estrutura é: data -> appProps -> pageProps -> initialState -> results
        try:
            results = (
                data.get("appProps", {})
                .get("pageProps", {})
                .get("initialState", {})
                .get("results", [])
            )
        except (AttributeError, TypeError):
            # Se a estrutura for diferente do esperado, registra aviso
            logger.warning("Estrutura inesperada no JSON SSR")
            return []

        # Lista para armazenar os itens convertidos
        raw_items: List[Dict[str, Any]] = []

        # Processa cada resultado
        for result in results:
            # Extrai o polycard do resultado
            polycard = result.get("polycard") if isinstance(result, dict) else None
            if not polycard:
                continue  # Pula se não tem polycard

            # Converte o polycard para formato padrão
            item = self._polycard_to_raw_item(polycard)
            if item:
                raw_items.append(item)

        logger.info("Extraídos %d itens do HTML (%d polycards)", len(raw_items), len(results))
        return raw_items

    def search(self, query: str) -> List[Dict[str, Any]]:
        """
        Busca itens no ML via scraping, retornando no formato padrão do parser.

        Esta é a função principal que deve ser chamada para fazer uma busca.
        Ela coordena todo o processo:
        1. Constrói a URL de busca
        2. Baixa o HTML
        3. Extrai os itens
        4. Respeita rate limiting
        5. Retorna os itens

        Args:
            query: Termo de busca (ex: "smartphone")

        Retorna:
            List[Dict]: Lista de itens no formato padrão, limitada a max_items.
                        Mesmo formato que MercadoLivreClient.search() retornaria.

        Exemplo:
            scraper = MercadoLivreScraperClient()
            items = scraper.search("smartphone")
            # items = [{"id": "MLB123", "price": 999, ...}, ...]
        """
        # Constrói a URL de busca
        # quote_plus codifica o termo (ex: "fone de ouvido" -> "fone+de+ouvido")
        url = f"{ML_SEARCH_BASE}/{quote_plus(query)}"
        logger.info("Scraping query=%r url=%s", query, url)

        # Baixa o HTML da página
        html = self._fetch_html(url)

        # Extrai os itens do HTML
        items = self._extract_items_from_html(html)

        logger.info("Scraping query=%r: %d itens coletados", query, len(items))

        # Respeita rate limiting (espera antes da próxima requisição)
        # Isso evita sobrecarregar o servidor do Mercado Livre
        time.sleep(self.delay_seconds)

        # Retorna apenas os primeiros max_items itens
        return items[: self.max_items]

