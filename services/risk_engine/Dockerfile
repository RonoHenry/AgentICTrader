# Build context is the repo root (see docker/docker-compose.yml)
FROM python:3.11-slim

WORKDIR /app

# curl is needed for the compose health-check probe
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY services/risk_engine/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

COPY services/risk_engine/ /app/services/risk_engine/
COPY services/__init__.py /app/services/__init__.py

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8004

CMD ["uvicorn", "services.risk_engine.main:app", "--host", "0.0.0.0", "--port", "8004"]
