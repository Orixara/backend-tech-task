from contextlib import asynccontextmanager

from database import close_redis_pool, get_redis_pool
from fastapi import FastAPI

from routes import events_router, stats_router, auth_router


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

app.include_router(events_router)
app.include_router(stats_router)
app.include_router(auth_router)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}
