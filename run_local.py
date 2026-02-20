"""Script para rodar o servidor localmente."""
import sys
import os

# Adiciona src ao path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

if __name__ == "__main__":
    import uvicorn
    # Usa 127.0.0.1 para funcionar no Windows
    # Acesse em: http://localhost:8080 ou http://127.0.0.1:8080
    print("🚀 Servidor iniciando em http://localhost:8080")
    print("📝 Acesse http://localhost:8080/docs para ver a documentação da API")
    uvicorn.run("promozone.api.main:app", host="127.0.0.1", port=8080, reload=True)

