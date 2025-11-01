from fastapi import FastAPI

app = FastAPI(
    title="Events Analytics API",
    version="0.1.0",
    description="Event ingestion and analytics service"
)

@app.get("/health")
async def health_check():
    return {"status": "healthy"}