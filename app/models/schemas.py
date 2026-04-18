from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TransferStatus(str, Enum):
    QUEUED = "queued"
    SUCCESS = "success"
    ERROR = "error"
    SKIPPED = "skipped"
    PARTIAL = "partial"


class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"


class AttachmentType(str, Enum):
    PHOTO = "photo"
    VIDEO = "video"
    DOCUMENT = "document"
    LINK = "link"
    AUDIO = "audio"
    POLL = "poll"
    UNKNOWN = "unknown"


class SignatureSettings(BaseModel):
    enabled: bool = True
    include_source: bool = True
    include_original_link: bool = True
    include_post_id: bool = True
    include_post_date: bool = True
    custom_template: str | None = None


class FilterSettings(BaseModel):
    publish_reposts: bool = True
    publish_links: bool = True
    skip_ads: bool = False
    skip_marked_as_ads: bool = True
    unsupported_mode: str = "caption"


class SourceSettings(BaseModel):
    include_text: bool = True
    include_photos: bool = True
    include_videos: bool = True
    include_audio: bool = True
    include_documents: bool = True
    include_links: bool = True
    include_signature: bool = True
    include_original_date: bool = True
    include_original_link: bool = True
    include_reposts: bool = True
    include_subscriber_posts: bool = False
    poll_count: int = 10


class SourceSchedule(BaseModel):
    timezone_name: str = "UTC"
    interval_seconds: int = 300
    priority: int = 100
    active_weekdays: list[int] = Field(default_factory=lambda: [0, 1, 2, 3, 4, 5, 6])
    window_start: str | None = None
    window_end: str | None = None
    pause_until: datetime | None = None
    base_backoff_seconds: int = 900
    max_backoff_seconds: int = 21600


class SourceRuntimeState(BaseModel):
    next_run_at: datetime | None = None
    last_started_at: datetime | None = None
    last_finished_at: datetime | None = None
    consecutive_failures: int = 0
    last_error_at: datetime | None = None
    last_error_message: str | None = None
    last_outcome: str | None = None
    scheduler_status: str = "idle"
    scheduler_note: str | None = None


class VKSource(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    name: str
    screen_name: str
    group_id: int | None = None
    is_active: bool = True
    telegram_target: str
    settings: SourceSettings = Field(default_factory=SourceSettings)
    schedule: SourceSchedule = Field(default_factory=SourceSchedule)
    runtime: SourceRuntimeState = Field(default_factory=SourceRuntimeState)
    last_checked_at: datetime | None = None
    last_detected_post_id: int | None = None
    last_transferred_post_id: int | None = None
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)


class TelegramDestination(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    chat_id: str
    title: str
    created_at: datetime = Field(default_factory=utc_now)


class SystemSettings(BaseModel):
    poll_interval_seconds: int = 300
    retry_limit: int = 3
    signature: SignatureSettings = Field(default_factory=SignatureSettings)
    filters: FilterSettings = Field(default_factory=FilterSettings)
    admin_username: str = "admin"
    admin_password_hash: str = ""
    session_secret: str = "change-me"
    vk_token: str = ""
    telegram_bot_token: str = ""
    telegram_proxy_url: str = ""
    vk_token_encrypted: str = ""
    telegram_bot_token_encrypted: str = ""
    telegram_proxy_url_encrypted: str = ""
    vk_token_valid: bool | None = None
    vk_token_validation_error: str | None = None
    vk_token_last_validated_at: datetime | None = None
    vk_token_last_alerted_at: datetime | None = None
    telegram_bot_token_valid: bool | None = None
    telegram_bot_token_validation_error: str | None = None
    telegram_bot_token_last_validated_at: datetime | None = None
    ffmpeg_binary: str = "ffmpeg"
    data_dir: str = "data"
    cache_dir: str = "data/cache"
    log_level: str = "INFO"


class TransferAttachment(BaseModel):
    type: AttachmentType
    url: str | None = None
    thumbnail_url: str | None = None
    title: str | None = None
    artist: str | None = None
    mime_type: str | None = None
    size: int | None = None
    duration: int | None = None
    local_path: str | None = None
    cache_cleared: bool = False
    sent: bool = False
    skipped: bool = False
    error: str | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class VKPost(BaseModel):
    post_id: int
    owner_id: int
    screen_name: str
    source_name: str
    text: str = ""
    created_at: datetime
    original_url: str
    attachments: list[TransferAttachment] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    is_repost: bool = False


class TransferRecord(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    created_at: datetime = Field(default_factory=utc_now)
    updated_at: datetime = Field(default_factory=utc_now)
    source_id: str
    source_name: str
    vk_post_id: int
    vk_post_url: str
    telegram_target: str
    telegram_message_ids: list[int] = Field(default_factory=list)
    telegram_message_url: str | None = None
    status: TransferStatus = TransferStatus.QUEUED
    attempts: int = 0
    error: str | None = None
    post_text: str = ""
    post_created_at: datetime | None = None
    attachments: list[TransferAttachment] = Field(default_factory=list)
    technical_logs: list[str] = Field(default_factory=list)


class LogEntry(BaseModel):
    id: str = Field(default_factory=lambda: uuid4().hex)
    timestamp: datetime = Field(default_factory=utc_now)
    level: LogLevel
    event: str
    message: str
    source_id: str | None = None
    transfer_id: str | None = None
    extra: dict[str, Any] = Field(default_factory=dict)


class DashboardStats(BaseModel):
    vk_groups: int
    telegram_targets: int
    successful_transfers: int
    failed_transfers: int
    queued_transfers: int
    last_check_at: datetime | None
    worker_status: str
    stats_today: int
    stats_7d: int
    stats_30d: int


class CacheFileInfo(BaseModel):
    name: str
    relative_path: str
    size_bytes: int
    modified_at: datetime


class CacheOverview(BaseModel):
    files: list[CacheFileInfo] = Field(default_factory=list)
    total_files: int = 0
    total_size_bytes: int = 0
