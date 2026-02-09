"""Testes para o parser do Mercado Livre."""

from promozone.collectors.mercadolivre_parser import parse_items, _calc_discount


def _make_raw_item(**overrides):
    """Helper para criar um item cru da API do ML."""
    base = {
        "id": "MLB12345",
        "title": "Produto Teste",
        "price": 100.0,
        "original_price": 200.0,
        "permalink": "https://www.mercadolivre.com.br/item/MLB12345",
        "thumbnail": "https://http2.mlstatic.com/D_NQ_NP_123.jpg",
        "seller": {"nickname": "VENDEDOR_TESTE"},
    }
    base.update(overrides)
    return base


def test_parse_single_item():
    """Parseia um item válido."""
    raw = [_make_raw_item()]
    result = parse_items(raw, source="test_source")
    assert len(result) == 1
    promo = result[0]
    assert promo.item_id == "MLB12345"
    assert promo.price == 100.0
    assert promo.original_price == 200.0
    assert promo.seller == "VENDEDOR_TESTE"
    assert promo.source == "test_source"


def test_parse_item_without_price_is_skipped():
    """Item sem preço é ignorado."""
    raw = [_make_raw_item(price=None)]
    result = parse_items(raw, source="test")
    assert len(result) == 0


def test_parse_item_without_id_is_skipped():
    """Item sem ID é ignorado."""
    raw = [_make_raw_item(id="")]
    result = parse_items(raw, source="test")
    assert len(result) == 0


def test_calc_discount():
    """Calcula desconto corretamente."""
    assert _calc_discount(80.0, 100.0) == 20.0
    assert _calc_discount(100.0, None) is None
    assert _calc_discount(100.0, 100.0) is None  # sem desconto
    assert _calc_discount(100.0, 50.0) is None  # preço maior que original


def test_parse_multiple_items():
    """Parseia múltiplos itens."""
    raw = [
        _make_raw_item(id="MLB001", price=50.0),
        _make_raw_item(id="MLB002", price=75.0),
        _make_raw_item(id="MLB003", price=None),  # será ignorado
    ]
    result = parse_items(raw, source="multi")
    assert len(result) == 2


def test_parse_item_with_official_store():
    """Extrai seller de official_store_name como fallback."""
    raw = [_make_raw_item(seller={}, official_store_name="Loja Oficial")]
    result = parse_items(raw, source="test")
    assert result[0].seller == "Loja Oficial"

