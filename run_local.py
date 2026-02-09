"""Script para rodar o servidor localmente."""
import sys
import os

# Adiciona src ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

if __name__ == "__main__":
    import uvicorn
    # Usa porta 8080 (padrão)
    uvicorn.run("promozone.api.main:app", host="0.0.0.0", port=8080, reload=True)

