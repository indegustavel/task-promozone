"""
Configuração de logging estruturado para Cloud Run e local.

Logging é o sistema de registro de mensagens do programa.
É como um "diário" que registra tudo que acontece:
- Informações normais (INFO)
- Avisos (WARNING)
- Erros (ERROR)
- Detalhes técnicos para debug (DEBUG)

Este arquivo configura como essas mensagens serão formatadas e exibidas.
"""

from __future__ import annotations

import logging  # Biblioteca padrão do Python para logs
import sys  # Acesso a recursos do sistema (stdout, stderr, etc)


def setup_logging(level: str = "INFO") -> None:
    """
    Configura o sistema de logging da aplicação.

    Define:
    - Formato das mensagens de log
    - Nível de detalhamento (INFO, DEBUG, WARNING, ERROR)
    - Onde as mensagens serão enviadas (console/terminal)

    Args:
        level: Nível de log desejado. Opções:
               - "DEBUG": Mostra tudo, incluindo detalhes técnicos
               - "INFO": Mostra informações normais de operação
               - "WARNING": Mostra apenas avisos e erros
               - "ERROR": Mostra apenas erros

    Nota:
        Em produção (Cloud Run), o Google captura automaticamente
        tudo que é impresso no console e salva nos logs do Cloud.
    """

    # Converte a string do nível (ex: "INFO") para o valor numérico
    # que a biblioteca logging entende
    # Se o nível for inválido, usa INFO como padrão
    log_level = getattr(logging, level.upper(), logging.INFO)

    # Define o formato de cada linha de log
    # Exemplo de saída: "2024-01-15T10:30:45 | INFO     | promozone.api | Servidor iniciado"
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        # asctime: data/hora
        # levelname: nível (INFO, ERROR, etc) com 8 caracteres de largura
        # name: nome do módulo que gerou o log
        # message: a mensagem em si

        datefmt="%Y-%m-%dT%H:%M:%S",  # Formato da data/hora (ISO 8601)
    )

    # Cria um "handler" que envia os logs para o console (stdout)
    # stdout = standard output = saída padrão = terminal/console
    handler = logging.StreamHandler(stream=sys.stdout)
    handler.setFormatter(formatter)  # Aplica o formato definido acima

    # Obtém o logger raiz (pai de todos os loggers)
    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)  # Define o nível de log

    # Remove handlers existentes para evitar duplicação de mensagens
    # (importante quando a função é chamada mais de uma vez)
    root_logger.handlers.clear()

    # Adiciona nosso handler configurado
    root_logger.addHandler(handler)

    # ===== REDUZ VERBOSIDADE DE BIBLIOTECAS EXTERNAS =====
    # Bibliotecas externas geram muitos logs técnicos que não são úteis
    # Configuramos para mostrar apenas WARNING ou superior (WARNING, ERROR)

    # httpx e httpcore: bibliotecas de requisições HTTP
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

    # google: biblioteca do Google Cloud
    logging.getLogger("google").setLevel(logging.WARNING)

    # uvicorn.access: logs de cada requisição HTTP recebida
    # (pode ser muito verboso em produção)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

