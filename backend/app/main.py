from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api.routes import router
from app.core.config import settings

app = FastAPI(
    title=settings.app_name,
    version="1.1.0",
    description="Live-data-first multi-modal travel search and 3D transport visualisation API.",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router, prefix=settings.api_prefix)


@app.get("/meta")
def meta() -> dict:
    return {"name": settings.app_name, "docs": "/docs", "version": "1.1.0"}


# Convenient single-process local preview. Docker production still serves the web
# client through nginx, but local developers can run only uvicorn from /backend.
web_dir = Path(__file__).resolve().parents[2] / "web"
if web_dir.exists():
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
