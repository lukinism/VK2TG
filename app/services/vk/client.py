from __future__ import annotations

from datetime import datetime, timezone

import httpx

from app.models.schemas import AttachmentType, TransferAttachment, VKPost, VKSource


class VKAPIError(RuntimeError):
    def __init__(self, message: str, *, error_code: int | None = None) -> None:
        super().__init__(message)
        self.error_code = error_code


class VKWallDisabledError(VKAPIError):
    pass


class VKClient:
    API_URL = "https://api.vk.com/method"
    API_VERSION = "5.199"

    def __init__(self, storage) -> None:
        self.storage = storage

    async def _call(self, method: str, params: dict, *, access_token: str | None = None) -> dict:
        token = access_token
        if token is None:
            settings = await self.storage.load_settings()
            token = settings.vk_token
        if not token:
            raise RuntimeError("VK token is not configured in admin panel")
        payload = {"access_token": token, "v": self.API_VERSION, **params}
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(f"{self.API_URL}/{method}", params=payload)
            response.raise_for_status()
            data = response.json()
        if "error" in data:
            error = data["error"] or {}
            error_code = error.get("error_code")
            error_message = error.get("error_msg", "VK API error")
            if method == "wall.get" and error_message == "Access denied: wall is disabled":
                raise VKWallDisabledError("VK wall is disabled for this source", error_code=error_code)
            raise VKAPIError(error_message, error_code=error_code)
        return data["response"]

    async def validate_token(self, token: str) -> dict:
        response = await self._call("users.get", {}, access_token=token)
        if not response:
            raise VKAPIError("VK token validation returned an empty response")
        return response[0]

    async def resolve_source(self, screen_name: str) -> dict:
        return await self._call("utils.resolveScreenName", {"screen_name": screen_name})

    async def fetch_new_posts(self, source: VKSource) -> list[VKPost]:
        owner_id = -abs(source.group_id) if source.group_id is not None else None
        if owner_id is None:
            resolved = await self.resolve_source(source.screen_name)
            if not resolved.get("object_id"):
                raise RuntimeError(f"Could not resolve VK screen name: {source.screen_name}")
            owner_id = -int(resolved["object_id"])
            source.group_id = abs(owner_id)
        wall_filter = "all" if source.settings.include_subscriber_posts else "owner"
        response = await self._call(
            "wall.get",
            {"owner_id": owner_id, "count": source.settings.poll_count, "filter": wall_filter},
        )
        posts: list[VKPost] = []
        for item in response.get("items", []):
            post_id = int(item["id"])
            if source.last_transferred_post_id and post_id <= source.last_transferred_post_id:
                continue
            posts.append(await self._normalize_post(source, item))
        posts.sort(key=lambda row: row.post_id)
        return posts

    async def _normalize_post(self, source: VKSource, item: dict) -> VKPost:
        owner_id = int(item["owner_id"])
        attachments = [await self._normalize_attachment(raw) for raw in item.get("attachments", [])]
        return VKPost(
            post_id=int(item["id"]),
            owner_id=owner_id,
            screen_name=source.screen_name,
            source_name=source.name,
            text=item.get("text", ""),
            created_at=datetime.fromtimestamp(item["date"], tz=timezone.utc),
            original_url=f"https://vk.com/wall{owner_id}_{item['id']}",
            attachments=attachments,
            raw=item,
            is_repost=bool(item.get("copy_history")),
        )

    async def _normalize_attachment(self, item: dict) -> TransferAttachment:
        attachment_type = item.get("type", "unknown")
        raw = item.get(attachment_type, {})
        if attachment_type == "photo":
            sizes = sorted(raw.get("sizes", []), key=lambda row: row.get("width", 0) * row.get("height", 0))
            best = sizes[-1] if sizes else {}
            thumb = sizes[0].get("url") if sizes else None
            return TransferAttachment(type=AttachmentType.PHOTO, url=best.get("url"), thumbnail_url=thumb, raw=item)
        if attachment_type == "doc":
            return TransferAttachment(
                type=AttachmentType.DOCUMENT,
                url=raw.get("url"),
                title=raw.get("title"),
                mime_type=raw.get("ext"),
                size=raw.get("size"),
                raw=item,
            )
        if attachment_type == "video":
            direct_url = await self._resolve_video_download_url(raw)
            return TransferAttachment(
                type=AttachmentType.VIDEO,
                url=direct_url,
                title=raw.get("title"),
                thumbnail_url=self._pick_video_thumbnail(raw),
                duration=raw.get("duration"),
                skipped=direct_url is None,
                error=None if direct_url else "VK did not provide a direct downloadable video file",
                raw=item,
            )
        if attachment_type == "audio":
            return TransferAttachment(
                type=AttachmentType.AUDIO,
                url=raw.get("url"),
                title=raw.get("title"),
                artist=raw.get("artist"),
                duration=raw.get("duration"),
                skipped=not raw.get("url"),
                error=None if raw.get("url") else "VK did not provide a direct downloadable audio file",
                raw=item,
            )
        if attachment_type == "link":
            return TransferAttachment(type=AttachmentType.LINK, url=raw.get("url"), title=raw.get("title"), raw=item)
        return TransferAttachment(type=AttachmentType.UNKNOWN, skipped=True, error="Unsupported VK attachment type", raw=item)

    async def _resolve_video_download_url(self, raw: dict) -> str | None:
        files = raw.get("files") or {}
        direct = self._pick_best_video_url(files)
        if direct:
            return direct
        owner_id = raw.get("owner_id")
        video_id = raw.get("id")
        access_key = raw.get("access_key")
        if owner_id is None or video_id is None:
            return None
        try:
            video_ref = f"{owner_id}_{video_id}"
            if access_key:
                video_ref = f"{video_ref}_{access_key}"
            response = await self._call("video.get", {"videos": video_ref})
            items = response.get("items", [])
            if not items:
                return None
            return self._pick_best_video_url((items[0] or {}).get("files") or {})
        except Exception:
            return None

    def _pick_best_video_url(self, files: dict) -> str | None:
        mp4_keys = [key for key in files if key.startswith("mp4_")]
        if mp4_keys:
            best_key = sorted(mp4_keys, key=lambda key: int(key.split("_", 1)[1]))[-1]
            return files.get(best_key)
        return files.get("external")

    def _pick_video_thumbnail(self, raw: dict) -> str | None:
        images = raw.get("image") or raw.get("first_frame") or []
        if not images:
            return None
        best = sorted(images, key=lambda row: row.get("width", 0) * row.get("height", 0))[-1]
        return best.get("url")
