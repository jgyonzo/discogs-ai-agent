"""FastAPI app shell.

The /health endpoint must remain reachable even when the published
DuckDB or Postgres are unavailable — that is how the operator
discovers the failure (FR-030 + spec edge cases). Lifespan therefore
does NOT call ``settings.validate_runtime()``; per-component
reachability is reported by ``/health`` instead.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from discogs_agent.config import settings
from discogs_agent.health import build_health_payload
from discogs_agent.observability.logging import configure_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def _lifespan(app: FastAPI) -> AsyncIterator[None]:
    configure_logging(settings.LOG_LEVEL)
    logger.info("agent_starting", model_provider="openai", version=settings.AGENT_VERSION)
    yield
    logger.info("agent_stopping")


app = FastAPI(title="Discogs Conversational Analytics Agent", lifespan=_lifespan)

# Cross-origin policy for the browser frontend (008-agent-frontend-v1).
# See specs/008-agent-frontend-v1/contracts/amendment-004-api-cors.md §8.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ALLOWED_ORIGINS,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    allow_credentials=False,
    max_age=600,
)


@app.get("/health")
def health() -> JSONResponse:
    payload, http_status = build_health_payload()
    return JSONResponse(payload, status_code=http_status)


# /query, /artifacts, and the US3 inspection endpoints are registered
# in sibling modules and pulled in here for side-effects only. Avoids
# a circular import where /query needs the graph builder and the
# graph builder needs the settings module.
def _register_routes() -> None:
    from discogs_agent import (
        api_admin,  # noqa: F401
        api_query,  # noqa: F401
    )


_register_routes()
