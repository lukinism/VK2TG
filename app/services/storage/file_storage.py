from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from pydantic import TypeAdapter

from app.core.security import TokenCipher
from app.models.schemas import CacheFileInfo, CacheOverview, DashboardStats, LogEntry, SystemSettings, TransferRecord, TransferStatus, VKSource


class FileStorage:
    def __init__(self, base_dir: Path, initial_settings: SystemSettings, cipher: TokenCipher) -> None:
        self.base_dir = base_dir
        self.sources_path = base_dir / "sources.json"
        self.settings_path = base_dir / "settings.json"
        self.transfers_dir = base_dir / "transfers"
        self.transfers_index_path = self.transfers_dir / "index.jsonl"
        self.logs_path = base_dir / "logs" / "service.jsonl"
        self.state_path = base_dir / "state" / "runtime.json"
        self.cache_dir = base_dir / "cache"
        self._settings = initial_settings
        self._cipher = cipher
        self._lock = asyncio.Lock()
        self._sources_adapter = TypeAdapter(list[VKSource])

    async def initialize(self) -> None:
        for path in [self.base_dir, self.transfers_dir, self.logs_path.parent, self.state_path.parent, self.cache_dir]:
            path.mkdir(parents=True, exist_ok=True)
        if not self.settings_path.exists():
            await self.save_settings(self._settings)
        else:
            await self._repair_settings_file()
        if not self.sources_path.exists():
            await self._atomic_write_json(self.sources_path, [])
        if not self.transfers_index_path.exists():
            self.transfers_index_path.touch()
        if not self.logs_path.exists():
            self.logs_path.touch()
        if not self.state_path.exists():
            await self._atomic_write_json(self.state_path, {"worker_status": "idle", "last_cycle_at": None})

    async def _repair_settings_file(self) -> None:
        async with self._lock:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            changed = False
            for field in ["admin_password_hash", "admin_username", "session_secret", "vk_token", "telegram_bot_token", "telegram_proxy_url", "ffmpeg_binary"]:
                if not data.get(field) and getattr(self._settings, field, None):
                    data[field] = getattr(self._settings, field)
                    changed = True
            if data.get("vk_token") and not data.get("vk_token_encrypted"):
                data["vk_token_encrypted"] = self._cipher.encrypt(data["vk_token"])
                data["vk_token"] = ""
                changed = True
            if data.get("telegram_bot_token") and not data.get("telegram_bot_token_encrypted"):
                data["telegram_bot_token_encrypted"] = self._cipher.encrypt(data["telegram_bot_token"])
                data["telegram_bot_token"] = ""
                changed = True
            if data.get("telegram_proxy_url") and not data.get("telegram_proxy_url_encrypted"):
                data["telegram_proxy_url_encrypted"] = self._cipher.encrypt(data["telegram_proxy_url"])
                data["telegram_proxy_url"] = ""
                changed = True
            if changed:
                await self._atomic_write_json(self.settings_path, data)

    async def _atomic_write_json(self, path: Path, payload) -> None:
        temp_path = path.parent / f".{path.name}.{uuid4().hex}.tmp"
        with temp_path.open("w", encoding="utf-8") as temp:
            json.dump(payload, temp, ensure_ascii=False, indent=2, default=self._json_default)
            temp.flush()
            os.fsync(temp.fileno())
        await self._replace_with_retry(temp_path, path)

    async def _replace_with_retry(self, temp_path: Path, path: Path, retries: int = 8, delay: float = 0.15) -> None:
        last_error: Exception | None = None
        for _ in range(retries):
            try:
                os.replace(temp_path, path)
                return
            except PermissionError as exc:
                last_error = exc
                await asyncio.sleep(delay)
        if temp_path.exists():
            temp_path.unlink(missing_ok=True)
        if last_error:
            raise last_error

    def _json_default(self, value):
        if isinstance(value, datetime):
            return value.isoformat()
        if hasattr(value, "model_dump"):
            return value.model_dump(mode="json")
        raise TypeError(f"Unsupported type: {type(value)!r}")

    async def load_settings(self) -> SystemSettings:
        async with self._lock:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
        settings = SystemSettings.model_validate(data)
        if settings.vk_token_encrypted:
            settings.vk_token = self._cipher.decrypt(settings.vk_token_encrypted)
        if settings.telegram_bot_token_encrypted:
            settings.telegram_bot_token = self._cipher.decrypt(settings.telegram_bot_token_encrypted)
        if settings.telegram_proxy_url_encrypted:
            settings.telegram_proxy_url = self._cipher.decrypt(settings.telegram_proxy_url_encrypted)
        self._settings = settings
        return self._settings

    async def save_settings(self, settings: SystemSettings) -> SystemSettings:
        payload = settings.model_dump(mode="json")
        payload["vk_token_encrypted"] = self._cipher.encrypt(settings.vk_token) if settings.vk_token else ""
        payload["telegram_bot_token_encrypted"] = self._cipher.encrypt(settings.telegram_bot_token) if settings.telegram_bot_token else ""
        payload["telegram_proxy_url_encrypted"] = self._cipher.encrypt(settings.telegram_proxy_url) if settings.telegram_proxy_url else ""
        payload["vk_token"] = ""
        payload["telegram_bot_token"] = ""
        payload["telegram_proxy_url"] = ""
        async with self._lock:
            await self._atomic_write_json(self.settings_path, payload)
        self._settings = settings
        return settings

    async def public_settings(self) -> dict:
        settings = await self.load_settings()
        payload = settings.model_dump(mode="json")
        payload["vk_token"] = ""
        payload["telegram_bot_token"] = ""
        payload["telegram_proxy_url"] = ""
        payload["vk_token_encrypted"] = ""
        payload["telegram_bot_token_encrypted"] = ""
        payload["telegram_proxy_url_encrypted"] = ""
        return payload

    async def list_sources(self) -> list[VKSource]:
        async with self._lock:
            data = json.loads(self.sources_path.read_text(encoding="utf-8"))
        return self._sources_adapter.validate_python(data)

    async def get_source(self, source_id: str) -> VKSource | None:
        sources = await self.list_sources()
        return next((item for item in sources if item.id == source_id), None)

    async def upsert_source(self, source: VKSource) -> VKSource:
        async with self._lock:
            raw = json.loads(self.sources_path.read_text(encoding="utf-8"))
            sources = self._sources_adapter.validate_python(raw)
            for index, current in enumerate(sources):
                if current.id == source.id:
                    sources[index] = source
                    break
            else:
                sources.append(source)
            await self._atomic_write_json(self.sources_path, [item.model_dump(mode="json") for item in sources])
        return source

    async def delete_source(self, source_id: str) -> bool:
        async with self._lock:
            raw = json.loads(self.sources_path.read_text(encoding="utf-8"))
            sources = self._sources_adapter.validate_python(raw)
            new_sources = [item for item in sources if item.id != source_id]
            changed = len(new_sources) != len(sources)
            if changed:
                await self._atomic_write_json(self.sources_path, [item.model_dump(mode="json") for item in new_sources])
        return changed

    async def save_transfer(self, transfer: TransferRecord) -> TransferRecord:
        path = self.transfers_dir / f"{transfer.id}.json"
        async with self._lock:
            await self._atomic_write_json(path, transfer.model_dump(mode="json"))
            with self.transfers_index_path.open("a", encoding="utf-8") as handle:
                handle.write(transfer.model_dump_json() + "\n")
        return transfer

    async def update_transfer(self, transfer: TransferRecord) -> TransferRecord:
        path = self.transfers_dir / f"{transfer.id}.json"
        async with self._lock:
            await self._atomic_write_json(path, transfer.model_dump(mode="json"))
            existing = await self._read_transfers_unlocked()
            deduped = [item for item in existing if item.id != transfer.id] + [transfer]
            temp_path = self.transfers_index_path.parent / f".{self.transfers_index_path.name}.{uuid4().hex}.tmp"
            with temp_path.open("w", encoding="utf-8") as temp:
                for item in sorted(deduped, key=lambda row: row.created_at):
                    temp.write(item.model_dump_json() + "\n")
                temp.flush()
                os.fsync(temp.fileno())
            await self._replace_with_retry(temp_path, self.transfers_index_path)
        return transfer

    async def _read_transfers_unlocked(self) -> list[TransferRecord]:
        if not self.transfers_index_path.exists():
            return []
        lines = [line.strip() for line in self.transfers_index_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        return [TransferRecord.model_validate_json(line) for line in lines]

    async def list_transfers(self) -> list[TransferRecord]:
        async with self._lock:
            return await self._read_transfers_unlocked()

    async def get_transfer(self, transfer_id: str) -> TransferRecord | None:
        path = self.transfers_dir / f"{transfer_id}.json"
        if not path.exists():
            return None
        async with self._lock:
            return TransferRecord.model_validate_json(path.read_text(encoding="utf-8"))

    async def clear_transfer_queue(self) -> dict[str, int]:
        async with self._lock:
            transfers = await self._read_transfers_unlocked()
            to_remove = [item for item in transfers if item.status in {TransferStatus.QUEUED, TransferStatus.ERROR}]
            remaining = [item for item in transfers if item.status not in {TransferStatus.QUEUED, TransferStatus.ERROR}]
            for item in to_remove:
                path = self.transfers_dir / f"{item.id}.json"
                path.unlink(missing_ok=True)
            temp_path = self.transfers_index_path.parent / f".{self.transfers_index_path.name}.{uuid4().hex}.tmp"
            with temp_path.open("w", encoding="utf-8") as temp:
                for item in sorted(remaining, key=lambda row: row.created_at):
                    temp.write(item.model_dump_json() + "\n")
                temp.flush()
                os.fsync(temp.fileno())
            await self._replace_with_retry(temp_path, self.transfers_index_path)
        return {"removed": len(to_remove), "remaining": len(remaining)}

    async def cache_overview(self, *, limit: int = 200) -> CacheOverview:
        async with self._lock:
            cache_files = [item for item in self.cache_dir.rglob("*") if item.is_file()]
        cache_files.sort(key=lambda item: item.stat().st_mtime, reverse=True)
        files: list[CacheFileInfo] = []
        total_size_bytes = 0
        for item in cache_files:
            stat = item.stat()
            total_size_bytes += stat.st_size
            if len(files) < limit:
                files.append(
                    CacheFileInfo(
                        name=item.name,
                        relative_path=str(item.relative_to(self.cache_dir)).replace("\\", "/"),
                        size_bytes=stat.st_size,
                        modified_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc),
                    )
                )
        return CacheOverview(files=files, total_files=len(cache_files), total_size_bytes=total_size_bytes)

    async def clear_cache(self) -> dict[str, int]:
        async with self._lock:
            cache_files = [item for item in self.cache_dir.rglob("*") if item.is_file()]
            removed_files = 0
            removed_bytes = 0
            for item in cache_files:
                stat = item.stat()
                item.unlink(missing_ok=True)
                removed_files += 1
                removed_bytes += stat.st_size
            for directory in sorted([item for item in self.cache_dir.rglob("*") if item.is_dir()], reverse=True):
                directory.rmdir()
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        return {"removed_files": removed_files, "removed_bytes": removed_bytes}

    async def append_log(self, entry: LogEntry) -> None:
        async with self._lock:
            with self.logs_path.open("a", encoding="utf-8") as handle:
                handle.write(entry.model_dump_json() + "\n")

    async def list_logs(self, *, level: str | None = None, source_id: str | None = None, transfer_id: str | None = None) -> list[LogEntry]:
        async with self._lock:
            lines = [line.strip() for line in self.logs_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        entries = [LogEntry.model_validate_json(line) for line in lines]
        if level:
            entries = [item for item in entries if item.level == level]
        if source_id:
            entries = [item for item in entries if item.source_id == source_id]
        if transfer_id:
            entries = [item for item in entries if item.transfer_id == transfer_id]
        return list(reversed(entries))

    async def mark_worker_state(self, status: str) -> None:
        async with self._lock:
            await self._atomic_write_json(
                self.state_path,
                {"worker_status": status, "last_cycle_at": datetime.now(timezone.utc).isoformat()},
            )

    async def load_worker_state(self) -> dict:
        async with self._lock:
            return json.loads(self.state_path.read_text(encoding="utf-8"))

    async def was_post_processed(self, source_id: str, vk_post_id: int) -> bool:
        transfers = await self.list_transfers()
        return any(
            item.source_id == source_id and item.vk_post_id == vk_post_id and item.status in {TransferStatus.SUCCESS, TransferStatus.PARTIAL, TransferStatus.SKIPPED}
            for item in transfers
        )

    async def dashboard_stats(self) -> DashboardStats:
        sources = await self.list_sources()
        transfers = await self.list_transfers()
        worker_state = await self.load_worker_state()
        now = datetime.now(timezone.utc)
        return DashboardStats(
            vk_groups=len(sources),
            telegram_targets=len({item.telegram_target for item in sources}),
            successful_transfers=sum(1 for item in transfers if item.status == TransferStatus.SUCCESS),
            failed_transfers=sum(1 for item in transfers if item.status == TransferStatus.ERROR),
            queued_transfers=sum(1 for item in transfers if item.status == TransferStatus.QUEUED),
            last_check_at=max((item.last_checked_at for item in sources if item.last_checked_at), default=None),
            worker_status=worker_state.get("worker_status", "idle"),
            stats_today=sum(1 for item in transfers if item.status == TransferStatus.SUCCESS and item.created_at >= now - timedelta(days=1)),
            stats_7d=sum(1 for item in transfers if item.status == TransferStatus.SUCCESS and item.created_at >= now - timedelta(days=7)),
            stats_30d=sum(1 for item in transfers if item.status == TransferStatus.SUCCESS and item.created_at >= now - timedelta(days=30)),
        )
