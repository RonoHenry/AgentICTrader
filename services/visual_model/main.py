"""
FastAPI entry point for the Visual Model service.

Run with: uvicorn services.visual_model.main:app --host 0.0.0.0 --port 8005
"""
from __future__ import annotations

from fastapi import FastAPI

from services.visual_model.api.router import router

app = FastAPI(title="AgentICTrader Visual Model", version="1.0.0")
app.include_router(router)
