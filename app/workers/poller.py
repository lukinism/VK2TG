from __future__ import annotations

import asyncio
import traceback
from contextlib import suppress
from datetime import datetime, timezone

from app.models.schemas import TransferStatus
from app.services.vk.client import VKWallDisabledError


class PollingWorker:
    def __init__(self, storage, logger, transfer_service) -> None:
        self.storage = storage
        self.logger = logger
        self.transfer_service = transfer_service
        self._task: asyncio.Task | None = None
        self._running = False
        self._cycle_lock = asyncio.Lock()

    async def start(self) -> None:
        if self._task:
            return
        self._running = True
        self._task = asyncio.create_task(self._loop())

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            with suppress(asyncio.CancelledError):
                await self._task
            self._task = None

    async def run_once(self) -> dict:
        if self._cycle_lock.locked():
            return {"transferred": 0, "failed": 0, "status": "busy"}
        async with self._cycle_lock:
            await self.storage.mark_worker_state("running")
            transferred = 0
            failed = 0
            for source in [item for item in await self.storage.list_sources() if item.is_active]:
                try:
                    results = await self.transfer_service.sync_source(source)
                    transferred += sum(1 for item in results if item.status in {TransferStatus.SUCCESS, TransferStatus.PARTIAL})
                    failed += sum(1 for item in results if item.status == TransferStatus.ERROR)
                except VKWallDisabledError:
                    failed += 1
                    source.last_checked_at = datetime.now(timezone.utc)
                    source.updated_at = datetime.now(timezone.utc)
                    await self.storage.upsert_source(source)
                    await self.logger.warning(
                        "worker.source_wall_disabled",
                        f"Source '{source.name}' cannot be synced because the VK wall is disabled.",
                        source_id=source.id,
                    )
                except Exception as exc:
                    failed += 1
                    source.last_checked_at = datetime.now(timezone.utc)
                    source.updated_at = datetime.now(timezone.utc)
                    await self.storage.upsert_source(source)
                    details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
                    await self.logger.error("worker.source_failed", f"Source sync failed for {source.name}: {details}", source_id=source.id)
            await self.storage.mark_worker_state("idle")
            return {"transferred": transferred, "failed": failed, "status": "completed"}

    async def _loop(self) -> None:
        while self._running:
            settings = await self.storage.load_settings()
            try:
                await self.run_once()
            except Exception as exc:
                details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
                await self.logger.error("worker.cycle_failed", f"Polling cycle failed: {details}")
                await self.storage.mark_worker_state("error")
            await asyncio.sleep(settings.poll_interval_seconds)
