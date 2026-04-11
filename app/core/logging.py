from __future__ import annotations

from app.models.schemas import LogEntry, LogLevel


class AppLogger:
    def __init__(self, storage) -> None:
        self.storage = storage

    async def log(self, level: LogLevel, event: str, message: str, **kwargs) -> LogEntry:
        entry = LogEntry(level=level, event=event, message=message, **kwargs)
        await self.storage.append_log(entry)
        return entry

    async def info(self, event: str, message: str, **kwargs) -> LogEntry:
        return await self.log(LogLevel.INFO, event, message, **kwargs)

    async def warning(self, event: str, message: str, **kwargs) -> LogEntry:
        return await self.log(LogLevel.WARNING, event, message, **kwargs)

    async def error(self, event: str, message: str, **kwargs) -> LogEntry:
        return await self.log(LogLevel.ERROR, event, message, **kwargs)
