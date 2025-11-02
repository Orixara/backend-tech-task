from contextlib import asynccontextmanager

from fastapi import FastAPI

from database import get_redis_pool, close_redis_pool


@asynccontextmanager
async def lifespan(app: FastAPI):
    await get_redis_pool()
    yield
    await close_redis_pool()

app = FastAPI(
    title="Events Analytics API",
    version="0.1.0",
    description="Event ingestion and analytics service",
    lifespan=lifespan,
)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}