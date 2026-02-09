"""Testes para a lógica de deduplicação."""

from promozone.models.promotion import Promotion
from promozone.services.dedup import build_dedupe_key, deduplicate_in_memory


def _make_promo(item_id: str = "MLB1", price: float = 100.0) -> Promotion:
    return Promotion(
        item_id=item_id,
        url=f"https://example.com/{item_id}",
        title="Produto",
        price=price,
        source="test",
    )


def test_build_dedupe_key_deterministic():
    """Mesma entrada gera mesma chave."""
    p1 = _make_promo("MLB1", 100.0)
    p2 = _make_promo("MLB1", 100.0)
    assert build_dedupe_key(p1) == build_dedupe_key(p2)


def test_build_dedupe_key_different_price():
    """Preço diferente gera chave diferente."""
    p1 = _make_promo("MLB1", 100.0)
    p2 = _make_promo("MLB1", 90.0)
    assert build_dedupe_key(p1) != build_dedupe_key(p2)


def test_build_dedupe_key_different_item():
    """Item diferente gera chave diferente."""
    p1 = _make_promo("MLB1", 100.0)
    p2 = _make_promo("MLB2", 100.0)
    assert build_dedupe_key(p1) != build_dedupe_key(p2)


def test_deduplicate_in_memory_removes_dupes():
    """Remove duplicatas com mesmo dedupe_key."""
    p1 = _make_promo("MLB1", 100.0)
    p2 = _make_promo("MLB1", 100.0)
    p1.dedupe_key = build_dedupe_key(p1)
    p2.dedupe_key = build_dedupe_key(p2)

    result = deduplicate_in_memory([p1, p2])
    assert len(result) == 1


def test_deduplicate_in_memory_keeps_unique():
    """Mantém itens com dedupe_key diferente."""
    p1 = _make_promo("MLB1", 100.0)
    p2 = _make_promo("MLB2", 200.0)
    p1.dedupe_key = build_dedupe_key(p1)
    p2.dedupe_key = build_dedupe_key(p2)

    result = deduplicate_in_memory([p1, p2])
    assert len(result) == 2

