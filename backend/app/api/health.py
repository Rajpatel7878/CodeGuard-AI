"""Health check endpoint."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.database.session import get_db
from app.llm.client import get_llm_client
from app.schemas.review import HealthResponse, LlmHealth

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def health(db: Session = Depends(get_db)) -> HealthResponse:
    database_status = "ok"
    try:
        db.execute(text("SELECT 1"))
    except SQLAlchemyError:
        database_status = "error"

    llm = get_llm_client()
    return HealthResponse(
        status="ok" if database_status == "ok" else "degraded",
        service=settings.app_name,
        version=settings.version,
        environment=settings.environment,
        database=database_status,
        llm=LlmHealth(
            provider=llm.provider,
            configured=llm.configured,
            status=llm.status,
            message=llm.message,
        ),
    )
