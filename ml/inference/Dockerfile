# Build context is the repo root (see docker/docker-compose.yml)
FROM python:3.11-slim

WORKDIR /app

# curl is needed for the compose health-check probe;
# libgomp1 is required at runtime by scikit-learn/mlflow's sklearn flavor.
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY ml/inference/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# The inference service imports from ml.features.*, so the whole ml/ package
# (minus training scripts excluded via .dockerignore-level pruning) is copied.
COPY ml/ /app/ml/

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INFERENCE_PORT=8001

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8001

CMD ["uvicorn", "ml.inference.main:app", "--host", "0.0.0.0", "--port", "8001"]
