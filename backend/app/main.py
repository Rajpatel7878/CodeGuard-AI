"""FastAPI application entry point."""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from sqlalchemy import inspect, text
from sqlalchemy.exc import SQLAlchemyError

from app.api import api_router
from app.api.limits import limiter
from app.config import settings
from app.database import models  # noqa: F401  (register ORM models with Base)
from app.database.session import Base, engine

logger = logging.getLogger(__name__)


def ensure_schema() -> None:
    """Create tables and add columns that ``create_all`` cannot add.

    SQLite (and SQLAlchemy's ``create_all``) never alters an existing table, so
    a database created before review ownership existed would reject the new
    ``user_id`` column. This keeps deployments upgradeable without a migration
    framework.
    """
    Base.metadata.create_all(bind=engine)

    inspector = inspect(engine)
    if "reviews" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("reviews")}
    if "user_id" not in columns:
        with engine.begin() as connection:
            connection.execute(text("ALTER TABLE reviews ADD COLUMN user_id VARCHAR(40)"))
            connection.execute(
                text("CREATE INDEX IF NOT EXISTS ix_reviews_user_id ON reviews (user_id)")
            )
        logger.info("Added reviews.user_id column for per-account review ownership.")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_schema()
    yield


app = FastAPI(
    title=settings.app_name,
    version=settings.version,
    description=(
        "Review submission and history API for ALPHA CodeGuard AI."
    ),
    lifespan=lifespan,
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=list(settings.cors_origins),
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.exception_handler(SQLAlchemyError)
async def database_error_handler(_request: Request, _exc: SQLAlchemyError) -> JSONResponse:
    return JSONResponse(
        status_code=503,
        content={"detail": "The review database is unavailable. Try again shortly."},
    )


@app.get("/", include_in_schema=False)
def root() -> dict[str, str]:
    return {
        "service": settings.app_name,
        "version": settings.version,
        "docs": "/docs",
        "health": "/health",
    }
