# ── Build stage ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

WORKDIR /app

# System dependencies (curl needed for health-check probe)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install CPU-only torch first. sentence-transformers depends on torch, and
# the default PyPI wheel drags in ~5GB of unused CUDA/nvidia-* packages since
# this service only ever runs embedding inference on CPU.
RUN pip install --no-cache-dir torch==2.5.1 --index-url https://download.pytorch.org/whl/cpu

# Install remaining Python dependencies
COPY services/algorag/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Copy only the algorag service source
COPY services/algorag/ /app/services/algorag/
# Ensure the package root is importable
COPY services/__init__.py /app/services/__init__.py

# ── Runtime ────────────────────────────────────────────────────────────────
ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN useradd --create-home --uid 1000 appuser \
    && chown -R appuser:appuser /app
USER appuser

EXPOSE 8003

CMD ["uvicorn", "services.algorag.main:app", "--host", "0.0.0.0", "--port", "8003"]
