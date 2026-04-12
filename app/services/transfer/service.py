from __future__ import annotations

import asyncio
import os
import subprocess
import traceback
from datetime import datetime, timezone
from mimetypes import guess_extension
from pathlib import Path
import shutil
from urllib.parse import urljoin

import httpx
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

from app.core.logging import AppLogger
from app.models.schemas import AttachmentType, TransferAttachment, TransferRecord, TransferStatus, VKPost, VKSource


class TransferService:
    def __init__(self, storage, logger: AppLogger, vk_client, telegram_client) -> None:
        self.storage = storage
        self.logger = logger
        self.vk_client = vk_client
        self.telegram_client = telegram_client

    async def sync_source(self, source: VKSource) -> list[TransferRecord]:
        posts = await self.vk_client.fetch_new_posts(source)
        records: list[TransferRecord] = []
        for post in posts:
            if await self.storage.was_post_processed(source.id, post.post_id):
                continue
            if post.is_repost and not source.settings.include_reposts:
                records.append(await self._build_skipped_transfer(source, post, "Repost skipped by source settings"))
                continue
            filtered_text = post.text if source.settings.include_text else ""
            filtered_attachments = [item for item in post.attachments if self._is_attachment_allowed(source, item)]
            filtered_out = len(post.attachments) - len(filtered_attachments)
            if not filtered_text.strip() and not filtered_attachments:
                reason = "Post skipped because all content was filtered out by source settings"
                if filtered_out:
                    reason += f" ({filtered_out} attachment(s) were disabled)"
                records.append(await self._build_skipped_transfer(source, post, reason))
                continue
            transfer = TransferRecord(
                source_id=source.id,
                source_name=source.name,
                vk_post_id=post.post_id,
                vk_post_url=post.original_url,
                telegram_target=source.telegram_target,
                post_text=filtered_text,
                post_created_at=post.created_at,
                attachments=filtered_attachments,
            )
            if filtered_out:
                transfer.technical_logs.append(f"{filtered_out} attachment(s) skipped by source settings before publish")
            await self.storage.save_transfer(transfer)
            transfer = await self.publish(source, post, transfer)
            records.append(transfer)
        source.last_checked_at = datetime.now(timezone.utc)
        if posts:
            source.last_detected_post_id = max(item.post_id for item in posts)
        successful = [item.vk_post_id for item in records if item.status in {TransferStatus.SUCCESS, TransferStatus.PARTIAL}]
        if successful:
            source.last_transferred_post_id = max(successful)
        await self.storage.upsert_source(source)
        return records

    async def _build_skipped_transfer(self, source: VKSource, post: VKPost, reason: str) -> TransferRecord:
        transfer = TransferRecord(
            source_id=source.id,
            source_name=source.name,
            vk_post_id=post.post_id,
            vk_post_url=post.original_url,
            telegram_target=source.telegram_target,
            post_text=post.text if source.settings.include_text else "",
            post_created_at=post.created_at,
            attachments=[],
            status=TransferStatus.SKIPPED,
            error=reason,
        )
        transfer.technical_logs.append(reason)
        await self.storage.save_transfer(transfer)
        await self.logger.info("transfer.skipped", f"VK post {post.post_id} skipped: {reason}", source_id=source.id, transfer_id=transfer.id)
        return transfer

    def _is_attachment_allowed(self, source: VKSource, attachment: TransferAttachment) -> bool:
        if attachment.type == AttachmentType.PHOTO:
            return source.settings.include_photos
        if attachment.type == AttachmentType.VIDEO:
            return source.settings.include_videos
        if attachment.type == AttachmentType.AUDIO:
            return source.settings.include_audio
        if attachment.type == AttachmentType.DOCUMENT:
            return source.settings.include_documents
        if attachment.type == AttachmentType.LINK:
            return source.settings.include_links
        return True

    async def publish(self, source: VKSource, post: VKPost, transfer: TransferRecord) -> TransferRecord:
        settings = await self.storage.load_settings()
        retry_limit = max(1, settings.retry_limit)
        transfer.technical_logs.append("Transfer queued")
        for attempt in range(1, retry_limit + 1):
            transfer.attempts = attempt
            try:
                await self._download_attachments(transfer.attachments)
                caption = self._build_caption(source, post)
                sent_ids: list[int] = []
                sendable_attachments = [
                    item for item in transfer.attachments if item.local_path and item.type in {AttachmentType.PHOTO, AttachmentType.DOCUMENT, AttachmentType.VIDEO, AttachmentType.AUDIO}
                ]
                leading_text, media_caption = self._split_publication_text(caption, has_media=bool(sendable_attachments))
                photo_attachments = [item for item in sendable_attachments if item.type == AttachmentType.PHOTO]
                if len(photo_attachments) > 1 and len(photo_attachments) == len(sendable_attachments):
                    if leading_text:
                        transfer.technical_logs.append(
                            f"Publication text exceeded Telegram media caption limit ({len(caption)} chars), sent as text before attachments"
                        )
                        sent_ids.extend(await self.telegram_client.send_text(source.telegram_target, leading_text))
                    sent_ids.extend(await self.telegram_client.send_media_group(source.telegram_target, photo_attachments, media_caption))
                    for item in photo_attachments:
                        item.sent = True
                else:
                    caption_consumed = False
                    if leading_text:
                        transfer.technical_logs.append(
                            f"Publication text exceeded Telegram media caption limit ({len(caption)} chars), sent as text before attachments"
                        )
                        sent_ids.extend(await self.telegram_client.send_text(source.telegram_target, leading_text))
                        caption_consumed = True
                    elif not sendable_attachments and caption:
                        sent_ids.extend(await self.telegram_client.send_text(source.telegram_target, caption))
                        caption_consumed = True
                    for attachment in transfer.attachments:
                        if attachment.local_path and attachment.type in {AttachmentType.PHOTO, AttachmentType.DOCUMENT, AttachmentType.VIDEO, AttachmentType.AUDIO}:
                            attachment_caption = media_caption if media_caption and not caption_consumed else ""
                            sent_ids.extend(await self.telegram_client.send_file(source.telegram_target, attachment, attachment_caption))
                            attachment.sent = True
                            caption_consumed = True
                        elif attachment.type == AttachmentType.LINK and attachment.url:
                            sent_ids.extend(await self.telegram_client.send_text(source.telegram_target, attachment.url))
                            attachment.sent = True
                        else:
                            attachment.skipped = True
                transfer.telegram_message_ids = sent_ids
                if sent_ids:
                    transfer.telegram_message_url = f"message_ids={','.join(str(item) for item in sent_ids)}"
                transfer.status = TransferStatus.PARTIAL if any(item.skipped or item.error for item in transfer.attachments) else TransferStatus.SUCCESS
                transfer.error = None
                transfer.updated_at = datetime.now(timezone.utc)
                removed_cache_files = await self._cleanup_cached_files(transfer.attachments)
                if removed_cache_files:
                    transfer.technical_logs.append(f"Cache cleaned after publish: {removed_cache_files} file(s) removed")
                transfer.technical_logs.append(f"Transfer completed on attempt {attempt}")
                await self.logger.info("transfer.completed", f"VK post {post.post_id} transferred", source_id=source.id, transfer_id=transfer.id)
                break
            except Exception as exc:
                traceback_text = "".join(traceback.format_exception(type(exc), exc, exc.__traceback__)).strip()
                transfer.status = TransferStatus.ERROR
                transfer.error = traceback_text or repr(exc)
                transfer.updated_at = datetime.now(timezone.utc)
                transfer.technical_logs.append(f"Attempt {attempt} failed:\n{traceback_text or repr(exc)}")
                await self.logger.error(
                    "transfer.failed",
                    f"Transfer failed for VK post {post.post_id}: {traceback_text or repr(exc)}",
                    source_id=source.id,
                    transfer_id=transfer.id,
                )
        await self.storage.update_transfer(transfer)
        return transfer

    async def _cleanup_cached_files(self, attachments: list[TransferAttachment]) -> int:
        removed_files = 0
        for attachment in attachments:
            if not attachment.local_path:
                continue
            path = Path(attachment.local_path)
            if path.exists():
                path.unlink(missing_ok=True)
                removed_files += 1
            attachment.cache_cleared = True
            attachment.local_path = None
        return removed_files

    def _build_caption(self, source: VKSource, post: VKPost) -> str:
        text_block = post.text.strip() if source.settings.include_text else ""
        signature: list[str] = []
        if source.settings.include_signature:
            signature = [
                f"🧩 Источник: {source.name}",
                f"🔗 Оригинал: {post.original_url}" if source.settings.include_original_link else "",
                f"🆔 ID поста: {post.post_id}",
                f"🕒 Дата: {post.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}" if source.settings.include_original_date else "",
            ]
        body_parts = ["📡 Новый пост", text_block, "\n".join(item for item in signature if item)]
        return "\n\n".join(item for item in body_parts if item)

    def _split_publication_text(self, text: str, *, has_media: bool) -> tuple[str, str]:
        if not text:
            return "", ""
        if has_media and len(text) > self.telegram_client.MEDIA_CAPTION_LIMIT:
            return text, ""
        return "", text

    async def _download_attachments(self, attachments: list[TransferAttachment]) -> None:
        cache_dir = Path(self.storage.cache_dir)
        cache_dir.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
            for index, attachment in enumerate(attachments):
                if not attachment.url or attachment.type == AttachmentType.LINK:
                    continue
                if attachment.local_path:
                    local_path = Path(attachment.local_path)
                    if local_path.exists():
                        continue
                    attachment.local_path = None
                if attachment.type == AttachmentType.VIDEO and "vk.com/" in attachment.url:
                    attachment.skipped = True
                    attachment.error = "VK did not provide a direct downloadable video file"
                    continue
                if attachment.type == AttachmentType.AUDIO and ".m3u8" in attachment.url:
                    destination = cache_dir / self._build_attachment_filename(index, attachment)
                    await self._download_hls_audio_to_mp3(client, attachment.url, destination)
                    attachment.local_path = str(destination)
                    attachment.mime_type = "audio/mpeg"
                    attachment.skipped = False
                    attachment.error = None
                    continue
                filename = self._build_attachment_filename(index, attachment)
                destination = cache_dir / f"{index}_{filename}"
                response = await client.get(attachment.url)
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";")[0].strip()
                if content_type and not attachment.mime_type:
                    attachment.mime_type = content_type
                if attachment.type == AttachmentType.AUDIO and content_type.startswith("audio/"):
                    desired_extension = guess_extension(content_type) or ".mp3"
                    if destination.suffix.lower() != desired_extension.lower():
                        destination = destination.with_suffix(desired_extension)
                if attachment.type == AttachmentType.VIDEO and content_type.startswith("video/"):
                    desired_extension = guess_extension(content_type) or ".mp4"
                    if destination.suffix.lower() != desired_extension.lower():
                        destination = destination.with_suffix(desired_extension)
                destination.write_bytes(response.content)
                attachment.local_path = str(destination)
                attachment.skipped = False
                attachment.error = None

    def _build_attachment_filename(self, index: int, attachment: TransferAttachment) -> str:
        source_name = Path((attachment.url or "").split("?")[0]).name
        if source_name and not (attachment.type == AttachmentType.AUDIO and source_name.endswith(".m3u8")):
            return self._sanitize_filename(source_name)
        if attachment.type == AttachmentType.AUDIO:
            artist = self._sanitize_filename_component(attachment.artist or "audio")
            title = self._sanitize_filename_component(attachment.title or f"track_{index}")
            return self._sanitize_filename(f"{index}_{artist}-{title}.mp3")
        if attachment.type == AttachmentType.VIDEO:
            title = self._sanitize_filename_component(attachment.title or f"video_{index}")
            return self._sanitize_filename(f"{title}.mp4")
        if attachment.type == AttachmentType.PHOTO:
            return f"photo_{index}.jpg"
        if attachment.type == AttachmentType.DOCUMENT:
            title = self._sanitize_filename_component(attachment.title or f"document_{index}")
            extension = attachment.mime_type.strip(".") if attachment.mime_type else "bin"
            return self._sanitize_filename(f"{title}.{extension}")
        return f"attachment_{index}.bin"

    def _sanitize_filename_component(self, value: str) -> str:
        sanitized = "".join("_" if char in '<>:"/\\|?*' else char for char in value)
        sanitized = sanitized.strip().rstrip(". ")
        return sanitized or "file"

    def _sanitize_filename(self, value: str) -> str:
        if "." in value:
            stem, suffix = value.rsplit(".", 1)
            return f"{self._sanitize_filename_component(stem)}.{self._sanitize_filename_component(suffix)}"
        return self._sanitize_filename_component(value)

    async def _download_hls_audio_to_mp3(self, client: httpx.AsyncClient, source_url: str, destination: Path) -> None:
        playlist_response = await client.get(source_url)
        playlist_response.raise_for_status()
        playlist_text = playlist_response.text
        base_url = source_url.rsplit("/", 1)[0] + "/"
        transport_stream_path = destination.with_suffix(".ts")
        await self._download_hls_transport_stream(client, playlist_text, base_url, transport_stream_path)
        try:
            await self._convert_transport_stream_to_mp3(transport_stream_path, destination)
        finally:
            transport_stream_path.unlink(missing_ok=True)

    async def _download_hls_transport_stream(
        self,
        client: httpx.AsyncClient,
        playlist_text: str,
        base_url: str,
        output_path: Path,
    ) -> None:
        current_key: bytes | None = None
        media_sequence = 0
        segment_index = 0
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with output_path.open("wb") as merged:
            for raw_line in playlist_text.splitlines():
                line = raw_line.strip()
                if not line:
                    continue
                if line.startswith("#EXT-X-MEDIA-SEQUENCE:"):
                    media_sequence = int(line.split(":", 1)[1])
                    continue
                if line.startswith("#EXT-X-KEY:"):
                    if "METHOD=NONE" in line:
                        current_key = None
                    else:
                        key_uri = self._extract_m3u8_attribute(line, "URI")
                        if key_uri:
                            key_response = await client.get(urljoin(base_url, key_uri))
                            key_response.raise_for_status()
                            current_key = key_response.content
                    continue
                if line.startswith("#"):
                    continue
                segment_url = urljoin(base_url, line)
                segment_response = await client.get(segment_url)
                segment_response.raise_for_status()
                payload = segment_response.content
                if current_key:
                    iv = (media_sequence + segment_index).to_bytes(16, byteorder="big")
                    decryptor = Cipher(algorithms.AES(current_key), modes.CBC(iv)).decryptor()
                    payload = decryptor.update(payload) + decryptor.finalize()
                merged.write(payload)
                segment_index += 1

    def _extract_m3u8_attribute(self, line: str, key: str) -> str | None:
        marker = f'{key}="'
        start = line.find(marker)
        if start == -1:
            return None
        start += len(marker)
        end = line.find('"', start)
        if end == -1:
            return None
        return line[start:end]

    async def _convert_transport_stream_to_mp3(self, source_path: Path, destination: Path) -> None:
        destination.parent.mkdir(parents=True, exist_ok=True)
        settings = await self.storage.load_settings()
        ffmpeg_binary = settings.ffmpeg_binary or "ffmpeg"
        resolved_ffmpeg = shutil.which(ffmpeg_binary) or (ffmpeg_binary if Path(ffmpeg_binary).exists() else None)
        if not resolved_ffmpeg:
            raise RuntimeError(
                f"FFmpeg binary '{ffmpeg_binary}' was not found. Install ffmpeg on this OS or set the correct binary path in settings."
            )
        completed = await asyncio.to_thread(
            subprocess.run,
            [
                resolved_ffmpeg,
                "-y",
                "-i",
                str(source_path),
                "-vn",
                "-acodec",
                "libmp3lame",
                "-b:a",
                "192k",
                str(destination),
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            check=False,
        )
        if completed.returncode != 0:
            stderr_text = (completed.stderr or "").strip()
            stdout_text = (completed.stdout or "").strip()
            details = stderr_text or stdout_text or f"exit code {completed.returncode}"
            raise RuntimeError(f"ffmpeg failed to convert VK audio: {details}")
