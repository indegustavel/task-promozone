"""Testes para o modelo Promotion."""

from promozone.models.promotion import Promotion


def test_promotion_defaults():
    """Verifica que campos obrigatórios e defaults funcionam."""
    promo = Promotion(
        item_id="MLB123",
        url="https://example.com/item",
        title="Smartphone X",
        price=999.90,
        source="busca_smartphone",
    )
    assert promo.marketplace == "mercado_livre"
    assert promo.item_id == "MLB123"
    assert promo.price == 999.90
    assert promo.original_price is None
    assert promo.discount_percent is None
    assert promo.collected_at is not None


def test_promotion_with_discount():
    """Verifica promoção com preço original e desconto."""
    promo = Promotion(
        item_id="MLB456",
        url="https://example.com/item2",
        title="Notebook Y",
        price=3500.00,
        original_price=5000.00,
        discount_percent=30.0,
        source="busca_notebook",
    )
    assert promo.original_price == 5000.00
    assert promo.discount_percent == 30.0


def test_to_bq_row():
    """Verifica conversão para dict compatível com BigQuery."""
    promo = Promotion(
        item_id="MLB789",
        url="https://example.com/item3",
        title="Fone Z",
        price=150.00,
        source="busca_fone",
        dedupe_key="abc123",
        execution_id="exec-001",
    )
    row = promo.to_bq_row()
    assert isinstance(row, dict)
    assert row["item_id"] == "MLB789"
    assert row["dedupe_key"] == "abc123"
    assert isinstance(row["collected_at"], str)  # ISO format

