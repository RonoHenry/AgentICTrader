# Build context is the repo root (see docker/docker-compose.yml)
FROM python:3.11-slim

WORKDIR /app

# curl is needed for the compose health-check probe
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/visual_model/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Service code + the pd_array_engine library it depends on (Candle,
# Timeframe, LiquidityMap types on the request/response schemas)
COPY pd_array_engine/ /app/pd_array_engine/
COPY services/visual_model/ /app/services/visual_model/
COPY services/__init__.py /app/services/__init__.py

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8005

CMD ["uvicorn", "services.visual_model.main:app", "--host", "0.0.0.0", "--port", "8005"]
