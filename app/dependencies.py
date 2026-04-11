from __future__ import annotations

from pathlib import Path

from app.core.config import BASE_DIR, load_settings
from app.core.logging import AppLogger
from app.core.security import TokenCipher
from app.services.auth import AuthService
from app.services.storage.file_storage import FileStorage
from app.services.telegram.client import TelegramClient
from app.services.transfer.service import TransferService
from app.services.vk.client import VKClient
from app.workers.poller import PollingWorker


class Container:
    def __init__(self) -> None:
        settings = load_settings()
        self.cipher = TokenCipher(BASE_DIR / settings.data_dir / "state" / "tokens.key")
        self.storage = FileStorage(BASE_DIR / settings.data_dir, settings, self.cipher)
        self.logger = AppLogger(self.storage)
        self.vk_client = VKClient(self.storage)
        self.telegram_client = TelegramClient(self.storage)
        self.transfer_service = TransferService(self.storage, self.logger, self.vk_client, self.telegram_client)
        self.auth_service = AuthService(self.storage)
        self.worker = PollingWorker(self.storage, self.logger, self.transfer_service)


container = Container()


def get_frontend_dist_dir() -> Path:
    return BASE_DIR / "frontend" / "dist"
