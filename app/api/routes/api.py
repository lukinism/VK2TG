from __future__ import annotations

from datetime import datetime, timezone
import traceback

from pydantic import BaseModel
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.api.common import CSRF_HEADER_NAME, get_or_create_csrf_token, is_admin, rotate_csrf_token, validate_csrf_token
from app.core.security import mask_secret
from app.dependencies import container
from app.models.schemas import SystemSettings, VKSource
from app.services.token_monitor import TokenValidationError


router = APIRouter(tags=["api"])
api_basic_auth = HTTPBasic(auto_error=False)
API_BASIC_CHALLENGE = 'Basic realm="VK Transfer API"'


class LoginPayload(BaseModel):
    username: str
    password: str


class SessionPayload(BaseModel):
    authenticated: bool
    username: str | None = None
    csrf_token: str | None = None


class SettingsViewPayload(BaseModel):
    poll_interval_seconds: int
    retry_limit: int
    admin_username: str
    session_secret: str
    ffmpeg_binary: str
    vk_token_masked: str
    telegram_bot_token_masked: str
    telegram_proxy_url_masked: str
    has_vk_token: bool
    has_telegram_bot_token: bool
    has_telegram_proxy_url: bool
    vk_token_valid: bool | None = None
    vk_token_validation_error: str | None = None
    vk_token_last_validated_at: datetime | None = None
    telegram_bot_token_valid: bool | None = None
    telegram_bot_token_validation_error: str | None = None
    telegram_bot_token_last_validated_at: datetime | None = None


class SettingsUpdatePayload(BaseModel):
    poll_interval_seconds: int
    retry_limit: int
    admin_username: str
    session_secret: str
    ffmpeg_binary: str = "ffmpeg"
    vk_token: str = ""
    telegram_bot_token: str = ""
    telegram_proxy_url: str = ""
    clear_vk_token: bool = False
    clear_telegram_token: bool = False
    clear_telegram_proxy: bool = False


async def require_api_access(
    request: Request,
    credentials: HTTPBasicCredentials | None = Depends(api_basic_auth),
) -> str:
    if is_admin(request):
        return "session"
    if credentials and await container.auth_service.validate_credentials(credentials.username, credentials.password):
        return "basic"
    raise HTTPException(
        status_code=401,
        detail="Authentication required",
        headers={"WWW-Authenticate": API_BASIC_CHALLENGE},
    )


def enforce_api_csrf_if_session_present(request: Request, csrf_token: str | None) -> None:
    if not is_admin(request):
        return
    get_or_create_csrf_token(request)
    if validate_csrf_token(request, csrf_token):
        return
    raise HTTPException(status_code=403, detail="Invalid CSRF token")


def build_session_payload(request: Request) -> SessionPayload:
    if not is_admin(request):
        return SessionPayload(authenticated=False)
    return SessionPayload(
        authenticated=True,
        username=request.session.get("username"),
        csrf_token=get_or_create_csrf_token(request),
    )


@router.get("/auth/session")
async def get_session(request: Request) -> SessionPayload:
    return build_session_payload(request)


@router.post("/auth/login")
async def login_with_session(payload: LoginPayload, request: Request) -> SessionPayload:
    if not await container.auth_service.validate_credentials(payload.username, payload.password):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    request.session["username"] = payload.username
    rotate_csrf_token(request)
    return build_session_payload(request)


@router.post("/auth/logout")
async def logout_from_session(
    request: Request,
    x_csrf_token: str | None = Header(None, alias=CSRF_HEADER_NAME),
    _auth: str = Depends(require_api_access),
):
    enforce_api_csrf_if_session_present(request, x_csrf_token)
    request.session.clear()
    return {"ok": True}


@router.get("/health")
async def healthcheck():
    return {"status": "ok", "timestamp": datetime.now(timezone.utc).isoformat()}


@router.get("/dashboard")
async def dashboard_stats(_auth: str = Depends(require_api_access)):
    return await container.storage.dashboard_stats()


