"""
Main FastAPI application.

This module creates and configures the FastAPI application.
"""

import asyncio
import logging
import time
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Any, Dict

import uvicorn
from backend.config.database import (
    database_health,
    init_engine,
    start_token_refresh,
    stop_token_refresh,
)
# from errors.handlers import register_exception_handlers
from fastapi import APIRouter, HTTPException, status
# from services.db.connector import close_connections
from sqlalchemy import text
from sqlmodel import SQLModel
from fastapi.staticfiles import StaticFiles
from fastapi import FastAPI, Request

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Handle application startup and shutdown events."""
    logger.info("Application startup initiated")
    
    health_check_task = None

    try:
        init_engine()
        from backend.config.database import engine

        async with engine.begin() as conn:
            await conn.run_sync(SQLModel.metadata.create_all)
        await start_token_refresh()
        health_check_task = asyncio.create_task(check_database_health(300))
        logger.info("Database engine initialized and health monitoring started")
    except Exception as e:
        logger.error(f"Failed to initialize database engine: {e}")
        logger.info("Application will start without database functionality")
    
    logger.info("Application startup complete")

    yield

    logger.info("Application shutdown initiated")
    if health_check_task:
        health_check_task.cancel()
        try:
            await health_check_task
        except asyncio.CancelledError:
            logger.info("Database health check task cancelled successfully")
        await stop_token_refresh()
    logger.info("Application shutdown complete")
    # close_connections()


# Create the main FastAPI application
app = FastAPI(
    title="FastAPI & Databricks Apps",
    description="A simple FastAPI application example for Databricks Apps runtime",
    version="1.0.0",
    lifespan=lifespan,
)

api_router = APIRouter()


@api_router.get("/api/lakebase/data")
async def get_lakebase_data(
    table: str = "information_schema.tables",
    limit: int = 10,
) -> dict[str, Any]:
    """Get data from a Lakebase table. Table must be in 'schema.table' format."""
    from backend.config.database import AsyncSessionLocal

    if AsyncSessionLocal is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database not initialized. Check server logs for connection issues.",
        )

    if not table or "." not in table:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Table must be in format: schema.table",
        )

    limit = min(max(limit, 1), 1000)

    try:
        async with AsyncSessionLocal() as db:
            result = await db.execute(text(f"SELECT * FROM {table} LIMIT {limit}"))
            columns = list(result.keys())
            rows = result.fetchall()
            return {"columns": columns, "data": [dict(zip(columns, row)) for row in rows]}
    except Exception as e:
        logger.error(f"Query error for table {table}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to execute query",
        )


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "ok"}


# Include the API router
app.include_router(api_router)

# Performance monitoring middleware
@app.middleware("http")
async def add_process_time_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    process_time = time.time() - start_time
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(
        f"Request: {request.method} {request.url.path} - {process_time * 1000:.1f}ms"
    )
    return response


async def check_database_health(interval: int):
    while True:
        try:
            is_healthy = await database_health()
            if not is_healthy:
                logger.warning(
                    "Database Health check failed. Connection is not healthy."
                )
        except Exception as e:
            logger.error(f"Exception during health check: {e}")
        await asyncio.sleep(interval)

# Serve frontend
frontend_dir = Path(__file__).parent.parent / "frontend" / "dist"

if frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dir), html=True), name="frontend")
else:
    @app.get("/")
    async def root() -> Dict[str, str]:
        return {
            "app": "Databricks FastAPI Example",
            "message": "Welcome to the Databricks FastAPI example app",
            "docs": "/docs",
        }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)