"""Testes para o pipeline (com mocks)."""

from unittest.mock import MagicMock, patch

from promozone.services.pipeline import run_pipeline


def _make_settings():
    """Cria settings mock para testes."""
    from promozone.config import Settings, SourceConfig

    settings = MagicMock(spec=Settings)
    settings.ml_request_delay_seconds = 0.0
    settings.ml_max_items_per_source = 5
    settings.get_sources.return_value = [
        SourceConfig(query="test", source="test_source")
    ]
    settings.bq_project_id = "test-project"
    settings.bq_dataset = "test_dataset"
    settings.bq_table = "promotions"
    settings.bq_staging_table = "promotions_staging"
    settings.bq_full_table = "test-project.test_dataset.promotions"
    settings.bq_full_staging_table = "test-project.test_dataset.promotions_staging"
    return settings


@patch("promozone.services.pipeline.BigQueryRepository")
@patch("promozone.services.pipeline.MercadoLivreScraperClient")
def test_pipeline_success(mock_client_cls, mock_bq_cls):
    """Pipeline executa com sucesso e retorna resultado."""
    # Mock do client
    mock_client = MagicMock()
    mock_client.search.return_value = [
        {
            "id": "MLB1",
            "title": "Produto",
            "price": 100.0,
            "original_price": 200.0,
            "permalink": "https://example.com/MLB1",
            "thumbnail": "https://example.com/img.jpg",
            "seller": {"nickname": "Vendedor"},
        }
    ]
    mock_client_cls.return_value = mock_client

    # Mock do BigQuery
    mock_bq = MagicMock()
    mock_bq.upsert_promotions.return_value = 1
    mock_bq_cls.return_value = mock_bq

    settings = _make_settings()
    result = run_pipeline(settings)

    assert result.status == "success"
    assert result.total_collected == 1
    assert result.total_after_dedup == 1
    assert result.total_loaded == 1
    assert len(result.errors) == 0
    mock_bq.ensure_dataset_and_tables.assert_called_once()


@patch("promozone.services.pipeline.BigQueryRepository")
@patch("promozone.services.pipeline.MercadoLivreScraperClient")
def test_pipeline_handles_source_error(mock_client_cls, mock_bq_cls):
    """Pipeline trata erro em uma fonte sem crashar."""
    mock_client = MagicMock()
    mock_client.search.side_effect = Exception("API error")
    mock_client_cls.return_value = mock_client

    mock_bq = MagicMock()
    mock_bq.upsert_promotions.return_value = 0
    mock_bq_cls.return_value = mock_bq

    settings = _make_settings()
    result = run_pipeline(settings)

    assert result.total_collected == 0
    assert len(result.errors) == 1
    assert "API error" in result.errors[0]