@router.get("/sources")
async def list_sources(_auth: str = Depends(require_api_access)):
    return await container.storage.list_sources()


@router.post("/sources")
async def create_source(
    source: VKSource,
    request: Request,
    x_csrf_token: str | None = Header(None, alias=CSRF_HEADER_NAME),
    _auth: str = Depends(require_api_access),
):
    enforce_api_csrf_if_session_present(request, x_csrf_token)
    source.updated_at = datetime.now(timezone.utc)
    return await container.storage.upsert_source(source)


@router.put("/sources/{source_id}")
async def update_source(
    source_id: str,
    source: VKSource,
    request: Request,
    x_csrf_token: str | None = Header(None, alias=CSRF_HEADER_NAME),
    _auth: str = Depends(require_api_access),
):
    enforce_api_csrf_if_session_present(request, x_csrf_token)
    existing = await container.storage.get_source(source_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Source not found")
    source.id = source_id
    source.created_at = existing.created_at
    source.updated_at = datetime.now(timezone.utc)
    return await container.storage.upsert_source(source)


@router.get("/sources/{source_id}")
async def get_source(source_id: str, _auth: str = Depends(require_api_access)):
    source = await container.storage.get_source(source_id)
    if not source:
        raise HTTPException(status_code=404, detail="Source not found")
    return source


@router.delete("/sources/{source_id}")
async def delete_source(
    source_id: str,
    request: Request,
    x_csrf_token: str | None = Header(None, alias=CSRF_HEADER_NAME),
    _auth: str = Depends(require_api_access),
):
    enforce_api_csrf_if_session_present(request, x_csrf_token)
    return {"deleted": await container.storage.delete_source(source_id)}


@router.get("/transfers")
async def list_transfers(_auth: str = Depends(require_api_access)):
    return list(reversed(await container.storage.list_transfers()))


@router.get("/transfers/{transfer_id}")
async def get_transfer(transfer_id: str, _auth: str = Depends(require_api_access)):
    transfer = await container.storage.get_transfer(transfer_id)
    if not transfer:
        raise HTTPException(status_code=404, detail="Transfer not found")
    return transfer


@router.get("/logs")
async def list_logs(
    level: str | None = None,
    source_id: str | None = None,
    transfer_id: str | None = None,
    _auth: str = Depends(require_api_access),
):
    return await container.storage.list_logs(level=level, source_id=source_id, transfer_id=transfer_id)


@router.post("/logs/clear")
async def clear_logs(
    request: Request,
    x_csrf_token: str | None = Header(None, alias=CSRF_HEADER_NAME),
    _auth: str = Depends(require_api_access),
):
    enforce_api_csrf_if_session_present(request, x_csrf_token)
    return await container.storage.clear_logs()


@router.get("/cache")
async def get_cache_overview(_auth: str = Depends(require_api_access)):
    return await container.storage.cache_overview()


@router.post("/cache/clear")
async def clear_cache(
    request: Request,
    x_csrf_token: str | None = Header(None, alias=CSRF_HEADER_NAME),
    _auth: str = Depends(require_api_access),
):
    enforce_api_csrf_if_session_present(request, x_csrf_token)
    return await container.storage.clear_cache()


@router.get("/settings")
async def get_settings(_auth: str = Depends(require_api_access)):
    return await container.storage.public_settings()


@router.get("/settings/view")
async def get_settings_view(_auth: str = Depends(require_api_access)) -> SettingsViewPayload:
    settings = await container.storage.load_settings()
    return SettingsViewPayload(
        poll_interval_seconds=settings.poll_interval_seconds,
        retry_limit=settings.retry_limit,
        admin_username=settings.admin_username,
        session_secret=settings.session_secret,
        ffmpeg_binary=settings.ffmpeg_binary or "ffmpeg",
        vk_token_masked=mask_secret(settings.vk_token),
        telegram_bot_token_masked=mask_secret(settings.telegram_bot_token),
        telegram_proxy_url_masked=mask_secret(settings.telegram_proxy_url),
        has_vk_token=bool(settings.vk_token),
        has_telegram_bot_token=bool(settings.telegram_bot_token),
        has_telegram_proxy_url=bool(settings.telegram_proxy_url),
        vk_token_valid=settings.vk_token_valid,
        vk_token_validation_error=settings.vk_token_validation_error,
        vk_token_last_validated_at=settings.vk_token_last_validated_at,
        telegram_bot_token_valid=settings.telegram_bot_token_valid,
        telegram_bot_token_validation_error=settings.telegram_bot_token_validation_error,
        telegram_bot_token_last_validated_at=settings.telegram_bot_token_last_validated_at,
    )


@router.put("/settings")
async def update_settings(
    settings: SystemSettings,
    request: Request,
    x_csrf_token: str | None = Header(None, alias=CSRF_HEADER_NAME),
    _auth: str = Depends(require_api_access),
):
    enforce_api_csrf_if_session_present(request, x_csrf_token)
    try:
        await container.token_monitor.validate_on_settings_save(settings)
    except TokenValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return await container.storage.save_settings(settings)


@router.put("/settings/view")
async def update_settings_view(
    payload: SettingsUpdatePayload,
    request: Request,
    x_csrf_token: str | None = Header(None, alias=CSRF_HEADER_NAME),
    _auth: str = Depends(require_api_access),
) -> SettingsViewPayload:
    enforce_api_csrf_if_session_present(request, x_csrf_token)
    settings = await container.storage.load_settings()
    vk_token_changed = payload.clear_vk_token or bool(payload.vk_token.strip())
    telegram_token_changed = payload.clear_telegram_token or bool(payload.telegram_bot_token.strip())
    telegram_proxy_changed = payload.clear_telegram_proxy or bool(payload.telegram_proxy_url.strip())
    settings.poll_interval_seconds = payload.poll_interval_seconds
    settings.retry_limit = payload.retry_limit
    settings.admin_username = payload.admin_username
    settings.session_secret = payload.session_secret
    settings.ffmpeg_binary = payload.ffmpeg_binary.strip() or "ffmpeg"
    if payload.clear_vk_token:
        settings.vk_token = ""
        settings.vk_token_encrypted = ""
    elif payload.vk_token.strip():
        settings.vk_token = payload.vk_token.strip()
    if payload.clear_telegram_token:
        settings.telegram_bot_token = ""
        settings.telegram_bot_token_encrypted = ""
    elif payload.telegram_bot_token.strip():
        settings.telegram_bot_token = payload.telegram_bot_token.strip()
    if payload.clear_telegram_proxy:
        settings.telegram_proxy_url = ""
        settings.telegram_proxy_url_encrypted = ""
    elif payload.telegram_proxy_url.strip():
        settings.telegram_proxy_url = payload.telegram_proxy_url.strip()
    try:
        if vk_token_changed:
            await container.token_monitor.validate_vk_token_value(settings.vk_token, settings)
        if telegram_token_changed or telegram_proxy_changed:
            await container.token_monitor.validate_telegram_token_value(settings.telegram_bot_token, settings.telegram_proxy_url, settings)
    except TokenValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await container.storage.save_settings(settings)
    return await get_settings_view(_auth)


@router.post("/worker/run")
async def run_worker_once(
    request: Request,
    x_csrf_token: str | None = Header(None, alias=CSRF_HEADER_NAME),
    _auth: str = Depends(require_api_access),
):
    enforce_api_csrf_if_session_present(request, x_csrf_token)
    try:
        return await container.worker.run_once()
    except Exception as exc:
        details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
        await container.logger.error("worker.manual_run_failed", details)
        raise HTTPException(status_code=500, detail=details)


@router.post("/worker/clear-queue")
async def clear_worker_queue(
    request: Request,
    x_csrf_token: str | None = Header(None, alias=CSRF_HEADER_NAME),
    _auth: str = Depends(require_api_access),
):
    enforce_api_csrf_if_session_present(request, x_csrf_token)
    return await container.storage.clear_transfer_queue()
