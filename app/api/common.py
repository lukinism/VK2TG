from __future__ import annotations

import secrets

from fastapi import Request
from fastapi import status

CSRF_SESSION_KEY = "csrf_token"
CSRF_FORM_FIELD = "csrf_token"
CSRF_HEADER_NAME = "X-CSRF-Token"


def is_admin(request: Request) -> bool:
    return bool(request.session.get("username"))


def push_flash(request: Request, level: str, message: str) -> None:
    request.session["flash"] = {"level": level, "message": message}


def pop_flash(request: Request) -> dict | None:
    return request.session.pop("flash", None)


def get_or_create_csrf_token(request: Request) -> str:
    token = request.session.get(CSRF_SESSION_KEY)
    if token:
        return token
    token = secrets.token_urlsafe(32)
    request.session[CSRF_SESSION_KEY] = token
    return token


def rotate_csrf_token(request: Request) -> str:
    token = secrets.token_urlsafe(32)
    request.session[CSRF_SESSION_KEY] = token
    return token


def validate_csrf_token(request: Request, submitted_token: str | None) -> bool:
    session_token = request.session.get(CSRF_SESSION_KEY)
    if not session_token or not submitted_token:
        return False
    return secrets.compare_digest(session_token, submitted_token)


def redirect(path: str):
    from fastapi.responses import RedirectResponse

    return RedirectResponse(path, status_code=status.HTTP_303_SEE_OTHER)
