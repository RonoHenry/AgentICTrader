# ── Build stage ────────────────────────────────────────────────────────────
FROM python:3.11-slim AS base

WORKDIR /app

# System dependencies (curl needed for health-check probe)
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
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

EXPOSE 8003

CMD ["uvicorn", "services.algorag.main:app", "--host", "0.0.0.0", "--port", "8003"]
