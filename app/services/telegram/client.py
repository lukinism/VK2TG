from __future__ import annotations

import json
from pathlib import Path
import asyncio

import httpx

from app.core.http import build_async_client
from app.models.schemas import AttachmentType, TransferAttachment


class TelegramAPIError(RuntimeError):
    def __init__(
        self,
        description: str,
        *,
        method: str,
        status_code: int | None = None,
        error_code: int | None = None,
        response_text: str | None = None,
    ) -> None:
        super().__init__(f"Telegram API {method} failed: {description}")
        self.description = description
        self.method = method
        self.status_code = status_code
        self.error_code = error_code
        self.response_text = response_text


class TelegramClient:
    MESSAGE_TEXT_LIMIT = 4096
    MEDIA_CAPTION_LIMIT = 1024

    def __init__(self, storage) -> None:
        self.storage = storage

    async def _request(self, method: str, *, data=None, files=None, bot_token: str | None = None, proxy_url: str | None = None) -> dict:
        if bot_token is None or proxy_url is None:
            settings = await self.storage.load_settings()
            if bot_token is None:
                bot_token = settings.telegram_bot_token
            if proxy_url is None:
                proxy_url = settings.telegram_proxy_url
        if not bot_token:
            raise RuntimeError("Telegram token is not configured in admin panel")
        base_url = f"https://api.telegram.org/bot{bot_token}"
        timeout = httpx.Timeout(connect=15.0, read=60.0, write=300.0, pool=60.0)
        client_kwargs = {"timeout": timeout}
        if proxy_url:
            client_kwargs["proxy"] = proxy_url
        max_attempts = 3
        last_error: Exception | None = None
        async with build_async_client(**client_kwargs) as client:
            response = None
            response_text = ""
            payload = None
            for attempt in range(1, max_attempts + 1):
                try:
                    response = await client.post(f"{base_url}/{method}", data=data, files=files)
                except (httpx.TimeoutException, httpx.TransportError) as exc:
                    last_error = exc
                    if attempt >= max_attempts:
                        raise RuntimeError(f"Telegram request failed after {attempt} attempts: {exc}") from exc
                    await asyncio.sleep(1.0 * attempt)
                    continue
                response_text = response.text
                try:
                    payload = response.json()
                except ValueError:
                    payload = None
                break
        if response is None:
            raise RuntimeError(f"Telegram request failed: {last_error}")
        description = None
        error_code = None
        if isinstance(payload, dict):
            description = payload.get("description")
            error_code = payload.get("error_code")
        if response.is_error:
            detail = description or response_text or f"HTTP {response.status_code}"
            raise TelegramAPIError(
                detail,
                method=method,
                status_code=response.status_code,
                error_code=error_code,
                response_text=response_text,
            )
        if not isinstance(payload, dict):
            raise TelegramAPIError(
                "Telegram returned a non-JSON response",
                method=method,
                status_code=response.status_code,
                response_text=response_text,
            )
        if not payload.get("ok"):
            raise TelegramAPIError(
                payload.get("description", "Telegram API error"),
                method=method,
                status_code=response.status_code,
                error_code=payload.get("error_code"),
                response_text=response_text,
            )
        return payload["result"]

    async def validate_token(self, bot_token: str, proxy_url: str = "") -> dict:
        return await self._request("getMe", bot_token=bot_token, proxy_url=proxy_url)

    async def send_text(self, chat_id: str, text: str) -> list[int]:
        message_ids: list[int] = []
        for chunk in self._split_text(text, self.MESSAGE_TEXT_LIMIT):
            result = await self._request("sendMessage", data={"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True})
            message_ids.append(result["message_id"])
        return message_ids

    async def send_media_group(self, chat_id: str, attachments: list[TransferAttachment], caption: str) -> list[int]:
        media = []
        files = {}
        for index, attachment in enumerate(attachments):
            if not attachment.local_path:
                continue
            path = Path(attachment.local_path)
            attach_name = f"file{index}"
            media_item = {"type": "photo", "media": f"attach://{attach_name}"}
            if index == 0 and caption:
                media_item["caption"] = caption
            media.append(media_item)
            files[attach_name] = (path.name, path.read_bytes())
        result = await self._request("sendMediaGroup", data={"chat_id": chat_id, "media": json.dumps(media)}, files=files)
        return [item["message_id"] for item in result]

    async def send_file(self, chat_id: str, attachment: TransferAttachment, caption: str = "") -> list[int]:
        if not attachment.local_path:
            raise RuntimeError("Attachment is not downloaded")
        path = Path(attachment.local_path)
        method = "sendDocument"
        field = "document"
        data = {"chat_id": chat_id, "caption": caption}
        file_bytes = path.read_bytes()
        if attachment.type == AttachmentType.PHOTO:
            method = "sendPhoto"
            field = "photo"
        elif attachment.type == AttachmentType.VIDEO:
            method = "sendVideo"
            field = "video"
        elif attachment.type == AttachmentType.AUDIO:
            method = "sendAudio"
            field = "audio"
            data["title"] = attachment.title or path.stem
            if attachment.artist:
                data["performer"] = attachment.artist
            if attachment.duration:
                data["duration"] = str(attachment.duration)
        content_type = attachment.mime_type or self._guess_content_type(attachment, path)
        try:
            result = await self._request(method, data=data, files={field: (path.name, file_bytes, content_type)})
        except TelegramAPIError as exc:
            if attachment.type == AttachmentType.PHOTO and self._should_fallback_photo_to_document(exc):
                result = await self._request("sendDocument", data=data, files={"document": (path.name, file_bytes, content_type)})
            else:
                raise
        return [result["message_id"]]

    def _guess_content_type(self, attachment: TransferAttachment, path: Path) -> str:
        if attachment.type == AttachmentType.AUDIO:
            return "audio/mpeg"
        if attachment.type == AttachmentType.VIDEO:
            return "video/mp4"
        if attachment.type == AttachmentType.PHOTO:
            return "image/jpeg"
        return "application/octet-stream"

    def _split_text(self, text: str, limit: int) -> list[str]:
        normalized = text.strip()
        if not normalized:
            return []
        chunks: list[str] = []
        remaining = normalized
        while remaining:
            if len(remaining) <= limit:
                chunks.append(remaining)
                break
            split_at = self._pick_split_index(remaining, limit)
            chunk = remaining[:split_at].rstrip()
            if not chunk:
                chunk = remaining[:limit]
                split_at = limit
            chunks.append(chunk)
            remaining = remaining[split_at:].lstrip()
        return chunks

    def _pick_split_index(self, text: str, limit: int) -> int:
        for separator in ("\n\n", "\n", " "):
            candidate = text.rfind(separator, 0, limit + 1)
            if candidate > 0:
                return candidate
        return limit

    def _should_fallback_photo_to_document(self, error: TelegramAPIError) -> bool:
        if error.status_code != 400:
            return False
        description = error.description.lower()
        photo_error_markers = (
            "photo_",
            "image_process_failed",
            "wrong type of the webp",
            "dimensions",
            "failed to get http url content",
            "wrong file identifier/http url specified",
            "file is too big",
        )
        return any(marker in description for marker in photo_error_markers)
