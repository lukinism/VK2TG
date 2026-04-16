from __future__ import annotations

from datetime import datetime, timedelta, timezone

from app.services.vk.client import VKAPIError


class TokenValidationError(RuntimeError):
    pass


class TokenMonitorService:
    VALIDATION_INTERVAL = timedelta(days=1)

    def __init__(self, storage, logger, vk_client, telegram_client) -> None:
        self.storage = storage
        self.logger = logger
        self.vk_client = vk_client
        self.telegram_client = telegram_client

    async def validate_vk_token_value(self, token: str, settings) -> None:
        now = datetime.now(timezone.utc)
        if not token:
            settings.vk_token_valid = None
            settings.vk_token_validation_error = None
            settings.vk_token_last_validated_at = None
            settings.vk_token_last_alerted_at = None
            return
        try:
            await self.vk_client.validate_token(token)
        except Exception as exc:
            settings.vk_token_valid = False
            settings.vk_token_validation_error = str(exc)
            settings.vk_token_last_validated_at = now
            raise TokenValidationError(f"VK token не прошёл проверку: {exc}") from exc
        settings.vk_token_valid = True
        settings.vk_token_validation_error = None
        settings.vk_token_last_validated_at = now

    async def validate_telegram_token_value(self, token: str, proxy_url: str, settings) -> None:
        now = datetime.now(timezone.utc)
        if not token:
            settings.telegram_bot_token_valid = None
            settings.telegram_bot_token_validation_error = None
            settings.telegram_bot_token_last_validated_at = None
            return
        try:
            await self.telegram_client.validate_token(token, proxy_url)
        except Exception as exc:
            settings.telegram_bot_token_valid = False
            settings.telegram_bot_token_validation_error = str(exc)
            settings.telegram_bot_token_last_validated_at = now
            raise TokenValidationError(f"Telegram token не прошёл проверку: {exc}") from exc
        settings.telegram_bot_token_valid = True
        settings.telegram_bot_token_validation_error = None
        settings.telegram_bot_token_last_validated_at = now

    async def validate_on_settings_save(self, settings) -> None:
        await self.validate_vk_token_value(settings.vk_token, settings)
        await self.validate_telegram_token_value(settings.telegram_bot_token, settings.telegram_proxy_url, settings)

    async def run_scheduled_checks(self) -> None:
        settings = await self.storage.load_settings()
        now = datetime.now(timezone.utc)
        changed = False

        if settings.vk_token and self._is_due(settings.vk_token_last_validated_at, now):
            changed = True
            try:
                await self.vk_client.validate_token(settings.vk_token)
            except Exception as exc:
                settings.vk_token_valid = False
                settings.vk_token_validation_error = str(exc)
                settings.vk_token_last_validated_at = now
                await self.logger.warning("token.vk.invalid", f"VK token validation failed: {exc}")
                await self._send_vk_invalid_warning(settings, str(exc), now)
            else:
                settings.vk_token_valid = True
                settings.vk_token_validation_error = None
                settings.vk_token_last_validated_at = now
                await self.logger.info("token.vk.valid", "VK token passed scheduled validation")

        if settings.telegram_bot_token and self._is_due(settings.telegram_bot_token_last_validated_at, now):
            changed = True
            try:
                await self.telegram_client.validate_token(settings.telegram_bot_token, settings.telegram_proxy_url)
            except Exception as exc:
                settings.telegram_bot_token_valid = False
                settings.telegram_bot_token_validation_error = str(exc)
                settings.telegram_bot_token_last_validated_at = now
                await self.logger.warning("token.telegram.invalid", f"Telegram token validation failed: {exc}")
            else:
                settings.telegram_bot_token_valid = True
                settings.telegram_bot_token_validation_error = None
                settings.telegram_bot_token_last_validated_at = now
                await self.logger.info("token.telegram.valid", "Telegram token passed scheduled validation")

        if changed:
            await self.storage.save_settings(settings)

    def _is_due(self, last_validated_at: datetime | None, now: datetime) -> bool:
        return last_validated_at is None or now - last_validated_at >= self.VALIDATION_INTERVAL

    async def _send_vk_invalid_warning(self, settings, reason: str, now: datetime) -> None:
        if not settings.telegram_bot_token:
            await self.logger.warning("token.vk.alert_skipped", "VK token is invalid, but Telegram token is missing so no alert was sent")
            return
        if settings.vk_token_last_alerted_at and now - settings.vk_token_last_alerted_at < self.VALIDATION_INTERVAL:
            return

        sources = await self.storage.list_sources()
        targets = sorted({item.telegram_target for item in sources if item.is_active and item.telegram_target})
        if not targets:
            await self.logger.warning("token.vk.alert_skipped", "VK token is invalid, but there are no active Telegram targets for alerts")
            return

        message = (
            "Warning: VK token is invalid.\n\n"
            f"Reason: {reason}\n"
            f"Checked at: {now.strftime('%Y-%m-%d %H:%M:%S UTC')}\n\n"
            "Update the VK token in Settings to restore synchronization."
        )
        sent_any = False
        for target in targets:
            try:
                await self.telegram_client.send_text(target, message)
                sent_any = True
            except Exception as exc:
                await self.logger.error("token.vk.alert_failed", f"Failed to send VK token warning to Telegram target {target}: {exc}")
        if sent_any:
            settings.vk_token_last_alerted_at = now
            await self.logger.warning("token.vk.alert_sent", f"VK token invalid warning sent to {len(targets)} Telegram target(s)")
