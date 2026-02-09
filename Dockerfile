FROM python:3.11-slim

WORKDIR /app

# Instala dependências primeiro (cache de camada Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia código-fonte
COPY src/ ./src/

ENV PYTHONPATH=/app/src
ENV PORT=8080

EXPOSE 8080

CMD ["uvicorn", "promozone.api.main:app", "--host", "0.0.0.0", "--port", "8080"]

