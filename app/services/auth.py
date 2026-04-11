from __future__ import annotations

import hashlib


class AuthService:
    def __init__(self, storage) -> None:
        self.storage = storage

    def hash_password(self, password: str) -> str:
        return hashlib.sha256(password.encode("utf-8")).hexdigest()

    async def validate_credentials(self, username: str, password: str) -> bool:
        settings = await self.storage.load_settings()
        return settings.admin_username == username and settings.admin_password_hash == self.hash_password(password)

