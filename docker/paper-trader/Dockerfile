# Paper forward test: the ICT agent on live Binance crypto, paper-filled,
# running unattended. Build context is the repo root (see docker/docker-compose.yml).
FROM python:3.11-slim

WORKDIR /app

COPY docker/paper-trader/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Only the packages the runner actually imports (see requirements.txt note).
COPY agent/ /app/agent/
COPY liquidity_engine/ /app/liquidity_engine/
COPY ml/__init__.py /app/ml/__init__.py
COPY ml/features/ /app/ml/features/
COPY services/__init__.py /app/services/__init__.py
COPY services/market_data/ /app/services/market_data/
COPY services/risk_engine/ /app/services/risk_engine/
COPY services/shadow_period/ /app/services/shadow_period/
COPY services/algorag/__init__.py services/algorag/models.py /app/services/algorag/
COPY services/visual_model/__init__.py /app/services/visual_model/__init__.py
COPY services/visual_model/api/ /app/services/visual_model/api/
COPY services/visual_model/schemas/ /app/services/visual_model/schemas/
COPY scripts/run_live_agent.py scripts/load_historical_data.py scripts/load_historical_data_binance.py /app/scripts/
COPY docker/paper-trader/entrypoint.sh /app/entrypoint.sh

# Strip CRLF in case the repo was checked out on Windows.
RUN sed -i 's/\r$//' /app/entrypoint.sh && chmod +x /app/entrypoint.sh

ENV PYTHONPATH=/app \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    INSTRUMENTS=BTCUSDT,ETHUSDT,SOLUSDT,BNBUSDT,XRPUSDT,DOGEUSDT \
    ENTRY_TIMEFRAME=M5 \
    BACKFILL_YEARS=0.05 \
    HEARTBEAT_MAX_AGE=900

RUN useradd --create-home --uid 1000 appuser \
    && mkdir -p /app/data \
    && chown -R appuser:appuser /app
USER appuser

# Healthy while a pass with fresh data landed within HEARTBEAT_MAX_AGE seconds
# (900 = three M5 bars). Start period covers the startup backfill.
HEALTHCHECK --interval=60s --timeout=10s --start-period=20m --retries=3 \
    CMD python -c "import os,sys,time; p='/app/data/heartbeat'; sys.exit(0 if os.path.exists(p) and time.time()-os.path.getmtime(p) < int(os.environ['HEARTBEAT_MAX_AGE']) else 1)"

ENTRYPOINT ["/app/entrypoint.sh"]
