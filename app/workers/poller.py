from __future__ import annotations

import asyncio
import traceback
from contextlib import suppress
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

from app.models.schemas import SourceSchedule, TransferStatus, VKSource
from app.services.vk.client import VKWallDisabledError


class PollingWorker:
    def __init__(self, storage, logger, transfer_service, token_monitor) -> None:
        self.storage = storage
        self.logger = logger
        self.transfer_service = transfer_service
        self.token_monitor = token_monitor
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
            await self.token_monitor.run_scheduled_checks()
            settings = await self.storage.load_settings()
            if settings.vk_token and settings.vk_token_valid is False:
                await self.logger.warning(
                    "worker.cycle_skipped_invalid_vk_token",
                    "Polling cycle skipped because the VK token is currently invalid. Update it in Settings to resume synchronization.",
                )
                await self.storage.mark_worker_state("idle")
                return {"transferred": 0, "failed": 0, "status": "blocked_invalid_vk_token"}
            now = datetime.now(timezone.utc)
            sources = await self.storage.list_sources()
            ready_sources: list[VKSource] = []
            deferred = 0
            for source in sources:
                if await self._prepare_source(source, now):
                    ready_sources.append(source)
                else:
                    deferred += 1

            ready_sources.sort(
                key=lambda item: (
                    -item.schedule.priority,
                    item.runtime.next_run_at or now,
                    item.last_checked_at or datetime.min.replace(tzinfo=timezone.utc),
                    item.name.lower(),
                )
            )
            transferred = 0
            failed = 0
            processed = 0
            for source in ready_sources:
                processed += 1
                source.runtime.scheduler_status = "running"
                source.runtime.scheduler_note = "Источник обрабатывается воркером"
                source.runtime.last_started_at = datetime.now(timezone.utc)
                source.updated_at = datetime.now(timezone.utc)
                await self.storage.upsert_source(source)
                try:
                    results = await self.transfer_service.sync_source(source)
                    transferred += sum(1 for item in results if item.status in {TransferStatus.SUCCESS, TransferStatus.PARTIAL})
                    failed += sum(1 for item in results if item.status == TransferStatus.ERROR)
                    await self._mark_source_success(source, results)
                except VKWallDisabledError:
                    failed += 1
                    await self._mark_source_failure(source, "VK wall is disabled for this source", status="wall_disabled")
                    await self.logger.warning(
                        "worker.source_wall_disabled",
                        f"Source '{source.name}' cannot be synced because the VK wall is disabled.",
                        source_id=source.id,
                    )
                except Exception as exc:
                    failed += 1
                    details = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
                    await self._mark_source_failure(source, self._summarize_exception(exc), status="error")
                    await self.logger.error("worker.source_failed", f"Source sync failed for {source.name}: {details}", source_id=source.id)
            await self.storage.mark_worker_state("idle")
            return {
                "transferred": transferred,
                "failed": failed,
                "processed": processed,
                "deferred": deferred,
                "status": "completed",
            }

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

    async def _prepare_source(self, source: VKSource, now: datetime) -> bool:
        if not source.is_active:
            source.runtime.scheduler_status = "inactive"
            source.runtime.scheduler_note = "Источник выключен"
            source.updated_at = now
            await self.storage.upsert_source(source)
            return False

        if source.schedule.pause_until and source.schedule.pause_until > now:
            source.runtime.next_run_at = source.schedule.pause_until
            source.runtime.scheduler_status = "paused_until"
            source.runtime.scheduler_note = f"Пауза до {source.schedule.pause_until.isoformat()}"
            source.updated_at = now
            await self.storage.upsert_source(source)
            return False

        desired_run_at = source.runtime.next_run_at or now
        aligned_run_at = self._align_with_schedule(source.schedule, max(desired_run_at, now))
        source.runtime.next_run_at = aligned_run_at
        source.updated_at = now

        if aligned_run_at is None:
            source.runtime.scheduler_status = "blocked_schedule"
            source.runtime.scheduler_note = "Расписание не содержит доступных дней или временных окон"
            await self.storage.upsert_source(source)
            return False

        if aligned_run_at > now:
            if desired_run_at > now:
                source.runtime.scheduler_status = "waiting_interval"
                source.runtime.scheduler_note = f"Следующий запуск запланирован на {aligned_run_at.isoformat()}"
            else:
                source.runtime.scheduler_status = "waiting_window"
                source.runtime.scheduler_note = f"Ожидает окно расписания: {aligned_run_at.isoformat()}"
            await self.storage.upsert_source(source)
            return False

        source.runtime.scheduler_status = "ready"
        source.runtime.scheduler_note = "Источник готов к обработке"
        await self.storage.upsert_source(source)
        return True

    async def _mark_source_success(self, source: VKSource, results) -> None:
        now = datetime.now(timezone.utc)
        source.runtime.consecutive_failures = 0
        source.runtime.last_error_at = None
        source.runtime.last_error_message = None
        source.runtime.last_finished_at = now
        source.runtime.last_outcome = self._pick_outcome(results)
        next_candidate = now + timedelta(seconds=max(60, source.schedule.interval_seconds))
        source.runtime.next_run_at = self._align_with_schedule(source.schedule, next_candidate)
        source.runtime.scheduler_status = "waiting_interval"
        if source.runtime.next_run_at:
            source.runtime.scheduler_note = f"Следующий запуск: {source.runtime.next_run_at.isoformat()}"
        else:
            source.runtime.scheduler_note = "Следующий запуск недоступен из-за настроек расписания"
        source.updated_at = now
        await self.storage.upsert_source(source)

    async def _mark_source_failure(self, source: VKSource, error_message: str, *, status: str) -> None:
        now = datetime.now(timezone.utc)
        source.last_checked_at = now
        source.runtime.consecutive_failures += 1
        source.runtime.last_error_at = now
        source.runtime.last_error_message = error_message
        source.runtime.last_finished_at = now
        source.runtime.last_outcome = status
        delay_seconds = min(
            source.schedule.max_backoff_seconds,
            source.schedule.base_backoff_seconds * (2 ** max(0, source.runtime.consecutive_failures - 1)),
        )
        next_candidate = now + timedelta(seconds=max(60, delay_seconds))
        source.runtime.next_run_at = self._align_with_schedule(source.schedule, next_candidate)
        source.runtime.scheduler_status = "backoff"
        if source.runtime.next_run_at:
            source.runtime.scheduler_note = f"Повторная попытка: {source.runtime.next_run_at.isoformat()}"
        else:
            source.runtime.scheduler_note = "Повторная попытка заблокирована текущим расписанием"
        source.updated_at = now
        await self.storage.upsert_source(source)

    def _pick_outcome(self, results) -> str:
        if any(item.status == TransferStatus.ERROR for item in results):
            return "partial"
        if any(item.status == TransferStatus.PARTIAL for item in results):
            return "partial"
        if any(item.status == TransferStatus.SUCCESS for item in results):
            return "success"
        return "idle"

    def _align_with_schedule(self, schedule: SourceSchedule, candidate_utc: datetime) -> datetime | None:
        timezone_info = self._resolve_timezone(schedule.timezone_name)
        local_candidate = candidate_utc.astimezone(timezone_info)
        windows = self._build_windows(schedule, local_candidate, timezone_info)
        next_start: datetime | None = None
        for start_at, end_at in windows:
            if start_at <= local_candidate <= end_at:
                return local_candidate.astimezone(timezone.utc)
            if local_candidate < start_at and (next_start is None or start_at < next_start):
                next_start = start_at
        return next_start.astimezone(timezone.utc) if next_start else None

    def _build_windows(self, schedule: SourceSchedule, local_candidate: datetime, timezone_info: ZoneInfo) -> list[tuple[datetime, datetime]]:
        allowed_days = set(schedule.active_weekdays or [0, 1, 2, 3, 4, 5, 6])
        if not allowed_days:
            return []
        start_time = self._parse_time(schedule.window_start)
        end_time = self._parse_time(schedule.window_end)
        windows: list[tuple[datetime, datetime]] = []
        for day_offset in range(-1, 8):
            base_date = (local_candidate + timedelta(days=day_offset)).date()
            if base_date.weekday() not in allowed_days:
                continue
            if start_time is None and end_time is None:
                start_at = datetime.combine(base_date, time.min, tzinfo=timezone_info)
                end_at = start_at + timedelta(days=1)
            elif start_time is not None and end_time is not None:
                start_at = datetime.combine(base_date, start_time, tzinfo=timezone_info)
                if start_time <= end_time:
                    end_at = datetime.combine(base_date, end_time, tzinfo=timezone_info)
                else:
                    end_at = datetime.combine(base_date + timedelta(days=1), end_time, tzinfo=timezone_info)
            elif start_time is not None:
                start_at = datetime.combine(base_date, start_time, tzinfo=timezone_info)
                end_at = datetime.combine(base_date + timedelta(days=1), time.min, tzinfo=timezone_info)
            else:
                start_at = datetime.combine(base_date, time.min, tzinfo=timezone_info)
                end_at = datetime.combine(base_date, end_time or time.max, tzinfo=timezone_info)
            windows.append((start_at, end_at))
        windows.sort(key=lambda item: item[0])
        return windows

    def _parse_time(self, value: str | None) -> time | None:
        if not value:
            return None
        try:
            hours, minutes = value.split(":", 1)
            return time(hour=int(hours), minute=int(minutes))
        except (TypeError, ValueError):
            return None

    def _resolve_timezone(self, timezone_name: str) -> ZoneInfo:
        try:
            return ZoneInfo(timezone_name or "UTC")
        except Exception:
            return ZoneInfo("UTC")

    def _summarize_exception(self, exc: Exception) -> str:
        message = str(exc).strip() or exc.__class__.__name__
        return f"{exc.__class__.__name__}: {message}"
