"""Prometheus scrape endpoint. Exposes only numeric metrics, no secrets."""
from fastapi import APIRouter
from prometheus_client import CONTENT_TYPE_LATEST
from starlette.responses import Response

from backend.core.metrics import render_latest

router = APIRouter(tags=["metrics"])


@router.get("/metrics", include_in_schema=False)
async def metrics() -> Response:
    return Response(content=render_latest(), media_type=CONTENT_TYPE_LATEST)
