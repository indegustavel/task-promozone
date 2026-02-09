"""
FastAPI app — endpoints /health e /run.

API = Application Programming Interface (Interface de Programação de Aplicação)
É como um "menu de restaurante" que lista o que o sistema pode fazer.

Este arquivo define a API REST do PromoZone com 2 endpoints:
- GET /health: Verifica se o sistema está funcionando
- POST /run: Executa o pipeline de coleta de promoções

FastAPI é um framework moderno para criar APIs em Python.
Ele gera documentação automática e valida dados automaticamente.
"""

from __future__ import annotations

import logging
import os  # Para acessar variáveis de ambiente
from contextlib import asynccontextmanager  # Para gerenciar ciclo de vida da app

from fastapi import FastAPI, HTTPException  # Framework para criar a API

from promozone.config import get_settings
from promozone.logging_config import setup_logging
from promozone.services.pipeline import run_pipeline

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Gerencia o ciclo de vida da aplicação (startup e shutdown).

    Lifespan = tempo de vida da aplicação.

    Esta função é executada:
    - ANTES da aplicação começar a receber requisições (startup)
    - DEPOIS da aplicação parar de receber requisições (shutdown)

    É útil para:
    - Configurar logging
    - Configurar credenciais
    - Inicializar conexões
    - Limpar recursos ao encerrar

    O "yield" divide a função em duas partes:
    - Antes do yield = startup (inicialização)
    - Depois do yield = shutdown (limpeza)
    """
    # ===== STARTUP (INICIALIZAÇÃO) =====
    # Carrega as configurações
    settings = get_settings()

    # Configura o sistema de logging
    setup_logging(level=settings.log_level)

    # ===== CONFIGURAÇÃO DE CREDENCIAIS DO GOOGLE CLOUD =====
    # O cliente BigQuery procura credenciais na variável de ambiente
    # GOOGLE_APPLICATION_CREDENTIALS
    # Se configurada, define essa variável de ambiente
    if settings.google_application_credentials:
        os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = settings.google_application_credentials
        logger.info("Credenciais GCP configuradas: %s", settings.google_application_credentials)

    # Log de inicialização com informações importantes
    logger.info(
        "PromoZone iniciado | env=%s | fontes=%s",
        settings.environment,
        settings.ml_sources,
    )

    # ===== YIELD =====
    # Aqui a aplicação fica rodando e atendendo requisições
    yield

    # ===== SHUTDOWN (ENCERRAMENTO) =====
    # Código após o yield é executado quando a aplicação é encerrada
    logger.info("PromoZone encerrado")


# ===== CRIAÇÃO DA APLICAÇÃO FASTAPI =====
# Cria a instância principal da aplicação
app = FastAPI(
    title="PromoZone",  # Nome da API (aparece na documentação)
    description="Coletor de promoções do Mercado Livre",  # Descrição
    version="0.1.0",  # Versão da API
    lifespan=lifespan,  # Função de ciclo de vida definida acima
)


@app.get("/health")
def health():
    """
    Health check simples.

    Endpoint para verificar se a aplicação está funcionando.
    Útil para:
    - Monitoramento (sistemas de alerta)
    - Load balancers (distribuição de carga)
    - Cloud Run (verificação de saúde)

    Método HTTP: GET
    URL: /health

    Retorna:
        dict: {"status": "ok"}

    Exemplo de uso:
        curl http://localhost:8080/health
        # Resposta: {"status": "ok"}
    """
    return {"status": "ok"}


@app.post("/run")
def run_collector():
    """
    Dispara uma execução completa do pipeline de coleta.

    Este é o endpoint principal da aplicação.
    Quando chamado, executa todo o processo de coleta:
    1. Busca promoções no Mercado Livre
    2. Normaliza os dados
    3. Remove duplicatas
    4. Salva no BigQuery

    Método HTTP: POST (porque inicia uma ação/processo)
    URL: /run

    Retorna:
        dict: Estatísticas da execução com os campos:
            - execution_id: ID único desta execução
            - status: "success", "partial_error" ou "error"
            - sources_processed: Quantas fontes foram processadas
            - total_collected: Total de itens coletados
            - total_after_dedup: Total após remover duplicatas
            - total_loaded: Total gravado no BigQuery
            - errors: Lista de mensagens de erro (se houver)
            - duration_seconds: Duração da execução em segundos

    Códigos de status HTTP:
        - 200: Sucesso total
        - 207: Sucesso parcial (alguns erros, mas gravou algo)
        - 500: Erro fatal

    Exemplo de uso:
        curl -X POST http://localhost:8080/run
        # Resposta: {"execution_id": "...", "status": "success", ...}
    """
    try:
        # Carrega as configurações
        settings = get_settings()

        # Executa o pipeline completo
        result = run_pipeline(settings)

        # Define o código de status HTTP baseado no resultado
        # 200 = OK (sucesso total)
        # 207 = Multi-Status (sucesso parcial)
        status_code = 200 if result.status == "success" else 207

        # Retorna as estatísticas da execução
        return {
            "execution_id": result.execution_id,
            "status": result.status,
            "sources_processed": result.sources_processed,
            "total_collected": result.total_collected,
            "total_after_dedup": result.total_after_dedup,
            "total_loaded": result.total_loaded,
            "errors": result.errors,
            "duration_seconds": result.duration_seconds,
        }

    except Exception as exc:
        # Se houver erro não tratado, registra no log
        logger.exception("Erro ao executar pipeline")

        # Lança exceção HTTP 500 (Internal Server Error)
        # O FastAPI converte isso em resposta JSON automaticamente
        raise HTTPException(status_code=500, detail=str(exc)) from exc

