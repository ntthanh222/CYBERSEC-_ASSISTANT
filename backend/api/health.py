"""Lightweight liveness probe for the Docker healthcheck.

Deliberately does not touch Postgres/Redis: it must answer fast and stay up
even while a dependency is down, so orchestration doesn't restart a backend
that is otherwise fine.
"""
from fastapi import APIRouter

from backend.schemas.health import ErrorResponse, LivenessResponse

router = APIRouter(tags=["health"])


@router.get(
    "/health",
    summary="Liveness probe",
    description=(
        "Dependency-free liveness check used by the Docker healthcheck and "
        "orchestrators. Always answers fast and never touches PostgreSQL or "
        "Redis, so a dependency outage never causes the backend container "
        "itself to be restarted. For real dependency status, use "
        "`/api/system/health`."
    ),
    response_description="Static liveness payload.",
    response_model=LivenessResponse,
    responses={500: {"model": ErrorResponse, "description": "Unexpected internal error."}},
)
async def liveness() -> dict:
    return {"status": "healthy", "service": "backend"}
