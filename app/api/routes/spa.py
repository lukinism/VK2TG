from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse

from app.dependencies import get_frontend_dist_dir


router = APIRouter(include_in_schema=False)


def _frontend_entry() -> Path:
    return get_frontend_dist_dir() / "index.html"


@router.get("/")
async def redirect_root():
    return RedirectResponse("/app/", status_code=307)


@router.get("/login")
@router.get("/sources")
@router.get("/transfers")
@router.get("/cache")
@router.get("/logs")
@router.get("/settings")
async def redirect_legacy_routes():
    return RedirectResponse("/app/", status_code=307)


@router.get("/app", response_class=HTMLResponse)
@router.get("/app/{path:path}", response_class=HTMLResponse)
async def serve_react_app(path: str = ""):
    entry = _frontend_entry()
    if entry.exists():
        return FileResponse(entry)
    return HTMLResponse(
        """
        <html lang="ru">
          <head>
            <meta charset="utf-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>React Admin Not Built</title>
            <style>
              body {
                margin: 0;
                font-family: "Segoe UI", sans-serif;
                background: linear-gradient(180deg, #f7fbff, #eef4fb);
                color: #162033;
                display: grid;
                place-items: center;
                min-height: 100vh;
                padding: 24px;
              }
              main {
                width: min(720px, 100%);
                background: rgba(255,255,255,0.92);
                border: 1px solid rgba(22,32,51,0.08);
                border-radius: 24px;
                padding: 28px;
                box-shadow: 0 24px 50px rgba(25,45,78,0.1);
              }
              code {
                background: rgba(31,111,255,0.08);
                padding: 2px 6px;
                border-radius: 8px;
              }
            </style>
          </head>
          <body>
            <main>
              <h1>React admin еще не собран</h1>
              <p>Сборка фронтенда ожидается в <code>frontend/dist</code>.</p>
              <p>Для разработки запусти Vite в <code>frontend/</code>, а для production сначала выполни <code>npm run build</code>.</p>
            </main>
          </body>
        </html>
        """,
        status_code=503,
    )
