from __future__ import annotations

import hashlib
import os
from pathlib import Path

from dotenv import load_dotenv

from app.models.schemas import SystemSettings


BASE_DIR = Path(__file__).resolve().parents[2]


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def load_settings() -> SystemSettings:
    load_dotenv(BASE_DIR / ".env")
    default_password = os.getenv("ADMIN_PASSWORD", "admin")
    session_secret = os.getenv("SESSION_SECRET") or "change-me"
    admin_password_hash = os.getenv("ADMIN_PASSWORD_HASH") or hash_password(default_password)
    return SystemSettings(
        poll_interval_seconds=int(os.getenv("POLL_INTERVAL_SECONDS", "300")),
        retry_limit=int(os.getenv("RETRY_LIMIT", "3")),
        admin_username=os.getenv("ADMIN_USERNAME", "admin"),
        admin_password_hash=admin_password_hash,
        session_secret=session_secret,
        ffmpeg_binary=os.getenv("FFMPEG_BINARY", "ffmpeg"),
        data_dir=os.getenv("DATA_DIR", "data"),
        cache_dir=os.getenv("CACHE_DIR", "data/cache"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
    )
