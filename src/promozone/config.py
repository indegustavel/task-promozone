"""
Configuração centralizada via variáveis de ambiente.

Este arquivo é responsável por ler todas as configurações do sistema
a partir de variáveis de ambiente (ou arquivo .env).
Isso permite que o mesmo código funcione em diferentes ambientes
(local, desenvolvimento, produção) apenas mudando as variáveis.
"""

from __future__ import annotations

import json
from typing import List

# Pydantic é uma biblioteca que valida dados automaticamente
# Field: define propriedades de cada campo (valor padrão, descrição, etc)
# field_validator: permite criar validações customizadas
# BaseSettings: classe base que lê variáveis de ambiente automaticamente
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings


class SourceConfig:
    """
    Representa uma fonte/consulta de coleta do Mercado Livre.

    Por exemplo: se queremos buscar "smartphone" e "notebook",
    teremos 2 objetos SourceConfig, um para cada busca.

    Atributos:
        query: O termo que será buscado no Mercado Livre (ex: "smartphone")
        source: Um nome identificador para essa busca (ex: "busca_smartphone")
    """

    def __init__(self, query: str, source: str) -> None:
        # Armazena o termo de busca (ex: "smartphone")
        self.query = query
        # Armazena o identificador da fonte (ex: "busca_smartphone")
        self.source = source

    def __repr__(self) -> str:
        """
        Define como o objeto será exibido quando impresso.
        Útil para debug e logs.
        """
        return f"SourceConfig(query={self.query!r}, source={self.source!r})"


class Settings(BaseSettings):
    """
    Configurações lidas de variáveis de ambiente (ou arquivo .env).

    Esta classe herda de BaseSettings, que automaticamente:
    1. Lê variáveis de ambiente do sistema
    2. Lê do arquivo .env se existir
    3. Valida os tipos de dados
    4. Fornece valores padrão quando não especificado

    Exemplo de uso:
        settings = Settings()
        print(settings.bq_project_id)  # Imprime o ID do projeto
    """

    # ===== CONFIGURAÇÕES DO GOOGLE CLOUD =====
    # Caminho para o arquivo JSON com credenciais do Google Cloud
    # Usado apenas em ambiente local. No Cloud Run, as credenciais
    # são fornecidas automaticamente pelo ambiente
    google_application_credentials: str = Field(
        default="", description="Caminho para chave de serviço (apenas local)"
    )

    # ===== CONFIGURAÇÕES DO BIGQUERY =====
    # BigQuery é o banco de dados onde salvamos as promoções coletadas

    # ID do projeto no Google Cloud (obrigatório, por isso tem "...")
    bq_project_id: str = Field(..., description="GCP project ID")

    # Nome do dataset (conjunto de tabelas) no BigQuery
    bq_dataset: str = Field(default="promozone", description="BigQuery dataset")

    # Nome da tabela final onde ficam as promoções únicas
    bq_table: str = Field(default="promotions", description="Tabela final")

    # Nome da tabela temporária usada antes de inserir na tabela final
    # Isso ajuda a evitar duplicatas
    bq_staging_table: str = Field(
        default="promotions_staging", description="Tabela de staging"
    )

    # ===== CONFIGURAÇÕES DO MERCADO LIVRE =====
    # Define quais buscas serão feitas no Mercado Livre

    # String JSON com lista de buscas a serem feitas
    # Exemplo: [{"query": "smartphone", "source": "busca_smartphone"}]
    ml_sources: str = Field(
        default='[{"query": "smartphone", "source": "busca_smartphone"}]',
        description="JSON array com as fontes de coleta",
    )

    # Quantos itens coletar no máximo por busca
    ml_max_items_per_source: int = Field(
        default=50, description="Máximo de itens por fonte"
    )

    # Tempo de espera (em segundos) entre cada requisição ao Mercado Livre
    # Isso evita sobrecarregar o servidor deles (rate limiting)
    ml_request_delay_seconds: float = Field(
        default=1.0, description="Delay entre requests (rate limiting)"
    )

    # ===== CONFIGURAÇÕES GERAIS =====
    # Nível de detalhamento dos logs (DEBUG, INFO, WARNING, ERROR)
    log_level: str = Field(default="INFO")

    # Ambiente de execução (local, development, production)
    environment: str = Field(default="local")

    # Porta onde a API vai rodar
    port: int = Field(default=8080)

    # Configuração do Pydantic sobre como ler as variáveis
    model_config = {
        "env_file": ".env",  # Lê do arquivo .env se existir
        "env_file_encoding": "utf-8",  # Codificação do arquivo
        "extra": "ignore",  # Ignora variáveis de ambiente que não estão mapeadas aqui
    }

    @field_validator("ml_sources", mode="before")
    @classmethod
    def _validate_ml_sources(cls, v: str) -> str:
        """
        Valida que ml_sources é um JSON array válido.

        Este método é executado automaticamente pelo Pydantic
        antes de atribuir o valor ao campo ml_sources.

        Garante que:
        1. O valor é um JSON válido
        2. O JSON é uma lista (array)

        Se algo estiver errado, lança um erro explicativo.
        """
        try:
            # Tenta converter a string JSON em objeto Python
            parsed = json.loads(v)

            # Verifica se é uma lista
            if not isinstance(parsed, list):
                raise ValueError("ml_sources deve ser um JSON array")
        except json.JSONDecodeError as exc:
            # Se não conseguir fazer o parse, lança erro
            raise ValueError(f"ml_sources não é JSON válido: {exc}") from exc

        # Se tudo OK, retorna o valor original
        return v

    def get_sources(self) -> List[SourceConfig]:
        """
        Retorna lista de SourceConfig a partir do JSON.

        Converte a string JSON armazenada em ml_sources
        em uma lista de objetos SourceConfig que são mais
        fáceis de trabalhar no código.

        Exemplo:
            settings = Settings()
            sources = settings.get_sources()
            for source in sources:
                print(source.query)  # Imprime "smartphone", "notebook", etc
        """
        # Converte a string JSON em lista de dicionários
        raw = json.loads(self.ml_sources)

        # Para cada dicionário, cria um objeto SourceConfig
        return [SourceConfig(query=s["query"], source=s["source"]) for s in raw]

    @property
    def bq_full_table(self) -> str:
        """
        Retorna o nome completo da tabela final no BigQuery.

        No BigQuery, o nome completo é: projeto.dataset.tabela
        Exemplo: "meu-projeto.promozone.promotions"

        @property faz com que possamos usar como: settings.bq_full_table
        (sem parênteses, como se fosse um atributo)
        """
        return f"{self.bq_project_id}.{self.bq_dataset}.{self.bq_table}"

    @property
    def bq_full_staging_table(self) -> str:
        """
        Retorna o nome completo da tabela de staging no BigQuery.

        Similar ao bq_full_table, mas para a tabela temporária.
        Exemplo: "meu-projeto.promozone.promotions_staging"
        """
        return f"{self.bq_project_id}.{self.bq_dataset}.{self.bq_staging_table}"


def get_settings() -> Settings:
    """
    Factory para obter as configurações.

    Esta função cria e retorna um objeto Settings.
    Usar uma função ao invés de criar o objeto diretamente
    facilita os testes (podemos substituir por configurações falsas).

    Retorna:
        Settings: Objeto com todas as configurações carregadas
    """
    return Settings()

