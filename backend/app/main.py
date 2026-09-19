from fastapi import FastAPI

from app.config import settings

app = FastAPI(title="Soccer Predictions API", version="0.1.0")


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "environment": settings.environment}
