from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware

from app.api.routes.api import router as api_router
from app.api.routes.spa import router as spa_router
from app.dependencies import container, get_frontend_dist_dir


@asynccontextmanager
async def lifespan(app: FastAPI):
    await container.storage.initialize()
    await container.worker.start()
    yield
    await container.worker.stop()


app = FastAPI(title="VK to Telegram Transfer Service", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=container.storage._settings.session_secret, max_age=60 * 60 * 12)
frontend_assets_dir = get_frontend_dist_dir() / "assets"
if frontend_assets_dir.exists():
    app.mount("/app/assets", StaticFiles(directory=frontend_assets_dir), name="frontend-assets")
app.include_router(api_router, prefix="/api")
app.include_router(spa_router)
